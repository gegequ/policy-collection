# src/fetchers/xwlb.py
"""新闻联播文字稿采集器。

数据来源：cn.govopendata.com（开源项目，提供每日新闻联播完整文字稿）
每日约 21:00 后可获取当天内容。
"""

from typing import List
import httpx
from src.fetchers.base import BaseFetcher
from src.models import Article
from datetime import datetime, timedelta


class XWLBFetcher(BaseFetcher):
    name = "xwlb"
    category = "新闻联播"
    tier = "一手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        today = datetime.now().strftime("%Y%m%d")
        url = f"https://cn.govopendata.com/xinwenlianbo/{today}/"

        try:
            html = await self.fetch_html(client, url, timeout=20)
        except Exception:
            # 如果今天的还没上线，尝试昨天
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            url = f"https://cn.govopendata.com/xinwenlianbo/{yesterday}/"
            try:
                html = await self.fetch_html(client, url, timeout=20)
            except Exception:
                return []

        soup = self.parse_html(html)
        articles = []

        # 新闻联播页面结构：每个新闻条目是独立的 section/article
        # 标题在 h2/h3，正文在后续的 p 标签中
        for section in soup.select("article, section, .item, .news-item"):
            title_tag = section.select_one("h2, h3, .title, strong")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if len(title) < 5:
                continue

            # 提取正文
            body_parts = []
            for p in section.select("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 10:
                    body_parts.append(text)

            summary = " ".join(body_parts)[:800] if body_parts else ""

            articles.append(Article(
                title=title,
                url=f"{url}#{title[:20]}",
                source="新闻联播",
                category=self.category,
                published_at=datetime.now().strftime("%Y-%m-%d"),
                summary=summary,
                tags=[],
            ))

        # 备选方案：如果上述选择器没抓到，尝试纯文本解析
        if not articles:
            articles = self._fallback_parse(soup, url)

        return articles

    def _fallback_parse(self, soup, url: str) -> List[Article]:
        """备选解析：从页面提取所有粗体标题+后续段落。"""
        articles = []
        strong_tags = soup.select("strong, b, h3, h4")
        for tag in strong_tags:
            title = tag.get_text(strip=True)
            if len(title) < 8:
                continue
            # 尝试获取后续文本
            next_p = tag.find_next("p")
            summary = next_p.get_text(strip=True)[:500] if next_p else ""
            articles.append(Article(
                title=title,
                url=url,
                source="新闻联播",
                category="新闻联播",
                published_at=datetime.now().strftime("%Y-%m-%d"),
                summary=summary,
                tags=[],
            ))
        return articles[:50]
