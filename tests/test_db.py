# tests/test_db.py
import pytest
from src.db import Database
from src.models import Article


def test_database_init_creates_tables(temp_db_path):
    db = Database(temp_db_path)
    db.initialize()

    import sqlite3
    conn = sqlite3.connect(temp_db_path)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    assert "articles" in table_names
    assert "daily_reports" in table_names
    conn.close()


def test_insert_and_get_article(temp_db_path):
    db = Database(temp_db_path)
    db.initialize()

    article = Article(
        title="测试文章",
        url="http://example.com/test1",
        source="测试源",
        category="货币政策",
        published_at="2025-01-20T09:00:00",
        summary="摘要内容",
        tags=["金融", "银行"],
    )
    article_id = db.insert_article(article)
    assert article_id == 1

    results = db.get_articles_by_date("2025-01-20")
    assert len(results) == 1
    assert results[0].title == "测试文章"
    assert results[0].tags == ["金融", "银行"]


def test_insert_duplicate_url_is_ignored(temp_db_path):
    db = Database(temp_db_path)
    db.initialize()

    article1 = Article(
        title="文章1",
        url="http://example.com/same-url",
        source="源A",
        category="货币政策",
        published_at="2025-01-20T09:00:00",
        summary="...",
        tags=[],
    )
    article2 = Article(
        title="文章1重复",
        url="http://example.com/same-url",
        source="源B",
        category="产业政策",
        published_at="2025-01-20T10:00:00",
        summary="...",
        tags=[],
    )
    id1 = db.insert_article(article1)
    id2 = db.insert_article(article2)
    assert id1 == 1
    assert id2 is None

    results = db.get_articles_by_date("2025-01-20")
    assert len(results) == 1


def test_get_unanalyzed_articles(temp_db_path):
    db = Database(temp_db_path)
    db.initialize()

    for i in range(3):
        db.insert_article(Article(
            title=f"文章{i}",
            url=f"http://example.com/{i}",
            source="src",
            category="货币政策",
            published_at="2025-01-20T09:00:00",
            summary="...",
            tags=[],
        ))
    unanalyzed = db.get_unanalyzed_articles()
    assert len(unanalyzed) == 3

    db.mark_analyzed([1, 2])
    unanalyzed2 = db.get_unanalyzed_articles()
    assert len(unanalyzed2) == 1
    assert unanalyzed2[0].id == 3


def test_insert_and_get_daily_report(temp_db_path):
    db = Database(temp_db_path)
    db.initialize()

    db.insert_daily_report(
        date="2025-01-20",
        article_count=5,
        stats_json='{"top": ["金融"]}',
        ai_analysis="分析文本",
        report_md="# 日报",
    )
    report = db.get_daily_report("2025-01-20")
    assert report is not None
    assert report.article_count == 5
    assert report.ai_analysis == "分析文本"

    db.insert_daily_report(
        date="2025-01-20",
        article_count=6,
        stats_json='{"top": ["能源"]}',
        ai_analysis="更新分析",
        report_md="# 日报v2",
    )
    report2 = db.get_daily_report("2025-01-20")
    assert report2.article_count == 6


def test_get_recent_dates_with_data(temp_db_path):
    db = Database(temp_db_path)
    db.initialize()

    db.insert_daily_report("2025-01-18", 3, "{}", "", "")
    db.insert_daily_report("2025-01-19", 5, "{}", "", "")
    db.insert_daily_report("2025-01-20", 7, "{}", "", "")

    dates = db.get_recent_dates(2)
    assert len(dates) == 2
    assert "2025-01-20" in dates
    assert "2025-01-19" in dates
