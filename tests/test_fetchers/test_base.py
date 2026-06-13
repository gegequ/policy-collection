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
