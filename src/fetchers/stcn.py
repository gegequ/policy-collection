# src/fetchers/stcn.py
"""证券时报 — 证监会指定披露媒体，政策权威解读"""

from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

STCN_URL = "https://www.stcn.com/"
STCN_BASE = "https://www.stcn.com"


class STCNFetcher(BaseFetcher):
    name = "stcn"
    category = "财经媒体"
    tier = "二手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, STCN_URL)
        soup = self.parse_html(html)
        articles = []

        for item in soup.select(".news-list li, .list li, .article-list li, a[href*='article']"):
            link = item if item.name == "a" else item.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = STCN_BASE + href
            if not title or not href or len(title) < 5:
                continue

            span = item.select_one("span, .date, time")
            date_str = span.get_text(strip=True) if span else ""

            articles.append(Article(
                title=title, url=href, source="证券时报",
                category=self.category, published_at=date_str,
                summary="", tags=[],
            ))
        return articles[:30]
