"""实时行情数据模块。

从新浪财经免费接口抓取黄金、美元指数、外汇汇率等数据。
美债收益率从 FRED (美联储经济数据库) 免费获取。
数据缓存到本地 JSON 文件，保留 90 天历史。
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "market_history.json")

# 新浪财经行情接口（免费，无需认证）
SINA_QUOTES = {
    "comex_gold": "hf_GC",        # COMEX 黄金期货（主力合约）
    "usd_index": "DINIW",         # 美元指数（DXY）
    "usd_cny": "fx_susdcny",      # 美元/离岸人民币 汇率
}

# FRED 美债收益率 & 通胀预期（免费 CSV，无需 API key）
FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
FRED_SERIES = {
    "us_10y": "DGS10",      # 美国 10 年期国债收益率
    "breakeven": "T10YIE",  # 10 年期盈亏平衡通胀率（市场隐含通胀预期）
}

# 板块指数（新浪股票接口）
SECTOR_INDICES = {
    "沪深300": "s_sh000300",
    "中证500": "s_sh000905",
    "创业板指": "s_sz399006",
    "科创50": "s_sh000688",
    "中证银行": "s_sh399986",
    "中证证券": "s_sh399975",
    "中证军工": "s_sz399967",
    "中证消费": "s_sh000932",
    "中证医药": "s_sh000933",
    "中证新能源": "s_sh399808",
    "半导体": "s_sh990001",
    "有色金属": "s_sh000819",
    "房地产": "s_sh399393",
    "CS新能车": "s_sz399976",
    "中证基建": "s_sz399995",
    "中证环保": "s_sz399970",
    "数字经济": "sh560800",
    "机器人": "sh562500",
    "光伏": "sh515790",
    "建材": "sh516750",
    "电力": "sh561560",
}

SINA_URL = "http://hq.sinajs.cn/list="


async def fetch_quote(code: str) -> Optional[Dict]:
    """抓取单个品种行情。

    Returns:
        dict with name, price, change, change_pct, high, low, open, prev_close
    """
    url = SINA_URL + code
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn",
    }
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            text = resp.text
            if "var hq_str_" not in text:
                return None
            # 解析 var hq_str_XXX="数据";
            data = text.split('"')[1] if '"' in text else ""
            if not data:
                return None
            parts = data.split(",")
            if len(parts) < 4:
                return None

            # 新浪期货格式 (hf_): 现价,,开盘,最高,最低,,时间,昨收,买价,卖价,持仓,日增,日期,名称,...
            if code.startswith("hf_"):
                price = float(parts[0]) if parts[0] else 0
                prev_close = float(parts[7]) if len(parts) > 7 and parts[7] else float(parts[2]) if parts[2] else 0
                change = price - prev_close if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
                return {
                    "name": parts[13] if len(parts) > 13 else parts[0],
                    "price": price,
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 4),
                    "prev_close": prev_close,
                    "open": float(parts[2]) if len(parts) > 2 and parts[2] else 0,
                    "high": float(parts[3]) if len(parts) > 3 and parts[3] else 0,
                    "low": float(parts[4]) if len(parts) > 4 and parts[4] else 0,
                }

            # 新浪外汇格式 (fx_): 时间,现价,昨收,今开,成交量,卖价,买价,最低,最高,名称,?,?,?,...
            if code.startswith("fx_"):
                price = float(parts[1]) if parts[1] else 0
                prev_close = float(parts[2]) if len(parts) > 2 and parts[2] else 0
                # parts[10]/[11] 含义不稳定（有时是点数而非百分比），直接从价格计算
                change = price - prev_close if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
                return {
                    "name": parts[9] if len(parts) > 9 else "",
                    "price": price,
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 4),
                    "prev_close": prev_close,
                    "high": float(parts[8]) if len(parts) > 8 and parts[8] else 0,
                    "low": float(parts[7]) if len(parts) > 7 and parts[7] else 0,
                    "open": float(parts[3]) if len(parts) > 3 and parts[3] else 0,
                }

            # DINIW 美元指数 (全球指数格式): 时间,现价,?,今开,成交量,买价,最高,最低,卖价,名称,日期
            # fields: [0]=time, [1]=price, [2]=?, [3]=open, [4]=vol, [5]=buy,
            #          [6]=high, [7]=low, [8]=sell, [9]=name, [10]=date
            # 注：DINIW 无昨收字段，change 为日内涨跌（相对今开），非日间涨跌
            if code == "DINIW":
                price = float(parts[1]) if parts[1] else 0
                open_p = float(parts[3]) if len(parts) > 3 and parts[3] else 0
                high_p = float(parts[6]) if len(parts) > 6 and parts[6] else 0
                low_p = float(parts[7]) if len(parts) > 7 and parts[7] else 0
                change = price - open_p if open_p else 0
                change_pct = (change / open_p * 100) if open_p else 0
                return {
                    "name": parts[9] if len(parts) > 9 else "美元指数",
                    "price": price,
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 2),
                    "prev_close": open_p,  # 无真正昨收，用今开作为参考基点（change=日内涨跌）
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                }

            return None
    except Exception as e:
        logger.warning("行情抓取失败 %s: %s", code, e)
        return None


def load_history() -> Dict:
    """加载本地缓存的历史数据。"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"records": []}


def save_history(data: Dict):
    """原子写入历史数据到本地缓存。"""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp_path = CACHE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CACHE_FILE)


def cleanup_old_records(data: Dict, max_days: int = 90):
    """清理超过 max_days 天的旧记录。"""
    cutoff = (datetime.now() - timedelta(days=max_days)).isoformat()
    data["records"] = [r for r in data.get("records", []) if r.get("timestamp", "") >= cutoff]


async def _fetch_fred_latest(series_id: str) -> Optional[Dict]:
    """从 FRED 获取指定时间序列的最新值。

    FRED 为美联储官方经济数据库，免费、无需 API key，CSV 格式。
    返回整个历史 CSV，解析后取最后一行的有效数据。

    Returns:
        {"date": "2026-06-26", "value": 4.38} or None
    """
    url = FRED_BASE + series_id
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv"}
    try:
        async with httpx.AsyncClient(timeout=25, trust_env=False) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            reader = csv.reader(io.StringIO(resp.text))
            rows = list(reader)
            if len(rows) < 2:
                return None
            for row in reversed(rows):
                if len(row) >= 2 and row[1].strip():
                    try:
                        return {"date": row[0], "value": float(row[1])}
                    except ValueError:
                        continue
            return None
    except Exception as e:
        logger.warning("FRED %s 抓取失败: %s", series_id, e)
        return None


async def fetch_us_macro() -> Dict[str, Optional[Dict]]:
    """从 FRED 并发获取美国宏观数据（国债收益率 + 通胀预期）。"""
    results = {}
    tasks = [
        _fetch_fred_latest(series_id)
        for series_id in FRED_SERIES.values()
    ]
    values = await asyncio.gather(*tasks, return_exceptions=True)
    for label, val in zip(FRED_SERIES.keys(), values):
        results[label] = val if not isinstance(val, Exception) else None
    return results


async def get_market_snapshot() -> Dict:
    """获取当前市场快照 + 计算涨跌幅。"""
    result = {"timestamp": datetime.now().isoformat(), "quotes": {}}

    for name, code in SINA_QUOTES.items():
        q = await fetch_quote(code)
        if q:
            # 优先使用 fetch_quote 返回的 pre-computed change（避免精度丢失）
            change = q.get("change", 0)
            change_pct = q.get("change_pct", 0)
            if change == 0 and q["prev_close"]:
                change = q["price"] - q["prev_close"]
                change_pct = (change / q["prev_close"] * 100) if q["prev_close"] else 0
            result["quotes"][name] = {
                "price": q["price"],
                "change": round(change, 4),      # 保留 4 位，适应汇率等小数品
                "change_pct": round(change_pct, 4),
                "prev_close": q["prev_close"],
                "high": q["high"],
                "low": q["low"],
            }

    # 获取美国宏观数据（FRED：国债收益率 + 通胀预期）
    us_macro = await fetch_us_macro()
    for label, data in us_macro.items():
        if data:
            result[label] = data

    # 加载历史 + 追加当前快照
    history = load_history()
    history["records"].append(result)
    cleanup_old_records(history)
    save_history(history)

    return result


async def fetch_index_quote(code: str) -> Optional[Dict]:
    """抓取单只指数/ETF行情。支持指数(s_前缀)和ETF(sh/sz前缀)两种格式。"""
    url = SINA_URL + code
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            text = resp.text
            data = text.split('"')[1] if '"' in text else ""
            if not data:
                return None
            parts = data.split(",")
            if len(parts) < 4:
                return None

            if code.startswith("s_"):
                # 指数格式: 名称,现价,涨跌额,涨跌幅,成交量,成交额
                price = float(parts[1]) if parts[1] else 0
                change = float(parts[2]) if parts[2] else 0
                return {
                    "name": parts[0],
                    "price": price,
                    "change": change,
                    "change_pct": float(parts[3]) if parts[3] and float(parts[3]) != 0 else (change / (price - change) * 100 if (price - change) != 0 else 0),
                    "prev_close": round(price - change, 2),
                }
            else:
                # ETF/股票格式: 名称,今开,昨收,现价,最高,最低,...
                price = float(parts[3]) if parts[3] else 0
                prev_close = float(parts[2]) if parts[2] else 0
                # 未开盘时 price=0，用昨收
                if price == 0 and prev_close > 0:
                    price = prev_close
                change = price - prev_close if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
                return {
                    "name": parts[0],
                    "price": price,
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 2),
                    "prev_close": prev_close,
                }
    except Exception as e:
        logger.warning("指数抓取失败 %s: %s", code, e)
        return None


async def get_index_snapshot() -> Dict:
    """抓取所有板块指数快照。"""
    result = {}

    for name, code in SECTOR_INDICES.items():
        q = await fetch_index_quote(code)
        if q and q["price"] > 0:
            result[name] = {
                "price": q["price"],
                "change": q.get("change", 0),
                "change_pct": q.get("change_pct", 0),
            }
    return result


def format_index_for_ai(indices: Dict) -> str:
    """格式化指数行情为 AI 可读文本。区分指数点位和ETF价格。"""
    if not indices:
        return ""
    lines = ["## 📊 板块指数实时行情"]
    lines.append("（⚠️ ETF类显示基金净值，非指数点位。引用时写数字+单位）")

    index_names = ["沪深300", "中证500", "创业板指", "科创50", "中证银行", "中证证券",
                   "中证军工", "中证消费", "中证医药", "中证新能源", "半导体",
                   "有色金属", "房地产", "CS新能车", "中证基建", "中证环保"]
    for name in index_names:
        q = indices.get(name)
        if q:
            arrow = "↑" if q["change"] >= 0 else "↓"
            lines.append(f"- {name}：{q['price']:.2f} 点 ({arrow}{q['change_pct']:+.1f}%)")

    etf_present = [n for n in ["数字经济", "机器人", "光伏", "建材", "电力"] if n in indices]
    if etf_present:
        lines.append("")
        for name in etf_present:
            q = indices[name]
            arrow = "↑" if q["change"] >= 0 else "↓"
            lines.append(f"- {name}ETF：¥{q['price']:.3f} ({arrow}{q['change_pct']:+.1f}%)")
    return "\n".join(lines)


def load_pe_data() -> Optional[Dict]:
    """加载 PE 估值数据。"""
    import json as _json
    pe_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pe_data.json")
    try:
        with open(pe_path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return None


def format_pe_for_ai() -> str:
    """格式化 PE 估值数据为 AI 可读文本。"""
    pe = load_pe_data()
    if not pe:
        return ""
    lines = [
        f"\n## 📊 指数PE估值参考（{pe.get('updated', '?')}，{pe.get('source', '?')}）",
        f"⚠️ {pe.get('note', '')}",
        "",
        "| 指数 | PE | PB | 分位 | 估值 | 数据源",
        "|------|----|----|------|------|------|",
    ]
    for name, d in pe.get("indices", {}).items():
        pe_val = d.get('pe', '—')
        pb_val = d.get('pb', '—')
        pct = d.get('pe_pct') or d.get('pb_pct')
        pct_str = f"{pct}%" if pct else '—'
        level = d.get('level') or '—'
        srcs = ', '.join(d.get('sources', [])[:2])
        lines.append(f"| {name} | {pe_val} | {pb_val} | {pct_str} | {level} | {srcs} |")
    return "\n".join(lines)


def format_market_for_ai(quote: Optional[Dict] = None) -> str:
    """将行情数据格式化为 AI 可读文本。

    所有数据来自实时抓取（新浪财经 + FRED），无 AI 训练知识参与。
    """
    history = load_history()
    records = history.get("records", [])

    lines = ["## 📊 实时行情数据"]

    # 最新报价
    if records:
        latest = records[-1]
        quotes = latest.get("quotes", {})
        timestamp = latest["timestamp"][:19]
        lines.append(f"数据时间：{timestamp}")
        lines.append("")

        # ── 黄金 ──
        gold = quotes.get("comex_gold")
        if gold:
            arrow = "↑" if gold["change"] >= 0 else "↓"
            lines.append(
                f"- COMEX 黄金期货：{gold['price']:.2f} 美元/盎司 "
                f"({arrow}{abs(gold['change_pct']):.1f}%)"
            )

            # 上海金估算（使用实时 USD/CNY 汇率）
            usd_cny = quotes.get("usd_cny", {}).get("price")
            if usd_cny and usd_cny > 0:
                shanghai_est = round(gold["price"] * usd_cny / 31.1035, 2)
                lines.append(
                    f"- 上海金估算价：约 {shanghai_est} 元/克"
                    f"（COMEX × 实时汇率 {usd_cny:.4f} ÷ 31.1）"
                )
            else:
                # 兜底：汇率未知时用近似值并标注
                shanghai_est = round(gold["price"] * 7.15 / 31.1035, 2)
                lines.append(
                    f"- 上海金估算价：约 {shanghai_est} 元/克"
                    f"（COMEX × 近似汇率 7.15 ÷ 31.1，实时汇率抓取失败）"
                )

        # ── 美元指数 ──
        dxy = quotes.get("usd_index")
        if dxy:
            arrow = "↑" if dxy["change"] >= 0 else "↓"
            lines.append(
                f"- 美元指数（DXY）：{dxy['price']:.4f} "
                f"({arrow}{abs(dxy['change_pct']):.2f}%)"
            )

        # ── 在岸人民币汇率 ──
        usd_cny = quotes.get("usd_cny")
        if usd_cny:
            arrow = "↑" if usd_cny["change"] >= 0 else "↓"
            lines.append(
                f"- 美元/在岸人民币：{usd_cny['price']:.4f} "
                f"({arrow}{abs(usd_cny['change_pct']):.4f}%)"
            )

        # ── 美国 10 年期国债收益率 ──
        treasury = latest.get("us_10y")
        if treasury:
            lines.append(
                f"- 美国 10 年期国债收益率：{treasury['value']:.2f}%"
                f"（{treasury['date']}，数据源：FRED）"
            )

        # ── 盈亏平衡通胀率（市场隐含通胀预期） ──
        breakeven = latest.get("breakeven")
        if breakeven:
            lines.append(
                f"- 10 年期盈亏平衡通胀率：{breakeven['value']:.2f}%"
                f"（{breakeven['date']}，TIPS 利差隐含，数据源：FRED）"
            )

    # 近3月走势概要
    if len(records) > 1:
        lines.append("")
        lines.append("## 📈 近3个月价格走势参考")

        for name, label in [("comex_gold", "COMEX黄金"), ("usd_index", "美元指数")]:
            prices = []
            for r in records:
                q = r.get("quotes", {}).get(name)
                if q:
                    prices.append((r["timestamp"][:10], q["price"]))
            if len(prices) >= 2:
                first_price = prices[0][1]
                last_price = prices[-1][1]
                change = (last_price - first_price) / first_price * 100 if first_price else 0
                high_price = max(p[1] for p in prices)
                low_price = min(p[1] for p in prices)
                lines.append(
                    f"- {label}：{prices[0][0]}~{prices[-1][0]}，"
                    f"区间 {low_price:.4f} - {high_price:.4f}，"
                    f"累计 {'+' if change >= 0 else ''}{change:.2f}%"
                )

    return "\n".join(lines)
