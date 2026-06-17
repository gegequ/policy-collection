"""实时行情数据模块。

从新浪财经免费接口抓取黄金、美元指数、美债收益率等数据。
数据缓存到本地 JSON 文件，保留 90 天历史。
"""

from __future__ import annotations

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
    "comex_gold": "hf_GC",  # COMEX 黄金期货（主力合约，可正常获取）
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
EM_URL = "http://push2.eastmoney.com/api/qt/stock/get"

# 东方财富板块指数 secid 映射（更稳定，数据更全）
EM_INDICES = {
    "沪深300": "1.000300",
    "中证500": "1.000905",
    "创业板指": "0.399006",
    "科创50": "1.000688",
    "中证银行": "0.399986",
    "中证证券": "0.399975",
    "中证军工": "0.399967",
    "中证消费": "1.000932",
    "中证医药": "1.000933",
    "中证新能源": "0.399808",
    "半导体": "1.990001",
    "有色金属": "1.000819",
    "房地产": "0.399393",
    "CS新能车": "0.399976",
    "中证基建": "0.399995",
}


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
        async with httpx.AsyncClient(timeout=10) as client:
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
            # 新浪期货格式: 现价,,开盘,最高,最低,,时间,昨收,买价,卖价,持仓,日增,日期,名称,...
            if code.startswith("hf_"):
                return {
                    "name": parts[13] if len(parts) > 13 else parts[0],
                    "price": float(parts[0]) if parts[0] else 0,
                    "prev_close": float(parts[7]) if len(parts) > 7 and parts[7] else float(parts[2]) if parts[2] else 0,
                    "open": float(parts[2]) if len(parts) > 2 and parts[2] else 0,
                    "high": float(parts[3]) if len(parts) > 3 and parts[3] else 0,
                    "low": float(parts[4]) if len(parts) > 4 and parts[4] else 0,
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
    """保存历史数据到本地缓存。"""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cleanup_old_records(data: Dict, max_days: int = 90):
    """清理超过 max_days 天的旧记录。"""
    cutoff = (datetime.now() - timedelta(days=max_days)).isoformat()
    data["records"] = [r for r in data.get("records", []) if r.get("timestamp", "") >= cutoff]


async def get_market_snapshot() -> Dict:
    """获取当前市场快照 + 计算涨跌幅。"""
    result = {"timestamp": datetime.now().isoformat(), "quotes": {}}

    for name, code in SINA_QUOTES.items():
        q = await fetch_quote(code)
        if q:
            change = q["price"] - q["prev_close"] if q["prev_close"] else 0
            change_pct = (change / q["prev_close"] * 100) if q["prev_close"] else 0
            result["quotes"][name] = {
                "price": q["price"],
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "prev_close": q["prev_close"],
                "high": q["high"],
                "low": q["low"],
            }

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
        async with httpx.AsyncClient(timeout=10) as client:
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


async def fetch_em_index(secid: str) -> Optional[Dict]:
    """从东方财富抓取指数行情。"""
    try:
        url = f"{EM_URL}?secid={secid}&fields=f43,f57,f58,f170"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers={"Referer": "https://quote.eastmoney.com"})
            data = resp.json().get("data")
            if not data:
                return None
            price = data.get("f43", 0) / 100 if data.get("f43") else 0
            prev_close = data.get("f57", 0) / 100 if data.get("f57") else 0
            change_pct = data.get("f170", 0) / 100 if data.get("f170") else 0
            if price <= 0:
                return None
            return {
                "name": data.get("f58", ""),
                "price": price,
                "change": round(price - prev_close, 2),
                "change_pct": change_pct,
                "prev_close": prev_close,
            }
    except Exception:
        return None


async def get_index_snapshot() -> Dict:
    """抓取所有板块指数快照。"""
    result = {}

    for name, code in SECTOR_INDICES.items():
        q = await fetch_index_quote(code)
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
        f"⚠️ 以下PE/分位数据来自公开数据源，{pe.get('note', '每周更新')}",
        "",
        "| 指数 | PE | 近5年分位 | 估值水平 |",
        "|------|----|----------|---------|",
    ]
    for name, d in pe.get("indices", {}).items():
        lines.append(f"| {name} | {d['pe']} | {d['pe_pct_5y']}% | {d['level']} |")
    return "\n".join(lines)


def format_market_for_ai(quote: Optional[Dict] = None) -> str:
    """将行情数据格式化为 AI 可读文本。"""
    history = load_history()
    records = history.get("records", [])

    lines = ["## 📊 实时行情数据"]

    # 最新报价
    if records:
        latest = records[-1]
        lines.append(f"数据时间：{latest['timestamp'][:19]}")
        lines.append("")
        for name, q in latest.get("quotes", {}).items():
            label_map = {"comex_gold": "COMEX黄金期货"}
            label = label_map.get(name, name)
            arrow = "↑" if q["change"] >= 0 else "↓"
            lines.append(f"- {label}：{q['price']:.2f} 美元/盎司 ({arrow}{abs(q['change_pct']):.1f}%)")
        # 估算上海金
        if "comex_gold" in latest.get("quotes", {}):
            comex = latest["quotes"]["comex_gold"]["price"]
            shanghai_est = round(comex * 7.15 / 31.1035, 2)  # 美元→人民币/克 近似
            lines.append(f"- 上海金估算价：约 {shanghai_est} 元/克（COMEX×汇率÷31.1）")

    # 近3月走势概要
    lines.append("")
    lines.append("## 📈 近3个月价格走势参考")
    if len(records) > 1:
        for name in ["comex_gold"]:
            label = {"comex_gold": "COMEX黄金"}[name]
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
                    f"区间 {low_price:.1f} - {high_price:.1f}，"
                    f"累计 {'+' if change >= 0 else ''}{change:.1f}%"
                )

    return "\n".join(lines)
