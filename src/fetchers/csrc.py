# src/fetchers/csrc.py
from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from datetime import datetime, timedelta
from src.models import Article

CSRC_URL = "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml"
CSRC_BASE = "http://www.csrc.gov.cn"

# 只采集最近90天的政策文件
MAX_AGE_DAYS = 90


class CSRCFetcher(BaseFetcher):
    name = "csrc"
    category = "金融监管"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        html = await self.fetch_html(client, CSRC_URL)
        soup = self.parse_html(html)
        articles = []
        cutoff = datetime.now() - timedelta(days=MAX_AGE_DAYS)

        for li in soup.select(".list li, .common-list li, ul.list li"):
            link = li.select_one("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = CSRC_BASE + href

            span = li.select_one("span, .date")
            date_str = span.get_text(strip=True) if span else ""

            if title and href:
                # 过滤旧文章
                try:
                    art_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    if art_date < cutoff:
                        continue
                except ValueError:
                    pass  # 无法解析的日期（如"1小时前"）保留

                articles.append(Article(
                    title=title,
                    url=href,
                    source="中国证监会",
                    category=self.category,
                    published_at=date_str,
                    summary="",
                    tags=[],
                ))
        return articles
