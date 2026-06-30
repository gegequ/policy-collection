# src/fetchers/ndrc.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NDRC_URL = "https://www.ndrc.gov.cn/xwdt/xwfb/"
NDRC_BASE = "https://www.ndrc.gov.cn"


class NDRCFetcher(BaseFetcher):
    name = "ndrc"
    category = "产业政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NDRC_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select("ul.u-list li, .news-list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = NDRC_BASE + href

            date_str = self.extract_date(li)

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="国家发改委",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))

        # 抓取每篇文章的正文
        for a in articles:
            if a.url:
                a.summary, date = await self.fetch_article_detail(client, a.url)
                if date:
                    a.published_at = date
                else:
                    a.published_at = ""  # 提取失败则清空，避免残留错误日期

        return articles
