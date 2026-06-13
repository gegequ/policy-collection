# tests/test_config.py
import os
import tempfile
from src.config import load_config


def test_load_config_parses_yaml():
    yaml_content = """
deepseek:
  api_key: sk-abc123
  model: deepseek-chat
  max_tokens: 2000
  base_url: https://api.deepseek.com
sources:
  货币政策: true
  宏观决策: false
  产业政策: true
  金融监管: false
  经济数据: false
  贸易数据: false
  能源政策: false
  财政商务: false
  政策研究: false
  媒体舆论: false
database:
  path: ./data/test.db
output:
  report_dir: ./reports
  keep_days: 30
fetch:
  timeout_sec: 15
  max_concurrent: 10
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        config = load_config(path)
        assert config.deepseek.api_key == "sk-abc123"
        assert config.deepseek.model == "deepseek-chat"
        assert config.sources["货币政策"] is True
        assert config.sources["宏观决策"] is False
        assert config.database.path == "./data/test.db"
        assert config.fetch.timeout_sec == 15
    finally:
        os.unlink(path)


def test_load_config_resolves_env_var():
    os.environ["TEST_DS_KEY"] = "sk-env-456"
    yaml_content = """
deepseek:
  api_key: ${TEST_DS_KEY}
  model: deepseek-chat
  max_tokens: 2000
  base_url: https://api.deepseek.com
sources:
  货币政策: true
  宏观决策: false
  产业政策: false
  金融监管: false
  经济数据: false
  贸易数据: false
  能源政策: false
  财政商务: false
  政策研究: false
  媒体舆论: false
database:
  path: ":memory:"
output:
  report_dir: ./reports
  keep_days: 365
fetch:
  timeout_sec: 30
  max_concurrent: 5
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        config = load_config(path)
        assert config.deepseek.api_key == "sk-env-456"
    finally:
        os.unlink(path)
        del os.environ["TEST_DS_KEY"]
