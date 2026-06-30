# src/fetchers/mof.py
from typing import List
from urllib.parse import urljoin
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
                href = urljoin(MOF_BASE + "/", href)

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

        # 为每篇文章抓正文
        for a in articles:
            if a.url:
                a.summary, date = await self.fetch_article_detail(client, a.url)
                if date:
                    a.published_at = date
                else:
                    a.published_at = ""  # 提取失败则清空，避免残留错误日期

        return articles
