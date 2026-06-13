# src/fetchers/nmpa.py
"""国家药品监督管理局 — 药品审评审批、创新药政策"""

from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NMPA_URL = "https://www.nmpa.gov.cn/yaopin/index.html"
NMPA_BASE = "https://www.nmpa.gov.cn"


class NMPAFetcher(BaseFetcher):
    name = "nmpa"
    category = "医药卫生"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NMPA_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .news-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = NMPA_BASE + href
            span = li.select_one("span, .date")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title, url=href, source="国家药监局",
                    category=self.category, published_at=date_str,
                    summary="", tags=[],
                ))
        return articles
