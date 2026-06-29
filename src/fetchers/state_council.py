# src/fetchers/state_council.py
import logging
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

logger = logging.getLogger(__name__)

GOV_ZHENGCE_URL = "https://www.gov.cn/zhengce/"


class StateCouncilFetcher(BaseFetcher):
    name = "state_council"
    category = "宏观决策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        # gov.cn/zhengce/ 是 JS 渲染页面，需要 Playwright
        try:
            html = await self.fetch_html_js(GOV_ZHENGCE_URL)
        except Exception as e:
            logger.warning("Playwright 抓取失败，回退到 httpx: %s", e)
            html = await self.fetch_html(client, GOV_ZHENGCE_URL)

        soup = self.parse_html(html)
        articles = []

        for a_tag in soup.select("a[href]"):
            title = a_tag.get_text(strip=True)
            if len(title) < 15:
                continue
            href = a_tag.get("href", "")
            # 只保留 gov.cn/zhengce/content/ 的政策文件链接
            if "/zhengce/content/" not in href:
                continue
            if href.startswith("/"):
                href = "https://www.gov.cn" + href

            date_str = self.extract_date(a_tag.parent)

            articles.append(Article(
                title=title,
                url=href,
                source="国务院",
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
