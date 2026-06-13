import pytest
import tempfile
import os


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def sample_config_dict():
    return {
        "deepseek": {
            "api_key": "sk-test",
            "model": "deepseek-chat",
            "max_tokens": 2000,
            "base_url": "https://api.deepseek.com",
        },
        "sources": {
            "货币政策": True,
            "宏观决策": False,
            "产业政策": False,
            "金融监管": False,
            "经济数据": False,
            "贸易数据": False,
            "能源政策": False,
            "财政商务": False,
            "政策研究": False,
            "媒体舆论": False,
        },
        "database": {"path": ":memory:"},
        "output": {"report_dir": "./reports", "keep_days": 365},
        "fetch": {"timeout_sec": 30, "max_concurrent": 5},
    }
