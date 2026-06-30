# src/fetchers/nea.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

NEA_URL = "https://www.nea.gov.cn/"
NEA_BASE = "https://www.nea.gov.cn"


class NEAFetcher(BaseFetcher):
    name = "nea"
    category = "能源政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, NEA_URL)
        soup = self.parse_html(html)
        articles = []

        for a_tag in soup.select("a[href]"):
            title = a_tag.get_text(strip=True)
            if len(title) < 15:
                continue
            href = a_tag.get("href", "")
            # nea 文章 URL 格式：20250625/xxxx/c.html 或 /2025-04/10/c_xxxx.htm
            if "/c.html" not in href and "/c_" not in href:
                continue
            if href.startswith(".."):
                href = NEA_BASE + href[2:]
            elif href.startswith("/"):
                href = NEA_BASE + href
            elif not href.startswith("http"):
                href = NEA_BASE + "/" + href

            date_str = self.extract_date(a_tag.parent)

            articles.append(Article(
                title=title,
                url=href,
                source="国家能源局",
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
