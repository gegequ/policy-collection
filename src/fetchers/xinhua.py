# src/fetchers/xinhua.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

XINHUA_URL = "https://www.news.cn/fortune/"
XINHUA_BASE = "https://www.news.cn"


class XinhuaFetcher(BaseFetcher):
    name = "xinhua"
    category = "媒体舆论"
    tier = "二手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, XINHUA_URL)
        soup = self.parse_html(html)
        articles = []

        for item in soup.select(".news-list li, .list-wrap li, .data-list li"):
            link = item.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = XINHUA_BASE + href

            date_str = self.extract_date(item)

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="新华社",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
