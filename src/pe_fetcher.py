"""PE 估值自动抓取模块。

数据来源：
1. 东方财富估值中心页面（Playwright）→ PE + 分位（多数指数）
2. 东方财富 push2 API → 仅记录相对趋势到历史（f115 字段对指数的绝对值不可靠）
3. pe_data.json 手动维护 → 券商研报/权威来源（优先使用）

同时记录每日 PE 历史到 pe_history.json，积累足够数据后自动计算分位。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, Optional

import httpx
import asyncio

logger = __import__("logging").getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(__file__))
PE_DATA_PATH = os.path.join(ROOT, "pe_data.json")
PE_HISTORY_PATH = os.path.join(ROOT, "data", "pe_history.json")

# ── 指数映射（东方财富 secid → 中文名） ─────────────────────

# 大盘指数（f115 有 PE 数据）
# 注意：东方财富 f115 字段对指数的返回值与常用 PE(TTM) 可能不一致，
# 此处作为参考值自动记录，人工维护的权威值优先
BROAD_INDICES: Dict[str, str] = {
    "1.000300": "沪深300",
    "1.000905": "中证500",
    "0.399006": "创业板指",
    "1.000688": "科创50",
}

# 行业/主题指数（部分有 f115 PE 数据）
SECTOR_INDICES: Dict[str, str] = {
    "1.000016": "上证50",
    "0.399986": "中证银行",
    "0.399975": "中证证券",
    "0.399967": "中证军工",
    "1.000932": "中证消费",
    "1.000933": "中证医药",
    "0.399808": "中证新能源",
    "1.990001": "半导体",
    "1.000819": "有色金属",
    "0.399393": "房地产",
    "0.399976": "CS新能车",
    "0.399995": "中证基建",
    "0.399970": "中证环保",
    "1.000929": "中证旅游",
}

# ── PE 历史管理 ──────────────────────────────────────────────


def load_pe_history() -> dict:
    """加载 PE 历史记录。"""
    if os.path.exists(PE_HISTORY_PATH):
        try:
            with open(PE_HISTORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"indices": {}, "dates": []}


def save_pe_history(history: dict) -> None:
    """原子写入 PE 历史记录。"""
    os.makedirs(os.path.dirname(PE_HISTORY_PATH), exist_ok=True)
    tmp = PE_HISTORY_PATH + ".tmp"
    history["updated"] = datetime.now().isoformat()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PE_HISTORY_PATH)


def compute_percentile(values: list[float], current: float) -> float | None:
    """计算当前值在历史序列中的分位 (0-100)。

    分位 = (低于当前值的数据点数 / 总数据点数) × 100
    值越低说明当前越便宜，<10 为极度低估，>90 为极度高估。

    至少需要 30 个数据点才返回有效分位（约 1 个月交易日）。
    """
    if len(values) < 30:
        return None
    below = sum(1 for v in values if v < current)
    return round(below / len(values) * 100, 1)


def record_pe_to_history(name: str, pe: float) -> None:
    """将当日 PE 值追加到历史记录中。

    同一日期重复调用时覆盖当天的值（幂等）。
    """
    today = datetime.now().strftime("%Y-%m-%d")

    history = load_pe_history()
    indices = history.setdefault("indices", {})

    if name not in indices:
        indices[name] = {}

    # 记录或覆盖今天的值
    indices[name][today] = round(pe, 2)

    # 维护 dates 列表
    dates_set = set(history.get("dates", []))
    dates_set.add(today)
    history["dates"] = sorted(dates_set)

    # 清理超过 5 年的数据（约 1260 个交易日）
    for idx_name in indices:
        sorted_dates = sorted(indices[idx_name].keys())
        if len(sorted_dates) > 1300:
            for old_date in sorted_dates[:-1300]:
                del indices[idx_name][old_date]

    save_pe_history(history)


def get_percentile_from_history(name: str, current_pe: float) -> float | None:
    """从历史数据计算当前 PE 的分位。"""
    history = load_pe_history()
    idx_data = history.get("indices", {}).get(name, {})
    if not idx_data:
        return None

    values = list(idx_data.values())
    return compute_percentile(values, current_pe)


# ── 东方财富 API ─────────────────────────────────────────────


async def fetch_eastmoney_pe(secid: str) -> Optional[Dict]:
    """从东方财富 JSON API 获取指数行情。

    Returns:
        {"price": 4931, "pe": 14.4, "name": "沪深300"} or None
    """
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}&fields=f43,f57,f58,f115,f116,f170"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"Referer": "https://quote.eastmoney.com"})
            data = resp.json().get("data")
            if not data:
                return None
            pe_val = data.get("f115")
            if pe_val is None or pe_val == 0 or pe_val == "-" or float(pe_val) <= 0:
                return None
            price = data.get("f43", 0)
            return {
                "price": price / 100 if price else 0,
                "pe": float(pe_val),
                "name": data.get("f58", ""),
            }
    except Exception:
        return None


async def update_pe_data():
    """主入口：从东方财富刷新 PE，记录历史，自动计算分位。

    - 大盘指数：自动更新 PE 值 + 历史记录 + 分位计算
    - 行业指数：自动获取 PE + 历史记录 + 分位计算（首次创建时）
    - 已有手动分位/level 的指数：保留手动数据，仅更新 PE 历史
    """
    print("📊 更新 PE 估值数据...")

    # 加载现有 PE 数据
    try:
        with open(PE_DATA_PATH, "r", encoding="utf-8") as f:
            pe_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pe_data = {"updated": "", "indices": {}, "note": "", "source": ""}

    pe_data.setdefault("indices", {})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 合并所有指数（大盘优先）
    all_indices = {**BROAD_INDICES, **SECTOR_INDICES}
    fetched = 0
    history_count = 0
    percentile_updated = 0

    for secid, name in all_indices.items():
        try:
            data = await fetch_eastmoney_pe(secid)
            if not data:
                continue

            pe_val = round(data["pe"], 2)

            # 记录到 PE 历史
            record_pe_to_history(name, pe_val)
            history_count += 1

            # 从历史计算分位
            history_pct = get_percentile_from_history(name, pe_val)

            if name in pe_data["indices"]:
                entry = pe_data["indices"][name]

                # 已有手动维护数据（有分位/level）→ 保留手动值，仅更新历史
                if entry.get("pe_pct") is not None or entry.get("level") is not None:
                    # 对比自动 PE 与手动 PE，差距过大时打印提示
                    manual_pe = entry.get("pe")
                    if manual_pe and abs(manual_pe - pe_val) / manual_pe > 0.3:
                        print(f"  ⚠ {name}: API PE={pe_val} vs 手动 PE={manual_pe}，差异>30%，保留手动值")
                    # 仅更新自动PE字段作为参考
                    entry["pe_auto"] = pe_val
                    entry["updated"] = now_str
                    if history_pct is not None:
                        entry["pe_pct_auto"] = history_pct
                        print(f"  {name}: 手动PE={entry.get('pe')} 自动PE={pe_val} "
                              f"历史数据{len(load_pe_history()['indices'].get(name,{}))}天 自动分位={history_pct}%")
                    continue

                # 无手动数据 → 自动更新
                entry["pe"] = pe_val
                entry["updated"] = now_str
                if history_pct is not None:
                    entry["pe_pct_auto"] = history_pct
                    entry["pe_pct"] = history_pct
                    percentile_updated += 1
            else:
                # 新指数：全部自动创建
                pe_data["indices"][name] = {
                    "pe": pe_val,
                    "pe_pct": history_pct,
                    "pe_pct_auto": history_pct,
                    "level": None,
                    "sources": ["东方财富(自动)"],
                    "updated": now_str,
                }
                if history_pct is not None:
                    percentile_updated += 1

            fetched += 1
            pct_info = f" 分位={history_pct}%" if history_pct else ""
            print(f"  {name}: PE={pe_val}{pct_info}")

        except Exception as e:
            logger.debug("东方财富 %s 抓取跳过: %s", name, e)

    pe_data["updated"] = now_str
    pe_data["source"] = "eastmoney.com API 自动获取 + 历史分位自动计算"

    pe_data["note"] = (
        "所有PE数据由东方财富API自动抓取。"
        "注意：API返回的f115字段对指数PE不准确（可能偏低），"
        "仅作相对趋势参考，不作为绝对估值判断依据。"
        "分位基于自积累历史数据计算，至少需30个交易日。"
    )

    # 原子写入
    os.makedirs(os.path.dirname(PE_DATA_PATH), exist_ok=True)
    tmp_path = PE_DATA_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(pe_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, PE_DATA_PATH)

    print(f"✅ PE 数据已更新：{fetched} 个指数自动获取"
          f"（{history_count} 个记录历史，{percentile_updated} 个自动计算分位）"
          f" → {PE_DATA_PATH}")


def show_pe_summary():
    """终端展示 PE 估值概览（供手动查阅用）。"""
    try:
        with open(PE_DATA_PATH, "r", encoding="utf-8") as f:
            pe_data = json.load(f)
    except Exception:
        print("PE 数据文件不存在或损坏")
        return

    history = load_pe_history()

    print(f"\n📊 PE 估值概览（{pe_data.get('updated', '?')}）")
    print(f"{'指数':<12} {'PE':>6} {'分位':>8} {'估值':>8} {'历史天数':>8}")
    print("-" * 50)

    for name, d in sorted(pe_data.get("indices", {}).items()):
        pe = d.get("pe", "—")
        pct = d.get("pe_pct") or d.get("pe_pct_auto")
        pct_str = f"{pct}%" if pct is not None else "—"
        level = d.get("level") or "—"
        hist_days = len(history.get("indices", {}).get(name, {}))
        print(f"{name:<12} {str(pe):>6} {pct_str:>8} {level:>8} {hist_days:>8}")

    print(f"\n数据来源: {pe_data.get('source', '?')}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--show":
        show_pe_summary()
    else:
        asyncio.run(update_pe_data())
