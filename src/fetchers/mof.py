# src/fetchers/mof.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

MOF_URL = "http://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/"
MOF_BASE = "http://www.mof.gov.cn"


class MOFFetcher(BaseFetcher):
    name = "mof"
    category = "财政商务"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, MOF_URL)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .news-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = MOF_BASE + href

            date_str = self.extract_date(li)

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="财政部",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))

        # 为前5篇抓正文
        for a in articles[:5]:
            if a.url:
                a.summary = await self.fetch_article_body(client, a.url)

        return articles
