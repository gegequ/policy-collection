# src/fetchers/pbc.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article

PBC_LIST_URL = "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html"
PBC_BASE = "http://www.pbc.gov.cn"


class PBCFetcher(BaseFetcher):
    name = "pbc"
    category = "货币政策"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, PBC_LIST_URL)
        soup = self.parse_html(html)
        articles = []

        for a_tag in soup.select("a[href]"):
            title = a_tag.get_text(strip=True)
            if len(title) < 15:
                continue
            href = a_tag.get("href", "")
            # 只保留 pbc.gov.cn 域名的新闻链接（排除外部链接）
            if "pbc.gov.cn" not in href and not href.startswith("/"):
                continue
            # 排除导航链接（纯英文/数字/短文本）
            if href.startswith("/"):
                href = PBC_BASE + href
            # 排除非新闻链接：网站导航、备案号等
            if any(kw in title for kw in ["English", "无障碍", "网站地图", "ICP", "公网安备"]):
                continue

            date_str = self.extract_date(a_tag.parent)

            articles.append(Article(
                title=title,
                url=href,
                source="中国人民银行",
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
