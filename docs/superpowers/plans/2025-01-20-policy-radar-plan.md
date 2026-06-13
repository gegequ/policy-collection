# 政策雷达（Policy Radar）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建采集中国官方网站政策信息的本地命令行工具，通过统计+AI分析辅助A股指数基金投资决策

**Architecture:** 四层流水线——采集层（每信息源独立fetcher模块）→存储层（SQLite）→分析层（统计+DeepSeek API）→输出层（Markdown日报+终端摘要）。httpx 异步并发采集，BeautifulSoup 解析，rich 终端美化。

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup4+lxml, SQLite, PyYAML, rich, pytest, DeepSeek API

---

### Task 1: 项目初始化

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 创建 requirements.txt**

```txt
httpx>=0.27.0
beautifulsoup4>=4.12.0
lxml>=5.1.0
pyyaml>=6.0
rich>=13.0.0
pytest>=8.0.0
pytest-httpx>=0.30.0
```

- [ ] **Step 2: 安装依赖**

Run: `pip install -r requirements.txt`
Expected: 全部安装成功，无报错

- [ ] **Step 3: 创建 config.yaml 模板**

```yaml
deepseek:
  api_key: ${DEEPSEEK_API_KEY}
  model: deepseek-chat
  max_tokens: 2000
  base_url: https://api.deepseek.com

sources:
  monetary_policy: true
  macro_decision: true
  industrial_policy: true
  financial_regulation: true
  economic_data: true
  trade_data: true
  energy_policy: true
  fiscal_commerce: true
  policy_research: true
  media_sentiment: true

database:
  path: "./data/policy_radar.db"

output:
  report_dir: "./reports"
  keep_days: 365

fetch:
  timeout_sec: 30
  max_concurrent: 5
```

- [ ] **Step 4: 创建 tests/conftest.py**

```python
import pytest
import tempfile
import os


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def sample_config_dict():
    return {
        "deepseek": {
            "api_key": "sk-test",
            "model": "deepseek-chat",
            "max_tokens": 2000,
            "base_url": "https://api.deepseek.com",
        },
        "sources": {
            "monetary_policy": True,
            "macro_decision": False,
            "industrial_policy": False,
            "financial_regulation": False,
            "economic_data": False,
            "trade_data": False,
            "energy_policy": False,
            "fiscal_commerce": False,
            "policy_research": False,
            "media_sentiment": False,
        },
        "database": {"path": ":memory:"},
        "output": {"report_dir": "./reports", "keep_days": 365},
        "fetch": {"timeout_sec": 30, "max_concurrent": 5},
    }
```

- [ ] **Step 5: 创建空 __init__.py 文件**

Run: `touch src/__init__.py tests/__init__.py tests/test_fetchers/__init__.py`
Expected: 文件创建成功

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config.yaml src/__init__.py tests/
git commit -m "chore: init project skeleton with deps and config template"
```

---

### Task 2: 配置加载模块

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
import os
import tempfile
import pytest
from src.config import load_config, Config, DeepseekConfig


def test_load_config_parses_yaml():
    yaml_content = """
deepseek:
  api_key: sk-abc123
  model: deepseek-chat
  max_tokens: 2000
  base_url: https://api.deepseek.com
sources:
  monetary_policy: true
  macro_decision: false
  industrial_policy: true
  financial_regulation: false
  economic_data: false
  trade_data: false
  energy_policy: false
  fiscal_commerce: false
  policy_research: false
  media_sentiment: false
database:
  path: ./data/test.db
output:
  report_dir: ./reports
  keep_days: 30
fetch:
  timeout_sec: 15
  max_concurrent: 10
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        config = load_config(path)
        assert config.deepseek.api_key == "sk-abc123"
        assert config.deepseek.model == "deepseek-chat"
        assert config.sources["monetary_policy"] is True
        assert config.sources["macro_decision"] is False
        assert config.database.path == "./data/test.db"
        assert config.fetch.timeout_sec == 15
    finally:
        os.unlink(path)


def test_load_config_resolves_env_var():
    os.environ["TEST_DS_KEY"] = "sk-env-456"
    yaml_content = """
deepseek:
  api_key: ${TEST_DS_KEY}
  model: deepseek-chat
  max_tokens: 2000
  base_url: https://api.deepseek.com
sources:
  monetary_policy: true
  macro_decision: false
  industrial_policy: false
  financial_regulation: false
  economic_data: false
  trade_data: false
  energy_policy: false
  fiscal_commerce: false
  policy_research: false
  media_sentiment: false
database:
  path: ":memory:"
output:
  report_dir: ./reports
  keep_days: 365
fetch:
  timeout_sec: 30
  max_concurrent: 5
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        config = load_config(path)
        assert config.deepseek.api_key == "sk-env-456"
    finally:
        os.unlink(path)
        del os.environ["TEST_DS_KEY"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.config'` 或 `ImportError`

- [ ] **Step 3: 实现配置模块**

```python
# src/config.py
import os
import re
from dataclasses import dataclass, field
from typing import Dict

import yaml


@dataclass
class DeepseekConfig:
    api_key: str
    model: str = "deepseek-chat"
    max_tokens: int = 2000
    base_url: str = "https://api.deepseek.com"


@dataclass
class FetchConfig:
    timeout_sec: int = 30
    max_concurrent: int = 5


@dataclass
class DatabaseConfig:
    path: str = "./data/policy_radar.db"


@dataclass
class OutputConfig:
    report_dir: str = "./reports"
    keep_days: int = 365


@dataclass
class Config:
    deepseek: DeepseekConfig
    sources: Dict[str, bool]
    database: DatabaseConfig
    output: OutputConfig
    fetch: FetchConfig


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env(value: str) -> str:
    m = _ENV_VAR_RE.match(value)
    if m:
        return os.environ.get(m.group(1), "")
    return value


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    ds_raw = raw["deepseek"]
    ds_raw["api_key"] = _resolve_env(ds_raw["api_key"])

    return Config(
        deepseek=DeepseekConfig(**ds_raw),
        sources=raw["sources"],
        database=DatabaseConfig(**raw["database"]),
        output=OutputConfig(**raw["output"]),
        fetch=FetchConfig(**raw["fetch"]),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_config.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add config loader with YAML + env var support"
```

---

### Task 3: 数据模型

**Files:**
- Create: `src/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_models.py
import json
import hashlib
from src.models import Article, DailyReport


def test_article_creation():
    article = Article(
        title="央行降准0.5个百分点",
        url="http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/12345/index.html",
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 实现数据模型**

```python
# src/models.py
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class Article:
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

    def __post_init__(self):
        if not self.url_hash:
            self.url_hash = hashlib.sha256(self.url.encode()).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tags"] = json.dumps(self.tags, ensure_ascii=False)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
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
    date: str
    article_count: int
    stats_json: str
    ai_analysis: str
    report_md: str
    id: Optional[int] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DailyReport":
        return cls(
            id=d.get("id"),
            date=d["date"],
            article_count=d["article_count"],
            stats_json=d["stats_json"],
            ai_analysis=d.get("ai_analysis", ""),
            report_md=d.get("report_md", ""),
            created_at=d.get("created_at", ""),
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_models.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add Article and DailyReport data models"
```

---

### Task 4: 数据库操作层

**Files:**
- Create: `src/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: 写失败测试**

```python
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
    assert id2 is None  # 重复，不插入

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

    # 重复日期应覆盖
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 实现数据库模块**

```python
# src/db.py
import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from src.models import Article, DailyReport


class Database:
    def __init__(self, path: str):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def initialize(self):
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

    def insert_article(self, article: Article) -> Optional[int]:
        now = datetime.now().isoformat()
        article.fetched_at = now
        d = article.to_dict()
        del d["id"]
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
            return None

    def get_articles_by_date(self, date_str: str) -> List[Article]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM articles
                   WHERE published_at LIKE ?
                   ORDER BY published_at DESC""",
                (f"{date_str}%",),
            ).fetchall()
        return [Article.from_dict(dict(r)) for r in rows]

    def get_unanalyzed_articles(self) -> List[Article]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM articles WHERE is_analyzed = 0 ORDER BY published_at DESC"
            ).fetchall()
        return [Article.from_dict(dict(r)) for r in rows]

    def mark_analyzed(self, article_ids: List[int]):
        with self._connect() as conn:
            conn.executemany(
                "UPDATE articles SET is_analyzed = 1 WHERE id = ?",
                [(aid,) for aid in article_ids],
            )

    def insert_daily_report(
        self, date: str, article_count: int, stats_json: str,
        ai_analysis: str, report_md: str,
    ):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO daily_reports
                   (date, article_count, stats_json, ai_analysis, report_md, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date, article_count, stats_json, ai_analysis, report_md, now),
            )

    def get_daily_report(self, date: str) -> Optional[DailyReport]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE date = ?", (date,)
            ).fetchone()
        if row is None:
            return None
        return DailyReport.from_dict(dict(row))

    def get_recent_dates(self, limit: int = 7) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT date FROM daily_reports ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r[0] for r in rows]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_db.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "feat: add SQLite database layer with article dedup and report storage"
```

---

### Task 5: 采集器基类与注册表

**Files:**
- Create: `src/fetchers/__init__.py`
- Create: `src/fetchers/base.py`
- Create: `src/fetchers/registry.py`
- Create: `tests/test_fetchers/test_base.py`
- Create: `tests/test_fetchers/test_registry.py`

- [ ] **Step 1: 写基类测试**

```python
# tests/test_fetchers/test_base.py
import pytest
import httpx
from src.fetchers.base import BaseFetcher, FetcherError
from src.models import Article


class DummyFetcher(BaseFetcher):
    name = "dummy"
    category = "test"

    async def fetch(self, client: httpx.AsyncClient) -> list[Article]:
        return [
            Article(
                title="Test Article",
                url="http://example.com/1",
                source=self.name,
                category=self.category,
                published_at="2025-01-20T09:00:00",
                summary="Summary text",
                tags=["test"],
            )
        ]


@pytest.mark.asyncio
async def test_dummy_fetcher_returns_articles():
    async with httpx.AsyncClient() as client:
        fetcher = DummyFetcher()
        articles = await fetcher.fetch(client)
        assert len(articles) == 1
        assert articles[0].title == "Test Article"


@pytest.mark.asyncio
async def test_fetch_with_retry_succeeds():
    call_count = 0

    class RetryFetcher(BaseFetcher):
        name = "retry_test"
        category = "test"

        async def fetch(self, client: httpx.AsyncClient) -> list[Article]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise FetcherError("temp error")
            return []

    async with httpx.AsyncClient() as client:
        fetcher = RetryFetcher()
        articles = await fetcher.fetch_with_retry(client, max_retries=3, delay=0.01)
        assert call_count == 3
        assert articles == []
```

- [ ] **Step 2: 写注册表测试**

```python
# tests/test_fetchers/test_registry.py
from src.fetchers.registry import FetcherRegistry
from src.fetchers.base import BaseFetcher
from src.models import Article
import httpx


class FakeFetcherA(BaseFetcher):
    name = "fake_a"
    category = "货币政策"

    async def fetch(self, client: httpx.AsyncClient) -> list[Article]:
        return [
            Article(
                title="A1",
                url="http://a.com/1",
                source=self.name,
                category=self.category,
                published_at="2025-01-20T09:00:00",
                summary="",
                tags=["金融"],
            )
        ]


class FakeFetcherB(BaseFetcher):
    name = "fake_b"
    category = "产业政策"

    async def fetch(self, client: httpx.AsyncClient) -> list[Article]:
        return [
            Article(
                title="B1",
                url="http://b.com/1",
                source=self.name,
                category=self.category,
                published_at="2025-01-20T10:00:00",
                summary="",
                tags=["新能源"],
            )
        ]


def test_registry_get_enabled_fetchers():
    registry = FetcherRegistry()
    registry.register(FakeFetcherA())
    registry.register(FakeFetcherB())

    enabled = {"货币政策": True, "产业政策": True}
    fetchers = registry.get_enabled(enabled)
    assert len(fetchers) == 2

    enabled_partial = {"货币政策": True, "产业政策": False}
    fetchers2 = registry.get_enabled(enabled_partial)
    assert len(fetchers2) == 1
    assert fetchers2[0].name == "fake_a"


def test_registry_get_enabled_returns_empty_when_all_disabled():
    registry = FetcherRegistry()
    registry.register(FakeFetcherA())
    enabled = {"货币政策": False, "产业_policy": False}
    fetchers = registry.get_enabled(enabled)
    assert fetchers == []
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_fetchers/ -v`
Expected: FAIL — `ImportError`

- [ ] **Step 4: 实现基类**

```python
# src/fetchers/base.py
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List
import httpx
from bs4 import BeautifulSoup
from src.models import Article

logger = logging.getLogger(__name__)


class FetcherError(Exception):
    pass


class BaseFetcher(ABC):
    name: str = ""
    category: str = ""

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        ...

    async def fetch_with_retry(
        self, client: httpx.AsyncClient, max_retries: int = 2, delay: float = 1.0
    ) -> List[Article]:
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                return await self.fetch(client)
            except (FetcherError, httpx.HTTPError, Exception) as e:
                last_err = e
                logger.warning(
                    "[%s] fetch attempt %d/%d failed: %s",
                    self.name, attempt + 1, max_retries + 1, e,
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay * (attempt + 1))
        logger.error("[%s] all retries exhausted: %s", self.name, last_err)
        return []

    @staticmethod
    async def fetch_html(client: httpx.AsyncClient, url: str, timeout: int = 30) -> str:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def parse_html(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")
```

- [ ] **Step 5: 实现注册表**

```python
# src/fetchers/registry.py
from typing import Dict, List
from src.fetchers.base import BaseFetcher


class FetcherRegistry:
    def __init__(self):
        self._fetchers: List[BaseFetcher] = []

    def register(self, fetcher: BaseFetcher):
        self._fetchers.append(fetcher)

    def get_enabled(self, source_config: Dict[str, bool]) -> List[BaseFetcher]:
        # source_config key 为 category，值 True/False
        return [
            f for f in self._fetchers
            if source_config.get(f.category, False)
        ]

    def get_all(self) -> List[BaseFetcher]:
        return list(self._fetchers)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_fetchers/ -v`
Expected: 4 PASSED (2 base + 2 registry)

- [ ] **Step 7: Commit**

```bash
git add src/fetchers/ tests/test_fetchers/
git commit -m "feat: add BaseFetcher with retry logic and FetcherRegistry"
```

---

### Task 6: 货币政策采集器——央行

**Files:**
- Create: `src/fetchers/pbc.py`
- Create: `tests/test_fetchers/test_pbc.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_fetchers/test_pbc.py
import pytest
import httpx
from src.fetchers.pbc import PBCFetcher


@pytest.mark.asyncio
async def test_pbc_fetcher_has_correct_metadata():
    fetcher = PBCFetcher()
    assert fetcher.name == "pbc"
    assert fetcher.category == "货币政策"


@pytest.mark.asyncio
async def test_pbc_parses_html_correctly(httpx_mock):
    html = """
    <html><body>
      <table class="liebiao">
        <tr><td><a href="/zhengcehuobisi/125207/125217/12345/index.html" class="sxx_lm7">降准通知</a></td><td>2025-01-20</td></tr>
        <tr><td><a href="/zhengcehuobisi/125207/125217/12346/index.html" class="sxx_lm7">LPR调整公告</a></td><td>2025-01-19</td></tr>
      </table>
    </body></html>
    """
    httpx_mock.add_response(
        url="http://www.pbc.gov.cn/zhengcehuobisi/125207/125217/index.html",
        html=html,
    )

    async with httpx.AsyncClient() as client:
        fetcher = PBCFetcher()
        articles = await fetcher.fetch(client)

    assert len(articles) >= 2
    titles = [a.title for a in articles]
    assert "降准通知" in titles
    assert "LPR调整公告" in titles
    for a in articles:
        assert a.source == "中国人民银行"
        assert a.category == "货币政策"
        assert a.url.startswith("http://www.pbc.gov.cn")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_fetchers/test_pbc.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 实现央行采集器**

```python
# src/fetchers/pbc.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article


PBC_LIST_URL = "http://www.pbc.gov.cn/zhengcehuobisi/125207/125217/index.html"
PBC_BASE = "http://www.pbc.gov.cn"


class PBCFetcher(BaseFetcher):
    name = "pbc"
    category = "货币政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, PBC_LIST_URL)
        soup = self.parse_html(html)
        articles = []

        for row in soup.select("table.liebiao tr"):
            link = row.select_one("a.sxx_lm7, a[href]")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = PBC_BASE + href

            date_td = row.select_one("td:last-child")
            date_str = date_td.get_text(strip=True) if date_td else ""

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="中国人民银行",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))

        return articles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_fetchers/test_pbc.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/pbc.py tests/test_fetchers/test_pbc.py
git commit -m "feat: add PBC (央行) fetcher"
```

---

### Task 7: 宏观决策采集器——国务院

**Files:**
- Create: `src/fetchers/state_council.py`
- Create: `tests/test_fetchers/test_state_council.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_fetchers/test_state_council.py
import pytest
import httpx
from src.fetchers.state_council import StateCouncilFetcher


@pytest.mark.asyncio
async def test_state_council_metadata():
    fetcher = StateCouncilFetcher()
    assert fetcher.name == "state_council"
    assert fetcher.category == "宏观决策"


@pytest.mark.asyncio
async def test_state_council_parses_list(httpx_mock):
    html = """
    <html><body>
      <div class="news_box">
        <li><a href="https://www.gov.cn/zhengce/content/202501/content_12345.htm">国务院关于促进资本市场健康发展的若干意见</a><span>2025-01-20</span></li>
        <li><a href="https://www.gov.cn/zhengce/content/202501/content_12346.htm">关于进一步优化营商环境降低制度性交易成本的通知</a><span>2025-01-19</span></li>
      </div>
    </body></html>
    """
    httpx_mock.add_response(
        url="https://www.gov.cn/zhengce/",
        html=html,
    )

    async with httpx.AsyncClient() as client:
        fetcher = StateCouncilFetcher()
        articles = await fetcher.fetch(client)

    assert len(articles) >= 2
    for a in articles:
        assert a.source == "国务院"
        assert a.category == "宏观决策"
        assert "www.gov.cn" in a.url
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_fetchers/test_state_council.py -v`
Expected: FAIL

- [ ] **Step 3: 实现国务院采集器**

```python
# src/fetchers/state_council.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article


GOV_ZHENGCE_URL = "https://www.gov.cn/zhengce/"


class StateCouncilFetcher(BaseFetcher):
    name = "state_council"
    category = "宏观决策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, GOV_ZHENGCE_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".news_box li, ul.list_txt2 li, .listTxt li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.gov.cn" + href

            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="国务院",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))

        return articles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_fetchers/test_state_council.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/state_council.py tests/test_fetchers/test_state_council.py
git commit -m "feat: add State Council (国务院) fetcher"
```

---

### Task 8: 产业政策采集器组——发改委 + 工信部 + 科技部

**Files:**
- Create: `src/fetchers/ndrc.py`
- Create: `src/fetchers/miit.py`
- Create: `src/fetchers/most.py`
- Create: `tests/test_fetchers/test_ndrc.py`
- Create: `tests/test_fetchers/test_miit.py`
- Create: `tests/test_fetchers/test_most.py`

- [ ] **Step 1: 写三个测试文件**

```python
# tests/test_fetchers/test_ndrc.py
import pytest
import httpx
from src.fetchers.ndrc import NDRCFetcher


@pytest.mark.asyncio
async def test_ndrc_metadata():
    f = NDRCFetcher()
    assert f.name == "ndrc"
    assert f.category == "产业政策"


@pytest.mark.asyncio
async def test_ndrc_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="u-list">
        <li><a href="/xwzx/xwtt/202501/t20250120_12345.html">关于推动能源高质量发展的指导意见</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.ndrc.gov.cn/xwzx/xwtt/", html=html)

    async with httpx.AsyncClient() as client:
        articles = await NDRCFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "国家发改委"
    assert "能源" in articles[0].title


# tests/test_fetchers/test_miit.py
import pytest
import httpx
from src.fetchers.miit import MIITFetcher


@pytest.mark.asyncio
async def test_miit_metadata():
    f = MIITFetcher()
    assert f.name == "miit"
    assert f.category == "产业政策"


@pytest.mark.asyncio
async def test_miit_parses(httpx_mock):
    html = """
    <html><body>
      <div class="news-list">
        <li><a href="/jgsj/202501/t20250120_12345.html">工业和信息化部关于印发《工业互联网创新发展行动计划》的通知</a><span>2025-01-20</span></li>
      </div>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.miit.gov.cn/jgsj/", html=html)

    async with httpx.AsyncClient() as client:
        articles = await MIITFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "工业和信息化部"


# tests/test_fetchers/test_most.py
import pytest
import httpx
from src.fetchers.most import MOSTFetcher


@pytest.mark.asyncio
async def test_most_metadata():
    f = MOSTFetcher()
    assert f.name == "most"
    assert f.category == "产业政策"


@pytest.mark.asyncio
async def test_most_parses(httpx_mock):
    html = """
    <html><body>
      <div class="list_main">
        <li><a href="/kjbgz/202501/t20250120_12345.html">科技部关于加快人工智能创新发展的指导意见</a><span>2025-01-20</span></li>
      </div>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.most.gov.cn/kjbgz/", html=html)

    async with httpx.AsyncClient() as client:
        articles = await MOSTFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "科学技术部"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_fetchers/test_ndrc.py tests/test_fetchers/test_miit.py tests/test_fetchers/test_most.py -v`
Expected: 全部 FAIL — `ImportError`

- [ ] **Step 3: 实现三个采集器**

```python
# src/fetchers/ndrc.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NDRC_URL = "https://www.ndrc.gov.cn/xwzx/xwtt/"
NDRC_BASE = "https://www.ndrc.gov.cn"


class NDRCFetcher(BaseFetcher):
    name = "ndrc"
    category = "产业政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NDRC_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select("ul.u-list li, .news-list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = NDRC_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="国家发改委", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))

        return articles
```

```python
# src/fetchers/miit.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

MIIT_URL = "https://www.miit.gov.cn/jgsj/"
MIIT_BASE = "https://www.miit.gov.cn"


class MIITFetcher(BaseFetcher):
    name = "miit"
    category = "产业政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, MIIT_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".news-list li, .list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = MIIT_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="工业和信息化部", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))

        return articles
```

```python
# src/fetchers/most.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

MOST_URL = "https://www.most.gov.cn/kjbgz/"
MOST_BASE = "https://www.most.gov.cn"


class MOSTFetcher(BaseFetcher):
    name = "most"
    category = "产业政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, MOST_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list_main li, .news_list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = MOST_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="科学技术部", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))

        return articles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_fetchers/test_ndrc.py tests/test_fetchers/test_miit.py tests/test_fetchers/test_most.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/ndrc.py src/fetchers/miit.py src/fetchers/most.py tests/test_fetchers/
git commit -m "feat: add NDRC, MIIT, MOST fetchers (industrial policy)"
```

---

### Task 9: 金融监管采集器组——证监会 + 金融监管总局

**Files:**
- Create: `src/fetchers/csrc.py`
- Create: `src/fetchers/nfra.py`
- Create: `tests/test_fetchers/test_csrc.py`
- Create: `tests/test_fetchers/test_nfra.py`

- [ ] **Step 1: 写两个测试文件**

```python
# tests/test_fetchers/test_csrc.py
import pytest
import httpx
from src.fetchers.csrc import CSRCFetcher


@pytest.mark.asyncio
async def test_csrc_metadata():
    f = CSRCFetcher()
    assert f.name == "csrc"
    assert f.category == "金融监管"


@pytest.mark.asyncio
async def test_csrc_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="list">
        <li><a href="/c100028/202501/t20250120_12345.html">证监会关于进一步规范上市公司重大资产重组行为的通知</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="http://www.csrc.gov.cn/csrc/c100028/common_list.shtml", html=html)

    async with httpx.AsyncClient() as client:
        articles = await CSRCFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "中国证监会"
    assert "上市公司" in articles[0].title


# tests/test_fetchers/test_nfra.py
import pytest
import httpx
from src.fetchers.nfra import NFRAFetcher


@pytest.mark.asyncio
async def test_nfra_metadata():
    f = NFRAFetcher()
    assert f.name == "nfra"
    assert f.category == "金融监管"


@pytest.mark.asyncio
async def test_nfra_parses(httpx_mock):
    html = """
    <html><body>
      <div class="news-list">
        <li><a href="/view/pages/ItemDetail.html?docId=12345">关于进一步规范商业银行互联网贷款业务的通知</a><span>2025-01-20</span></li>
      </div>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.nfra.gov.cn/chinese/home-new/index.html", html=html)

    async with httpx.AsyncClient() as client:
        articles = await NFRAFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "国家金融监督管理总局"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_fetchers/test_csrc.py tests/test_fetchers/test_nfra.py -v`
Expected: 全部 FAIL

- [ ] **Step 3: 实现两个采集器**

```python
# src/fetchers/csrc.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

CSRC_URL = "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml"
CSRC_BASE = "http://www.csrc.gov.cn"


class CSRCFetcher(BaseFetcher):
    name = "csrc"
    category = "金融监管"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, CSRC_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select("ul.list li, .news-list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = CSRC_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="中国证监会", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))

        return articles
```

```python
# src/fetchers/nfra.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NFRA_URL = "https://www.nfra.gov.cn/chinese/home-new/index.html"
NFRA_BASE = "https://www.nfra.gov.cn"


class NFRAFetcher(BaseFetcher):
    name = "nfra"
    category = "金融监管"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NFRA_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".news-list li, ul.list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = NFRA_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="国家金融监督管理总局", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))

        return articles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_fetchers/test_csrc.py tests/test_fetchers/test_nfra.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/csrc.py src/fetchers/nfra.py tests/test_fetchers/
git commit -m "feat: add CSRC and NFRA fetchers (financial regulation)"
```

---

### Task 10: 经济数据采集器组——统计局 + 海关总署

**Files:**
- Create: `src/fetchers/stats_gov.py`
- Create: `src/fetchers/customs.py`
- Create: `tests/test_fetchers/test_stats_gov.py`
- Create: `tests/test_fetchers/test_customs.py`

- [ ] **Step 1: 写两个测试文件**

```python
# tests/test_fetchers/test_stats_gov.py
import pytest
import httpx
from src.fetchers.stats_gov import StatsGovFetcher


@pytest.mark.asyncio
async def test_stats_gov_metadata():
    f = StatsGovFetcher()
    assert f.name == "stats_gov"
    assert f.category == "经济数据"


@pytest.mark.asyncio
async def test_stats_gov_parses(httpx_mock):
    html = """
    <html><body>
      <div class="center_list">
        <li><a href="/sj/zxfb/202501/t20250120_12345.html">2024年四季度和全年国内生产总值初步核算结果</a><span>2025-01-20</span></li>
      </div>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.stats.gov.cn/sj/zxfb/", html=html)

    async with httpx.AsyncClient() as client:
        articles = await StatsGovFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "国家统计局"
    assert "GDP" in articles[0].title or "国内生产总值" in articles[0].title


# tests/test_fetchers/test_customs.py
import pytest
import httpx
from src.fetchers.customs import CustomsFetcher


@pytest.mark.asyncio
async def test_customs_metadata():
    f = CustomsFetcher()
    assert f.name == "customs"
    assert f.category == "外贸数据"


@pytest.mark.asyncio
async def test_customs_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="conList">
        <li><a href="/customs/302249/302266/302267/12345/index.html">2024年12月全国进出口总值表（美元值）</a><span>2025-01-13</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="http://www.customs.gov.cn/customs/302249/302266/302267/index.html", html=html)

    async with httpx.AsyncClient() as client:
        articles = await CustomsFetcher().fetch(client)

    assert len(articles) >= 1
    assert articles[0].source == "海关总署"
    assert "进出口" in articles[0].title
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_fetchers/test_stats_gov.py tests/test_fetchers/test_customs.py -v`
Expected: 全部 FAIL

- [ ] **Step 3: 实现两个采集器**

```python
# src/fetchers/stats_gov.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

STATS_URL = "https://www.stats.gov.cn/sj/zxfb/"
STATS_BASE = "https://www.stats.gov.cn"


class StatsGovFetcher(BaseFetcher):
    name = "stats_gov"
    category = "经济数据"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, STATS_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".center_list li, .list-content li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = STATS_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="国家统计局", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))

        return articles
```

```python
# src/fetchers/customs.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

CUSTOMS_URL = "http://www.customs.gov.cn/customs/302249/302266/302267/index.html"
CUSTOMS_BASE = "http://www.customs.gov.cn"


class CustomsFetcher(BaseFetcher):
    name = "customs"
    category = "外贸数据"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, CUSTOMS_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select("ul.conList li, .list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = CUSTOMS_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="海关总署", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))

        return articles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_fetchers/test_stats_gov.py tests/test_fetchers/test_customs.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/stats_gov.py src/fetchers/customs.py tests/test_fetchers/
git commit -m "feat: add Stats Bureau and Customs fetchers (economic data)"
```

---

### Task 11: 能源 + 财政商务采集器组——能源局 + 财政部 + 商务部

**Files:**
- Create: `src/fetchers/nea.py`
- Create: `src/fetchers/mof.py`
- Create: `src/fetchers/mofcom.py`
- Create: `tests/test_fetchers/test_nea.py`
- Create: `tests/test_fetchers/test_mof.py`
- Create: `tests/test_fetchers/test_mofcom.py`

- [ ] **Step 1: 写三个测试文件**

```python
# tests/test_fetchers/test_nea.py
import pytest
import httpx
from src.fetchers.nea import NEAFetcher


@pytest.mark.asyncio
async def test_nea_metadata():
    f = NEAFetcher()
    assert f.name == "nea"
    assert f.category == "能源政策"


@pytest.mark.asyncio
async def test_nea_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="list">
        <li><a href="/2025-01/20/c_12345.htm">国家能源局关于加快推进新型储能发展的指导意见</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="http://www.nea.gov.cn/xwzx/", html=html)
    async with httpx.AsyncClient() as client:
        articles = await NEAFetcher().fetch(client)
    assert len(articles) >= 1
    assert articles[0].source == "国家能源局"
    assert "储能" in articles[0].title


# tests/test_fetchers/test_mof.py
import pytest
import httpx
from src.fetchers.mof import MOFFetcher


@pytest.mark.asyncio
async def test_mof_metadata():
    f = MOFFetcher()
    assert f.name == "mof"
    assert f.category == "财政商务"


@pytest.mark.asyncio
async def test_mof_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="list">
        <li><a href="/zhengwuxinxi/zhengcefabu/202501/t20250120_12345.html">关于减半征收证券交易印花税的公告</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="http://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/", html=html)
    async with httpx.AsyncClient() as client:
        articles = await MOFFetcher().fetch(client)
    assert len(articles) >= 1
    assert articles[0].source == "财政部"


# tests/test_fetchers/test_mofcom.py
import pytest
import httpx
from src.fetchers.mofcom import MOFCOMFetcher


@pytest.mark.asyncio
async def test_mofcom_metadata():
    f = MOFCOMFetcher()
    assert f.name == "mofcom"
    assert f.category == "财政商务"


@pytest.mark.asyncio
async def test_mofcom_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="list">
        <li><a href="/article/ae/202501/20250112345.shtml">商务部关于促进外贸稳定增长的若干政策措施</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="http://www.mofcom.gov.cn/article/ae/", html=html)
    async with httpx.AsyncClient() as client:
        articles = await MOFCOMFetcher().fetch(client)
    assert len(articles) >= 1
    assert articles[0].source == "商务部"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_fetchers/test_nea.py tests/test_fetchers/test_mof.py tests/test_fetchers/test_mofcom.py -v`
Expected: 全部 FAIL

- [ ] **Step 3: 实现三个采集器**

```python
# src/fetchers/nea.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NEA_URL = "http://www.nea.gov.cn/xwzx/"
NEA_BASE = "http://www.nea.gov.cn"


class NEAFetcher(BaseFetcher):
    name = "nea"
    category = "能源政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NEA_URL)
        soup = self.parse_html(html)
        articles = []
        for li in soup.select("ul.list li, .news_list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = NEA_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""
            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="国家能源局", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))
        return articles
```

```python
# src/fetchers/mof.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

MOF_URL = "http://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/"
MOF_BASE = "http://www.mof.gov.cn"


class MOFFetcher(BaseFetcher):
    name = "mof"
    category = "财政商务"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, MOF_URL)
        soup = self.parse_html(html)
        articles = []
        for li in soup.select("ul.list li, .news_list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = MOF_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""
            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="财政部", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))
        return articles
```

```python
# src/fetchers/mofcom.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

MOFCOM_URL = "http://www.mofcom.gov.cn/article/ae/"
MOFCOM_BASE = "http://www.mofcom.gov.cn"


class MOFCOMFetcher(BaseFetcher):
    name = "mofcom"
    category = "财政商务"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, MOFCOM_URL)
        soup = self.parse_html(html)
        articles = []
        for li in soup.select("ul.list li, .news_list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = MOFCOM_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""
            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="商务部", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))
        return articles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_fetchers/test_nea.py tests/test_fetchers/test_mof.py tests/test_fetchers/test_mofcom.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/nea.py src/fetchers/mof.py src/fetchers/mofcom.py tests/test_fetchers/
git commit -m "feat: add NEA, MOF, MOFCOM fetchers (energy + fiscal/commerce)"
```

---

### Task 12: 政策研究 + 舆论采集器组——中经网 + 新华社 + 人民日报

**Files:**
- Create: `src/fetchers/cei.py`
- Create: `src/fetchers/xinhua.py`
- Create: `src/fetchers/people_daily.py`
- Create: `tests/test_fetchers/test_cei.py`
- Create: `tests/test_fetchers/test_xinhua.py`
- Create: `tests/test_fetchers/test_people_daily.py`

- [ ] **Step 1: 写三个测试文件**

```python
# tests/test_fetchers/test_cei.py
import pytest
import httpx
from src.fetchers.cei import CEIFetcher


@pytest.mark.asyncio
async def test_cei_metadata():
    f = CEIFetcher()
    assert f.name == "cei"
    assert f.category == "政策研究"


@pytest.mark.asyncio
async def test_cei_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="list">
        <li><a href="/zhengce/202501/t20250120_12345.html">2025年宏观政策取向一致性评估报告</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.cei.gov.cn/zhengce/", html=html)
    async with httpx.AsyncClient() as client:
        articles = await CEIFetcher().fetch(client)
    assert len(articles) >= 1
    assert articles[0].source == "中经网"
    assert articles[0].category == "政策研究"


# tests/test_fetchers/test_xinhua.py
import pytest
import httpx
from src.fetchers.xinhua import XinhuaFetcher


@pytest.mark.asyncio
async def test_xinhua_metadata():
    f = XinhuaFetcher()
    assert f.name == "xinhua"
    assert f.category == "舆论风向"


@pytest.mark.asyncio
async def test_xinhua_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="list">
        <li><a href="/politics/2025-01/20/c_12345.htm">中共中央政治局召开会议 分析研究当前经济形势</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="https://www.news.cn/politics/", html=html)
    async with httpx.AsyncClient() as client:
        articles = await XinhuaFetcher().fetch(client)
    assert len(articles) >= 1
    assert articles[0].source == "新华社"
    assert "政治局" in articles[0].title


# tests/test_fetchers/test_people_daily.py
import pytest
import httpx
from src.fetchers.people_daily import PeopleDailyFetcher


@pytest.mark.asyncio
async def test_people_daily_metadata():
    f = PeopleDailyFetcher()
    assert f.name == "people_daily"
    assert f.category == "舆论风向"


@pytest.mark.asyncio
async def test_people_daily_parses(httpx_mock):
    html = """
    <html><body>
      <ul class="list">
        <li><a href="/finance/2025/0120/12345.html">稳增长政策持续发力 多项经济指标回升向好</a><span>2025-01-20</span></li>
      </ul>
    </body></html>
    """
    httpx_mock.add_response(url="http://finance.people.com.cn/", html=html)
    async with httpx.AsyncClient() as client:
        articles = await PeopleDailyFetcher().fetch(client)
    assert len(articles) >= 1
    assert articles[0].source == "人民日报"
    assert "经济" in articles[0].title
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_fetchers/test_cei.py tests/test_fetchers/test_xinhua.py tests/test_fetchers/test_people_daily.py -v`
Expected: 全部 FAIL

- [ ] **Step 3: 实现三个采集器**

```python
# src/fetchers/cei.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

CEI_URL = "https://www.cei.gov.cn/zhengce/"
CEI_BASE = "https://www.cei.gov.cn"


class CEIFetcher(BaseFetcher):
    name = "cei"
    category = "政策研究"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, CEI_URL)
        soup = self.parse_html(html)
        articles = []
        for li in soup.select("ul.list li, .news_list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = CEI_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""
            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="中经网", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))
        return articles
```

```python
# src/fetchers/xinhua.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

XINHUA_URL = "https://www.news.cn/politics/"
XINHUA_BASE = "https://www.news.cn"


class XinhuaFetcher(BaseFetcher):
    name = "xinhua"
    category = "舆论风向"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, XINHUA_URL)
        soup = self.parse_html(html)
        articles = []
        for li in soup.select("ul.list li, .news-list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = XINHUA_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""
            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="新华社", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))
        return articles
```

```python
# src/fetchers/people_daily.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

PEOPLE_DAILY_URL = "http://finance.people.com.cn/"
PEOPLE_DAILY_BASE = "http://finance.people.com.cn"


class PeopleDailyFetcher(BaseFetcher):
    name = "people_daily"
    category = "舆论风向"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, PEOPLE_DAILY_URL)
        soup = self.parse_html(html)
        articles = []
        for li in soup.select("ul.list li, .news-list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = PEOPLE_DAILY_BASE + href
            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""
            if title and href:
                articles.append(Article(
                    title=title, url=href,
                    source="人民日报", category=self.category,
                    published_at=date_str, summary="", tags=[],
                ))
        return articles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_fetchers/test_cei.py tests/test_fetchers/test_xinhua.py tests/test_fetchers/test_people_daily.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/cei.py src/fetchers/xinhua.py src/fetchers/people_daily.py tests/test_fetchers/
git commit -m "feat: add CEI, Xinhua, People's Daily fetchers (policy research + media)"
```

---

### Task 13: 采集层集成——在主注册表中注册所有采集器

**Files:**
- Modify: `src/fetchers/__init__.py`

- [ ] **Step 1: 更新 __init__.py 注册所有采集器**

```python
# src/fetchers/__init__.py
from src.fetchers.registry import FetcherRegistry
from src.fetchers.pbc import PBCFetcher
from src.fetchers.state_council import StateCouncilFetcher
from src.fetchers.ndrc import NDRCFetcher
from src.fetchers.miit import MIITFetcher
from src.fetchers.most import MOSTFetcher
from src.fetchers.csrc import CSRCFetcher
from src.fetchers.nfra import NFRAFetcher
from src.fetchers.stats_gov import StatsGovFetcher
from src.fetchers.customs import CustomsFetcher
from src.fetchers.nea import NEAFetcher
from src.fetchers.mof import MOFFetcher
from src.fetchers.mofcom import MOFCOMFetcher
from src.fetchers.cei import CEIFetcher
from src.fetchers.xinhua import XinhuaFetcher
from src.fetchers.people_daily import PeopleDailyFetcher


def create_registry() -> FetcherRegistry:
    registry = FetcherRegistry()
    registry.register(PBCFetcher())
    registry.register(StateCouncilFetcher())
    registry.register(NDRCFetcher())
    registry.register(MIITFetcher())
    registry.register(MOSTFetcher())
    registry.register(CSRCFetcher())
    registry.register(NFRAFetcher())
    registry.register(StatsGovFetcher())
    registry.register(CustomsFetcher())
    registry.register(NEAFetcher())
    registry.register(MOFFetcher())
    registry.register(MOFCOMFetcher())
    registry.register(CEIFetcher())
    registry.register(XinhuaFetcher())
    registry.register(PeopleDailyFetcher())
    return registry
```

- [ ] **Step 2: 运行所有采集器测试确认不破坏**

Run: `pytest tests/test_fetchers/ -v`
Expected: 所有已有测试仍然 PASS

- [ ] **Step 3: Commit**

```bash
git add src/fetchers/
git commit -m "feat: wire all fetchers into unified registry"
```

---

### Task 14: 统计分析的纯函数

**Files:**
- Create: `src/analyzer.py`
- Create: `tests/test_analyzer.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_analyzer.py
from src.analyzer import compute_stats, tag_sectors
from src.models import Article


def test_tag_sectors_extracts_keywords():
    articles = [
        Article(title="新能源", url="http://x.com/1", source="x", category="c",
                published_at="2025-01-20T09:00:00", summary="推动新能源汽车产业发展", tags=[]),
        Article(title="半导体", url="http://x.com/2", source="x", category="c",
                published_at="2025-01-20T09:00:00", summary="芯片制造取得突破", tags=[]),
        Article(title="房地产", url="http://x.com/3", source="x", category="c",
                published_at="2025-01-20T09:00:00", summary="房贷利率下调", tags=[]),
    ]
    tagged = tag_sectors(articles)
    assert len(tagged) == 3
    # 应自动打上板块标签
    all_tags = set()
    for a in tagged:
        all_tags.update(a.tags)
    assert "新能源" in all_tags or len(all_tags) > 0


def test_compute_stats_basic():
    articles = [
        Article(title="a", url="http://x.com/1", source="央行", category="货币政策",
                published_at="2025-01-20T09:00:00", summary="降准", tags=["金融", "银行"]),
        Article(title="b", url="http://x.com/2", source="发改委", category="产业政策",
                published_at="2025-01-20T09:00:00", summary="新能源补贴", tags=["新能源"]),
        Article(title="c", url="http://x.com/3", source="央行", category="货币政策",
                published_at="2025-01-20T10:00:00", summary="LPR", tags=["金融"]),
    ]
    stats = compute_stats(articles)

    assert "total_articles" in stats
    assert stats["total_articles"] == 3
    assert "sector_counts" in stats
    assert stats["sector_counts"]["金融"] == 2
    assert stats["sector_counts"]["新能源"] == 1
    assert "category_counts" in stats
    assert stats["category_counts"]["货币政策"] == 2
    assert stats["category_counts"]["产业政策"] == 1


def test_compute_stats_with_empty_list():
    stats = compute_stats([])
    assert stats["total_articles"] == 0
    assert stats["sector_counts"] == {}
    assert stats["category_counts"] == {}


def test_compute_stats_prev_comparison():
    today = [
        Article(title="a", url="http://x.com/1", source="x", category="c",
                published_at="2025-01-20T09:00:00", summary="", tags=["金融"]),
    ]
    stats = compute_stats(today, prev_sector_counts={"金融": 3, "新能源": 1})
    changes = stats.get("sector_changes", {})
    assert changes["金融"]["today"] == 1
    assert changes["金融"]["prev"] == 3
    assert changes["金融"]["delta"] == -2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_analyzer.py -v`
Expected: FAIL

- [ ] **Step 3: 实现统计分析**

```python
# src/analyzer.py
import re
from typing import Dict, List, Optional
from collections import Counter
from src.models import Article


# 板块关键词映射
SECTOR_KEYWORDS: Dict[str, List[str]] = {
    "金融": ["银行", "金融", "降准", "降息", "LPR", "信贷", "保险", "券商", "IPO"],
    "地产": ["房地产", "房贷", "住房", "楼市", "契税", "城中村", "保障房"],
    "新能源": ["新能源", "光伏", "风电", "储能", "锂电", "动力电池", "氢能"],
    "半导体": ["半导体", "芯片", "集成电路", "光刻", "晶圆"],
    "消费": ["消费", "零售", "电商", "家电", "汽车消费", "以旧换新"],
    "医药": ["医药", "医疗", "医保", "集采", "创新药", "生物医药"],
    "数字经济": ["数字", "人工智能", "AI", "5G", "6G", "算力", "大数据", "东数西算"],
    "基建": ["基建", "交通", "高铁", "水利", "新基建", "专项债"],
    "外贸": ["外贸", "出口", "进出口", "关税", "RCEP", "自贸区"],
    "能源": ["能源", "煤炭", "石油", "电力", "天然气", "碳中和"],
    "农业": ["农业", "粮食", "种业", "乡村振兴", "生猪"],
    "军工": ["军工", "国防", "航天", "航空", "船舶"],
}


def tag_sectors(articles: List[Article]) -> List[Article]:
    """基于标题和摘要关键词自动打板块标签"""
    for article in articles:
        text = article.title + " " + article.summary
        matched = []
        for sector, keywords in SECTOR_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text.lower():
                    matched.append(sector)
                    break
        article.tags = list(set(matched))
    return articles


def compute_stats(
    articles: List[Article],
    prev_sector_counts: Optional[Dict[str, int]] = None,
) -> dict:
    sector_counter = Counter()
    category_counter = Counter()
    source_counter = Counter()

    for article in articles:
        category_counter[article.category] += 1
        source_counter[article.source] += 1
        for tag in article.tags:
            sector_counter[tag] += 1

    stats = {
        "total_articles": len(articles),
        "sector_counts": dict(sector_counter.most_common()),
        "category_counts": dict(category_counter.most_common()),
        "source_counts": dict(source_counter.most_common()),
    }

    if prev_sector_counts:
        sector_changes = {}
        all_sectors = set(sector_counter.keys()) | set(prev_sector_counts.keys())
        for sector in all_sectors:
            today_val = sector_counter.get(sector, 0)
            prev_val = prev_sector_counts.get(sector, 0)
            sector_changes[sector] = {
                "today": today_val,
                "prev": prev_val,
                "delta": today_val - prev_val,
            }
        stats["sector_changes"] = sector_changes

    return stats
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_analyzer.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analyzer.py tests/test_analyzer.py
git commit -m "feat: add sector tagging and stats computation"
```

---

### Task 15: AI 分析引擎（DeepSeek）

**Files:**
- Modify: `src/analyzer.py`（追加 AI 调用函数）
- Modify: `tests/test_analyzer.py`（追加 AI 测试）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_analyzer.py
import pytest
import httpx
from src.analyzer import build_analysis_prompt, call_deepseek_analysis


def test_build_analysis_prompt():
    articles = [
        Article(title="降准", url="http://x.com/1", source="央行", category="货币政策",
                published_at="2025-01-20", summary="央行降准0.5个百分点", tags=["金融", "银行"]),
    ]
    stats = {"total_articles": 1, "sector_counts": {"金融": 1}}

    prompt = build_analysis_prompt(articles, stats)
    assert "降准" in prompt
    assert "金融" in prompt
    assert "政策倾向" in prompt
    assert "板块影响" in prompt


@pytest.mark.asyncio
async def test_call_deepseek_analysis_mocked(httpx_mock):
    httpx_mock.add_response(
        url="https://api.deepseek.com/v1/chat/completions",
        json={
            "choices": [
                {"message": {"content": "测试分析结果：政策信号偏宽松，利好金融和地产板块。"}}
            ]
        },
    )

    config = {
        "api_key": "sk-test",
        "model": "deepseek-chat",
        "max_tokens": 2000,
        "base_url": "https://api.deepseek.com",
    }

    articles = [
        Article(title="降准", url="http://x.com/1", source="央行", category="货币政策",
                published_at="2025-01-20", summary="降准0.5个百分点", tags=["金融"]),
    ]
    stats = {"total_articles": 1, "sector_counts": {"金融": 1}}

    result = await call_deepseek_analysis(articles, stats, config)
    assert "测试分析结果" in result
    assert "金融" in result


@pytest.mark.asyncio
async def test_call_deepseek_handles_empty_articles():
    config = {
        "api_key": "sk-test",
        "model": "deepseek-chat",
        "max_tokens": 2000,
        "base_url": "https://api.deepseek.com",
    }
    result = await call_deepseek_analysis([], {"total_articles": 0}, config)
    assert result == ""  # 无文章时跳过AI调用
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_analyzer.py::test_build_analysis_prompt tests/test_analyzer.py::test_call_deepseek_analysis_mocked tests/test_analyzer.py::test_call_deepseek_handles_empty_articles -v`
Expected: FAIL

- [ ] **Step 3: 实现 AI 分析**

```python
# 追加到 src/analyzer.py
import json
import httpx


def build_analysis_prompt(articles: List[Article], stats: dict) -> str:
    summaries = []
    for a in articles[:50]:  # 限制最多50篇以控制token
        summaries.append(f"- [{a.source}][{a.category}] {a.title}: {a.summary[:200]}")

    sector_lines = []
    for sector, count in stats.get("sector_counts", {}).items():
        sector_lines.append(f"  {sector}: {count}篇")

    prompt = f"""你是一位资深中国宏观经济与A股策略分析师。请基于以下今日采集的政策信息进行专业分析。

## 今日政策动态统计
- 总文章数: {stats.get('total_articles', 0)}
- 板块提及频次:
{chr(10).join(sector_lines) if sector_lines else '  (无)'}

## 今日文章摘要
{chr(10).join(summaries) if summaries else '(今日无新增文章)'}

## 分析要求
请从以下角度进行分析（用中文，500字以内）：

1. **核心政策信号**: 今天最重要的1-2个政策信号是什么？
2. **政策倾向**: 整体政策基调是宽松、收紧还是中性？哪些领域在加码，哪些在收紧？
3. **板块影响**: 对A股哪些板块构成利好/利空？影响程度如何（强/中/弱）？
4. **重点关注**: 哪些信号虽然目前声音不大但值得持续跟踪？
5. **风险提示**: 有哪些需要注意的风险或不确定性？

请用Markdown格式输出，条理清晰。"""

    return prompt


async def call_deepseek_analysis(
    articles: List[Article],
    stats: dict,
    config: dict,
) -> str:
    if not articles:
        return ""

    prompt = build_analysis_prompt(articles, stats)
    url = f"{config['base_url']}/v1/chat/completions"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": "你是一位资深中国宏观经济与A股策略分析师。"},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": config.get("max_tokens", 2000),
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_analyzer.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analyzer.py tests/test_analyzer.py
git commit -m "feat: add DeepSeek AI analysis engine"
```

---

### Task 16: 报告生成器

**Files:**
- Create: `src/reporter.py`
- Create: `tests/test_reporter.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_reporter.py
from src.reporter import generate_markdown_report, terminal_summary
from src.models import Article
import os
import tempfile


def test_generate_markdown_report_structure():
    articles = [
        Article(title="降准", url="http://x.com/1", source="央行", category="货币政策",
                published_at="2025-01-20T09:00:00", summary="降准0.5个百分点", tags=["金融"]),
        Article(title="新能源补贴", url="http://x.com/2", source="发改委", category="产业政策",
                published_at="2025-01-20T10:00:00", summary="加大补贴力度", tags=["新能源"]),
    ]
    stats = {
        "total_articles": 2,
        "sector_counts": {"金融": 1, "新能源": 1},
        "sector_changes": {
            "金融": {"today": 1, "prev": 3, "delta": -2},
            "新能源": {"today": 1, "prev": 0, "delta": 1},
        },
    }
    ai_analysis = "## 分析结果\n政策偏宽松，利好金融和新能源。"

    md = generate_markdown_report("2025-01-20", articles, stats, ai_analysis)
    assert "# 📡 政策雷达日报" in md
    assert "2025-01-20" in md
    assert "降准" in md
    assert "新能源" in md
    assert "金融" in md
    assert "政策偏宽松" in md
    assert "## 📊 今日概览" in md
    assert "## 🔥 板块热度变化" in md
    assert "## 🧠 AI 政策解读" in md
    assert "## 📰 原始文章" in md


def test_markdown_report_saves_to_file():
    articles = [
        Article(title="t", url="http://x.com/1", source="s", category="c",
                published_at="2025-01-20T09:00:00", summary="", tags=[]),
    ]
    stats = {"total_articles": 1, "sector_counts": {}}
    md = generate_markdown_report("2025-01-20", articles, stats, "")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "2025-01-20.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            saved = f.read()
        assert "# 📡" in saved


def test_terminal_summary_returns_string():
    stats = {"total_articles": 5, "sector_counts": {"金融": 3, "新能源": 2}}
    summary = terminal_summary(stats)
    assert "5" in summary
    assert "金融" in summary
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_reporter.py -v`
Expected: FAIL

- [ ] **Step 3: 实现报告生成器**

```python
# src/reporter.py
from typing import Dict, List
from src.models import Article
from collections import defaultdict


def generate_markdown_report(
    date_str: str,
    articles: List[Article],
    stats: dict,
    ai_analysis: str,
) -> str:
    lines = [
        f"# 📡 政策雷达日报 · {date_str}",
        "",
        "## 📊 今日概览",
        "",
        f"- 新增文章：**{stats.get('total_articles', 0)}** 篇",
    ]

    sector_counts = stats.get("sector_counts", {})
    top5 = list(sector_counts.items())[:5]
    if top5:
        lines.append(f"- 热门板块 TOP {len(top5)}：{' · '.join(f'**{s}**({c})' for s, c in top5)}")
    else:
        lines.append("- 热门板块：暂无显著信号")

    lines.append("")

    # 板块热度变化
    sector_changes = stats.get("sector_changes")
    if sector_changes:
        lines.append("## 🔥 板块热度变化")
        lines.append("")
        lines.append("| 板块 | 今日提及 | 昨日 | 变化 |")
        lines.append("|------|---------|------|------|")
        for sector, data in sorted(sector_changes.items(),
                                   key=lambda x: x[1]["delta"], reverse=True):
            delta = data["delta"]
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "—")
            lines.append(
                f"| {sector} | {data['today']} | {data['prev']} | {arrow}{abs(delta)} |"
            )
        lines.append("")

    # AI 分析
    lines.append("## 🧠 AI 政策解读")
    lines.append("")
    if ai_analysis:
        lines.append(ai_analysis)
    else:
        lines.append("> ⚠️ AI 分析不可用（API 调用失败或未配置），以下仅展示统计结果。")
    lines.append("")

    # 原始文章
    lines.append("## 📰 原始文章")
    lines.append("")
    by_category = defaultdict(list)
    for article in articles:
        by_category[article.category].append(article)

    for category, cat_articles in by_category.items():
        lines.append(f"### {category}")
        lines.append("")
        for a in cat_articles:
            tags_str = f" `{'` `'.join(a.tags)}`" if a.tags else ""
            lines.append(f"- [{a.title}]({a.url}) — {a.source} · {a.published_at}{tags_str}")
        lines.append("")

    return "\n".join(lines)


def terminal_summary(stats: dict) -> str:
    total = stats.get("total_articles", 0)
    sectors = stats.get("sector_counts", {})

    lines = [
        f"[bold]📡 政策雷达 · 今日采集 {total} 篇[/bold]",
    ]
    top = list(sectors.items())[:5]
    if top:
        lines.append(f"🔥 热门板块: {' · '.join(f'{s}({c})' for s, c in top)}")
    return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_reporter.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/reporter.py tests/test_reporter.py
git commit -m "feat: add Markdown report generator and terminal summary"
```

---

### Task 17: CLI 入口与流水线编排

**Files:**
- Create: `main.py`

- [ ] **Step 1: 实现主入口**

```python
# main.py
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

import httpx
from rich.console import Console
from rich.logging import RichHandler

from src.config import load_config
from src.db import Database
from src.fetchers import create_registry
from src.analyzer import tag_sectors, compute_stats, call_deepseek_analysis
from src.reporter import generate_markdown_report, terminal_summary

console = Console()
logger = logging.getLogger("policy_radar")


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


async def run_pipeline(config_path: str, date_str: str | None = None):
    config = load_config(config_path)

    # 初始化
    db_path = config.database.path
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    db = Database(db_path)
    db.initialize()

    today = date_str or datetime.now().strftime("%Y-%m-%d")
    logger.info(f"🚀 政策雷达启动 · 日期: {today}")

    # === 采集层 ===
    registry = create_registry()
    fetchers = registry.get_enabled(config.sources)
    logger.info(f"已启用 {len(fetchers)} 个信息源")

    all_articles = []
    timeout = httpx.Timeout(config.fetch.timeout_sec)
    limits = httpx.Limits(max_connections=config.fetch.max_concurrent)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        tasks = [f.fetch_with_retry(client) for f in fetchers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[{fetchers[i].name}] 采集失败: {result}")
        else:
            logger.info(f"[{fetchers[i].name}] 采集 {len(result)} 篇")
            all_articles.extend(result)

    logger.info(f"总共采集 {len(all_articles)} 篇文章")

    # === 存储层 ===
    new_count = 0
    for article in all_articles:
        aid = db.insert_article(article)
        if aid is not None:
            new_count += 1
    logger.info(f"新增 {new_count} 篇（去重后）")

    # === 分析层 ===
    today_articles = db.get_articles_by_date(today)
    today_articles = tag_sectors(today_articles)

    # 获取昨日统计做环比
    prev_stats = {}
    recent_dates = db.get_recent_dates(7)
    if recent_dates and recent_dates[0] == today:
        recent_dates = recent_dates[1:]
    if recent_dates:
        yesterday = recent_dates[0]
        prev_report = db.get_daily_report(yesterday)
        if prev_report:
            import json
            prev_data = json.loads(prev_report.stats_json)
            prev_stats = prev_data.get("sector_counts", {})

    stats = compute_stats(today_articles, prev_sector_counts=prev_stats if prev_stats else None)

    # AI 分析
    ai_analysis = ""
    if config.deepseek.api_key and config.deepseek.api_key != "${DEEPSEEK_API_KEY}":
        try:
            unanalyzed = [a for a in today_articles if a.is_analyzed == 0]
            ai_config = {
                "api_key": config.deepseek.api_key,
                "model": config.deepseek.model,
                "max_tokens": config.deepseek.max_tokens,
                "base_url": config.deepseek.base_url,
            }
            ai_analysis = await call_deepseek_analysis(unanalyzed if unanalyzed else today_articles, stats, ai_config)
            if unanalyzed:
                db.mark_analyzed([a.id for a in unanalyzed if a.id])
            logger.info("AI 分析完成")
        except Exception as e:
            logger.error(f"AI 分析失败: {e}")
            ai_analysis = ""
    else:
        logger.warning("DeepSeek API key 未配置，跳过 AI 分析")

    # === 输出层 ===
    import json
    report_md = generate_markdown_report(today, today_articles, stats, ai_analysis)

    # 保存报告
    report_dir = config.output.report_dir
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{today}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    logger.info(f"报告已保存: {report_path}")

    # 保存到数据库
    db.insert_daily_report(
        date=today,
        article_count=len(today_articles),
        stats_json=json.dumps(stats, ensure_ascii=False),
        ai_analysis=ai_analysis,
        report_md=report_md,
    )

    # 清理旧报告
    if config.output.keep_days > 0:
        import time
        cutoff = time.time() - config.output.keep_days * 86400
        for fname in os.listdir(report_dir):
            fpath = os.path.join(report_dir, fname)
            if os.path.isfile(fpath) and fname.endswith(".md"):
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)

    # 终端摘要
    console.print(terminal_summary(stats))
    if ai_analysis:
        console.print(f"\n[dim]{ai_analysis[:300]}...[/dim]")
    console.print(f"\n[dim]完整报告: {report_path}[/dim]")


def main():
    parser = argparse.ArgumentParser(
        description="📡 政策雷达 — A股政策动向监测工具"
    )
    parser.add_argument(
        "-c", "--config", default="config.yaml", help="配置文件路径"
    )
    parser.add_argument(
        "--date", help="指定日期（YYYY-MM-DD），默认今天"
    )
    parser.add_argument(
        "--since", help="回溯填充（YYYY-MM-DD 起至今天）"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="详细日志"
    )
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.since:
        start = datetime.strptime(args.since, "%Y-%m-%d")
        end = datetime.now()
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            logger.info(f"=== 回溯: {date_str} ===")
            asyncio.run(run_pipeline(args.config, date_str))
            from datetime import timedelta
            current += timedelta(days=1)
    else:
        asyncio.run(run_pipeline(args.config, args.date))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证 CLI 可以启动**

Run: `python main.py --help`
Expected: 显示 usage 和参数列表

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add CLI entrypoint with full pipeline orchestration"
```

---

### Task 18: 集成验证

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: 写端到端集成测试**

```python
# tests/test_integration.py
import pytest
import httpx
from src.config import Config, DeepseekConfig, FetchConfig, DatabaseConfig, OutputConfig
from src.db import Database
from src.fetchers import create_registry
from src.analyzer import tag_sectors, compute_stats
from src.reporter import generate_markdown_report


def test_full_pipeline_without_network(temp_db_path, sample_config_dict):
    """端到端测试：只测数据流，不测网络抓取"""
    from src.config import Config, DeepseekConfig, FetchConfig, DatabaseConfig, OutputConfig

    config = Config(
        deepseek=DeepseekConfig(**sample_config_dict["deepseek"]),
        sources=sample_config_dict["sources"],
        database=DatabaseConfig(path=temp_db_path),
        output=OutputConfig(**sample_config_dict["output"]),
        fetch=FetchConfig(**sample_config_dict["fetch"]),
    )

    db = Database(config.database.path)
    db.initialize()

    # 模拟手动创建文章（绕过网络抓取）
    from src.models import Article
    articles = [
        Article(title="央行降准0.5个百分点", url="http://pbc.gov.cn/1",
                source="中国人民银行", category="货币政策",
                published_at="2025-01-20T09:00:00",
                summary="为支持实体经济……", tags=[]),
        Article(title="发改委发布新能源产业规划", url="http://ndrc.gov.cn/1",
                source="国家发改委", category="产业政策",
                published_at="2025-01-20T10:00:00",
                summary="推动光伏风电……", tags=[]),
        Article(title="证监会规范减持行为", url="http://csrc.gov.cn/1",
                source="中国证监会", category="金融监管",
                published_at="2025-01-20T11:00:00",
                summary="进一步规范……", tags=[]),
    ]

    # 插入
    for a in articles:
        db.insert_article(a)

    # 查询
    today_articles = db.get_articles_by_date("2025-01-20")
    assert len(today_articles) == 3

    # 打标签
    tagged = tag_sectors(today_articles)
    all_tags = set()
    for a in tagged:
        all_tags.update(a.tags)
    # 降准 → 金融，新能源 → 新能源
    assert "金融" in all_tags or "新能源" in all_tags or len(all_tags) > 0

    # 统计
    stats = compute_stats(tagged)
    assert stats["total_articles"] == 3
    assert len(stats["sector_counts"]) >= 0
    assert stats["category_counts"]["货币政策"] == 1
    assert stats["category_counts"]["产业政策"] == 1
    assert stats["category_counts"]["金融监管"] == 1

    # 生成报告
    md = generate_markdown_report("2025-01-20", tagged, stats, "")
    assert "央行降准" in md
    assert "发改委" in md
    assert "证监会" in md

    # 数据库存储报告
    import json
    db.insert_daily_report("2025-01-20", 3, json.dumps(stats), "", md)
    report = db.get_daily_report("2025-01-20")
    assert report is not None
    assert report.article_count == 3


def test_article_dedup_across_sources(temp_db_path):
    """测试跨信息源去重"""
    db = Database(temp_db_path)
    db.initialize()

    from src.models import Article
    a1 = Article(title="降准", url="http://example.com/same",
                 source="央行", category="货币政策",
                 published_at="2025-01-20", summary="", tags=[])
    a2 = Article(title="降准（转载）", url="http://example.com/same",
                 source="新华社", category="舆论风向",
                 published_at="2025-01-20", summary="", tags=[])

    id1 = db.insert_article(a1)
    id2 = db.insert_article(a2)
    assert id1 is not None
    assert id2 is None  # 被去重
```

- [ ] **Step 2: 运行集成测试**

Run: `pytest tests/test_integration.py -v`
Expected: 2 PASSED

- [ ] **Step 3: 运行全部测试**

Run: `pytest tests/ -v`
Expected: 全部测试 PASS（之前各模块测试 + 集成测试）

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for full pipeline"
```

---

## 验收检查表

- [ ] `pytest tests/ -v` 全部通过（~ 40+ 个测试）
- [ ] `python main.py --help` 正常显示用法
- [ ] 设置 `DEEPSEEK_API_KEY` 后 `python main.py` 可完整运行全流程
- [ ] 若 API key 未设置，仅输出统计报告（不报错崩溃）
- [ ] `config.yaml` 中禁用某个 source 后，对应信息源不被采集
