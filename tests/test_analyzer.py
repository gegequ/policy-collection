# src/analyzer.py 的测试
# tests/test_analyzer.py
from src.analyzer import extract_sectors, compute_stats
from src.models import Article


def test_extract_sectors_from_title():
    text = "央行降准0.5个百分点，支持实体经济发展"
    sectors = extract_sectors(text)
    assert "金融" in sectors


def test_extract_sectors_new_energy():
    text = "国家能源局推动光伏和风电产业发展"
    sectors = extract_sectors(text)
    assert "新能源" in sectors


def test_extract_sectors_multiple():
    text = "工信部推动人工智能与半导体产业发展，财政部出台新能源汽车补贴政策"
    sectors = extract_sectors(text)
    assert "数字经济" in sectors or "半导体" in sectors
    assert "新能源" in sectors or "消费" in sectors


def test_compute_stats_basic():
    articles = [
        Article(
            title="降准通知",
            url="http://example.com/1",
            source="央行",
            category="货币政策",
            published_at="2025-01-20T09:00:00",
            summary="",
            tags=["金融"],
        ),
        Article(
            title="光伏新政",
            url="http://example.com/2",
            source="能源局",
            category="能源政策",
            published_at="2025-01-20T10:00:00",
            summary="",
            tags=["新能源"],
        ),
    ]
    stats = compute_stats(articles, today="2025-01-20")
    assert stats["total_articles"] == 2
    assert stats["date"] == "2025-01-20"
    assert ("金融", 1) in stats["top_sectors"]
    assert ("新能源", 1) in stats["top_sectors"]


def test_auto_tagging_when_tags_empty():
    articles = [
        Article(
            title="国务院常务会议研究促进消费政策措施",
            url="http://example.com/1",
            source="国务院",
            category="宏观决策",
            published_at="2025-01-20T09:00:00",
            summary="",
            tags=[],  # 空标签，应自动标注
        ),
    ]
    stats = compute_stats(articles, today="2025-01-20")
    assert stats["total_articles"] == 1
    # 应该自动匹配到"消费"板块
    assert len(articles[0].tags) > 0
    assert "消费" in articles[0].tags
