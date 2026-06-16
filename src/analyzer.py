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
    "新能源": ["新能源", "风电", "氢能", "锂电", "电池", "充电桩", "电动汽车"],
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
    "能源": ["能源", "煤炭", "石油", "天然气"],
    "电力": [
        "电力", "电网", "火电", "水电", "核电",
        "输配电", "电价", "售电", "虚拟电厂",
        "电力改革", "绿电", "碳交易",
    ],
    "机器人": [
        "机器人", "人形机器人", "工业机器人", "服务机器人", "具身智能",
        "机械臂", "伺服电机", "减速器", "控制器", "传感器",
        "自动化", "智能装备", "机器视觉",
    ],
    "制造": ["制造", "工业", "装备", "机床", "新材料", "高端制造"],
    "军工航天": [
        "军工", "航天", "航空", "卫星", "导弹", "雷达", "舰船",
        "军民融合", "国防", "武器装备", "战斗机", "无人机", "火箭军",
        "北斗", "空间站", "载人航天", "探月",
    ],
    "光伏": [
        "光伏", "太阳能", "硅料", "硅片", "组件", "逆变器", "分布式",
        "集中式", "TOPCon", "HJT", "钙钛矿", "光伏玻璃", "储能",
    ],
    "建材": [
        "建材", "水泥", "玻璃", "管材", "涂料", "防水", "石膏板",
        "基建材料", "装配式建筑", "绿色建材", "玻纤",
    ],
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
            change_label = f"{change_pct:+.1f}%"
        elif count > 0:
            change_pct = None  # None = 无昨日对比数据，非0%变化
            change_label = "🆕"
        else:
            change_pct = 0.0
            change_label = "—"
        changes.append({
            "sector": sector,
            "today": count,
            "yesterday": prev,
            "change_pct": change_pct,
            "change_label": change_label,
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

    # 趋势方向判断（仅对数据充足的板块计算）
    for sector in top_sectors:
        series = trend_series[sector]
        total_mentions = sum(series)
        if len(series) >= 3 and total_mentions >= 3:
            first_half = sum(series[:len(series)//2]) / max(1, len(series)//2)
            second_half = sum(series[len(series)//2:]) / max(1, len(series) - len(series)//2)
            if second_half > first_half * 1.2:
                trend_series[sector + "_direction"] = "📈 上升"
            elif second_half < first_half * 0.8:
                trend_series[sector + "_direction"] = "📉 下降"
            else:
                trend_series[sector + "_direction"] = "📊 平稳"
        else:
            trend_series[sector + "_direction"] = "📊 数据不足"

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

SYSTEM_PROMPT = """你是一位专业的中国宏观政策与基金配置分析师。基于当日中国官方政策信息，分析政策动向并给出基金配置参考。

写作要求：
1. 事件标注具体日期，禁用「近日」「近期」等模糊词。每个结论必须引用当日具体政策事件或数据作为依据。
2. 逻辑链用 → 串联，简洁有力。
3. 首次出现的专业术语括号解释，如 MLF（中期借贷便利）、LPR（贷款市场报价利率）等。
4. ⚠️ 基金代码必须来自下方的「真实基金数据库」，禁止编造代码。每只基金必须解释选基逻辑：跟踪什么指数、规模多大、费率水平、为什么当前环境下选它。
5. 每个板块给出短期（1-4周）和长期（3-12月）走势预测，注明预测依据。
6. **信息源权重**（极其重要）：
   - 一手来源（政府官网：央行/国务院/发改委/财政部等）：最高权重。必须优先引用，尽可能引用原文具体措辞。
   - 二手来源（媒体/研究：新华社/人民日报/证券时报/第一财经/中经网）：辅助参考。仅在一手来源不足时用来补充背景和解读，不得替代一手来源作为主要判断依据。
   - 分析时区分：哪个结论来自一手政策文件，哪个来自媒体解读。
   - 如一手来源和二手来源信息矛盾，以一手来源为准。
7. **客观性要求**：
   - 区分「数据支撑的判断」和「推测」，不确定的地方明确标注。
   - 当缺乏一手政策证据时，如实说明「当日无直接政策信号」，不强行编造逻辑。
   - 多空因素并存时，列出双方论据，不选择性呈现。
   - 板块热度是政策关注度指标，不等于涨跌预测，需提醒用户区分。
   - 如果某板块数据稀疏（热度<3），标注数据局限性。
8. **连续性要求**：
   - 如果提供了昨日报告的结论，必须对照昨日判断做出评价。
   - 方向一致时标注「延续昨日判断：金融板块维持增配」。
   - 方向改变时必须标注「调整原因：新政策信号XXX导致判断从增配→中性」。
   - 不允许无理由反转昨日判断。

报告格式：

## 📌 核心政策信号
按日期列2-3条最重要的政策信号，每条附逻辑链和具体出处。

> ⚠️ 本报告基于中国官方公开政策文本的语义分析，反映政策关注度而非市场涨跌预测。板块热度高 = 政策文件在讨论这个领域，不等于该板块一定会上涨。投资决策请结合行情、估值、个人风险偏好综合判断。

## 📈 板块热度与趋势
覆盖 TOP5 + 消费 + 医药 + 军工航天 + 光伏 + 电力 + 建材 + 机器人，逐个简述：
- **板块**：热度N次，趋势📈/📉/📊
- 短期（1-4周）：预测方向 + 依据
- 长期（3-12月）：预测方向 + 依据

## 📊 重点板块评估
逐板块深度分析（TOP5 + 消费 + 医药 + 军工航天 + 光伏 + 电力 + 建材 + 机器人），格式：
- **板块**：利好/利空/中性，程度强/中/弱
- 近期走势回顾：（该板块近1-3个月的市场表现、涨跌原因分析）
- 当前位置判断：（估值分位/历史百分位，处于高位/中位/低位/底部区间）
- 参考依据：（引用当日哪条具体政策/事件支撑此判断）
- 逻辑链：事件 → 传导 → 影响
- 短期走势（1-4周）：判断 + 可能催化剂
- 长期走势（3-12月）：判断 + 核心驱动因素
- 上行风险 / 下行风险：各列1条

## 🥇 黄金深度分析（独立板块）

### 🏷️ 影响金价的五大核心因素
逐一分析当日各因素状态：
1. **美元强弱**：DXY 当前值 ____，走势 ____。与金价负相关（美元涨→金价跌）
2. **实际利率**：10年期美债收益率 ____%。利率上升→持有黄金机会成本增加→利空
3. **地缘政治风险**：当前主要地缘事件 ____。避险情绪 ____
4. **通胀预期**：当前通胀环境 ____。通胀高→保值需求→利多黄金
5. **央行购金**：中国央行/全球央行购金动态 ____。持续购金→需求支撑

### 📈 当前行情
- COMEX 黄金期货（实时数据）：见上方行情数据中的价格和日内涨跌
- 上海金估算价：见上方估算值
- ⚠️ 注：美元指数和10年期美债收益率暂缺实时数据，请基于 AI 训练知识给出参考值，并明确标注"非实时数据，仅供参考"

### 📉 近3月走势回顾
- 区间：最低 ____ 最高 ____ 累计涨跌 ____%
- 关键节点：（标注近3个月内的重要拐点及触发事件）
- 当前所处位置：（高位/中位/低位/关键支撑/压力位）

### ⚖️ 多空力量对比
- **上涨动力**（列2-3条，引用具体数据/事件）
- **下行压力**（列2-3条，引用具体数据/事件）
- **综合判断**：利多因素 ____ vs 利空因素 ____，当前 ____ 方占优

### 💰 配置建议
- 方向：增配/中性持有/减配
- 短期（1-4周）：判断 + 依据
- 中长期（3-12月）：判断 + 依据
- 参考基金：华安黄金易ETF联接A(000216) / 博时黄金ETF联接A(002610)
- 风险提示：

## 📉 债券市场
- 利率债 / 信用债 / 可转债，各给短期+长期判断

## 💰 基金配置参考（不构成投资建议）

| 类别 | 方向 | 参考基金（场外，来自真实基金库） | 选基逻辑（为什么是它） | 建议持有周期 |
|------|------|-------------------------------|----------------------|-------------|
| 宽基 | 增/中/减 | 具名基金+代码 | 说明：这只基金跟踪什么指数、费率水平、规模、跟踪误差、适合当前环境的原因（写2-3句） | 短线/中长线 |
| 行业 | 同上 | 3-5个方向各1-2只 | 同上，每个方向都要写清逻辑 | 同上 |
| 债券 | 同上 | 纯债/固收+各1只 | 同上 | 同上 |
| 黄金 | 同上 | 1-2只 | 同上 | 同上 |
| 现金 | 同上 | 货币/短债 | 同上 | - |

## 📋 数据说明
- 数据来源：今日采集自 N 个信息源，共 M 篇文章
- 覆盖范围：注明哪些类别的信息源有数据、哪些缺失
- 板块热度说明：热度 = 政策文件中相关关键词出现频次，反映政策关注度而非市场涨跌
- 局限性：本报告仅基于公开政策文本分析，不含实时行情数据；近期的市场走势判断基于 AI 训练知识，可能滞后

## ⚠️ 风险提示
每条风险注明：事件、监测指标、潜在影响。

## 💡 总结
一段话概括当日结论，区分短期策略和中长期布局。
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
            label = ch.get("change_label",
                f"{'+' if ch['change_pct'] and ch['change_pct'] > 0 else ''}{ch['change_pct']:.1f}%" if ch.get('change_pct') is not None else '—')
            lines.append(f"  - {ch['sector']}: {ch['today']}篇 ({label})")

    lines.append("\n- 按类别分布：")
    for cat, cnt in stats.get("categories", {}).items():
        lines.append(f"  - {cat}: {cnt} 篇")

    # 按来源层级分组
    tier1_cats = {"货币政策", "宏观决策", "产业政策", "金融监管", "经济数据", "贸易数据", "能源政策", "财政商务"}
    tier1 = [a for a in articles if a.category in tier1_cats]
    tier2 = [a for a in articles if a.category not in tier1_cats]

    lines.append(f"\n## 📋 一手政策来源（政府官网）— {len(tier1)} 篇，分析以这些为准")
    for i, a in enumerate(tier1[:12], 1):
        lines.append(f"{i}. [{a.source}]({a.url}) {a.title}")
        if a.summary:
            lines.append(f"   {a.summary[:150]}")
        tag_str = ", ".join(a.tags) if a.tags else "—"
        lines.append(f"   #{tag_str}")

    lines.append(f"\n## 📰 二手参考来源（媒体/研究）— {len(tier2)} 篇，仅作背景补充")
    for i, a in enumerate(tier2[:8], 1):
        lines.append(f"{i}. [{a.source}]({a.url}) {a.title}")
        if a.summary:
            lines.append(f"   {a.summary[:150]}")
        tag_str = ", ".join(a.tags) if a.tags else "—"
        lines.append(f"   #{tag_str}")

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
