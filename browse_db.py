"""数据库文章浏览工具。

Usage:
    python browse_db.py              # 输出今天的所有文章
    python browse_db.py 2026-06-25   # 输出指定日期
    python browse_db.py --all        # 输出全部
    python browse_db.py --sources    # 只看来源统计
"""

import sqlite3
import sys

DB_PATH = "./data/policy_radar.db"


def print_articles(date_filter: str = None):
    conn = sqlite3.connect(DB_PATH)
    if date_filter:
        rows = conn.execute(
            "SELECT published_at, source, category, title, summary, url "
            "FROM articles WHERE published_at = ? "
            "ORDER BY source, title",
            (date_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT published_at, source, category, title, summary, url "
            "FROM articles ORDER BY published_at DESC, source, title"
        ).fetchall()

    by_date_source = {}
    for pub, src, cat, title, summary, url in rows:
        by_date_source.setdefault(pub, {}).setdefault(src, []).append(
            (title, cat, summary, url)
        )

    for date in sorted(by_date_source.keys(), reverse=True):
        sources = by_date_source[date]
        total = sum(len(v) for v in sources.values())
        print(f"\n{'='*60}")
        print(f"  {date}  — 共 {total} 篇，{len(sources)} 个来源")
        print(f"{'='*60}")
        for src in sorted(sources.keys()):
            articles = sources[src]
            print(f"\n  ┌─ {src}（{len(articles)} 篇）")
            for i, (title, cat, summary, url) in enumerate(articles, 1):
                print(f"  │ {i}. {title}")
                print(f"  │    {url}")


def print_sources():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT source, category, COUNT(*) as cnt, "
        "MIN(published_at) as first_date, MAX(published_at) as last_date "
        "FROM articles GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    total = sum(r[2] for r in rows)
    print(f"\n数据库共 {total} 篇\n")
    print(f"{'来源':<16} {'类别':<10} {'篇数':>5} {'最早':>12} {'最晚':>12}")
    print("-" * 60)
    for src, cat, cnt, first, last in rows:
        print(f"{src:<16} {cat:<10} {cnt:>5} {first:>12} {last:>12}")


def write_markdown(date_filter: str = None):
    conn = sqlite3.connect(DB_PATH)
    if date_filter:
        rows = conn.execute(
            "SELECT published_at, source, category, title, summary, url "
            "FROM articles WHERE published_at = ? "
            "ORDER BY source, title",
            (date_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT published_at, source, category, title, summary, url "
            "FROM articles ORDER BY published_at DESC, source, title"
        ).fetchall()

    by_date_source = {}
    for pub, src, cat, title, summary, url in rows:
        by_date_source.setdefault(pub, {}).setdefault(src, []).append(
            (title, cat, summary, url)
        )

    label = date_filter if date_filter else "all"
    path = f"./reports/db-browse-{label}.md"
    lines = [f"# 📂 数据库文章浏览 · {label}", ""]

    for date in sorted(by_date_source.keys(), reverse=True):
        sources = by_date_source[date]
        total = sum(len(v) for v in sources.values())
        lines.append(f"## {date}  — {total} 篇，{len(sources)} 个来源")
        lines.append("")
        for src in sorted(sources.keys()):
            lines.append(f"### {src}（{len(sources[src])} 篇）")
            lines.append("")
            for i, (title, cat, summary, url) in enumerate(sources[src], 1):
                lines.append(f"{i}. [{title}]({url})")
                if summary:
                    lines.append(f"   > {summary[:150]}...")
                lines.append("")
            lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 已生成: {path}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "today"
    if arg == "--sources":
        print_sources()
    elif arg == "--all":
        write_markdown()
    else:
        from datetime import datetime
        date = arg if arg != "today" else datetime.now().strftime("%Y-%m-%d")
        write_markdown(date)
