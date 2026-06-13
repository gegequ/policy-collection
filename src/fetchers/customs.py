# src/fetchers/customs.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

CUSTOMS_URL = "http://www.customs.gov.cn/customs/xwfb34/302425/302426/index.html"
CUSTOMS_BASE = "http://www.customs.gov.cn"


class CustomsFetcher(BaseFetcher):
    name = "customs"
    category = "贸易数据"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, CUSTOMS_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .con-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = CUSTOMS_BASE + href

            span = li.select_one("span, .date")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="海关总署",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
