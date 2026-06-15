# src/fetchers/yicai.py
"""第一财经 — 财经政策快速解读"""

from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

YICAI_URL = "https://www.yicai.com/"
YICAI_BASE = "https://www.yicai.com"


class YicaiFetcher(BaseFetcher):
    name = "yicai"
    category = "财经媒体"
    tier = "二手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, YICAI_URL)
        soup = self.parse_html(html)
        articles = []

        for item in soup.select(".news-list li, .list li, a[href*='news']"):
            link = item if item.name == "a" else item.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = YICAI_BASE + href
            if not title or not href or len(title) < 5:
                continue

            span = item.select_one("span, .date, time")
            date_str = span.get_text(strip=True) if span else ""

            articles.append(Article(
                title=title, url=href, source="第一财经",
                category=self.category, published_at=date_str,
                summary="", tags=[],
            ))
        return articles[:30]
