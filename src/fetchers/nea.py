# src/fetchers/nea.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NEA_URL = "https://www.nea.gov.cn/xwzx/nyyw.htm"
NEA_BASE = "http://www.nea.gov.cn"


class NEAFetcher(BaseFetcher):
    name = "nea"
    category = "能源政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NEA_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .news-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = NEA_BASE + href

            date_str = self.extract_date(li)

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="国家能源局",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
