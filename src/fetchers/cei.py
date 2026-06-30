# src/fetchers/cei.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

CEI_URL = "https://www.cei.cn/"
CEI_BASE = "https://www.cei.cn"


class CEIFetcher(BaseFetcher):
    name = "cei"
    category = "政策研究"
    tier = "二手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, CEI_URL, timeout=45)
        soup = self.parse_html(html)
        articles = []

        for li in soup.select(".list li, .news-list li, ul li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = CEI_BASE + href

            date_str = self.extract_date(li)

            if title and href:
                articles.append(Article(
                    title=title,
                    url=href,
                    source="中经网",
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
