# tests/test_models.py
import json
import hashlib
from src.models import Article, DailyReport


def test_article_creation():
    article = Article(
        title="央行降准0.5个百分点",
        url="http://www.pbc.gov.cn/goutongjiaoliu/113456/12345/index.html",
        source="中国人民银行",
        category="货币政策",
        published_at="2025-01-20T09:00:00",
        summary="为支持实体经济发展，降低社会融资实际成本……",
        tags=["银行", "金融", "地产"],
    )
    assert article.title == "央行降准0.5个百分点"
    assert article.source == "中国人民银行"
    assert article.category == "货币政策"
    assert article.tags == ["银行", "金融", "地产"]
    assert article.is_analyzed == 0
    assert article.id is None


def test_article_url_hash_is_sha256_of_url():
    article = Article(
        title="test",
        url="http://example.com/12345",
        source="test",
        category="test",
        published_at="2025-01-01T00:00:00",
        summary="",
        tags=[],
    )
    expected = hashlib.sha256("http://example.com/12345".encode()).hexdigest()
    assert article.url_hash == expected


def test_article_to_dict_roundtrip():
    article = Article(
        title="测试",
        url="http://example.com/1",
        source="src",
        category="cat",
        published_at="2025-01-01T00:00:00",
        summary="摘要",
        tags=["a", "b"],
    )
    d = article.to_dict()
    restored = Article.from_dict(d)
    assert restored.title == article.title
    assert restored.url == article.url
    assert restored.tags == article.tags
    assert restored.url_hash == article.url_hash


def test_daily_report_creation():
    report = DailyReport(
        date="2025-01-20",
        article_count=15,
        stats_json='{"top_sectors": ["金融"]}',
        ai_analysis="政策信号偏宽松……",
        report_md="# 日报\n...",
    )
    assert report.date == "2025-01-20"
    assert report.article_count == 15
    assert report.id is None
