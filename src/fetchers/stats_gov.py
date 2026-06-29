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

        for a_tag in soup.select("a[href]"):
            title = a_tag.get_text(strip=True)
            if len(title) < 15:
                continue
            href = a_tag.get("href", "")
            if href and not href.startswith("http"):
                href = STATS_BASE + href

            date_str = self.extract_date(a_tag.parent)

            articles.append(Article(
                title=title,
                url=href,
                source="国家统计局",
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
