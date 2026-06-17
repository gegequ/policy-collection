"""PE 估值自动抓取模块。

使用 playwright-cli（Node.js CLI）获取 JS 渲染后的页面内容，
从乐咕乐股、东方财富等公开数据源提取指数 PE/分位数据，
自动更新 pe_data.json。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Dict, Optional

import httpx
import asyncio

logger = __import__("logging").getLogger(__name__)

PE_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pe_data.json")


def _run_cli(args: str, timeout: int = 30) -> str:
    """执行 playwright-cli 命令，返回 stdout。"""
    try:
        result = subprocess.run(
            f"playwright-cli {args}",
            shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        logger.warning("playwright-cli failed: %s", e)
        return ""


def _ensure_browser() -> bool:
    """确保浏览器已启动。"""
    out = _run_cli("open", timeout=10)
    return "opened" in out.lower() or "Browser" in out


def _extract_numbers(text: str) -> Dict[str, float]:
    """从文本中提取所有数字键值对。"""
    result = {}
    for m in re.finditer(r'(市盈率|PE|PB|分位|指数|估值)[^\d]*(\d+\.?\d*)', text, re.I):
        result[m.group(1)] = float(m.group(2))
    return result


async def fetch_legulegu_pe() -> Optional[Dict]:
    """从乐咕乐股抓取大盘PE数据。

    使用 playwright-cli 渲染 JS 页面后提取 PE 数值。

    Returns:
        {"上证": 16.83, "深证": 34.1, "创业板": 53.34, "科创板": 102.59} or None
    """
    if not _ensure_browser():
        return None

    _run_cli('goto "https://www.legulegu.com/stockdata/market_pe"', timeout=20)
    text = _run_cli('eval "document.body.innerText"', timeout=10)

    if not text:
        return None

    # 从页面文本中提取 PE
    result = {}
    patterns = [
        (r'上证[^\d]*(\d+\.?\d*)', '上证'),
        (r'深证[^\d]*(\d+\.?\d*)', '深证'),
        (r'创业板[^\d]*(\d+\.?\d*)', '创业板'),
        (r'科创板[^\d]*(\d+\.?\d*)', '科创板'),
    ]
    for pattern, name in patterns:
        m = re.search(pattern, text)
        if m:
            result[name] = float(m.group(1))

    return result if result else None


async def fetch_sina_pe(secid: str = "1.000300") -> Optional[Dict]:
    """从东方财富 JSON API 获取指数 PE（需要代理）。

    Args:
        secid: 东方财富 secid，如 1.000300=沪深300

    Returns:
        {"price": 4931, "pe": 14.4, "pb": 1.45} or None
    """
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f57,f58,f170,f115,f116,f20,f21"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"Referer": "https://quote.eastmoney.com"})
            data = resp.json().get("data")
            if not data:
                return None
            return {
                "price": data.get("f43", 0) / 100 if data.get("f43") else 0,
                "pe": data.get("f115") or data.get("f20") or None,
                "pb": data.get("f116") or data.get("f21") or None,
                "name": data.get("f58", ""),
            }
    except Exception:
        return None


async def update_pe_data():
    """主入口：抓取最新 PE 数据并更新 pe_data.json。"""
    print("📊 更新 PE 估值数据...")

    # 加载现有数据
    try:
        with open(PE_DATA_PATH, "r", encoding="utf-8") as f:
            pe_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pe_data = {"updated": "", "indices": {}}

    # 1. 乐咕乐股——大盘PE
    try:
        legu = await fetch_legulegu_pe()
        if legu:
            for name, pe in legu.items():
                if name in pe_data.get("indices", {}):
                    pe_data["indices"][name]["pe"] = pe
            pe_data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            pe_data["source"] = "legulegu.com + eastmoney.com (自动抓取)"
            print(f"  乐咕乐股: {legu}")
    except Exception as e:
        logger.warning("乐咕乐股抓取失败: %s", e)

    # 2. 东方财富 API——指数PE
    em_indices = {
        "1.000300": "沪深300", "1.000905": "中证500",
        "0.399006": "创业板指", "1.000688": "科创50",
        "0.399986": "中证银行", "1.000932": "中证消费",
        "1.000933": "中证医药", "0.399967": "中证军工",
        "0.399808": "中证新能源", "1.000819": "有色金属",
    }
    for secid, name in em_indices.items():
        try:
            data = await fetch_sina_pe(secid)
            if data and data.get("pe") and data["pe"] > 0:
                if name in pe_data.get("indices", {}):
                    pe_data["indices"][name]["pe"] = round(data["pe"], 2)
                print(f"  {name}: PE={data.get('pe')}")
        except Exception:
            pass

    # 保存
    with open(PE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(pe_data, f, ensure_ascii=False, indent=2)

    print(f"✅ PE 数据已更新 → {PE_DATA_PATH}")


if __name__ == "__main__":
    asyncio.run(update_pe_data())
