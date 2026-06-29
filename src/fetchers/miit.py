# src/fetchers/miit.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

MIIT_URL = "https://www.miit.gov.cn/xwdt/"
MIIT_BASE = "https://www.miit.gov.cn"


class MIITFetcher(BaseFetcher):
    name = "miit"
    category = "产业政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, MIIT_URL)
        soup = self.parse_html(html)
        articles = []

        for a_tag in soup.select("a[href]"):
            title = a_tag.get_text(strip=True)
            if len(title) < 12:
                continue
            href = a_tag.get("href", "")
            # 跳过非本站链接和导航链接
            if "miit.gov.cn" not in href and not href.startswith("/"):
                continue
            if href.startswith("/"):
                href = MIIT_BASE + href

            date_str = self.extract_date(a_tag.parent)

            articles.append(Article(
                title=title,
                url=href,
                source="工业和信息化部",
                category=self.category,
                published_at=date_str,
                summary="",
                tags=[],
            ))

        # 抓取前 10 篇正文
        for a in articles[:10]:
            if a.url:
                a.summary = await self.fetch_article_body(client, a.url)
                date = await self.fetch_article_date(client, a.url)
                if date:
                    a.published_at = date
                else:
                    a.published_at = ""  # 提取失败则清空，避免残留错误日期

        return articles
