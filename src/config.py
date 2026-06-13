"""配置加载模块。

从 YAML 配置文件加载系统配置，支持 `${ENV_VAR}` 环境变量替换。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict

import yaml


@dataclass
class DeepseekConfig:
    """DeepSeek API 配置。

    Attributes:
        api_key: API 密钥，支持 `${ENV_VAR}` 格式引用环境变量。
        model: 模型名称，默认 `deepseek-chat`。
        max_tokens: 单次最大输出 token 数。
        base_url: API 端点 URL。
    """

    api_key: str
    model: str = "deepseek-chat"
    max_tokens: int = 2000
    base_url: str = "https://api.deepseek.com"


@dataclass
class FetchConfig:
    """采集器运行参数。

    Attributes:
        timeout_sec: 单个请求超时秒数。
        max_concurrent: 最大并发连接数。
    """

    timeout_sec: int = 30
    max_concurrent: int = 5


@dataclass
class DatabaseConfig:
    """SQLite 数据库配置。

    Attributes:
        path: 数据库文件路径，`:memory:` 表示使用内存数据库。
    """

    path: str = "./data/policy_radar.db"


@dataclass
class OutputConfig:
    """报告输出配置。

    Attributes:
        report_dir: 日报 Markdown 文件保存目录。
        keep_days: 保留天数，超期自动清理；0 表示不清理。
    """

    report_dir: str = "./reports"
    keep_days: int = 365


@dataclass
class Config:
    """顶层配置聚合。

    Attributes:
        deepseek: DeepSeek API 配置。
        sources: 信息源启用配置，key 为类别名，value 为是否启用。
        database: 数据库配置。
        output: 输出配置。
        fetch: 采集参数配置。
    """

    deepseek: DeepseekConfig
    sources: Dict[str, bool]
    database: DatabaseConfig
    output: OutputConfig
    fetch: FetchConfig


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env(value: str) -> str:
    """解析 `${ENV_VAR}` 格式的环境变量引用。

    Args:
        value: 原始值，可能是 `$VAR` 或 `${VAR}` 或普通字符串。

    Returns:
        环境变量的值（不存在则返回空字符串），非引用格式原样返回。
    """
    m = _ENV_VAR_RE.match(value)
    if m:
        return os.environ.get(m.group(1), "")
    return value


def load_config(path: str = "config.yaml") -> Config:
    """从 YAML 文件加载并解析配置。

    Args:
        path: 配置文件路径。

    Returns:
        解析完成的 Config 对象。

    Raises:
        FileNotFoundError: 配置文件不存在。
        KeyError: 配置文件缺少必要字段。
        yaml.YAMLError: YAML 格式错误。
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"配置文件为空: {path}")

    ds_raw = raw.get("deepseek", {})
    ds_raw["api_key"] = _resolve_env(ds_raw.get("api_key", ""))

    return Config(
        deepseek=DeepseekConfig(**{k: v for k, v in ds_raw.items()
                                   if k in DeepseekConfig.__dataclass_fields__}),
        sources=raw.get("sources", {}),
        database=DatabaseConfig(**raw.get("database", {})),
        output=OutputConfig(**raw.get("output", {})),
        fetch=FetchConfig(**raw.get("fetch", {})),
    )
