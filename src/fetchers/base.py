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
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def parse_html(html: str) -> BeautifulSoup:
        """使用 lxml 解析 HTML。

        Args:
            html: HTML 文本。

        Returns:
            BeautifulSoup 对象。
        """
        return BeautifulSoup(html, "lxml")
