# src/fetchers/cei.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

CEI_URL = "https://www.cei.cn/"
CEI_BASE = "https://www.cei.cn"


class CEIFetcher(BaseFetcher):
    name = "cei"
    category = "政策研究"
    tier = "二手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, CEI_URL, timeout=45)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .news-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = CEI_BASE + href

            span = li.select_one("span, .date")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="中经网",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
