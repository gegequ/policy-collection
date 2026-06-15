"""基金数据库查询模块。

从 funds.json 加载真实场外基金数据，支持按板块/类型查询。
替换 AI 凭空生成的基金代码，确保推荐100%可购买。
"""

from __future__ import annotations

import json
import os
from typing import List, Dict, Optional

FUNDS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "funds.json")

# 懒加载
_funds_cache: Optional[List[Dict]] = None
_sector_cache: Optional[Dict] = None


def _load() -> List[Dict]:
    global _funds_cache
    if _funds_cache is None:
        with open(FUNDS_PATH, "r", encoding="utf-8") as f:
            _funds_cache = json.load(f)["funds"]
    return _funds_cache


def get_funds_by_sector(sector: str, limit: int = 3, prefer_type: str = "ETF联接") -> List[Dict]:
    """按板块获取真实基金列表。

    Args:
        sector: 板块名（如 "金融", "半导体", "医药"）
        limit: 最多返回数
        prefer_type: 优先类型（ETF联接/指数基金/主动基金）

    Returns:
        基金列表，每项含 code/name/type/fee/scale
    """
    funds = _load()
    matched = [f for f in funds if f["sector"] == sector]
    # 优先返回指定类型
    preferred = [f for f in matched if f["type"] == prefer_type]
    others = [f for f in matched if f["type"] != prefer_type]
    result = preferred + others
    return result[:limit]


def get_fund_names_for_prompt(sectors: List[str]) -> str:
    """为 AI prompt 生成基金推荐参考文本。

    Args:
        sectors: 需要的板块列表（如 ["金融", "半导体", "宽基"]）

    Returns:
        格式化的基金列表文本，供 AI 在生成报告时引用。
    """
    lines = [
        "## 🏦 真实基金数据库（以下基金代码均真实有效，请从中选择推荐，禁止编造代码）",
        ""
    ]
    for sector in sectors:
        funds = get_funds_by_sector(sector, limit=3)
        if funds:
            lines.append(f"### {sector}板块可选基金：")
            for f in funds:
                lines.append(
                    f"- {f['code']} {f['name']} "
                    f"| 类型:{f['type']} | 费率:{f['fee']}% | 规模:{f['scale']} | 跟踪:{f['index']}"
                )
            lines.append("")
    return "\n".join(lines)


def get_all_sectors() -> List[str]:
    """获取所有板块名。"""
    with open(FUNDS_PATH, "r", encoding="utf-8") as f:
        sm = json.load(f).get("sector_map", {})
    return list(sm.keys())


def verify_fund_code(code: str) -> Optional[Dict]:
    """验证一个基金代码是否在数据库中。"""
    funds = _load()
    for f in funds:
        if f["code"] == code:
            return f
    return None
