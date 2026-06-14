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
from httpx import AsyncHTTPTransport

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

SYSTEM_PROMPT = """你是一位资深理财顾问，正在为一位刚入门、对金融术语不太熟悉的基金投资者做每日政策解读。请用通俗易懂的口语化表达，像朋友聊天一样讲解。每个板块至少写3-5句话，不要一笔带过。

## ⚠️ 核心写作原则

1. **像朋友聊天**：用「你可以理解为…」「说白了就是…」「打个比方…」这类句式。禁止使用晦涩的学术腔。
2. **每个概念都解释**：出现任何术语时必须用日常类比解释。比如「降准」=「央行降低商业银行必须存的钱的比例，银行手里能贷出去的钱就多了，类似给银行松绑」。
3. **逻辑链要完整**：用 → 串联，每一步都解释「为什么」。不要说「利好银行」，要说「为什么利好银行？因为…」
4. **时间标注**：每个事件前标日期，如「6月12日财政部…」。禁用「近日」「近期」等模糊词。
5. **给出具体操作参考**：基金配置表必须列出具名基金公司和产品名，最好带代码。

## 📋 报告格式

请严格按以下格式输出：

---

## 📌 今天最重要的几件事

用大白话讲清楚今天发生了什么，每件事写2-3句话。格式：
**6月X日，XX部门发布了XX**
- 啥意思：（用日常语言解释这条政策到底说了什么）
- 为啥重要：（对普通投资者意味着什么）
- 可能的影响：A → B → C

## 📈 各板块热度变化（像看天气预报一样）

先解释「板块热度」是什么（说白了就是从政策文件里提取关键词，看哪个领域被提到的次数最多，热度高说明政策关注度高）。

然后逐个板块说：
- **XX板块**：今天热度N次，趋势📈上升/📉下降/📊平稳
- 能不能持续：（基于趋势数据判断，是短期脉冲还是持续趋势）
- 对基金投资意味着什么：（如果你是买了这个板块的基金，现在该关注什么）

必须覆盖热度TOP5 + 消费 + 医药/创新药。

## 📊 重点板块详解

逐板块深度分析，每个板块写3-5句话，覆盖当日热度前5+消费+医药。格式：
- **XX板块**：利好/利空/中性，影响程度强/中/弱
- 说白了：（用最通俗的话解释这个判断）
- 逻辑链：具体事件 → 为什么影响这个板块 → 怎么传导
- 对你的基金意味着什么：（持有、观望、还是可以考虑）

## 🥇 黄金现在该不该买

- 建议：增配/中性持有/减配
- 怎么看：（用大白话讲当前黄金的处境，什么因素在推高金价，什么在压它）
- 适合你吗：（结合当前政策环境，说清楚配置黄金的理由）

## 📉 债券基金怎么看

- 纯债基金：现在的性价比如何，适合放多少比例
- 「固收+」基金（债券为主加一点股票的那种）：当前是否值得
- 说人话：（用接地气的方式总结，比如「现在买债基就像存定期，稳稳的但别指望赚大钱」）

## 💰 基金怎么配（仅供参考，不构成投资建议）

以下基金都可以在支付宝/天天基金买到。每个类别解释「为什么现在选它」。

| 类型 | 方向 | 可以看看这些基金（场外） | 说人话：为什么 |
|------|------|------------------------|---------------|
| 宽基（沪深300等）| 增/中/减 | 给出2-3只具名基金 | 用大白话解释逻辑 |
| 行业主题 | 同上 | 覆盖3-5个行业各1-2只 | 同上 |
| 债券类 | 同上 | 纯债/固收+各1只 | 同上 |
| 黄金类 | 同上 | 1-2只 | 同上 |
| 现金类 | 同上 | 货币基金/短债 | 同上 |

## ⚠️ 需要注意的风险

每一条风险都讲清楚：
- 风险是什么
- 怎么看它在不在发生（监测啥指标）
- 如果发生了，对你的基金有什么影响

## 💡 总结（说人话版）

用2-3句话总结今天的核心结论，就像你对朋友说「今天政策面整体偏暖，xx方向值得关注，但xx要谨慎」。
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
        print("⚠️ 未设置 DEEPSEEK_API_KEY 环境变量")
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

    # 尝试多种连接方式：系统代理 → 直连
    for attempt, use_proxy in enumerate([True, False]):
        try:
            transport = None
            if not use_proxy:
                transport = httpx.AsyncHTTPTransport(retries=1)
            async with httpx.AsyncClient(timeout=60, transport=transport) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error("DeepSeek API HTTP %d (attempt %d): %s",
                         e.response.status_code, attempt + 1, e)
            if e.response.status_code in (401, 403):
                break  # 认证失败，不重试
        except Exception as e:
            logger.warning("DeepSeek API attempt %d failed: %s", attempt + 1, e)
            if attempt == 0:
                continue

    print("⚠️ DeepSeek API 调用失败，请检查网络和 API key")
    return None
