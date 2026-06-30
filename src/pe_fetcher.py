"""PE 估值自动抓取模块。

数据来源（双轨制）：
1. AKShare / 乐股网 (legulegu.com) → 高精度 PE(TTM) + 多年历史 → 即时分位
   支持：上证50、沪深300、中证500、中证1000、创业板50
2. 东方财富 push2 API (f115) → 近似 PE，仅作趋势参考
   支持：创业板指、科创50、各行业指数

分位规则：
- 乐股网指数：从全量历史数据直接计算（rank pct），数据可追溯 10+ 年
- 东方财富指数：从自积累 pe_history.json 计算，至少需要 30 个交易日
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, Optional, List

import asyncio
import httpx

logger = __import__("logging").getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(__file__))
PE_DATA_PATH = os.path.join(ROOT, "pe_data.json")
PE_HISTORY_PATH = os.path.join(ROOT, "data", "pe_history.json")

# ═══════════════════════════════════════════════════════════════
# 数据源一：乐股网 / AKShare（高精度 PE + 历史分位）
# ═══════════════════════════════════════════════════════════════

# 乐股网支持的指数（index_code → 中文名）
LEGU_INDICES: Dict[str, str] = {
    "000016.SH": "上证50",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "399673.SZ": "创业板50",
}

# ═══════════════════════════════════════════════════════════════
# 数据源二：东方财富 push2 API（近似 PE，行业指数兜底）
# ═══════════════════════════════════════════════════════════════

# 注意：这些指数在乐股网上没有独立 PE 页面，用东方财富 f115 兜底
# f115 对指数的 PE 绝对值不准确，仅作相对趋势参考
BROAD_FALLBACK: Dict[str, str] = {
    "0.399006": "创业板指",
    "1.000688": "科创50",
}

SECTOR_INDICES: Dict[str, str] = {
    "1.000016": "上证50",       # 注意：乐股网已覆盖，此处仅兜底
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

# ═══════════════════════════════════════════════════════════════
# PE 历史管理（东方财富数据积累用）
# ═══════════════════════════════════════════════════════════════


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


def compute_percentile(values: List[float], current: float) -> float | None:
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
    """将当日 PE 值追加到历史记录中（幂等）。"""
    today = datetime.now().strftime("%Y-%m-%d")

    history = load_pe_history()
    indices = history.setdefault("indices", {})

    if name not in indices:
        indices[name] = {}

    indices[name][today] = round(pe, 2)

    dates_set = set(history.get("dates", []))
    dates_set.add(today)
    history["dates"] = sorted(dates_set)

    # 清理超过 5 年的数据（约 1300 个交易日）
    for idx_name in indices:
        sorted_dates = sorted(indices[idx_name].keys())
        if len(sorted_dates) > 1300:
            for old_date in sorted_dates[:-1300]:
                del indices[idx_name][old_date]

    save_pe_history(history)


def get_percentile_from_history(name: str, current_pe: float) -> float | None:
    """从自积累历史数据计算当前 PE 的分位。"""
    history = load_pe_history()
    idx_data = history.get("indices", {}).get(name, {})
    if not idx_data:
        return None

    values = list(idx_data.values())
    return compute_percentile(values, current_pe)


# ═══════════════════════════════════════════════════════════════
# 东方财富 API（行业指数兜底）
# ═══════════════════════════════════════════════════════════════


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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            resp = await client.get(url, headers={"Referer": "https://quote.eastmoney.com"})
            data = resp.json().get("data")
            if not data:
                return None
            pe_val = data.get("f115")
            if pe_val is None or pe_val == 0 or pe_val == "-":
                return None
            pe_float = float(pe_val)
            # f115 字段对部分行业指数会返回异常低值（如 1.0/2.0），
            # 真实指数 PE(TTM) 几乎不可能低于 3，过滤掉
            if pe_float < 3.0:
                logger.debug("东方财富 %s PE=%.1f 异常偏低，已忽略", secid, pe_float)
                return None
            price = data.get("f43", 0)
            return {
                "price": price / 100 if price else 0,
                "pe": pe_float,
                "name": data.get("f58", ""),
            }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# 乐股网 / AKShare API（高精度 PE）
# ═══════════════════════════════════════════════════════════════


def fetch_legu_pe_history(index_code: str, max_retries: int = 3) -> Optional[Dict]:
    """从乐股网获取指数完整 PE 历史 + 最新值。

    通过 AKShare 的 stock_index_pe_lg 接口，返回包含多年历史数据的
    DataFrame，包含：日期、收盘价、滚动市盈率(TTM)、静态市盈率 等。

    注意：AKShare/乐股网需要代理，本函数临时设置 HTTP_PROXY，
    完成后恢复，不影响其他模块（httpx 直连）。

    Args:
        index_code: 乐股网指数代码，如 "000300.SH"
        max_retries: 最大重试次数（网络偶发 IncompleteRead）

    Returns:
        {
            "current_pe": 13.76,          # 最新 PE(TTM)
            "current_static_pe": 14.01,   # 最新静态 PE
            "pe_series": [12.5, 13.1, ...], # 历史 PE(TTM) 序列
            "dates": [...],                 # 历史日期序列
            "days": 5155,                   # 历史数据天数
            "percentile": 45.2,            # 当前分位 (0-100)
        }
        or None on failure
    """
    import time

    # 乐股网需要代理，临时设置（AKShare 底层用 requests 库，读的是环境变量）
    _saved_http = os.environ.get("HTTP_PROXY")
    _saved_https = os.environ.get("HTTPS_PROXY")
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7897"
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"

    try:
        for attempt in range(1, max_retries + 1):
            try:
                import akshare as ak
                import pandas as pd

                # 用中文名调用（AKShare 内部映射到 index_code）
                name = None
                for code, cname in LEGU_INDICES.items():
                    if code == index_code:
                        name = cname
                        break
                if not name:
                    return None

                df = ak.stock_index_pe_lg(symbol=name)
                if df is None or df.empty:
                    return None

                # 列名：日期, 指数, 等权静态市盈率, 静态市盈率, 静态市盈率中位数,
                #       等权滚动市盈率, 滚动市盈率, 滚动市盈率中位数
                ttm_col = "滚动市盈率"
                static_col = "静态市盈率"

                if ttm_col not in df.columns:
                    return None

                # 去掉 NaN
                df_clean = df.dropna(subset=[ttm_col])

                if df_clean.empty:
                    return None

                last = df_clean.iloc[-1]
                current_pe = float(last[ttm_col])
                current_static_pe = float(last[static_col]) if static_col in df_clean.columns else None

                pe_series = df_clean[ttm_col].astype(float).tolist()
                dates = df_clean["日期"].astype(str).tolist() if "日期" in df_clean.columns else []

                # 直接从全量历史计算分位
                below = sum(1 for v in pe_series if v < current_pe)
                percentile = round(below / len(pe_series) * 100, 1)

                return {
                    "current_pe": round(current_pe, 2),
                    "current_static_pe": round(current_static_pe, 2) if current_static_pe else None,
                    "pe_series": pe_series,
                    "dates": dates,
                    "days": len(pe_series),
                    "percentile": percentile,
                }

            except ImportError:
                logger.warning("AKShare 未安装，无法使用乐股网数据")
                return None
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(2 * attempt)  # 递增等待：2s, 4s
                    continue
                logger.debug("乐股网 %s 获取失败（%d次重试后）: %s", index_code, max_retries, e)
                return None

        return None

    finally:
        # 恢复环境变量，避免影响其他模块的直连请求
        if _saved_http is not None:
            os.environ["HTTP_PROXY"] = _saved_http
        else:
            os.environ.pop("HTTP_PROXY", None)
        if _saved_https is not None:
            os.environ["HTTPS_PROXY"] = _saved_https
        else:
            os.environ.pop("HTTPS_PROXY", None)


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════


def _get_level(pct: float | None) -> str | None:
    """根据分位返回估值水平标签。"""
    if pct is None:
        return None
    if pct < 10:
        return "极度低估"
    elif pct < 30:
        return "低估"
    elif pct < 70:
        return "正常"
    elif pct < 90:
        return "高估"
    else:
        return "极度高估"


async def update_pe_data():
    """主入口：从乐股网 + 东方财富刷新 PE 估值数据。

    - 乐股网指数（5 个）：高精度 PE(TTM) + 全量历史分位
    - 东方财富指数（行业等）：f115 近似 PE + 自积累分位（≥30 天）
    """
    # 确保东方财富 API 不走代理（代理会导致 302 空响应）
    no_proxy = os.environ.get("NO_PROXY", "")
    em_domains = "push2.eastmoney.com,eastmoney.com"
    if not no_proxy:
        os.environ["NO_PROXY"] = em_domains
    elif "push2.eastmoney.com" not in no_proxy:
        os.environ["NO_PROXY"] = f"{no_proxy},{em_domains}"

    print("📊 更新 PE 估值数据...")

    # 加载现有 PE 数据
    try:
        with open(PE_DATA_PATH, "r", encoding="utf-8") as f:
            pe_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pe_data = {"updated": "", "indices": {}, "note": "", "source": ""}

    pe_data.setdefault("indices", {})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    fetched_legu = 0
    fetched_em = 0
    failed_legu = []

    # ── 第一阶段：乐股网高精度指数 ──
    for index_code, name in LEGU_INDICES.items():
        try:
            result = await asyncio.to_thread(fetch_legu_pe_history, index_code)
            if not result:
                failed_legu.append(name)
                continue

            pe_val = result["current_pe"]
            pct = result["percentile"]
            days = result["days"]
            level = _get_level(pct)

            # 也记录到历史文件（供预测追踪表使用）
            record_pe_to_history(name, pe_val)

            if name in pe_data["indices"]:
                entry = pe_data["indices"][name]
                # 保留旧的 sources，追加乐股网
                sources = entry.get("sources", [])
                if "乐股网(准确)" not in sources:
                    sources.insert(0, "乐股网(准确)")
                # 清理旧标签：乐股网已覆盖的指数，移除东方财富自动标签
                sources = [s for s in sources if not (s.startswith("东方财富") and "自动" in s)]
                if not any("东方财富" in s for s in sources):
                    pass  # 乐股网已覆盖，不需要东方财富

                entry.update({
                    "pe": pe_val,
                    "pe_pct": pct,
                    "pe_pct_auto": pct,
                    "level": level,
                    "sources": sources,
                    "updated": now_str,
                })
            else:
                pe_data["indices"][name] = {
                    "pe": pe_val,
                    "pe_pct": pct,
                    "pe_pct_auto": pct,
                    "level": level,
                    "sources": ["乐股网(准确)"],
                    "updated": now_str,
                }

            fetched_legu += 1
            print(f"  ✅ {name}: PE(TTM)={pe_val} 分位={pct}% [{level}] (历史{days}天)")

        except Exception as e:
            logger.debug("乐股网 %s 抓取异常: %s", name, e)
            failed_legu.append(name)

    # 乐股网失败的指数，自动通过 em_indices 回退到东方财富
    if failed_legu:
        print(f"  ⚠ 乐股网失败 {len(failed_legu)} 个: {failed_legu}，回退东方财富")

    # ── 第二阶段：东方财富兜底（创业板指、科创50、行业指数）──
    # 跳过乐股网已覆盖的
    legu_names = set(LEGU_INDICES.values())
    all_em = {**BROAD_FALLBACK, **SECTOR_INDICES}
    # 去重：乐股网已覆盖的指数不再用东方财富获取（除非乐股网失败）
    em_indices = {}
    for secid, name in all_em.items():
        if name in legu_names and name not in failed_legu:
            continue  # 乐股网已成功覆盖
        em_indices[secid] = name

    history_count = 0
    percentile_updated = 0

    for secid, name in em_indices.items():
        try:
            data = await fetch_eastmoney_pe(secid)
            if not data:
                continue

            pe_val = round(data["pe"], 2)
            source_label = "东方财富(自动)"

            # 记录到 PE 历史
            record_pe_to_history(name, pe_val)
            history_count += 1

            # 从历史计算分位
            history_pct = get_percentile_from_history(name, pe_val)

            if name in pe_data["indices"]:
                entry = pe_data["indices"][name]

                # 已有手动维护数据 → 保留手动值
                if entry.get("pe_pct") is not None and entry.get("sources") and \
                   any("手动" in s or "券商" in s for s in entry.get("sources", [])):
                    # 仅更新自动PE作为参考
                    entry["pe_auto"] = pe_val
                    entry["updated"] = now_str
                    if history_pct is not None:
                        entry["pe_pct_auto"] = history_pct
                    continue

                # 已有乐股网数据 → 保留（仅记录历史）
                if any("乐股网" in s for s in entry.get("sources", [])):
                    entry["pe_auto"] = pe_val
                    entry["updated"] = now_str
                    if history_pct is not None:
                        entry["pe_pct_auto"] = history_pct
                    continue

                # 纯自动更新
                entry["pe"] = pe_val
                entry["updated"] = now_str
                sources = entry.get("sources", [])
                if source_label not in sources:
                    sources.append(source_label)
                entry["sources"] = sources
                if history_pct is not None:
                    entry["pe_pct_auto"] = history_pct
                    entry["pe_pct"] = history_pct
                    entry["level"] = _get_level(history_pct)
                    percentile_updated += 1
            else:
                # 新指数
                pe_data["indices"][name] = {
                    "pe": pe_val,
                    "pe_pct": history_pct,
                    "pe_pct_auto": history_pct,
                    "level": _get_level(history_pct) if history_pct else None,
                    "sources": [source_label],
                    "updated": now_str,
                }
                if history_pct is not None:
                    percentile_updated += 1

            fetched_em += 1
            pct_info = f" 分位={history_pct}%" if history_pct else " (积累中)"
            print(f"  {name}: PE≈{pe_val}{pct_info}  [{source_label}]")

        except Exception as e:
            logger.debug("东方财富 %s 抓取跳过: %s", name, e)

    # ── 写入 pe_data.json ──
    pe_data["updated"] = now_str
    pe_data["source"] = "乐股网(准确PE+即时分位) + 东方财富API(行业指数趋势参考)"

    pe_data["note"] = (
        "双数据源："
        "① 乐股网 — 上证50/沪深300/中证500/中证1000/创业板50，PE(TTM)准确，"
        "分位从10+年历史即时计算；"
        "② 东方财富f115 — 行业指数PE为近似值（可能偏低），仅作趋势参考，"
        "分位需自积累30个交易日。"
    )

    os.makedirs(os.path.dirname(PE_DATA_PATH), exist_ok=True)
    tmp_path = PE_DATA_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(pe_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, PE_DATA_PATH)

    total = fetched_legu + fetched_em
    legu_info = f"{fetched_legu} 个乐股网(准确PE+即时分位)" if fetched_legu else ""
    em_info = f"{fetched_em} 个东方财富(近似PE)" if fetched_em else ""
    parts = [p for p in [legu_info, em_info] if p]
    detail = " + ".join(parts)

    print(f"✅ PE 数据已更新：{total} 个指数（{detail}）"
          f"（{history_count} 个记录历史，{percentile_updated} 个自动计算分位）"
          f" → {PE_DATA_PATH}")


def show_pe_summary():
    """终端展示 PE 估值概览。"""
    try:
        with open(PE_DATA_PATH, "r", encoding="utf-8") as f:
            pe_data = json.load(f)
    except Exception:
        print("PE 数据文件不存在或损坏")
        return

    history = load_pe_history()

    print(f"\n📊 PE 估值概览（{pe_data.get('updated', '?')}）")
    print(f"{'指数':<10} {'PE':>6} {'分位':>8} {'估值':>10} {'来源':<20} {'历史':>6}")
    print("-" * 70)

    for name, d in sorted(pe_data.get("indices", {}).items()):
        pe = d.get("pe", "—")
        pct = d.get("pe_pct") or d.get("pe_pct_auto")
        pct_str = f"{pct}%" if pct is not None else "—"
        level = d.get("level") or "—"
        sources = d.get("sources", [])
        source_str = sources[0] if sources else "—"
        hist_days = len(history.get("indices", {}).get(name, {}))
        print(f"{name:<10} {str(pe):>6} {pct_str:>8} {level:>10} {source_str:<20} {hist_days:>6}")

    print(f"\n数据来源: {pe_data.get('source', '?')}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--show":
        show_pe_summary()
    else:
        asyncio.run(update_pe_data())
