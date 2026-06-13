# src/fetchers/state_council.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

GOV_ZHENGCE_URL = "https://www.gov.cn/zhengce/"


class StateCouncilFetcher(BaseFetcher):
    name = "state_council"
    category = "宏观决策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, GOV_ZHENGCE_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".news_box li, ul.list_txt2 li, .listTxt li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.gov.cn" + href

            span = li.select_one("span")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="国务院",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
