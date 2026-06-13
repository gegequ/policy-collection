# src/fetchers/stats_gov.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

STATS_URL = "https://www.stats.gov.cn/sj/"
STATS_BASE = "https://www.stats.gov.cn"


class StatsGovFetcher(BaseFetcher):
    name = "stats_gov"
    category = "经济数据"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, STATS_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list_main li, .news-list li, ul.pub_list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = STATS_BASE + href

            span = li.select_one("span, em")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="国家统计局",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
