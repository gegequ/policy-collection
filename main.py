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
import os
import sys
from datetime import datetime, timedelta

import httpx

from src.config import load_config
from src.db import Database
from src.fetchers.registry import FetcherRegistry
from src.analyzer import compute_stats, compute_trends, compute_xwlb_monthly, format_stats_for_ai, format_trends_for_ai, analyze_with_deepseek
from src.market_data import get_market_snapshot, format_market_for_ai, get_index_snapshot, format_index_for_ai, format_pe_for_ai
from src.pe_fetcher import update_pe_data
from src.funds import get_fund_names_for_prompt, get_all_sectors
from src.backtest import extract_predictions, save_predictions
from src.pred_tracker import generate_prediction_table
from src.validator import validate_ai_output
from src.reporter import (
    generate_markdown_report,
    print_summary,
    save_report,
    cleanup_old_reports,
    split_xwlb_analysis,
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
# from src.fetchers.customs import CustomsFetcher  # 反爬，暂未启用
from src.fetchers.nea import NEAFetcher
from src.fetchers.mof import MOFFetcher
# from src.fetchers.mofcom import MOFCOMFetcher  # 反爬，暂未启用
from src.fetchers.cei import CEIFetcher
from src.fetchers.xinhua import XinhuaFetcher
from src.fetchers.people_daily import PeopleDailyFetcher
# from src.fetchers.nhc import NHCFetcher  # 412 反爬，暂未启用
# from src.fetchers.nmpa import NMPAFetcher  # 412 反爬，暂未启用
from src.fetchers.stcn import STCNFetcher
from src.fetchers.yicai import YicaiFetcher
from src.fetchers.xwlb import XWLBFetcher

# ── 日志配置 ────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("policy_radar")


# ── 中国节假日（A股休市日） ──────────────────────────────

# 2026年中国节假日（需每年年初更新）
HOLIDAYS = {
    "2026-01-01", "2026-01-02",                                    # 元旦
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",  # 春节
    "2026-04-06",                                                   # 清明节
    "2026-05-01", "2026-05-04", "2026-05-05",                      # 劳动节
    "2026-06-19",                                                   # 端午节
    "2026-09-25",                                                   # 中秋节
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",  # 国庆
}


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
    # registry.register(CustomsFetcher())    # 海关总署 — 有反爬，暂时跳过
    registry.register(NEAFetcher())            # 国家能源局
    registry.register(MOFFetcher())            # 财政部
    # registry.register(MOFCOMFetcher())     # 商务部 — 有反爬，暂时跳过
    registry.register(CEIFetcher())            # 中经网
    registry.register(XinhuaFetcher())         # 新华社
    registry.register(PeopleDailyFetcher())    # 人民日报
    # registry.register(NHCFetcher())         # 国家卫健委 — 412 反爬
    # registry.register(NMPAFetcher())        # 国家药监局 — 412 反爬
    registry.register(STCNFetcher())            # 证券时报
    registry.register(YicaiFetcher())           # 第一财经
    registry.register(XWLBFetcher())            # 新闻联播文字稿
    return registry


# ── 主管线 ──────────────────────────────────────────────────

async def run_pipeline(config_path: str = "config.yaml", fresh: bool = False) -> None:
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
    # Windows 控制台默认 GBK 编码无法输出 emoji，强制 UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    config = load_config(config_path)
    db = Database(config.database.path)
    db.initialize()

    today = datetime.now().strftime("%Y-%m-%d")
    weekday = datetime.now().weekday()  # 0=Mon, 6=Sun

    is_weekend = weekday >= 5
    is_holiday = today in HOLIDAYS
    is_trading_day = not is_weekend and not is_holiday
    status = "节假日休市" if is_holiday else ("周末休市" if is_weekend else "交易日")
    logger.info("=== 政策雷达启动 · %s (%s) ===", today, status)

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
    # 中国官网域名直连（后缀匹配，不用 glob）
    gov_domains = [
        "gov.cn", "pbc.gov.cn", "ndrc.gov.cn", "miit.gov.cn",
        "most.gov.cn", "csrc.gov.cn", "nfra.gov.cn", "stats.gov.cn",
        "customs.gov.cn", "nea.gov.cn", "mof.gov.cn", "mofcom.gov.cn",
        "cei.cn", "news.cn", "people.com.cn", "people.cn",
    ]
    os.environ.setdefault("no_proxy", "")
    existing = os.environ["no_proxy"]
    if existing:
        os.environ["no_proxy"] = existing + "," + ",".join(gov_domains)
    else:
        os.environ["no_proxy"] = ",".join(gov_domains)

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

    # 2.5 新闻联播 — fetcher 内部已处理时间门控（详情页无内容时自动回退）
    xwlb_articles = [a for a in all_articles if a.source == "新闻联播"]
    if xwlb_articles:
        xwlb_dir = os.path.join(config.output.report_dir, "xwlb")
        os.makedirs(xwlb_dir, exist_ok=True)
        xwlb_path = os.path.join(xwlb_dir, f"{today}.md")
        with open(xwlb_path, "w", encoding="utf-8") as f:
            f.write(f"# 📺 新闻联播 · {today}\n\n")
            for i, a in enumerate(xwlb_articles, 1):
                f.write(f"## {i}. {a.title}\n\n")
                if a.summary:
                    f.write(f"{a.summary}\n\n")
                f.write(f"---\n\n")
        print(f"📺 新闻联播：{len(xwlb_articles)} 条 → {xwlb_path}")

    # 2.6 日期过滤 — 仅保留当日（发布日期必须严格等于今天）
    today_date = today
    filtered = []
    for a in all_articles:
        if a.source == "新闻联播":
            continue  # 新闻联播不参与日期过滤，由时间门控决定
        pub = a.published_at or ""
        if pub == today_date:
            filtered.append(a)
        # 日期不是今天的全部丢弃，不兜底
    skipped = len(all_articles) - len(filtered)
    # XWLB 不参与日期过滤，加回 all_articles
    all_articles = filtered
    all_articles.extend(xwlb_articles)
    print(f"📅 日期过滤（仅当日）：{len(filtered)} 篇保留，{skipped} 篇跳过（+{len(xwlb_articles)} 篇新闻联播）")

    # 3. 存储（去重）
    new_count = 0
    for article in all_articles:
        aid = db.insert_article(article)
        if aid is not None:
            new_count += 1

    print(f"✅ 去重后新增：{new_count} 篇")

    if new_count == 0:
        report_path = os.path.join(config.output.report_dir, f"{today}.md")
        if os.path.exists(report_path):
            print("ℹ️ 没有新文章且报告已存在，跳过分析")
            return
        print("ℹ️ 没有新文章，但报告文件缺失，用今日已有数据重新生成")

    # 4. 统计
    today_articles = db.get_unanalyzed_articles(date=today)
    if not today_articles:
        # 重新生成模式：从数据库取今日全部文章
        today_articles = db.get_articles_by_date(today)
    stats = compute_stats(today_articles, db, today)
    stats["total_in_db"] = db.count_articles()

    # 5. 趋势分析
    trends = compute_trends(db, days=7)
    trend_text = format_trends_for_ai(trends) if trends["top_sectors"] else ""

    # 初始化行情变量（校准模式下可能不获取）
    market_data = None
    indices = None

    # 6. 检查是否已有今日报告 → 增量模式 vs 全量模式
    existing_report = db.get_daily_report(today)
    is_update = existing_report is not None
    if fresh:
        is_update = False  # --fresh 强制全量重新生成
        # 同时重置今日文章的已分析标记，让已采集的文章重新参与分析
        reset_count = db.reset_analyzed_for_date(today)
        if reset_count:
            logger.info("--fresh: 已重置 %d 篇文章的已分析标记", reset_count)


    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_report = db.get_daily_report(yesterday)

    if is_update:
        # 校准模式：统计部分全量刷新，分析部分仅输出变化
        print(f"📝 检测到今日已有报告，进入校准模式（+{new_count}篇新文章）")

        # 先重新生成统计部分
        stats_section = f"""## 📌 核心政策信号
（基于本轮新增 {new_count} 篇文章更新）

{format_stats_for_ai(stats, today_articles[:15])}

"""
        if trend_text:
            stats_section += f"\n{trend_text}\n"

        calibration_prompt = f"""你已有今日的初版报告分析部分如下。现在统计数据和板块热度已经更新（见上方新数据），另外采集到 {new_count} 篇新增文章。

## ⚠️ 输出规则（极其重要）
1. 只输出分析部分有变化的内容，不要输出统计部分。
2. 新增事实 → 简洁补充，格式「补充：XXX」。
3. 结论改变 → 格式「修正：原结论XXX → 新结论XXX。原因：XXX」。
4. 结论未变 → 不输出。
5. 输出格式示例：
   ## 🔄 校准（{datetime.now().strftime('%H:%M')}）
   - 修正：金融板块从增配→中性。原因：新增证监会监管文件显示收紧。
   - 补充：黄金利多因素增加一条——美伊协议破裂风险上升。
   - 修正：医药短期走势从「震荡」→「偏弱」。原因：新增集采文件。

## 初版报告分析部分
{existing_report.report_md[existing_report.report_md.find('📊'):][:8000] if '📊' in existing_report.report_md else existing_report.report_md[:8000]}

## 新增文章
{format_stats_for_ai(stats, today_articles[:12])}

请输出校准内容。
"""
        correction = await analyze_with_deepseek(calibration_prompt, config)
        if correction:
            ai_analysis = existing_report.report_md + "\n\n---\n\n" + correction
        else:
            ai_analysis = existing_report.report_md
    else:
        # 全量模式：首次生成完整报告
        # 获取实时行情数据
        print("📊 获取行情数据...")
        try:
            market_data = await get_market_snapshot()
            indices = await get_index_snapshot()
            # PE 估值数据更新
            try:
                await update_pe_data()
            except Exception as e:
                logger.warning("PE 估值更新失败（不影响管线）: %s", e)
            market_text = format_market_for_ai() + "\n\n" + format_index_for_ai(indices)
            print(f"   行情更新（COMEX + {len(indices)} 个指数）")
        except Exception as e:
            logger.warning("行情获取失败: %s", e)
            market_text = "（行情数据暂不可用）"

        # 读昨日报告作为连续性参考（已在上面获取）
        continuity_note = ""
        if yesterday_report:
            # 从昨日报告中提取板块方向（简洁表格，AI 必须对照）
            from src.backtest import extract_predictions as _extract
            try:
                yesterday_preds = _extract(yesterday_report.report_md, yesterday)
                if yesterday_preds:
                    pred_table = "\n".join(
                        f"| {p['sector']} | {p['direction']} | {p.get('confidence','?')} |"
                        for p in yesterday_preds
                    )
                    continuity_note = f"""
## ⚠️ 昨日报告板块方向（必须严格对照，禁止杜撰）
| 板块 | 昨日方向 | 强度 |
|------|---------|------|
{pred_table}

规则：保持一致标注「延续昨日」。改变方向必须标注原因。**昨天方向以本表格为准，不准凭记忆编造。**
"""
            except Exception:
                continuity_note = f"昨日报告摘要（供参考）：{yesterday_report.report_md[:500]}"


        # 真实基金数据库的板块覆盖
        fund_ref = get_fund_names_for_prompt(get_all_sectors())

        ai_prompt = format_stats_for_ai(stats, today_articles)
        if continuity_note:
            ai_prompt = continuity_note + "\n\n" + ai_prompt
        if market_text:
            ai_prompt = market_text + "\n\n" + ai_prompt
        # PE 估值数据
        pe_text = format_pe_for_ai()
        if pe_text:
            ai_prompt += "\n\n" + pe_text
        if trend_text:
            ai_prompt += "\n\n" + trend_text
        if fund_ref:
            ai_prompt += "\n\n" + fund_ref

        # 新闻联播要目 + 月度趋势
        if xwlb_articles:
            xwlb_text = "\n## 📺 新闻联播今日要目\n"
            for i, a in enumerate(xwlb_articles[:12], 1):
                xwlb_text += f"{i}. {a.title}\n"
                if a.summary:
                    xwlb_text += f"   {a.summary[:200]}...\n"
            xwlb_text += "\n" + compute_xwlb_monthly(db, config.output.report_dir)
            ai_prompt = xwlb_text + "\n" + ai_prompt

        # 休市提示
        if not is_trading_day:
            reason = "节假日" if is_holiday else "周末"
            ai_prompt = (
                f"⚠️ 今天是{reason}，A股休市。以下指数行情为上一个交易日收盘数据，"
                "政府网站今日不更新，新增政策信息极少属正常。"
                "报告中禁止声称\"今日行情\"，应标注\"上一交易日\"。\n\n"
            ) + ai_prompt

        ai_analysis = await analyze_with_deepseek(ai_prompt, config)

        if ai_analysis is None:
            ai_analysis = (
                "⚠️ AI 分析暂不可用（API key 未配置或调用失败），以下仅为统计数据。"
            )
            print("⚠️ AI 分析跳过（需配置 DEEPSEEK_API_KEY 环境变量）")

    # 标记已分析，避免下次运行时重复统计
    # 只标记实际参与报告的 article（防止非当日文章被永久标记）
    report_urls = {a.url for a in all_articles}
    db.mark_analyzed([a.id for a in today_articles if a.id and a.url in report_urls])

    # 回测：从报告中提取预测并保存
    try:
        predictions = extract_predictions(ai_analysis, today)
        if predictions:
            save_predictions(predictions)
            logger.info("回测记录：%d 条预测已保存", len(predictions))
            generate_prediction_table()  # 更新追踪表
    except Exception as e:
        logger.debug("回测记录失败: %s", e)

    # 🔍 事后校验：检测 AI 杜撰（基金代码/URL/价格/板块一致性等）
    validation_warnings = ""
    try:
        real_urls = {a.url for a in today_articles}
        yday_preds = extract_predictions(yesterday_report.report_md, yesterday) if yesterday_report else []
        old_analysis_for_check = existing_report.report_md if is_update else None

        validation_warnings = validate_ai_output(
            ai_analysis,
            real_urls=real_urls,
            stats=stats,
            market_data=market_data if market_data and market_data.get("quotes") else None,
            index_data=indices if indices else None,
            yesterday_predictions=yday_preds,
            old_analysis=old_analysis_for_check,
        )
        if validation_warnings:
            ai_analysis = ai_analysis.rstrip() + "\n" + validation_warnings
            logger.info("校验完成：发现 %d 条疑似问题", validation_warnings.count("- "))
    except Exception as e:
        logger.warning("校验异常（跳过，不影响报告生成）: %s", e)

    # 7. 生成 / 更新报告
    if is_update:
        # 校准模式：统计刷新 + 分析追加修正
        report_path = os.path.join(config.output.report_dir, f"{today}.md")
        # 拼接：重新生成的统计 + 原报告分析 + AI校准
        stats_header = f"# 📡 政策雷达日报 · {today}\n\n"
        original_analysis = existing_report.report_md[existing_report.report_md.find('📊'):] if '📊' in existing_report.report_md else existing_report.report_md
        full_report = stats_header + stats_section + "\n" + original_analysis
        # 如果 AI 有校准内容，追加
        if correction:
            full_report = full_report.rstrip() + "\n\n---\n\n" + correction
        if validation_warnings:
            full_report = full_report.rstrip() + "\n" + validation_warnings
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_report)
        report_md = full_report
    else:
        report_md = generate_markdown_report(stats, ai_analysis, today_articles, trends)
        report_path = save_report(report_md, config.output.report_dir, today)

    # 7.5 拆出新闻联播分析到独立文件
    xwlb_count = len([a for a in all_articles if a.source == "新闻联播"])
    report_md = split_xwlb_analysis(report_md, today, config.output.report_dir, xwlb_count)
    # 主报告可能已被修改，重新写入
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    # 8. 存储报告到数据库
    db.insert_daily_report(
        date=today,
        article_count=new_count + (existing_report.article_count if existing_report else 0),
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
    parser.add_argument(
        "--fresh",
        action="store_true",
        default=False,
        help="强制全量重新生成报告（跳过校准/增量模式）",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_pipeline(args.config, fresh=args.fresh))
    except KeyboardInterrupt:
        print("\n⏹ 用户中断")
        sys.exit(0)
    except Exception as e:
        logger.exception("管线执行失败: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
