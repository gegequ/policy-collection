"""采集器基础框架。

提供所有信息源采集器的抽象基类和数据采集的通用工具：
- BaseFetcher: 异步采集器抽象基类（含重试逻辑）
- FetcherError: 采集异常
- 工具函数：fetch_html / parse_html
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List

import httpx
from bs4 import BeautifulSoup

from src.models import Article

logger = logging.getLogger(__name__)


class FetcherError(Exception):
    """采集器可恢复异常。

    触发重试逻辑，不会中断整个管线。
    """
    pass


class BaseFetcher(ABC):
    """采集器抽象基类。

    每个信息源对应一个子类，需实现：
    - name: 采集器标识（用于日志/注册）
    - category: 信息类别（如 "货币政策"，与 config.yaml 中 sources key 对应）
    - fetch(): 异步采集方法

    Usage:
        class MyFetcher(BaseFetcher):
            name = "my_source"
            category = "货币政策"

            async def fetch(self, client):
                html = await self.fetch_html(client, URL)
                soup = self.parse_html(html)
                # ... 解析并返回 List[Article]
    """

    name: str = ""
    category: str = ""
    tier: str = "一手"  # 一手=政府官方来源, 二手=媒体/研究机构

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> List[Article]:
        """执行采集逻辑，子类必须实现。

        Args:
            client: 共享的 httpx.AsyncClient 实例。

        Returns:
            采集到的 Article 列表，空列表表示无新文章。
        """
        ...

    async def fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        max_retries: int = 2,
        delay: float = 1.0,
    ) -> List[Article]:
        """带重试的采集包装。

        指数退避重试策略：delay * (attempt + 1)。

        Args:
            client: httpx 客户端。
            max_retries: 最大重试次数（总尝试 = max_retries + 1）。
            delay: 基准延时秒数。

        Returns:
            采集到的 Article 列表；全部重试失败返回空列表。
        """
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await self.fetch(client)
            except (FetcherError, httpx.HTTPError, Exception) as e:
                last_err = e
                logger.warning(
                    "[%s] fetch attempt %d/%d failed: %s",
                    self.name,
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay * (attempt + 1))

        logger.error("[%s] all retries exhausted: %s", self.name, last_err)
        return []

    # ── 工具方法 ──────────────────────────────────────────────

    # 浏览器 UA，避免被反爬拦截
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    @staticmethod
    async def fetch_html(
        client: httpx.AsyncClient,
        url: str,
        timeout: int = 30,
    ) -> str:
        """获取网页 HTML 源码。

        Args:
            client: httpx 客户端。
            url: 目标 URL。
            timeout: 超时秒数。

        Returns:
            HTML 文本。

        Raises:
            httpx.HTTPError: HTTP 错误（触发重试）。
        """
        resp = await client.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers=BaseFetcher.DEFAULT_HEADERS,
        )
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def extract_date(element) -> str:
        """从 HTML 元素中提取日期。支持 YYYY-MM-DD、YYYY年MM月DD、MM-DD 等格式。"""
        import re as _re
        text = element.get_text(strip=True) if hasattr(element, 'get_text') else str(element)
        if not text:
            return ""
        patterns = [
            (r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', True),  # 2026-06-18
            (r'(\d{4}年\d{1,2}月\d{1,2}日)', True),      # 2026年6月18日
            (r'(\d{1,2}[-/]\d{1,2})', False),              # 06-18
        ]
        for p, is_full in patterns:
            m = _re.search(p, text)
            if m:
                d = m.group(1)
                if '年' in d:
                    parts = _re.findall(r'\d+', d)
                    return f"{parts[0]}-{parts[1]:0>2}-{parts[2]:0>2}" if len(parts) == 3 else d
                if not is_full:
                    import datetime as _dt
                    sep = '-' if '-' in d else '/'
                    parts = d.split(sep)
                    return f"{_dt.datetime.now().year}-{parts[0]:0>2}-{parts[1]:0>2}"
                return d.replace('/', '-')
        return text[:10] if text else ""

    @staticmethod
    def parse_html(html: str) -> BeautifulSoup:
        """使用 lxml 解析 HTML。"""
        return BeautifulSoup(html, "lxml")

    @staticmethod
    async def fetch_article_body(
        client: httpx.AsyncClient, url: str, max_chars: int = 500
    ) -> str:
        """抓取文章详情页并提取正文摘要。

        尝试多种常见选择器定位正文容器，提取纯文本。

        Args:
            client: httpx 客户端。
            url: 文章详情页 URL。
            max_chars: 最大提取字符数。

        Returns:
            正文摘要文本，抓取失败返回空字符串。
        """
        try:
            resp = await client.get(
                url, timeout=15, follow_redirects=True,
                headers=BaseFetcher.DEFAULT_HEADERS,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # 去除脚本、样式、注释
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            # 尝试常见正文选择器（政府网站 + 新闻网站）
            selectors = [
                "#UCAP-CONTENT", ".article-con", ".TRS_Editor",
                ".Custom_UnionStyle", ".article-content", ".news-content",
                ".content", "article", ".article", ".post-body",
                ".entry-content", ".main-content",
            ]
            body = None
            for sel in selectors:
                body = soup.select_one(sel)
                if body:
                    break

            if body is None:
                body = soup  # fallback: 全文

            text = body.get_text(separator="\n", strip=True)
            # 清理多余空行
            lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 10]
            return "\n".join(lines)[:max_chars]
        except Exception:
            return ""

    @staticmethod
    def extract_body_sync(html: str, max_chars: int = 500) -> str:
        """同步版正文提取（用于测试或已有 HTML）。"""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        selectors = [
            "#UCAP-CONTENT", ".article-con", ".TRS_Editor",
            ".Custom_UnionStyle", ".article-content", ".news-content",
            ".content", "article", ".article",
        ]
        for sel in selectors:
            body = soup.select_one(sel)
            if body:
                text = body.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 10]
                return "\n".join(lines)[:max_chars]
        text = soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 10]
        return "\n".join(lines)[:max_chars]
