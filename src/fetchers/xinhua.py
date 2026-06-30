# src/fetchers/xinhua.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

XINHUA_URL = "https://www.news.cn/fortune/index.htm"
XINHUA_BASE = "https://www.news.cn"


class XinhuaFetcher(BaseFetcher):
    name = "xinhua"
    category = "媒体舆论"
    tier = "二手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, XINHUA_URL)
        soup = self.parse_html(html)
        articles = []

        for a_tag in soup.select("a[href]"):
            title = a_tag.get_text(strip=True)
            if len(title) < 12:
                continue
            href = a_tag.get("href", "")
            # 只保留 /fortune/ 路径下的文章链接
            if "/fortune/" not in href:
                continue
            if href.startswith("/"):
                href = XINHUA_BASE + href

            date_str = self.extract_date(a_tag.parent)

            articles.append(Article(
                title=title,
                url=href,
                source="新华社",
                category=self.category,
                published_at=date_str,
                summary="",
                tags=[],
            ))

        # 抓取前 10 篇正文
        for a in articles[:10]:
            if a.url:
                a.summary, date = await self.fetch_article_detail(client, a.url)
                if date:
                    a.published_at = date
                else:
                    a.published_at = ""  # 提取失败则清空，避免残留错误日期

        return articles
