# src/fetchers/xwlb.py
"""新闻联播文字稿采集器。

数据来源：cn.govopendata.com（开源项目，提供每日新闻联播完整文字稿）
每日约 21:00 后可获取当天内容。

采集策略：
1. 优先从每日详情页抓取完整文字稿（标题 + 正文）
2. 详情页不可用时回退到月度汇总页（仅标题）
"""

from typing import List
import re
import httpx
from bs4 import Tag, NavigableString
from src.fetchers.base import BaseFetcher
from src.models import Article
from datetime import datetime, timedelta


class XWLBFetcher(BaseFetcher):
    name = "xwlb"
    category = "新闻联播"
    tier = "一手"

    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        today = datetime.now()
        today_date = today.strftime("%Y-%m-%d")
        today_fmt = today.strftime("%Y%m%d")

        # ── 策略 1：每日详情页（完整文字稿） ──
        detail_url = f"https://cn.govopendata.com/xinwenlianbo/{today_fmt}/"
        try:
            html = await self.fetch_html(client, detail_url, timeout=20)
            articles = self._parse_detail_page(html, today_date, today_fmt)
            if articles:
                return articles
        except Exception:
            pass

        # ── 策略 2：月度汇总页回退（仅标题） ──
        return await self._fetch_from_listing(client, today, today_date, today_fmt)

    # ── 详情页解析 ──────────────────────────────────────────

    def _parse_detail_page(
        self, html: str, date_str: str, date_fmt: str
    ) -> List[Article]:
        """从每日详情页解析完整文字稿。

        页面结构：每个新闻段落的标题是 h2/h3/h4，正文是后续文本节点。
        """
        soup = self.parse_html(html)
        body = soup.find("body")
        if not body:
            return []

        segments = self._split_into_segments(body)

        articles = []
        seen_titles = set()
        for title, body_text in segments:
            title = self._clean_title(title)
            if not title or len(title) < 5:
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)
            # 跳过导航/页脚/错误信息
            skip_patterns = [
                "返回顶部", "跳转到主要内容", "对不起",
                "新闻联播 文字版", "首页",
            ]
            if any(p in title for p in skip_patterns):
                continue

            summary = body_text[:1200].strip() if body_text else ""
            # 所有文章在同一页面，URL 加唯一 fragment 避免 DB 去重误杀
            seg_idx = len(articles)
            articles.append(Article(
                title=title,
                url=f"https://cn.govopendata.com/xinwenlianbo/{date_fmt}/#seg-{seg_idx}",
                source="新闻联播",
                category=self.category,
                published_at=date_str,
                summary=summary,
                tags=[],
            ))

        return articles

    def _split_into_segments(self, body: Tag) -> List:
        """将 HTML body 按 h2/h3/h4 标题切分为 (标题, 正文) 列表。"""
        segments = []
        current_title = None
        current_body: List[str] = []

        heading_tags = {"h2", "h3", "h4"}

        for el in body.descendants:
            if isinstance(el, Tag) and el.name in heading_tags:
                title_text = el.get_text(strip=True)
                if title_text and len(title_text) >= 5:
                    if current_title:
                        segments.append((current_title, "\n".join(current_body)))
                    current_title = title_text
                    current_body = []
                continue

            # 跳过导航/脚本/样式/链接
            if isinstance(el, Tag) and el.name in {
                "nav", "script", "style", "header", "footer", "a",
            }:
                continue

            if isinstance(el, NavigableString):
                text = str(el).strip()
                if text and len(text) > 1:
                    current_body.append(text)

        if current_title:
            segments.append((current_title, "\n".join(current_body)))

        return segments

    # ── 月度汇总页回退 ──────────────────────────────────────

    async def _fetch_from_listing(
        self, client: httpx.AsyncClient,
        today: datetime, today_date: str, today_fmt: str,
    ) -> List[Article]:
        """从月度汇总页抓取标题（旧行为，summary 为空）。"""
        list_url = "https://cn.govopendata.com/xinwenlianbo/"
        try:
            html = await self.fetch_html(client, list_url, timeout=20)
        except Exception:
            return []

        soup = self.parse_html(html)
        articles = []

        for a_tag in soup.select("a[href]"):
            href = a_tag.get("href", "")
            if today_fmt not in href:
                continue
            title = a_tag.get_text(strip=True)
            if len(title) < 8:
                continue
            if "新闻联播 文字版" in title or "新闻联播" == title:
                continue

            articles.append(Article(
                title=title,
                url=f"https://cn.govopendata.com{href}",
                source="新闻联播",
                category=self.category,
                published_at=today_date,
                summary="",
                tags=[],
            ))

        if not articles:
            yesterday_fmt = (today - timedelta(days=1)).strftime("%Y%m%d")
            yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            for a_tag in soup.select("a[href]"):
                href = a_tag.get("href", "")
                if yesterday_fmt not in href:
                    continue
                title = a_tag.get_text(strip=True)
                if len(title) < 8:
                    continue
                if "新闻联播 文字版" in title:
                    continue
                articles.append(Article(
                    title=title,
                    url=f"https://cn.govopendata.com{href}",
                    source="新闻联播",
                    category=self.category,
                    published_at=yesterday_date,
                    summary="",
                    tags=[],
                ))

        return articles

    # ── 工具 ────────────────────────────────────────────────

    @staticmethod
    def _clean_title(title: str) -> str:
        """清洗标题：去日期前缀、多余空格。"""
        title = re.sub(r'^\d{4}年\d{1,2}月\d{1,2}日\s*', '', title)
        title = re.sub(r'\s*新闻联播\s*$', '', title)
        return title.strip()
