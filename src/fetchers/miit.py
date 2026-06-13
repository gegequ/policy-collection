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

        for li in soup.select(".news-list li, .list_main li, ul li"):
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
                    title=title,
                    url=href,
                    source="工业和信息化部",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
