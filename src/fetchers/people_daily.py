# src/fetchers/people_daily.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

PEOPLE_URL = "http://finance.people.com.cn/"
PEOPLE_BASE = "http://finance.people.com.cn"


class PeopleDailyFetcher(BaseFetcher):
    name = "people_daily"
    category = "媒体舆论"
    tier = "二手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, PEOPLE_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .news-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = PEOPLE_BASE + href

            date_str = self.extract_date(li)

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="人民日报",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
