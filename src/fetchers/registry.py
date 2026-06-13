# src/fetchers/registry.py
from typing import Dict, List
from src.fetchers.base import BaseFetcher


class FetcherRegistry:
    def __init__(self):
        self._fetchers: List[BaseFetcher] = []

    def register(self, fetcher: BaseFetcher):
        self._fetchers.append(fetcher)

    def get_enabled(self, source_config: Dict[str, bool]) -> List[BaseFetcher]:
        return [
            f for f in self._fetchers
            if source_config.get(f.category, False)
        ]

    def get_all(self) -> List[BaseFetcher]:
        return list(self._fetchers)
