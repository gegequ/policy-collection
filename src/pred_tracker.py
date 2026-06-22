"""预测追踪表生成模块。
每次运行后从 backtest.json 聚合各板块历史方向，
生成 reports/predictions.md 时间序列表。
"""

import json
import os
from collections import defaultdict
from typing import Dict, List

BACKTEST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "backtest.json")
PRED_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports", "predictions.md")


def generate_prediction_table():
    """生成板块方向历史追踪表。"""
    if not os.path.exists(BACKTEST_PATH):
        return

    with open(BACKTEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    predictions = data.get("predictions", [])
    if not predictions:
        return

    # 按日期+板块聚合（取最新的方向）
    by_date_sector: Dict[str, Dict[str, str]] = defaultdict(dict)
    all_dates = set()
    all_sectors = set()

    for p in predictions:
        date = p["date"]
        sector = p["sector"]
        direction = p["direction"]
        by_date_sector[date][sector] = direction
        all_dates.add(date)
        all_sectors.add(sector)

    sorted_dates = sorted(all_dates)
    # 只取最近30天
    if len(sorted_dates) > 30:
        sorted_dates = sorted_dates[-30:]

    sorted_sectors = sorted(all_sectors)

    lines = [
        "# 📊 板块预测方向追踪",
        "",
        f"自动生成，每次运行后更新。共 {len(predictions)} 条预测记录。",
        "",
        "| 日期 | " + " | ".join(sorted_sectors) + " |",
        "|------|" + "|".join(["------" for _ in sorted_sectors]) + "|",
    ]

    for date in sorted_dates:
        row = [date]
        for sector in sorted_sectors:
            d = by_date_sector[date].get(sector, "")
            if d == "利好":
                row.append("🟢 利好")
            elif d == "利空":
                row.append("🔴 利空")
            elif d == "中性":
                row.append("⚪ 中性")
            else:
                row.append("—")
        lines.append("| " + " | ".join(row) + " |")

    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    generate_prediction_table()
