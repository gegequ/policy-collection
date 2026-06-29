"""数据库操作层。

封装 SQLite 操作，提供文章存储、去重、报告管理等功能。
使用 WAL 模式提升并发读写性能。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from src.models import Article, DailyReport


class DatabaseError(Exception):
    """数据库操作异常。"""
    pass


class Database:
    """SQLite 数据库封装。

    核心功能：
    - 文章插入（URL 哈希去重）
    - 按日期/分析状态查询
    - 日报存储与查询

    Usage:
        db = Database("path/to/policy_radar.db")
        db.initialize()  # 首次使用时创建表
    """

    def __init__(self, path: str) -> None:
        """初始化数据库连接配置。

        Args:
            path: 数据库文件路径，`:memory:` 表示内存数据库。
        """
        self.path = path
        if path != ":memory:":
            db_dir = os.path.dirname(path) or "."
            os.makedirs(db_dir, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        """创建数据库连接。

        使用 WAL 模式以支持并发读写，Row 工厂以支持字段名访问。
        """
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        """初始化数据库表（幂等操作）。

        创建 articles 和 daily_reports 两张核心表。
        """
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_hash TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    summary TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    fetched_at TEXT DEFAULT '',
                    is_analyzed INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_date
                ON articles(published_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_unanalyzed
                ON articles(is_analyzed) WHERE is_analyzed = 0
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    article_count INTEGER DEFAULT 0,
                    stats_json TEXT DEFAULT '{}',
                    ai_analysis TEXT DEFAULT '',
                    report_md TEXT DEFAULT '',
                    created_at TEXT DEFAULT ''
                )
            """)

    # ── 文章操作 ──────────────────────────────────────────────

    def insert_article(self, article: Article) -> Optional[int]:
        """插入一篇文章，URL 重复时静默忽略。

        Args:
            article: 待插入的 Article 对象。

        Returns:
            新插入行的 id，重复则返回 None。
        """
        now = datetime.now().isoformat()
        article.fetched_at = now
        d = article.to_dict()
        # id 由数据库自增，不传给 INSERT
        d.pop("id", None)
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """INSERT INTO articles
                       (url_hash, title, url, source, category, published_at,
                        summary, tags, fetched_at, is_analyzed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        d["url_hash"], d["title"], d["url"], d["source"],
                        d["category"], d["published_at"], d["summary"],
                        d["tags"], d["fetched_at"], d["is_analyzed"],
                    ),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            # URL 重复 — 静默忽略
            return None

    def count_articles(self) -> int:
        """返回数据库中的文章总数。

        Returns:
            文章总行数。
        """
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
            return row[0] if row else 0

    def get_articles_by_date(self, date_str: str) -> List[Article]:
        """按日期查询文章（匹配 published_at 前缀）。

        Args:
            date_str: 日期字符串，如 "2025-01-20"。

        Returns:
            匹配日期的 Article 列表，按发布时间倒序。
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM articles
                   WHERE published_at LIKE ?
                   ORDER BY published_at DESC""",
                (f"{date_str}%",),
            ).fetchall()
        return [Article.from_dict(dict(r)) for r in rows]

    def get_unanalyzed_articles(self, date: str | None = None) -> List[Article]:
        """获取尚未 AI 分析的文章。

        Args:
            date: 可选，限定日期（YYYY-MM-DD）。不传返回全部日期。

        Returns:
            is_analyzed=0 的 Article 列表，按发布时间倒序。
        """
        with self._connect() as conn:
            if date:
                rows = conn.execute(
                    "SELECT * FROM articles WHERE is_analyzed = 0 "
                    "AND published_at LIKE ? "
                    "ORDER BY published_at DESC",
                    (f"{date}%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM articles WHERE is_analyzed = 0 "
                    "ORDER BY published_at DESC"
                ).fetchall()
        return [Article.from_dict(dict(r)) for r in rows]

    def mark_analyzed(self, article_ids: List[int]) -> None:
        """将指定文章标记为已分析。

        Args:
            article_ids: 要标记的文章 id 列表。
        """
        with self._connect() as conn:
            conn.executemany(
                "UPDATE articles SET is_analyzed = 1 WHERE id = ?",
                [(aid,) for aid in article_ids],
            )

    def reset_analyzed_for_date(self, date_str: str) -> int:
        """重置指定日期所有文章的 is_analyzed 标记（--fresh 用）。

        Args:
            date_str: 日期 YYYY-MM-DD。

        Returns:
            重置的文章数。
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE articles SET is_analyzed = 0 "
                "WHERE published_at = ?",
                (date_str,),
            )
            return cursor.rowcount

    # ── 日报操作 ──────────────────────────────────────────────

    def insert_daily_report(
        self,
        date: str,
        article_count: int,
        stats_json: str,
        ai_analysis: str,
        report_md: str,
    ) -> None:
        """插入或更新日报（同日期覆盖）。

        Args:
            date: 日期 YYYY-MM-DD。
            article_count: 当日文章数。
            stats_json: 统计结果 JSON。
            ai_analysis: AI 分析全文。
            report_md: 完整 Markdown 报告。
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO daily_reports
                   (date, article_count, stats_json, ai_analysis,
                    report_md, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date, article_count, stats_json, ai_analysis, report_md, now),
            )

    def get_daily_report(self, date: str) -> Optional[DailyReport]:
        """按日期查询日报。

        Args:
            date: 日期 YYYY-MM-DD。

        Returns:
            DailyReport 或 None（若该日无报告）。
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE date = ?", (date,)
            ).fetchone()
        if row is None:
            return None
        return DailyReport.from_dict(dict(row))

    def get_recent_dates(self, limit: int = 7) -> List[str]:
        """获取最近有报告数据的日期列表。

        Args:
            limit: 返回的最大日期数。

        Returns:
            日期字符串列表，从新到旧。
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT date FROM daily_reports ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r[0] for r in rows]
