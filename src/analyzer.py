"""分析引擎。

包含两个核心分析模块：
1. 本地统计分析：板块标注、频次统计、环比变化
2. AI 语义分析：DeepSeek API 调用
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import httpx

from src.models import Article
from src.db import Database
from src.config import Config

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# 板块关键词映射
# ────────────────────────────────────────────────────────────

SECTOR_KEYWORDS: Dict[str, List[str]] = {
    "金融": ["银行", "金融", "券商", "保险", "信托", "信贷", "利率", "LPR", "降准", "降息", "存款", "贷款"],
    "地产": ["房地产", "地产", "房价", "楼市", "住房", "保障房", "公积金", "土地"],
    "新能源": ["新能源", "光伏", "风电", "储能", "氢能", "锂电", "电池", "充电桩", "电动汽车"],
    "半导体": ["半导体", "芯片", "集成电路", "光刻", "晶圆", "先进制程"],
    "医药": [
        "医药", "医疗", "药品", "医保", "疫苗", "生物药", "创新药", "集采",
        "仿制药", "临床试验", "新药", "药监", "处方药", "OTC", "中药",
        "化学药", "生物制药", "CXO", "医疗器械", "基因", "细胞治疗",
        "药企", "药厂", "制药", "制剂", "原料药", "研发管线", "License",
        "NDA", "IND", "上市申请", "优先审评", "突破性疗法",
        "卫生健康", "公立医院", "基层医疗", "分级诊疗", "DRG",
        "药监局", "卫健委", "医保局", "药品集采", "耗材集采",
    ],
    "贵金属": [
        "黄金", "贵金属", "白银", "金价", "黄金储备", "央行购金",
        "避险资产", "现货黄金", "COMEX", "金矿",
    ],
    "消费": ["消费", "零售", "汽车", "家电", "餐饮", "旅游", "免税", "电商", "直播"],
    "基建": ["基建", "铁路", "公路", "水利", "新基建", "5G", "特高压", "REITs"],
    "数字经济": ["数字", "人工智能", "AI", "大数据", "云计算", "区块链", "数据要素", "算力"],
    "能源": ["能源", "煤炭", "石油", "天然气", "电力", "电网", "火电", "水电"],
    "制造": ["制造", "工业", "装备", "机器人", "机床", "新材料", "高端制造"],
    "农业": ["农业", "农村", "粮食", "种业", "乡村振兴", "耕地"],
    "环保": ["环保", "碳中和", "碳达峰", "减排", "绿色", "低碳"],
    "贸易": [
        "贸易", "进出口", "外贸", "关税", "自贸区", "跨境电商",
        "制裁", "反制裁", "出口管制", "实体清单", "贸易摩擦",
        "WTO", "反倾销", "反补贴", "301调查", "供应链",
    ],
    "有色金属": [
        "有色金属", "铜", "铝", "锌", "镍", "锡", "铅",
        "稀土", "锂矿", "钴", "钨", "钼", "锑", "镁",
        "电解铝", "铜价", "铝价", "矿产", "冶炼",
    ],
    "科技": ["科技", "创新", "研发", "专精特新", "科创板", "硬科技"],
}


def extract_sectors(text: str) -> List[str]:
    """从文本中提取相关板块标签。

    基于 SECTOR_KEYWORDS 做子串匹配，每个板块只计一次。

    Args:
        text: 待分析文本（标题 + 摘要）。

    Returns:
        匹配到的板块名列表，按 KEYWORDS 定义顺序。
    """
    hits: List[str] = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                hits.append(sector)
                break
    return hits


# ────────────────────────────────────────────────────────────
# 统计分析
# ────────────────────────────────────────────────────────────

def compute_stats(
    articles: List[Article],
    db: Optional[Database] = None,
    today: Optional[str] = None,
) -> Dict:
    """计算当日统计指标。

    Args:
        articles: 当日的 Article 列表。
        db: 数据库实例（用于查询昨日数据做环比）。可为 None。
        today: 日期字符串 YYYY-MM-DD，默认今天。

    Returns:
        统计字典，包含：
        - date: 日期
        - total_articles: 文章总数
        - categories: 按类别分布
        - top_sectors: 板块频次 TOP 10
        - sector_changes: 板块环比变化
    """
    if not today:
        today = datetime.now().strftime("%Y-%m-%d")

    # 自动标注板块标签
    for a in articles:
        if not a.tags:
            a.tags = extract_sectors(a.title + " " + a.summary)

    sector_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    for a in articles:
        for tag in a.tags:
            sector_counter[tag] += 1
        category_counter[a.category] += 1

    top_sectors = sector_counter.most_common(10)

    # 环比变化
    yesterday = (
        datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)
    ).strftime("%Y-%m-%d")
    yesterday_sectors: Dict[str, int] = {}

    if db:
        try:
            yesterday_articles = db.get_articles_by_date(yesterday)
            y_counter: Counter[str] = Counter()
            for a in yesterday_articles:
                if not a.tags:
                    a.tags = extract_sectors(a.title + " " + a.summary)
                for tag in a.tags:
                    y_counter[tag] += 1
            yesterday_sectors = dict(y_counter.most_common(10))
        except Exception:
            logger.debug("无法获取昨日数据用于环比计算")

    changes = []
    for sector, count in top_sectors:
        prev = yesterday_sectors.get(sector, 0)
        if prev > 0:
            change_pct = round((count - prev) / prev * 100, 1)
        elif count > 0:
            change_pct = 100.0
        else:
            change_pct = 0.0
        changes.append({
            "sector": sector,
            "today": count,
            "yesterday": prev,
            "change_pct": change_pct,
        })

    return {
        "date": today,
        "total_articles": len(articles),
        "categories": dict(category_counter.most_common()),
        "top_sectors": top_sectors,
        "sector_changes": changes,
    }


def compute_trends(db: Database, days: int = 7) -> Dict:
    """计算板块多日热度趋势。

    Args:
        db: 数据库实例。
        days: 回溯天数。

    Returns:
        trend_data: {date: {sector: count}} 时间序列
        trend_top: 按总提及量排序的板块列表
    """
    from collections import defaultdict

    end = datetime.now()
    start = end - timedelta(days=days)
    dates = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    dates.reverse()

    trend_data: Dict[str, Dict[str, int]] = {d: defaultdict(int) for d in dates}

    for d in dates:
        try:
            arts = db.get_articles_by_date(d)
            for a in arts:
                if not a.tags:
                    a.tags = extract_sectors(a.title + " " + a.summary)
                for tag in a.tags:
                    trend_data[d][tag] += 1
        except Exception:
            continue

    # 按总量排序的板块列表
    total_counter: Counter[str] = Counter()
    for d in dates:
        for sector, count in trend_data[d].items():
            total_counter[sector] += count

    top_sectors = [s for s, _ in total_counter.most_common(10)]

    # 构建趋势序列
    trend_series = {}
    for sector in top_sectors:
        trend_series[sector] = [trend_data[d].get(sector, 0) for d in dates]

    # 趋势方向判断（线性回归斜率简化版）
    for sector in top_sectors:
        series = trend_series[sector]
        if len(series) >= 3:
            # 简单的三日移动平均斜率
            first_half = sum(series[:len(series)//2]) / max(1, len(series)//2)
            second_half = sum(series[len(series)//2:]) / max(1, len(series) - len(series)//2)
            if second_half > first_half * 1.1:
                trend_series[sector + "_direction"] = "📈 上升"
            elif second_half < first_half * 0.9:
                trend_series[sector + "_direction"] = "📉 下降"
            else:
                trend_series[sector + "_direction"] = "📊 平稳"

    return {
        "dates": dates,
        "series": trend_series,
        "top_sectors": top_sectors,
    }


def format_trends_for_ai(trends: Dict) -> str:
    """将趋势数据格式化为 AI prompt 文本。"""
    lines = ["## 📈 板块热度 {days} 日趋势".format(days=len(trends["dates"]))]
    lines.append("")

    for sector in trends["top_sectors"]:
        direction = trends["series"].get(sector + "_direction", "")
        series = trends["series"].get(sector, [])
        values = " → ".join(str(v) for v in series)
        lines.append(f"- **{sector}** {direction}: {values}")

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────
# AI 分析
# ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一位专业的中国宏观经济与大类资产配置分析师。你的任务是基于当日中国官方发布的政策信息，分析政策动向并给出资产配置建议。

## 重要写作要求：
1. **时间标注**：陈述每个事件时，必须在前面标注具体时间（如「6月12日财政部发布…」「6月10日国务院常务会议…」），禁止使用「近日」「近期」「日前」等模糊表述。
2. **逻辑链条**：每个结论必须呈现清晰的因果链，用 → 符号连接。例如：「央行降准 → 银行负债成本下降 → 信贷投放意愿增强 → 利好银行板块」。
3. **术语解释**：首次出现的专业术语，用括号给出通俗解释，如：MLF（中期借贷便利，央行向商业银行提供中期资金的工具）、OMO（公开市场操作）、LPR（贷款市场报价利率）、PSL（抵押补充贷款）、SLF（常备借贷便利）、逆回购（央行向市场投放短期流动性）、信用利差（信用债与国债的收益率差）、期限利差（长短期国债收益率差）等。

请按以下格式输出分析：

## 📌 核心政策信号
（按时间排列当日最重要的2-3条政策信号，每条标注日期，附简要逻辑链）

## 📈 趋势研判
（基于板块热度多日趋势数据，判断哪些板块处于上升/下降通道，哪些即将拐点，持续性预估）

## 📊 A股板块影响评估
逐个板块分析，必须覆盖当日热度前5板块，另**必须包含消费、医药/创新药板块**（即使当日无直接政策，也需基于宏观环境做专业研判）。格式：
- **板块名称**：影响方向（利好/利空/中性），影响程度（强/中/弱）
- 逻辑链：具体事件 → 传导路径 → 影响机制 → 板块影响
- （如有专业术语，加括号解释）

## 🥇 黄金/贵金属配置建议
- 配置建议：增配 / 中性持有 / 减配
- 逻辑链：当日事件 → 避险/通胀/利率预期变化 → 黄金定价影响
- 风险提示：

## 📉 债券市场研判
- 利率债：判断 + 逻辑链
- 信用债：判断 + 逻辑链（出现「信用利差」等术语时解释）
- 可转债：当前性价比判断

## 💰 指数基金配置参考（不构成投资建议）

| 资产类别 | 建议方向 | 参考标的 | 逻辑链 |
|----------|---------|---------|--------|
| 宽基指数 | 增配/中性/减配 | 沪深300/中证500/创业板 | 用 → 连接 |
| 行业ETF | 增配/中性/减配 | 必须包含券商/半导体/新能源/消费/医药，推荐3-5个方向 | 用 → 连接 |
| 债券基金 | 增配/中性/减配 | 纯债/二级债基 | 用 → 连接 |
| 黄金ETF | 增配/中性/减配 | 黄金ETF | 用 → 连接 |
| 货币基金 | 增配/中性/减配 | 货基/短债 | 用 → 连接 |

## ⚠️ 风险提示
（列出需跟踪的风险点，每个注明监测指标和潜在影响）

## 💡 综合配置思路
（2-3句话的逻辑链总结）
"""


def format_stats_for_ai(stats: Dict, articles: List[Article]) -> str:
    """将统计结果和文章列表格式化为 AI 可读的 prompt 文本。

    Args:
        stats: compute_stats() 返回的统计字典。
        articles: 当日文章列表。

    Returns:
        适合作为 DeepSeek user message 的文本。
    """
    lines: list[str] = []
    lines.append(f"## 当日统计 ({stats['date']})")
    lines.append(f"- 新增文章：{stats['total_articles']} 篇")
    lines.append("- 热门板块 TOP 5：")
    for sector, count in stats["top_sectors"][:5]:
        lines.append(f"  - {sector}: {count} 篇")

    if stats.get("sector_changes"):
        lines.append("\n- 板块热度环比变化：")
        for ch in stats["sector_changes"][:10]:
            arrow = "↑" if ch["change_pct"] > 0 else "↓" if ch["change_pct"] < 0 else "→"
            lines.append(
                f"  - {ch['sector']}: {ch['today']}篇 "
                f"({arrow}{abs(ch['change_pct'])}%)"
            )

    lines.append("\n- 按类别分布：")
    for cat, cnt in stats.get("categories", {}).items():
        lines.append(f"  - {cat}: {cnt} 篇")

    lines.append("\n## 当日文章摘要")
    for i, a in enumerate(articles[:50], 1):
        lines.append(f"{i}. [{a.source}] {a.title}")
        if a.summary:
            lines.append(f"   摘要: {a.summary[:120]}")
        tag_str = ", ".join(a.tags) if a.tags else "无"
        lines.append(f"   标签: {tag_str}")

    return "\n".join(lines)


async def analyze_with_deepseek(
    prompt: str,
    config: Config,
) -> Optional[str]:
    """调用 DeepSeek API 进行政策分析。

    Args:
        prompt: 格式化后的分析 prompt。
        config: 系统配置（含 API key）。

    Returns:
        AI 分析全文（Markdown），失败或未配置 key 时返回 None。
    """
    if not config.deepseek.api_key:
        logger.warning("DeepSeek API key 未配置，跳过 AI 分析")
        return None

    url = f"{config.deepseek.base_url}/v1/chat/completions"

    payload = {
        "model": config.deepseek.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": config.deepseek.max_tokens,
        "temperature": 0.3,
    }

    headers = {
        "Authorization": f"Bearer {config.deepseek.api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error("DeepSeek API HTTP 错误 %d: %s", e.response.status_code, e)
        return None
    except (httpx.RequestError, KeyError, json.JSONDecodeError) as e:
        logger.error("DeepSeek API 调用失败: %s", e)
        return None
