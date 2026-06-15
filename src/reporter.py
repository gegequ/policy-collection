"""报告生成模块。

负责生成和输出每日政策分析报告：
- Markdown 日报文件
- 终端彩色摘要（rich）
- 旧报告自动清理
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Dict, List

from src.models import Article


def generate_markdown_report(
    stats: Dict,
    ai_analysis: str,
    articles: List[Article],
    trends: Dict | None = None,
) -> str:
    """生成完整 Markdown 日报。

    Args:
        stats: compute_stats() 返回的统计字典。
        ai_analysis: AI 分析全文（Markdown）。
        articles: 当日文章列表。
        trends: compute_trends() 返回的趋势数据（可选）。

    Returns:
        完整的 Markdown 报告文本。
    """
    date = stats["date"]
    lines: list[str] = []

    # ── 头部 ──
    lines.append(f"# 📡 政策雷达日报 · {date}")
    lines.append("")

    # ── 今日概览 ──
    lines.append("## 📊 今日概览")
    lines.append(f"- 新增文章：**{stats['total_articles']}** 篇")
    if stats.get("top_sectors"):
        top5 = stats["top_sectors"][:5]
        top5_str = " > ".join(f"{s}({c})" for s, c in top5)
        lines.append(f"- 热门板块 TOP 5：{top5_str}")
    lines.append("")

    # ── 板块热度变化表 ──
    if stats.get("sector_changes"):
        lines.append("## 🔥 板块热度变化")
        lines.append("| 板块 | 今日提及 | 昨日 | 变化 |")
        lines.append("|------|---------|------|------|")
        for ch in stats["sector_changes"]:
            label = ch.get("change_label", f"{ch['change_pct']:+.1f}%")
            lines.append(
                f"| {ch['sector']} | {ch['today']} | {ch['yesterday']} "
                f"| {label} |"
            )
        lines.append("")

    # ── 趋势图 ──
    if trends and trends.get("top_sectors"):
        lines.append("## 📈 板块热度 {days} 日趋势".format(days=len(trends["dates"])))
        lines.append("| 板块 | 趋势 | " + " | ".join(trends["dates"]) + " |")
        lines.append("|------|------|" + "|".join(["-" * 6 for _ in trends["dates"]]) + "|")
        for sector in trends["top_sectors"]:
            direction = trends["series"].get(sector + "_direction", "➖")
            values = " | ".join(str(trends["series"].get(sector, [0]*len(trends["dates"]))[i]) for i in range(len(trends["dates"])))
            lines.append(f"| {sector} | {direction} | {values} |")
        lines.append("")

    # ── 类别分布 ──
    if stats.get("categories"):
        lines.append("## 📂 信息源类别分布")
        for cat, cnt in stats["categories"].items():
            lines.append(f"- **{cat}**：{cnt} 篇")
        lines.append("")

    # ── AI 分析 ──
    if ai_analysis:
        lines.append("## 🧠 AI 政策解读")
        lines.append(ai_analysis)
        lines.append("")

    # ── 原始文章（按类别分组） ──
    lines.append("## 📰 原始文章")
    categorized: Dict[str, List[Article]] = {}
    for a in articles:
        categorized.setdefault(a.category, []).append(a)

    for cat, arts in categorized.items():
        lines.append(f"### {cat}")
        for a in arts:
            tags_str = ""
            if a.tags:
                tags_str = " " + " ".join(f"`{t}`" for t in a.tags)
            lines.append(
                f"- [{a.title}]({a.url}) "
                f"— *{a.source}* · {a.published_at}{tags_str}"
            )
        lines.append("")

    # ── 页脚 ──
    lines.append("---")
    lines.append(f"*报告生成时间：{datetime.now().isoformat()}*")

    return "\n".join(lines)


def print_summary(stats: Dict, ai_analysis: str) -> None:
    """终端彩色摘要输出。

    使用 rich 库渲染美观的终端界面，rich 不可用时降级为纯文本。

    Args:
        stats: compute_stats() 返回的统计字典。
        ai_analysis: AI 分析全文。
    """
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()

        console.print()
        console.print(
            Panel.fit(
                f"[bold cyan]📡 政策雷达日报 · {stats['date']}[/bold cyan]",
                border_style="cyan",
            )
        )
        console.print(f"[bold]新增文章：[/bold]{stats['total_articles']} 篇")

        if stats.get("top_sectors"):
            top5 = stats["top_sectors"][:5]
            top5_str = " > ".join(f"{s}({c})" for s, c in top5)
            console.print(f"[bold]热门板块：[/bold]{top5_str}")

        if stats.get("sector_changes"):
            table = Table(title="板块热度变化")
            table.add_column("板块", style="cyan")
            table.add_column("今日", justify="right")
            table.add_column("昨日", justify="right")
            table.add_column("变化", justify="right")

            for ch in stats["sector_changes"]:
                label = ch.get("change_label", f"{ch['change_pct']:+.1f}%")
                if ch["change_pct"] > 0:
                    change_style = "green"
                elif ch["change_pct"] < 0:
                    change_style = "red"
                else:
                    change_style = "cyan" if label == "🆕" else "white"

                table.add_row(
                    ch["sector"],
                    str(ch["today"]),
                    str(ch["yesterday"]),
                    f"[{change_style}]{label}[/{change_style}]",
                )
                    f"[{change_style}]{arrow} {ch['change_pct']:+.1f}%[/{change_style}]",
                )
            console.print(table)

        if ai_analysis:
            first_para = ai_analysis.split("\n\n")[0] if ai_analysis else ""
            console.print(
                Panel(first_para[:500], title="🧠 AI 解读", border_style="green")
            )

    except ImportError:
        # 降级：纯文本输出
        print(f"\n=== 政策雷达日报 · {stats['date']} ===")
        print(f"新增文章：{stats['total_articles']} 篇")
        if stats.get("top_sectors"):
            top5 = stats["top_sectors"][:5]
            print(f"热门板块：{', '.join(f'{s}({c})' for s, c in top5)}")
        if ai_analysis:
            print(f"\n--- AI 解读 ---")
            print(ai_analysis[:500])
        print()


def save_report(report_md: str, report_dir: str, date: str) -> str:
    """保存报告到文件。

    Args:
        report_md: Markdown 报告全文。
        report_dir: 输出目录。
        date: 日期字符串 YYYY-MM-DD。

    Returns:
        已保存文件的完整路径。
    """
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"{date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_md)
    return path


def cleanup_old_reports(report_dir: str, keep_days: int) -> None:
    """清理超过保留期限的旧报告文件。

    Args:
        report_dir: 报告目录。
        keep_days: 保留天数，0 或负数跳过清理。
    """
    if keep_days <= 0:
        return
    if not os.path.isdir(report_dir):
        return

    cutoff = time.time() - keep_days * 86400
    for fname in os.listdir(report_dir):
        fpath = os.path.join(report_dir, fname)
        if fname.endswith(".md") and os.path.isfile(fpath):
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                logger = __import__("logging").getLogger(__name__)
                logger.debug("清理旧报告: %s", fpath)
