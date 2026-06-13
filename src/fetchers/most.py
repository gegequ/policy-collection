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

        for li in soup.select(".list_main li, .news-list li"):
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
                    title=title,
                    url=href,
                    source="科学技术部",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
