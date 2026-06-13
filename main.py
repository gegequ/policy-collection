#!/usr/bin/env python
"""政策雷达（Policy Radar）— A 股指数基金政策动向监测工具。

四层流水线：
    采集层（15 个官网采集器）
    → 存储层（SQLite 去重 + 查询）
    → 分析层（统计 + DeepSeek AI）
    → 输出层（Markdown 日报 + 终端摘要）

Usage:
    python main.py --now              # 立即运行一次
    python main.py -c myconfig.yaml   # 指定配置文件
    # 定时运行请配合系统 cron / 任务计划程序
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime

import httpx

from src.config import load_config
from src.db import Database
from src.fetchers.registry import FetcherRegistry
from src.analyzer import compute_stats, format_stats_for_ai, analyze_with_deepseek
from src.reporter import (
    generate_markdown_report,
    print_summary,
    save_report,
    cleanup_old_reports,
)

# 注册所有采集器
from src.fetchers.pbc import PBCFetcher
from src.fetchers.state_council import StateCouncilFetcher
from src.fetchers.ndrc import NDRCFetcher
from src.fetchers.miit import MIITFetcher
from src.fetchers.most import MOSTFetcher
from src.fetchers.csrc import CSRCFetcher
from src.fetchers.nfra import NFRAFetcher
from src.fetchers.stats_gov import StatsGovFetcher
from src.fetchers.customs import CustomsFetcher
from src.fetchers.nea import NEAFetcher
from src.fetchers.mof import MOFFetcher
from src.fetchers.mofcom import MOFCOMFetcher
from src.fetchers.cei import CEIFetcher
from src.fetchers.xinhua import XinhuaFetcher
from src.fetchers.people_daily import PeopleDailyFetcher

# ── 日志配置 ────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("policy_radar")


# ── 采集器注册 ──────────────────────────────────────────────

def build_registry() -> FetcherRegistry:
    """构建并注册所有 15 个信息源采集器。

    Returns:
        已注册所有采集器的 FetcherRegistry 实例。
    """
    registry = FetcherRegistry()
    registry.register(PBCFetcher())            # 中国人民银行
    registry.register(StateCouncilFetcher())   # 国务院
    registry.register(NDRCFetcher())           # 国家发改委
    registry.register(MIITFetcher())           # 工业和信息化部
    registry.register(MOSTFetcher())           # 科学技术部
    registry.register(CSRCFetcher())           # 中国证监会
    registry.register(NFRAFetcher())           # 金融监管总局
    registry.register(StatsGovFetcher())       # 国家统计局
    registry.register(CustomsFetcher())        # 海关总署
    registry.register(NEAFetcher())            # 国家能源局
    registry.register(MOFFetcher())            # 财政部
    registry.register(MOFCOMFetcher())         # 商务部
    registry.register(CEIFetcher())            # 中经网
    registry.register(XinhuaFetcher())         # 新华社
    registry.register(PeopleDailyFetcher())    # 人民日报
    return registry


# ── 主管线 ──────────────────────────────────────────────────

async def run_pipeline(config_path: str = "config.yaml") -> None:
    """执行完整采集 → 分析 → 输出管线。

    Args:
        config_path: 配置文件路径。

    管线步骤：
        1. 加载配置 + 初始化数据库
        2. 并发采集所有已启用信息源
        3. 存入数据库（URL 哈希去重）
        4. 统计分析（板块频次/环比）
        5. AI 分析（DeepSeek API）
        6. 生成并保存 Markdown 日报
        7. 终端摘要输出
        8. 清理过期报告
    """
    # 1. 初始化
    config = load_config(config_path)
    db = Database(config.database.path)
    db.initialize()

    today = datetime.now().strftime("%Y-%m-%d")
    logger.info("=== 政策雷达启动 · %s ===", today)

    # 2. 采集
    registry = build_registry()
    fetchers = registry.get_enabled(config.sources)

    if not fetchers:
        print("⚠️ 没有启用的信息源，请检查 config.yaml 中 sources 配置")
        return

    logger.info("开始采集 %d 个信息源...", len(fetchers))

    limits = httpx.Limits(max_connections=config.fetch.max_concurrent)
    timeout = httpx.Timeout(config.fetch.timeout_sec)

    # 中国官网域名直连，不走系统代理（否则 Clash 等代理会导致这些网站不可达）
    gov_domains = [
        "*.gov.cn", "*.pbc.gov.cn", "*.ndrc.gov.cn", "*.miit.gov.cn",
        "*.most.gov.cn", "*.csrc.gov.cn", "*.nfra.gov.cn", "*.stats.gov.cn",
        "*.customs.gov.cn", "*.nea.gov.cn", "*.mof.gov.cn", "*.mofcom.gov.cn",
        "*.cei.cn", "*.news.cn", "*.people.com.cn", "*.people.cn",
    ]
    import os as _os
    _os.environ.setdefault("no_proxy", "")
    existing = _os.environ["no_proxy"]
    if existing:
        _os.environ["no_proxy"] = existing + "," + ",".join(gov_domains)
    else:
        _os.environ["no_proxy"] = ",".join(gov_domains)

    async with httpx.AsyncClient(limits=limits, timeout=timeout, trust_env=True) as client:
        tasks = [f.fetch_with_retry(client) for f in fetchers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles = []
    success_count = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("[%s] 采集失败: %s", fetchers[i].name, result)
        else:
            all_articles.extend(result)
            success_count += 1

    print(f"✅ 采集完成：共 {len(all_articles)} 篇文章 "
          f"（{success_count}/{len(fetchers)} 个信息源成功）")

    # 3. 存储（去重）
    new_count = 0
    for article in all_articles:
        aid = db.insert_article(article)
        if aid is not None:
            new_count += 1

    print(f"✅ 去重后新增：{new_count} 篇")

    if new_count == 0:
        print("ℹ️ 没有新文章，跳过分析")
        return

    # 4. 统计（取本轮新采集且未分析的文章）
    today_articles = db.get_unanalyzed_articles()
    stats = compute_stats(today_articles, db, today)

    # 5. AI 分析
    ai_prompt = format_stats_for_ai(stats, today_articles)
    ai_analysis = await analyze_with_deepseek(ai_prompt, config)

    if ai_analysis is None:
        ai_analysis = (
            "⚠️ AI 分析暂不可用（API key 未配置或调用失败），以下仅为统计数据。"
        )
        print("⚠️ AI 分析跳过（需配置 DEEPSEEK_API_KEY 环境变量）")

    # 6. 生成 + 保存报告
    report_md = generate_markdown_report(stats, ai_analysis, today_articles)
    report_path = save_report(report_md, config.output.report_dir, today)

    # 7. 存储报告到数据库
    db.insert_daily_report(
        date=today,
        article_count=new_count,
        stats_json=json.dumps(stats, ensure_ascii=False),
        ai_analysis=ai_analysis,
        report_md=report_md,
    )

    # 8. 清理
    cleanup_old_reports(config.output.report_dir, config.output.keep_days)

    # 9. 终端输出
    print_summary(stats, ai_analysis)
    print(f"📄 完整报告：{report_path}")
    logger.info("=== 管线完成 ===")


# ── CLI ─────────────────────────────────────────────────────

def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        description="📡 政策雷达 — A股政策动向监测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --now              # 立即运行一次
  python main.py -c myconfig.yaml   # 指定配置文件
        """,
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径（默认 config.yaml）",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        default=True,
        help="立即运行一次采集分析",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_pipeline(args.config))
    except KeyboardInterrupt:
        print("\n⏹ 用户中断")
        sys.exit(0)
    except Exception as e:
        logger.exception("管线执行失败: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
