# src/fetchers/nfra.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NFRA_URL = "https://www.nfra.gov.cn/cn/view/pages/governmentDetail.html?governmentId=1"
NFRA_BASE = "https://www.nfra.gov.cn"


class NFRAFetcher(BaseFetcher):
    name = "nfra"
    category = "金融监管"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NFRA_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .news-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = NFRA_BASE + href

            span = li.select_one("span, .date")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="金融监管总局",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
