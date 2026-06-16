"""AI 输出事后校验模块。

在 AI 生成分析报告后，对其中的基金代码、引用 URL、板块判断、
价格数字、昨日连续性声明进行自动化核查，防止 AI 杜撰。

每个校验函数返回 List[Dict]，每条记录包含：
- type: 警告类型
- severity: "error"（确定杜撰）/ "warning"（疑似）/ "info"（提示）
- message: 人类可读描述
- detail: 额外上下文字典

汇总入口：validate_ai_output() → 格式化警告 Markdown 文本。
"""

from __future__ import annotations

import json
import logging
import os
import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

FUNDS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "funds.json")


# ── 基金代码校验 ────────────────────────────────────────────

def _load_fund_codes() -> set[str]:
    """加载所有真实基金代码。"""
    codes: set[str] = set()
    try:
        with open(FUNDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for fund in data.get("funds", []):
                codes.add(fund["code"])
    except (json.JSONDecodeError, OSError, KeyError) as e:
        logger.warning("无法加载基金库: %s", e)
    return codes


def _load_fund_map() -> Dict[str, Dict]:
    """加载基金代码→详情映射。"""
    fund_map: Dict[str, Dict] = {}
    try:
        with open(FUNDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for fund in data.get("funds", []):
                fund_map[fund["code"]] = fund
    except (json.JSONDecodeError, OSError, KeyError) as e:
        logger.warning("无法加载基金库: %s", e)
    return fund_map


def verify_fund_codes(ai_analysis: str) -> List[Dict]:
    """校验 AI 输出中的基金代码是否都在真实基金库中。

    提取所有 6 位数字，排除明显非基金代码的（年份 202xxx、
    日期前缀等），然后逐一到 funds.json 中查证。

    Args:
        ai_analysis: AI 生成的完整分析文本。

    Returns:
        警告列表，每条是一个疑似杜撰的基金代码。
    """
    fund_map = _load_fund_map()
    if not fund_map:
        return []

    # 提取所有 6 位数字
    all_codes = set(re.findall(r"\b(\d{6})\b", ai_analysis))

    # 排除明显非基金代码的数字：年份 2020xx-2029xx、2000xx-2019xx
    # 以及一些常见非代码模式
    non_code_prefixes = {
        "202", "203", "204", "205", "206", "207", "208", "209",  # 年份
        "200", "201",  # 2000-2019 年
    }

    warnings = []
    for code in sorted(all_codes):
        # 跳过年份
        if code[:3] in non_code_prefixes:
            continue
        if code not in fund_map:
            warnings.append({
                "type": "fake_fund_code",
                "severity": "error",
                "message": f"基金代码 `{code}` 不在真实基金库中，疑似 AI 杜撰",
                "detail": {"code": code},
            })
        else:
            # 记录已使用的基金（可选：供后续分析 AI 是否合理选择了基金）
            pass

    if warnings:
        logger.warning("基金代码校验：发现 %d 个不在库中的代码", len(warnings))

    return warnings


# ── URL 引用校验 ────────────────────────────────────────────

def verify_cited_urls(ai_analysis: str, real_urls: set[str]) -> List[Dict]:
    """校验 AI 输出中引用的 URL 是否来自当日真实文章。

    如果 AI 引用了一个 URL，但该 URL 不在当日采集的文章列表中，
    则可能是编造的。

    Args:
        ai_analysis: AI 生成的完整分析文本。
        real_urls: 当日采集的所有文章 URL 集合。

    Returns:
        警告列表。
    """
    if not real_urls:
        return []

    # 提取 AI 输出中的 URL（Markdown 链接 + 纯 URL）
    cited_urls = set()
    # Markdown 链接: [text](url)
    for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", ai_analysis):
        cited_urls.add(m.group(2))
    # 纯 URL
    for m in re.finditer(r"https?://[^\s\)\]>]+", ai_analysis):
        cited_urls.add(m.group(0))

    if not cited_urls:
        return []

    # 构建真实 URL 的域+路径片段集合（用于模糊匹配）
    real_domains = set()
    for u in real_urls:
        # 提取域名
        m = re.match(r"https?://([^/]+)", u)
        if m:
            real_domains.add(m.group(1))

    warnings = []
    for url in sorted(cited_urls):
        # 精确匹配
        if url in real_urls:
            continue
        # 检查是否是真实 URL 的前缀（AI 可能截断参数）
        matched = False
        for real_url in real_urls:
            if real_url.startswith(url) or url.startswith(real_url):
                matched = True
                break
        if matched:
            continue
        # 检查域名是否至少匹配（宽松模式：同域名 + 同路径前 30 字符）
        m = re.match(r"https?://([^/]+)(/.+)?", url)
        if m:
            domain = m.group(1)
            path = m.group(2) or ""
            if domain in real_domains and len(path) > 0:
                # 尝试检查是否有任何真实 URL 与此相近
                for real_url in real_urls:
                    if domain in real_url:
                        # 路径相似度
                        real_path = real_url[real_url.find(domain) + len(domain):]
                        if SequenceMatcher(None, path[:30], real_path[:30]).ratio() > 0.5:
                            matched = True
                            break
        if matched:
            continue

        warnings.append({
            "type": "fake_url",
            "severity": "warning",
            "message": f"AI 引用的 URL 不在当日采集文章中：`{url[:100]}`",
            "detail": {"url": url},
        })

    if warnings:
        logger.warning("URL 校验：发现 %d 个不在当日文章中的引用", len(warnings))

    return warnings


# ── 板块判断 vs 统计一致性 ─────────────────────────────────

def verify_sector_consistency(ai_analysis: str, stats: Dict) -> List[Dict]:
    """校验 AI 对板块的判断方向与统计数据的信号是否矛盾。

    如果 AI 说某板块"利好"但该板块当日提及量环比大幅下降，
    或 AI 说"利空"但提及量大幅上升，则标记为矛盾。

    这并非绝对错误（政策内容比数量更重要），但值得人工复核。

    Args:
        ai_analysis: AI 生成的完整分析文本。
        stats: compute_stats() 返回的统计字典。

    Returns:
        警告列表。
    """
    sector_changes = stats.get("sector_changes", [])
    if not sector_changes:
        return []

    # 构建板块→环比变化映射
    change_map = {}
    for ch in sector_changes:
        change_map[ch["sector"]] = ch

    # 在 AI 输出中搜索每个板块的判断方向
    warnings = []
    for sector, ch in change_map.items():
        # 在 AI 输出中定位该板块附近的分析段落
        section = _find_sector_section(ai_analysis, sector)
        if not section:
            continue

        # 判断 AI 说的方向
        ai_direction = None
        if any(w in section for w in ["利好", "增配", "看多", "看涨", "利多"]):
            ai_direction = "利好"
        elif any(w in section for w in ["利空", "减配", "看空", "看跌", "利淡"]):
            ai_direction = "利空"
        else:
            # 可能是中性，不检查
            continue

        # 统计信号方向（提及量环比大幅变化）
        change_pct = ch.get("change_pct")
        if change_pct is None:
            continue  # 无昨日数据

        # 判断矛盾：AI 说利好但提及量暴跌，或 AI 说利空但提及量暴涨
        is_contradiction = False
        reason = ""
        if ai_direction == "利好" and change_pct < -30:
            is_contradiction = True
            reason = f"AI 判断利好，但板块提及量环比 {change_pct:+.1f}%（大幅下降），请人工复核"
        elif ai_direction == "利空" and change_pct > 30:
            is_contradiction = True
            reason = f"AI 判断利空，但板块提及量环比 {change_pct:+.1f}%（大幅上升），请人工复核"

        if is_contradiction:
            warnings.append({
                "type": "sector_contradiction",
                "severity": "warning",
                "message": f"板块 **{sector}**：{reason}",
                "detail": {
                    "sector": sector,
                    "ai_direction": ai_direction,
                    "change_pct": change_pct,
                    "today": ch["today"],
                    "yesterday": ch["yesterday"],
                },
            })

    if warnings:
        logger.warning("板块一致性校验：发现 %d 处矛盾", len(warnings))

    return warnings


# ── 行情数字交叉验证 ────────────────────────────────────────

def verify_price_numbers(
    ai_analysis: str,
    market_data: Optional[Dict] = None,
    index_data: Optional[Dict] = None,
) -> List[Dict]:
    """校验 AI 输出中的价格数字与实时行情数据是否一致。

    提取 AI 文本中出现在"COMEX""黄金""指数"附近的数字，
    与实际行情数据对比，偏差超过 2% 则标记。

    Args:
        ai_analysis: AI 生成的完整分析文本。
        market_data: get_market_snapshot() 的返回值（可选）。
        index_data: get_index_snapshot() 的返回值（可选）。

    Returns:
        警告列表。
    """
    warnings = []

    # 汇总所有已知价格
    known_prices: Dict[str, float] = {}

    if market_data:
        for name, q in market_data.get("quotes", {}).items():
            label_map = {"comex_gold": "COMEX黄金"}
            label = label_map.get(name, name)
            known_prices[label] = q["price"]

    if index_data:
        for name, q in index_data.items():
            known_prices[name] = q["price"]

    if not known_prices:
        return []

    for label, actual_price in known_prices.items():
        # 在 AI 文本中搜索该标签附近的价格数字
        # 找到 label 出现的位置，然后在前后 200 字符内找数字
        for m in re.finditer(re.escape(label), ai_analysis):
            start = max(0, m.start() - 200)
            end = min(len(ai_analysis), m.end() + 200)
            context = ai_analysis[start:end]

            # 提取上下文中的数字（含小数点）
            numbers = re.findall(r"(\d{1,4}(?:\.\d{1,2})?)", context)
            for num_str in numbers:
                try:
                    num = float(num_str)
                except ValueError:
                    continue
                # 只有量级相近才比较（例如不能拿 15% 跟价格 2350 比较）
                if num < 10 or actual_price < 10:
                    continue
                if num < actual_price * 0.01 or num > actual_price * 100:
                    continue

                # 计算偏差
                deviation = abs(num - actual_price) / actual_price
                if deviation > 0.05:  # 超过 5% 偏差
                    warnings.append({
                        "type": "price_mismatch",
                        "severity": "warning",
                        "message": (
                            f"**{label}**：AI 输出价格 {num:.1f}，"
                            f"实际行情 {actual_price:.1f}，偏差 {deviation:.1%}"
                        ),
                        "detail": {
                            "label": label,
                            "ai_price": num,
                            "actual_price": actual_price,
                            "deviation": round(deviation, 4),
                        },
                    })
                    break  # 每个 label 只报告一次

    if warnings:
        logger.warning("行情数字校验：发现 %d 处偏差", len(warnings))

    return warnings


# ── 昨日判断防杜撰 ──────────────────────────────────────────

def verify_continuity_claims(
    ai_analysis: str,
    yesterday_predictions: List[Dict],
) -> List[Dict]:
    """校验 AI 声称的「昨日判断」是否与实际昨日报告一致。

    如果 AI 说"延续昨日增配金融的判断"，但昨日实际是中性或减配，
    则标记为杜撰。

    Args:
        ai_analysis: AI 生成的完整分析文本。
        yesterday_predictions: 昨日报告 extract_predictions() 的返回值。

    Returns:
        警告列表。
    """
    if not yesterday_predictions:
        return []

    # 构建昨日方向映射
    yesterday_direction: Dict[str, str] = {}
    for p in yesterday_predictions:
        yesterday_direction[p["sector"]] = p["direction"]

    warnings = []

    # 搜索 AI 声称的 "延续昨日" "昨日判断" "昨日认为" 等模式
    # 使用已知板块名做候选匹配，而非硬性要求「板块」后缀
    sector_names = "|".join(re.escape(s) for s in yesterday_direction.keys())
    if not sector_names:
        return []

    continuity_patterns = [
        (rf"延续昨日.*?(?:{sector_names})", "延续"),
        (rf"维持昨日.*?(?:{sector_names})", "维持"),
        (rf"昨日判断.*?(?:{sector_names})", "引用"),
        (rf"与昨日一致.*?(?:{sector_names})", "一致"),
        (rf"继续.*?(利好|利空|增配|减配).*?(?:{sector_names})", "继续"),
    ]

    for pattern, claim_type in continuity_patterns:
        for m in re.finditer(pattern, ai_analysis):
            # 扩展匹配上下文：取匹配点后 40 字符以捕获方向词
            context_end = min(len(ai_analysis), m.end() + 40)
            matched_text = ai_analysis[m.start():context_end]

            # 确定板块（从已匹配文本或捕获组中提取）
            sector = None
            for s in yesterday_direction:
                if s in matched_text:
                    sector = s
                    break
            if not sector:
                continue

            # AI 声称的昨日方向
            claimed_direction = None
            if any(w in matched_text for w in ["利好", "增配", "看多"]):
                claimed_direction = "利好"
            elif any(w in matched_text for w in ["利空", "减配", "看空"]):
                claimed_direction = "利空"
            elif "中性" in matched_text:
                claimed_direction = "中性"

            # 实际昨日方向
            actual_direction = yesterday_direction.get(sector)

            if claimed_direction and actual_direction and claimed_direction != actual_direction:
                warnings.append({
                    "type": "continuity_fabrication",
                    "severity": "error",
                    "message": (
                        f"AI 声称「{matched_text[:60]}」，"
                        f"但昨日 **{sector}** 实际为 **{actual_direction}**"
                    ),
                    "detail": {
                        "sector": sector,
                        "claimed": claimed_direction,
                        "actual": actual_direction,
                        "claim_type": claim_type,
                    },
                })

    if warnings:
        logger.warning("连续性校验：发现 %d 处矛盾", len(warnings))

    return warnings


# ── 输出退化检测 ────────────────────────────────────────────

def detect_degradation(new_analysis: str, old_analysis: str) -> Optional[Dict]:
    """检测校准模式下 AI 输出是否有实质性变化。

    使用行级 SequenceMatcher 计算相似度。如果相似度 > 90%
    但 AI 声称做了修改，可能存在「偷懒复读」退化。

    Args:
        new_analysis: 新生成的 AI 分析文本。
        old_analysis: 旧的 AI 分析文本。

    Returns:
        退化检测结果，相似但无实质变化时返回 warning dict。
    """
    if not old_analysis or not new_analysis:
        return None

    # 行级相似度（更稳定）
    old_lines = old_analysis.splitlines()
    new_lines = new_analysis.splitlines()

    matcher = SequenceMatcher(None, old_lines, new_lines)
    similarity = matcher.ratio()

    if similarity > 0.90:
        return {
            "type": "degradation",
            "severity": "info",
            "message": (
                f"校准模式输出与旧报告相似度 {similarity:.0%}，"
                f"可能无实质更新"
            ),
            "detail": {"similarity": round(similarity, 4)},
        }

    return None


# ── 工具函数 ────────────────────────────────────────────────

def _find_sector_section(text: str, sector: str) -> str:
    """在文本中定位某板块的分析段落。

    Args:
        text: 全文。
        sector: 板块名。

    Returns:
        匹配点之后的上下文（仅后向，避免前一个板块的干扰），未找到返回空串。
    """
    patterns = [
        rf"\*\*{re.escape(sector)}\*\*",
        rf"{re.escape(sector)}板块",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            # 只取匹配点之后的文本（避免前一个板块的方向判断污染当前板块）
            return text[m.start():min(len(text), m.end() + 250)]
    return ""


# ── 汇总入口 ────────────────────────────────────────────────

def validate_ai_output(
    ai_analysis: str,
    *,
    real_urls: Optional[set[str]] = None,
    stats: Optional[Dict] = None,
    market_data: Optional[Dict] = None,
    index_data: Optional[Dict] = None,
    yesterday_predictions: Optional[List[Dict]] = None,
    old_analysis: Optional[str] = None,
) -> str:
    """汇总所有校验，返回格式化警告文本。

    所有参数通过关键字传入，按需提供即可。

    Args:
        ai_analysis: AI 生成的完整分析文本（必填）。
        real_urls: 当日真实文章 URL 集合。
        stats: compute_stats() 统计结果。
        market_data: get_market_snapshot() 行情快照。
        index_data: get_index_snapshot() 指数快照。
        yesterday_predictions: 昨日 extract_predictions() 结果。
        old_analysis: 旧版 AI 分析（校准模式）。

    Returns:
        格式化的 Markdown 警告段落。无警告时返回空字符串。
    """
    all_warnings: List[Dict] = []

    # 1. 基金代码
    all_warnings.extend(verify_fund_codes(ai_analysis))

    # 2. URL 引用
    if real_urls:
        all_warnings.extend(verify_cited_urls(ai_analysis, real_urls))

    # 3. 板块一致性
    if stats:
        all_warnings.extend(verify_sector_consistency(ai_analysis, stats))

    # 4. 行情数字
    if market_data or index_data:
        all_warnings.extend(verify_price_numbers(ai_analysis, market_data, index_data))

    # 5. 昨日连续性
    if yesterday_predictions:
        all_warnings.extend(verify_continuity_claims(ai_analysis, yesterday_predictions))

    # 6. 退化检测
    if old_analysis:
        deg = detect_degradation(ai_analysis, old_analysis)
        if deg:
            all_warnings.append(deg)

    if not all_warnings:
        return ""

    # 格式化输出
    errors = [w for w in all_warnings if w["severity"] == "error"]
    warns = [w for w in all_warnings if w["severity"] == "warning"]
    infos = [w for w in all_warnings if w["severity"] == "info"]

    lines = [
        "",
        "---",
        "",
        "## ⚠️ 验证警告（自动检测，供人工复核）",
        "",
        f"本次共检测到 **{len(all_warnings)}** 条疑似问题："
        f" {len(errors)} 条错误 · {len(warns)} 条警告 · {len(infos)} 条提示",
        "",
    ]

    if errors:
        lines.append("### 🔴 错误（高度疑似杜撰）")
        for w in errors:
            lines.append(f"- {w['message']}")
        lines.append("")

    if warns:
        lines.append("### 🟡 警告（需要人工复核）")
        for w in warns:
            lines.append(f"- {w['message']}")
        lines.append("")

    if infos:
        lines.append("### 🔵 提示")
        for w in infos:
            lines.append(f"- {w['message']}")
        lines.append("")

    lines.append("*以上警告由自动化校验生成，不保证 100% 准确，请结合原文判断。*")

    return "\n".join(lines)
