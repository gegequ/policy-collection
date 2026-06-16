"""回测引擎。

记录每份报告的板块预测，N天后与指数实际走势对比，计算准确率。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

BACKTEST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "backtest.json")

SECTOR_TO_INDEX = {
    "金融": "中证银行",
    "消费": "中证消费",
    "医药": "中证医药",
    "新能源": "中证新能源",
    "半导体": "半导体",
    "军工航天": "中证军工",
    "地产": "房地产",
    "有色金属": "有色金属",
    "科技": "科创50",
}


def extract_predictions(report_md: str, date: str) -> List[Dict]:
    """从报告中提取板块方向预测。

    优先解析结构化 [预测标记] 格式（精确），
    旧报告无标记时回退到关键词匹配（兼容）。

    Returns:
        [{sector, direction, confidence, index}]
    """
    predictions = []
    seen_sectors = set()

    # ── 方式 1：结构化标记解析（精确） ──
    # 格式: [预测标记] 板块名 | 方向:利好/利空/中性 | 强度:强/中/弱 | 置信度:高/中/低
    marker_pattern = re.compile(
        r"\[预测标记\]\s*(\S+?)\s*\|\s*方向\s*:\s*(利好|利空|中性)\s*"
        r"\|\s*强度\s*:\s*(强|中|弱)\s*"
        r"(?:\|\s*置信度\s*:\s*(高|中|低))?"
    )
    for m in marker_pattern.finditer(report_md):
        sector = m.group(1)
        direction = m.group(2)
        confidence = m.group(3)  # 强度即 confidence
        index = SECTOR_TO_INDEX.get(sector, sector)

        predictions.append({
            "date": date,
            "sector": sector,
            "index": index,
            "direction": direction,
            "confidence": confidence,
        })
        seen_sectors.add(sector)

    # ── 方式 2：关键词回退（兼容旧报告） ──
    for sector, index in SECTOR_TO_INDEX.items():
        if sector in seen_sectors:
            continue

        section = _find_sector_section(report_md, sector)
        if not section:
            continue

        direction = None
        confidence = None
        if "利好" in section:
            direction = "利好"
        elif "利空" in section:
            direction = "利空"

        if "程度强" in section:
            confidence = "强"
        elif "程度中" in section:
            confidence = "中"
        elif "程度弱" in section:
            confidence = "弱"
        elif "中性" in section:
            direction = "中性"
            confidence = "中"

        if direction:
            predictions.append({
                "date": date,
                "sector": sector,
                "index": index,
                "direction": direction,
                "confidence": confidence,
            })

    return predictions


def save_predictions(predictions: List[Dict]):
    """保存预测到回测文件。"""
    records = []
    if os.path.exists(BACKTEST_PATH):
        try:
            with open(BACKTEST_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                records = data.get("predictions", [])
        except (json.JSONDecodeError, OSError):
            pass

    records.extend(predictions)
    os.makedirs(os.path.dirname(BACKTEST_PATH), exist_ok=True)
    with open(BACKTEST_PATH, "w", encoding="utf-8") as f:
        json.dump({"predictions": records, "updated": datetime.now().isoformat()},
                  f, ensure_ascii=False, indent=2)


def evaluate_predictions(days_later: int = 1) -> Dict:
    """评估历史预测准确率。

    将预测方向与实际涨跌对比：
    - 利好预测 + 指数上涨 = 正确
    - 利空预测 + 指数下跌 = 正确
    - 中性预测不计入

    Args:
        days_later: 检查几天后的走势（默认1天=次日）

    Returns:
        {total, correct, accuracy, by_sector: {sector: {total, correct}}}
    """
    if not os.path.exists(BACKTEST_PATH):
        return {"total": 0, "correct": 0, "accuracy": 0, "by_sector": {}}

    try:
        with open(BACKTEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"total": 0, "correct": 0, "accuracy": 0, "by_sector": {}}

    predictions = data.get("predictions", [])
    if not predictions:
        return {"total": 0, "correct": 0, "accuracy": 0, "by_sector": {}}

    # 暂不加载实际行情做对比，先输出预测记录供人工审核
    by_sector = {}
    for p in predictions:
        s = p["sector"]
        if s not in by_sector:
            by_sector[s] = {"total": 0, "correct": 0, "predictions": []}
        by_sector[s]["total"] += 1

    return {
        "total": len(predictions),
        "correct": 0,
        "accuracy": 0,
        "by_sector": by_sector,
        "note": "回测数据已记录，需积累实际行情数据后自动计算准确率"
    }


def get_backtest_summary() -> str:
    """生成回测摘要文本。"""
    result = evaluate_predictions()
    if result["total"] == 0:
        return "暂无回测数据"

    lines = [f"## 📊 预测回测（共 {result['total']} 条记录）"]
    for sector, data in sorted(result.get("by_sector", {}).items()):
        lines.append(f"- {sector}：{data['total']} 次预测，待行情验证")
    lines.append(f"\n{result.get('note', '')}")
    return "\n".join(lines)


def _find_sector_section(report: str, sector: str) -> str:
    """在报告中定位某板块的分析段落。"""
    # 搜索 "**板块名**" 或 "板块名：" 开头的段落
    patterns = [
        rf"\*\*{sector}\*\*",    # **金融**
        rf"{sector}板块",        # 金融板块
    ]
    for p in patterns:
        m = re.search(p, report)
        if m:
            start = m.start()
            # 取前后各200字符
            return report[max(0, start - 50):min(len(report), start + 250)]
    return ""
