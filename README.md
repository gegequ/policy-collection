# 📡 政策雷达（Policy Radar）

> A 股指数基金政策动向监测工具 — 采集中国官方网站政策信息，通过统计 + AI 分析预测政策动向。

## 架构

```
采集层（15 个官网采集器）
  → 存储层（SQLite 去重 + 查询）
  → 分析层（板块统计 + DeepSeek AI）
  → 输出层（Markdown 日报 + 终端摘要）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

编辑 `config.yaml`，或设置环境变量：

```bash
# DeepSeek API key（用于 AI 分析，可选）
export DEEPSEEK_API_KEY=sk-your-key-here
```

`config.yaml` 中可按类别启用/禁用信息源：

```yaml
sources:
  货币政策: true    # 央行
  宏观决策: true    # 国务院
  产业政策: true    # 发改委/工信部/科技部
  金融监管: true    # 证监会/金融监管总局
  经济数据: true    # 统计局
  贸易数据: true    # 海关总署
  能源政策: true    # 能源局
  财政商务: true    # 财政部/商务部
  政策研究: true    # 中经网
  媒体舆论: true    # 新华社/人民日报
```

### 3. 运行

```bash
# 立即运行一次
python main.py --now

# 指定配置文件
python main.py -c myconfig.yaml
```

### 4. 定时运行

- **Windows**：任务计划程序，每天 8:00 执行 `python main.py --now`
- **Linux / macOS**：`crontab -e` 添加 `0 8 * * * cd /path/to/project && python main.py --now`

## 信息源覆盖

| 类别 | 信息源 | 采集方式 |
|------|--------|----------|
| 货币政策 | 中国人民银行（pbc） | 网页抓取 |
| 宏观决策 | 国务院政策文件库 | 网页抓取 |
| 产业政策 | 发改委 / 工信部 / 科技部 | 网页抓取 |
| 金融监管 | 证监会 / 金融监管总局 | 网页抓取 |
| 经济数据 | 国家统计局 | 网页抓取 |
| 贸易数据 | 海关总署 | 网页抓取 |
| 能源政策 | 国家能源局 | 网页抓取 |
| 财政商务 | 财政部 / 商务部 | 网页抓取 |
| 政策研究 | 中经网政策库 | 网页抓取 |
| 媒体舆论 | 新华社 / 人民日报 | 网页抓取 |

## 输出

运行后生成：
- **终端摘要**：彩色面板，一键看重点
- **Markdown 日报**：保存到 `reports/YYYY-MM-DD.md`

日报结构：
- 📊 今日概览
- 🔥 板块热度变化表（含环比）
- 🧠 AI 政策解读
- 📰 原始文章（按类别分组）

## 扩展

新增信息源只需 3 步：

1. 在 `src/fetchers/` 下创建新模块
2. 继承 `BaseFetcher`，实现 `fetch()` 方法
3. 在 `main.py` 的 `build_registry()` 中注册

```python
# src/fetchers/my_source.py
from src.fetchers.base import BaseFetcher

class MyFetcher(BaseFetcher):
    name = "my_source"
    category = "货币政策"

    async def fetch(self, client):
        html = await self.fetch_html(client, "https://example.com/news")
        soup = self.parse_html(html)
        # ... 解析逻辑
        return articles
```

## 项目结构

```
policy_radar/
├── main.py              # CLI 入口 + 管线编排
├── config.yaml          # 配置文件
├── requirements.txt     # Python 依赖
├── pyproject.toml       # 项目元数据
├── src/
│   ├── config.py        # YAML 配置加载
│   ├── models.py        # Article / DailyReport 数据模型
│   ├── db.py            # SQLite 数据库（去重/查询/日报）
│   ├── analyzer.py      # 统计引擎 + AI 分析
│   ├── reporter.py      # Markdown 日报 + 终端输出
│   └── fetchers/        # 15 个官网采集器
│       ├── base.py      # 采集器基类
│       └── registry.py  # 注册表
├── tests/               # 27 个单元测试
├── reports/             # 生成的日报
└── data/                # SQLite 数据库文件
```

## 开发

```bash
# 运行测试
pytest tests/ -v

# 安装开发依赖
pip install -r requirements.txt
```

## License

MIT
