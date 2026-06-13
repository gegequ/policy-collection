# src/fetchers/pbc.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

PBC_LIST_URL = "http://www.pbc.gov.cn/zhengcehuobisi/125207/125217/index.html"
PBC_BASE = "http://www.pbc.gov.cn"


class PBCFetcher(BaseFetcher):
    name = "pbc"
    category = "货币政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, PBC_LIST_URL)
        soup = self.parse_html(html)
        articles = []

        for row in soup.select("table.liebiao tr"):
            link = row.select_one("a.sxx_lm7, a[href]")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = PBC_BASE + href

            date_td = row.select_one("td:last-child")
            date_str = date_td.get_text(strip=True) if date_td else ""

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="中国人民银行",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
