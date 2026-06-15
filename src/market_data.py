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

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "gold_history.json")

# 新浪财经行情接口（免费，无需认证）
SINA_QUOTES = {
    "comex_gold": "hf_GC",  # COMEX 黄金期货（主力合约，可正常获取）
}

# 备用：其他品种通过不同前缀
EXTRA_QUOTES = {
    "sh_index": "s_sh000001",  # 上证指数（非黄金，但可验证接口）
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
