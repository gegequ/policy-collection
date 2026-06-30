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
    total_in_db = stats.get("total_in_db")
    if total_in_db:
        lines.append(f"- 数据库收录：**{total_in_db}** 篇")
    lines.append(f"- 今日新增：**{stats['total_articles']}** 篇")
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
            pct = ch.get("change_pct")
            if pct is not None:
                default_label = f"{pct:+.1f}%"
            else:
                default_label = "—"
            label = ch.get("change_label", default_label)
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
        num_days = len(trends["dates"])
        for sector in trends["top_sectors"]:
            direction = trends["series"].get(sector + "_direction", "➖")
            sector_values = trends["series"].get(sector, [0] * num_days)
            values = " | ".join(str(sector_values[i]) for i in range(num_days))
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
        total_in_db = stats.get("total_in_db")
        if total_in_db:
            console.print(f"[bold]数据库收录：[/bold]{total_in_db} 篇")
        console.print(f"[bold]今日新增：[/bold]{stats['total_articles']} 篇")

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
                pct = ch.get("change_pct")
                if pct is not None:
                    default_label = f"{pct:+.1f}%"
                else:
                    default_label = "—"
                label = ch.get("change_label", default_label)
                if pct is None:
                    change_style = "cyan"
                elif pct > 0:
                    change_style = "green"
                elif pct < 0:
                    change_style = "red"
                else:
                    change_style = "white"

                table.add_row(
                    ch["sector"],
                    str(ch["today"]),
                    str(ch["yesterday"]),
                    f"[{change_style}]{label}[/{change_style}]",
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
    # 清理主报告目录
    for fname in os.listdir(report_dir):
        fpath = os.path.join(report_dir, fname)
        if fname.endswith(".md") and os.path.isfile(fpath):
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                logger = __import__("logging").getLogger(__name__)
                logger.debug("清理旧报告: %s", fpath)
    # 同时清理 xwlb 子目录（每日文字稿 + 分析文件 + 月度汇总）
    xwlb_dir = os.path.join(report_dir, "xwlb")
    if os.path.isdir(xwlb_dir):
        for fname in os.listdir(xwlb_dir):
            fpath = os.path.join(xwlb_dir, fname)
            if fname.endswith(".md") and os.path.isfile(fpath):
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    logger = __import__("logging").getLogger(__name__)
                    logger.debug("清理旧XWLB文件: %s", fpath)


# ── 新闻联播分析独立输出 ──────────────────────────────────

def split_xwlb_analysis(report_md: str, date: str, report_dir: str,
                        article_count: int = 0) -> str:
    """从完整报告中提取新闻联播分析段落，独立保存。

    在报告中找到「## 📺 新闻联播信号解读」和「## 📺 新闻联播月度趋势」
    段落，提取到独立文件 reports/xwlb/{date}-analysis.md，
    主报告该位置替换为简要摘要和文件链接。

    Args:
        report_md: 完整 Markdown 报告。
        date: 日期 YYYY-MM-DD。
        report_dir: 报告输出目录。
        article_count: XWLB 文章数（用于摘要）。

    Returns:
        替换后的主报告 Markdown。
    """
    import re

    # 匹配两个 XWLB 段落（从 ## 标题到下一个 ## 或文档末尾）
    xwlb_signal_pattern = re.compile(
        r'(## 📺 新闻联播信号解读\n.*?)(?=\n## [^#]|\Z)', re.DOTALL
    )
    xwlb_monthly_pattern = re.compile(
        r'(## 📺 新闻联播月度趋势[^\n]*\n.*?)(?=\n## [^#]|\Z)', re.DOTALL
    )

    signal_match = xwlb_signal_pattern.search(report_md)
    monthly_match = xwlb_monthly_pattern.search(report_md)

    extracted_parts = []
    if signal_match:
        extracted_parts.append(signal_match.group(1))
    if monthly_match:
        extracted_parts.append(monthly_match.group(1))

    if not extracted_parts:
        return report_md  # 无 XWLB 内容，不处理

    # 写入独立 XWLB 分析文件
    xwlb_dir = os.path.join(report_dir, "xwlb")
    os.makedirs(xwlb_dir, exist_ok=True)
    xwlb_path = os.path.join(xwlb_dir, f"{date}-analysis.md")

    xwlb_content = (
        f"# 📺 新闻联播深度分析 · {date}\n\n"
        f"> 关联报告：[政策雷达日报](../{date}.md)\n\n"
        + "\n\n".join(extracted_parts)
        + f"\n\n---\n*分析时间：{datetime.now().isoformat()}*"
    )

    with open(xwlb_path, "w", encoding="utf-8") as f:
        f.write(xwlb_content)

    # 主报告中替换为摘要 + 链接
    replacement = (
        f"## 📺 新闻联播信号\n\n"
        f"> 📺 今日新闻联播已采集 **{article_count}** 条。"
        f" 完整分析请见："
        f"[新闻联播深度分析](xwlb/{date}-analysis.md)\n"
    )

    # 先替换信号解读段落
    if signal_match:
        report_md = report_md[:signal_match.start()] + replacement + report_md[signal_match.end():]
    # 再替换月度趋势段落（注意位置已偏移）
    monthly_match = xwlb_monthly_pattern.search(report_md) if monthly_match else None
    if monthly_match:
        report_md = report_md[:monthly_match.start()] + report_md[monthly_match.end():]

    return report_md
