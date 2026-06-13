"""数据模型。

定义系统中的两个核心数据类型：
- Article: 采集到的单篇文章
- DailyReport: 每日分析报告
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any


@dataclass
class Article:
    """一篇文章/政策信息。

    Attributes:
        title: 标题。
        url: 原文链接。
        source: 信息来源名称，如 "中国人民银行"。
        category: 信息类别，如 "货币政策"。
        published_at: 原文发布时间，ISO-8601 格式。
        summary: 正文摘要（前 500 字）。
        tags: 板块标签列表，如 ["金融", "银行"]。
        id: 数据库主键，插入前为 None。
        url_hash: URL 的 SHA256 去重指纹，创建时自动计算。
        fetched_at: 采集时间。
        is_analyzed: 是否已被 AI 分析（0/1）。
    """

    title: str
    url: str
    source: str
    category: str
    published_at: str
    summary: str
    tags: List[str] = field(default_factory=list)
    id: Optional[int] = None
    url_hash: str = ""
    fetched_at: str = ""
    is_analyzed: int = 0

    def __post_init__(self) -> None:
        """数据校验和自动字段生成。"""
        if not self.url_hash:
            self.url_hash = hashlib.sha256(self.url.encode()).hexdigest()
        if not isinstance(self.tags, list):
            self.tags = []

    def to_dict(self) -> dict[str, Any]:
        """转为数据库行字典（tags 序列化为 JSON 字符串）。

        Returns:
            适合 SQLite INSERT 的字段字典。
        """
        d = asdict(self)
        d["tags"] = json.dumps(self.tags, ensure_ascii=False)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Article":
        """从数据库行字典重建 Article。

        Args:
            d: 数据库查询返回的字段字典。

        Returns:
            重建的 Article 实例。
        """
        tags_raw = d.get("tags", "[]")
        if isinstance(tags_raw, str):
            tags = json.loads(tags_raw)
        else:
            tags = tags_raw
        return cls(
            id=d.get("id"),
            title=d["title"],
            url=d["url"],
            url_hash=d.get("url_hash", ""),
            source=d["source"],
            category=d["category"],
            published_at=d["published_at"],
            summary=d.get("summary", ""),
            tags=tags,
            fetched_at=d.get("fetched_at", ""),
            is_analyzed=d.get("is_analyzed", 0),
        )


@dataclass
class DailyReport:
    """每日分析报告。

    Attributes:
        date: 报告日期 YYYY-MM-DD。
        article_count: 当日新增文章数。
        stats_json: 统计结果 JSON。
        ai_analysis: AI 分析全文（Markdown）。
        report_md: 完整报告 Markdown。
        id: 数据库主键。
        created_at: 报告生成时间。
    """

    date: str
    article_count: int
    stats_json: str
    ai_analysis: str
    report_md: str
    id: Optional[int] = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转为数据库行字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DailyReport":
        """从数据库行字典重建 DailyReport。"""
        return cls(
            id=d.get("id"),
            date=d["date"],
            article_count=d["article_count"],
            stats_json=d["stats_json"],
            ai_analysis=d.get("ai_analysis", ""),
            report_md=d.get("report_md", ""),
            created_at=d.get("created_at", ""),
        )
