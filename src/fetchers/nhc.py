# src/fetchers/nhc.py
"""国家卫生健康委员会 — 医药卫生政策"""

from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NHC_URL = "http://www.nhc.gov.cn/wjw/xwdt/list.shtml"
NHC_BASE = "http://www.nhc.gov.cn"


class NHCFetcher(BaseFetcher):
    name = "nhc"
    category = "医药卫生"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NHC_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .news-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = NHC_BASE + href
            date_str = self.extract_date(li)

            if title and href:
                articles.append(Article(
                    title=title, url=href, source="国家卫健委",
                    category=self.category, published_at=date_str,
                    summary="", tags=[],
                ))
        return articles
