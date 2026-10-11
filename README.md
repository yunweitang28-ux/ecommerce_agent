# 电商售后 Agent

> 基于 LangGraph + Hybrid RAG 的电商售后客服 Agent 原型，覆盖物流查询、退货退款、争议处理、发货规则、评价规则、超时规则 6 类场景。

## 📌 项目简介

本项目是一个电商售后 Agent 原型，重点探索三件事：
1. 用 LangGraph 管理"LLM 决策 → 工具调用 → 观察 → 再决策"的执行循环；
2. 用 Hybrid RAG（BM25 + 向量 + RRF）提升长尾语义问题的检索效果；
3. 用规则引擎把"能不能退/运费谁出"这类确定性判定从 LLM 手里抽出来，交给结构化规则处理。

> ⚠️ 说明：本项目为个人原型，不接入真实电商平台，所有订单/物流数据为模拟数据。

## 🏗️ 架构概览
用户输入
→ LangGraph StateGraph
→ chatbot 节点（LLM + System Prompt）
├─ 决策：调用工具
│ ├─ query_logistics → SQLite（订单/物流）
│ ├─ check_return_eligibility → 规则引擎（return_rules.json）
│ ├─ search_knowledge → Hybrid RAG（6 个 KB 文件）
│ └─ query_tickets → SQLite（工单）
└─ 决策：直接回答 / 提示联系人工

关于"转人工"**：当前实现为Prompt 层面的文字提示（如"正在为您转接人工客服"），未接入真实工单系统或人工客服系统。若后续接入，需新增 create_ticket 工具并打通下游流程。

## 📂 项目结构
ecommerce_agent/
├── data/
│ ├── kb/ # 知识库（6 个场景）
│ │ ├── logistics_kb.json # 物流规范
│ │ ├── return_kb.json # 退货规范
│ │ ├── dispute_kb.json # 争议处理
│ │ ├── shipping_kb.json # 发货规范
│ │ ├── review_kb.json # 评价规范
│ │ └── timeout_kb.json # 超时规则
│ ├── rules/
│ │ ├── return_rules.json # 退货规则（结构化判定）
│ │ └── logistics_rules.json # 物流规则
│ └── eval/
│ └── golden.jsonl # 评测集（28 条）
├── scripts/
│ └── extract_kb.py # 数据标注 Skill（从规则文本提取 KB）
├── tests/
│ ├── check_data.py # 数据完整性检查
│ └── run_eval.py # 评测脚本（当前为人工复核模式）
├── agent.py # LangGraph 主流程
├── db_tools.py # 工具层（4 个工具）
└── init_db.py # 数据库初始化

## 🔧 技术选型

| 层 | 选型 | 说明 |
|---|---|---|
| 语言/框架 | Python 3.10+ + LangGraph | Agent 工作流 |
| LLM | DeepSeek API | 决策与生成 |
| 向量模型 | bge-small-zh-v1.5 | 中文语义检索 |
| 关键词检索 | BM25 + jieba | 精确匹配 |
| 融合重排 | RRF (k=60) | BM25 + 向量结果融合 |
| 存储 | SQLite | 订单/物流/工单 |

## 🛠️ 工具层（4 个）

| 工具 | 作用 | 数据源 |
|---|---|---|
| `query_logistics` | 查订单物流/状态/金额/包邮/签收时间 | SQLite |
| `check_return_eligibility` | 退货资格判定（走规则引擎） | return_rules.json |
| `search_knowledge` | 政策知识检索（Hybrid RAG） | 6 个 KB 文件 |
| `query_tickets` | 查工单/退款进度 | SQLite |

## 📊 评测情况

构建了 28 条评测集，覆盖物流查询、退换货、政策咨询、多意图、拼写错误、情绪化投诉 6 类场景。

| 阶段 | 符合标准用例数 | 主要改动 |
|---|---|---|
| 基线 | 11/28 | 初版 Agent |
| 第 2 轮 | 20/28 | 补 KB 同义词 + 5 条 Prompt 强制规则 |
| 第 3 轮 | 20/28 | 数据库补 4 字段（金额/包邮/签收时间/退款状态） |
| 第 4 轮 | 25/28 | 精细化 Prompt（情绪阈值、包邮字段利用、签收天数自算） |
| 第 5 轮 | 23/28 | 规则引擎上线，发现政策咨询类新退化 |
| 第 6 轮 | 25/28 | 修复 Prompt：区分"通用政策咨询"与"具体订单问题" |

> 判定口径说明：以上"符合标准"为人工复核结果——逐条比对 `golden.jsonl` 中的 `expected_tools`、`expected_kb`、`must_not`、`handoff` 字段，观察 Agent 输出是否满足。当前 `run_eval.py` 未实现自动判定，自动评测能力为待办项。

## 🧩 实现要点

### 1. Hybrid RAG 检索

实现：BM25 + bge-small-zh 向量检索并行召回，通过 RRF 融合重排。

观察到的效果（基于 2 条代表性用例）：
- 用例 T003（"内裤拆封能退吗"）：纯关键词检索无法召回 `KB-RET-004`（知识库原文写的是"贴身用品"），引入向量检索后命中。
- 用例 T018（"定制品能退吗"）：短 Query（6 字）下 BM25 权重被高频词"退"稀释，向量相似度也不聚焦；最终通过**把知识标题改为问答式**修复。

> 未做系统性 Recall@K 实验，以上为两条用例的观察结果。

### 2. 规则引擎

实现：`return_rules.json` 中每条规则有 `priority` 字段，`check_return_eligibility` 按优先级降序遍历，命中即返回。

优先级设计：
- `999` 强制转人工
- `200` 质量问题允许退货（不受 7 天/类目限制）
- `170` 特殊类目未发货可取消
- `150` 特殊类目拒绝无理由
- `100` 未发货直接退款
- `90` 超 7 天拒绝
- `80` 运费判定

### 3. 数据标注 Skill

实现：`scripts/extract_kb.py` 支持"预清洗 → 分段提取 → 合并去重 → 字段校验 → ID 冲突扫描 → 自动入库"。

用途：冷启动阶段以人工精编为主，Pipeline 用于批量扩充。

已跑通场景：超时规则文本（10466 字），一次提取 25 条 KB。

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key（在项目根目录创建 .env）
echo "DEEPSEEK_API_KEY=sk-your-key" > .env

# 3. 初始化数据库
python init_db.py

# 4. 数据完整性检查
python tests/check_data.py

# 5. 运行评测（当前为人工复核模式，脚本仅打印预期）
python tests/run_eval.py
🎯 已知局限
自动评测未实现：run_eval.py 目前只打印预期标准，是否通过需要人工复核。

转人工为文字提示：未接入真实工单系统或人工客服系统。

订单数据为模拟：data/logistics.db 中为模拟数据。

知识库规模有限：6 个 KB 文件，覆盖 6 类高频场景，长尾场景覆盖仍不足。

未做系统性检索实验：Hybrid RAG 的量化收益（Recall@K）尚未系统测量。

📄 License
本项目仅用于个人学习与作品展示，未做商业用途。数据来源于淘宝官方规则中心的公开规则文本。

📮 联系方式
GitHub: [@yunweitang28-ux]
