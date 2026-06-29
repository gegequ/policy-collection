# src/fetchers/csrc.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

CSRC_URL = "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml"
CSRC_BASE = "http://www.csrc.gov.cn"


class CSRCFetcher(BaseFetcher):
    name = "csrc"
    category = "金融监管"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, CSRC_URL)
        soup = self.parse_html(html)
        articles = []

        for a_tag in soup.select("a[href]"):
            title = a_tag.get_text(strip=True)
            if len(title) < 12:
                continue
            href = a_tag.get("href", "")
            # 只保留政策文章链接，排除 footer（京ICP备…）等
            if "/content.shtml" not in href:
                continue
            if href and not href.startswith("http"):
                href = CSRC_BASE + href

            date_str = self.extract_date(a_tag.parent)

            articles.append(Article(
                title=title,
                url=href,
                source="中国证监会",
                category=self.category,
                published_at=date_str,
                summary="",
                tags=[],
            ))

        # 抓取每篇文章的正文
        for a in articles:
            if a.url:
                a.summary = await self.fetch_article_body(client, a.url)
                date = await self.fetch_article_date(client, a.url)
                if date:
                    a.published_at = date
                else:
                    a.published_at = ""  # 提取失败则清空，避免残留错误日期

        return articles
