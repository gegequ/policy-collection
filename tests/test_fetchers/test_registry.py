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
    enabled = {"货币政策": False, "产业政策": False}
    fetchers = registry.get_enabled(enabled)
    assert fetchers == []
