# 政策雷达（Policy Radar）— 设计规格

> A 股指数基金政策动向监测工具 · 本地命令行 · 模块化流水线架构

**日期：** 2025-01-20  
**状态：** 已确认  
**目标：** 采集中国官方网站政策信息，通过统计 + AI 分析预测政策动向，辅助指数基金投资决策

---

## 1. 产品形态

| 维度 | 决策 |
|------|------|
| 形态 | 本地命令行工具（Python） |
| 运行方式 | cron 定时（每日 8:00）+ 手动触发 |
| 输出 | Markdown 日报 + 终端彩色摘要 |
| AI 引擎 | DeepSeek API |
| 存储 | SQLite 本地单文件 |
| 扩展 | 模块化信息源，按需增删 |

---

## 2. 整体架构

四层流水线：

```
采集层 ──→ 存储层 ──→ 分析层 ──→ 输出层
(各官网)   (SQLite)   (统计+AI)   (MD报告)
```

- **采集层：** 每个信息源一个独立 Python 模块，统一接口 `fetch() → list[Article]`
- **存储层：** SQLite，两张核心表（articles + daily_reports），URL 哈希 + 标题相似度去重
- **分析层：** 先本地统计（频次/排名/环比），再调 DeepSeek API 做语义解读
- **输出层：** Markdown 日报文件 + 终端摘要打印

---

## 3. 信息源清单

### 3.1 货币政策
- 中国人民银行·货币政策司（http://www.pbc.gov.cn/zhengcehuobisi/）
- 中国人民银行·公告

### 3.2 宏观决策
- 国务院政策文件库（https://www.gov.cn/zhengce/）
- 政治局会议通稿（新华社电讯）

### 3.3 产业政策
- 国家发改委（https://www.ndrc.gov.cn/）
- 工业和信息化部（https://www.miit.gov.cn/）
- 科学技术部（https://www.most.gov.cn/）

### 3.4 金融监管
- 中国证监会（http://www.csrc.gov.cn/）
- 国家金融监督管理总局（https://www.nfra.gov.cn/）

### 3.5 经济数据
- 国家统计局（https://www.stats.gov.cn/）

### 3.6 外贸数据
- 海关总署（http://www.customs.gov.cn/）

### 3.7 能源政策
- 国家能源局（http://www.nea.gov.cn/）

### 3.8 财政与商务
- 财政部（http://www.mof.gov.cn/）
- 商务部（http://www.mofcom.gov.cn/）

### 3.9 政策研究
- 国家信息中心·中经网政策库

### 3.10 舆论风向
- 新华社
- 人民日报经济版

---

## 4. 数据模型

### 4.1 articles 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| url_hash | TEXT UNIQUE | URL SHA256 去重指纹 |
| title | TEXT | 原始标题 |
| url | TEXT | 原文链接 |
| source | TEXT | 信息源名称 |
| category | TEXT | 类别（货币/产业/监管/数据/能源/外贸/舆论等） |
| published_at | TEXT | 原文发布时间（ISO-8601） |
| summary | TEXT | 正文前 500 字摘要 |
| tags | TEXT | JSON 数组，板块标签 |
| fetched_at | TEXT | 采集时间 |
| is_analyzed | INTEGER | 0=未分析, 1=已分析 |

### 4.2 daily_reports 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| date | TEXT UNIQUE | 日期 YYYY-MM-DD |
| article_count | INTEGER | 当日新增文章数 |
| stats_json | TEXT | 统计结果 JSON |
| ai_analysis | TEXT | DeepSeek 分析全文 |
| report_md | TEXT | 完整报告 Markdown |
| created_at | TEXT | 生成时间 |

---

## 5. 分析引擎

### 5.1 统计层（本地，无成本）

- 板块提及频次排名（消费、新能源、半导体、医药、地产、金融……）
- 环比变化（与昨日/上周对比）
- 关键词共现热度
- 按信息源类别统计发文量变化

### 5.2 AI 层（DeepSeek API）

**输入：** 当日新文章摘要列表 + 统计结果  
**Prompt 要点：**
- 提炼核心政策信号
- 判断政策倾向（宽松/收紧/中性）
- 评估对具体板块的影响方向和程度
- 标注需要重点关注的信号
- 风险提示

**成本估算：** 若每日 ~30 篇文章摘要，每次调用约 3K input + 1K output tokens，DeepSeek 定价极低，单次约 ¥0.01 以内。

---

## 6. 输出格式

### 6.1 Markdown 日报文件

保存至 `reports/YYYY-MM-DD.md`，结构：

```
# 📡 政策雷达日报 · YYYY-MM-DD

## 📊 今日概览
- 新增文章：N 篇
- 热门板块 TOP 5：...

## 🔥 板块热度变化
| 板块 | 今日提及 | 昨日 | 变化 |
|------|---------|------|------|
| ... | ... | ... | ↑/↓ |

## 🧠 AI 政策解读
(DeepSeek 分析全文)

## 📰 原始文章
### 货币政策
- [标题](URL) — 来源 · 时间
...
```

### 6.2 终端摘要

运行完成后打印彩色精简版：概览 + TOP 5 + AI 解读关键句。

---

## 7. 配置文件

`config.yaml` 结构：

```yaml
deepseek:
  api_key: ${DEEPSEEK_API_KEY}  # 支持环境变量
  model: deepseek-chat
  max_tokens: 2000

schedule:
  default_time: "08:00"

sources:
  # 均可按类别启用/禁用
  monetary_policy: true
  macro_decision: true
  industrial_policy: true
  financial_regulation: true
  economic_data: true
  trade_data: true
  energy_policy: true
  fiscal_commerce: true
  policy_research: true
  media_sentiment: true

database:
  path: "./data/policy_radar.db"

output:
  report_dir: "./reports"
  keep_days: 365  # 自动清理超过此天数的报告
```

---

## 8. 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 生态丰富（爬虫/NLP/数据处理） |
| HTTP 客户端 | httpx（异步） | 多个信息源并发采集 |
| HTML 解析 | BeautifulSoup4 + lxml | 中文网页兼容好 |
| 数据库 | SQLite（内置 sqlite3） | 零依赖，单文件 |
| 配置 | PyYAML | 简单易读 |
| CLI | argparse + rich | 终端美化输出 |
| 测试 | pytest | 标准工具 |
| 调度 | 系统 cron / 任务计划程序 | 不需要额外服务 |

---

## 9. 非功能需求

- **性能：** 全部信息源采集 < 60 秒（通过异步并发）
- **容错：** 单个信息源失败不影响其余，记录错误日志
- **降级：** DeepSeek API 不可用时，仅输出统计报告（不丢数据）
- **隐私：** 所有数据存本地，不上传任何第三方
- **可扩展：** 新增信息源只需新增一个模块文件 + 注册到配置
