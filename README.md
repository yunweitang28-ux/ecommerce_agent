# 电商售后 Agent

> 基于 LangGraph + Hybrid RAG 的电商售后客服 Agent 原型，覆盖物流查询、退货退款、争议处理、发货规则、评价规则、超时规则 6 类场景。

## 📌 项目简介

本项目是一个**电商售后 Agent 原型**，重点探索三件事：

1. 用 LangGraph 管理"LLM 决策 → 工具调用 → 观察 → 再决策"的执行循环
2. 用 Hybrid RAG（BM25 + 向量 + RRF）提升长尾语义问题的检索效果
3. 用规则引擎把"能不能退/运费谁出"这类确定性判定从 LLM 手里抽出来，交给结构化规则处理

> ⚠️ 说明：本项目为**个人原型**，不接入真实电商平台，所有订单/物流数据为模拟数据。

## 🏗️ 架构概览

用户输入 → LangGraph StateGraph → chatbot 节点（LLM + System Prompt）→ 两种决策路径：

- **调用工具**：
  - `query_logistics` → SQLite（订单/物流）
  - `check_return_eligibility` → 规则引擎（return_rules.json）
  - `search_knowledge` → Hybrid RAG（6 个 KB 文件）
  - `query_tickets` → SQLite（工单）
- **直接回答**：或提示联系人工

**关于"转人工"**：当前实现为 Prompt 层面的文字提示（如"正在为您转接人工客服"），未接入真实工单系统或人工客服系统。

## 📂 项目结构

- `agent.py` — LangGraph 主流程
- `db_tools.py` — 工具层（4 个工具）
- `init_db.py` — 数据库初始化
- `data/kb/` — 知识库（6 个场景）
  - `logistics_kb.json` — 物流规范
  - `return_kb.json` — 退货规范
  - `dispute_kb.json` — 争议处理
  - `shipping_kb.json` — 发货规范
  - `review_kb.json` — 评价规范
  - `timeout_kb.json` — 超时规则
- `data/rules/` — 规则库
  - `return_rules.json` — 退货规则（结构化判定）
  - `logistics_rules.json` — 物流规则
- `data/eval/golden.jsonl` — 评测集（28 条）
- `scripts/extract_kb.py` — 数据标注 Skill
- `tests/check_data.py` — 数据完整性检查
- `tests/run_eval.py` — 评测脚本

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
| `check_return_eligibility` | 退货资格判定 | return_rules.json |
| `search_knowledge` | 政策知识检索 | 6 个 KB 文件 |
| `query_tickets` | 查工单/退款进度 | SQLite |

## 📊 评测情况

构建了 **28 条评测集**，覆盖物流查询、退换货、政策咨询、多意图、拼写错误、情绪化投诉 6 类场景。

| 阶段 | 符合标准用例数 | 主要改动 |
|---|---|---|
| 基线 | 11/28 | 初版 Agent |
| 第 2 轮 | 20/28 | 补 KB 同义词 + 5 条 Prompt 强制规则 |
| 第 3 轮 | 20/28 | 数据库补 4 字段 |
| 第 4 轮 | 25/28 | 精细化 Prompt |
| 第 5 轮 | 23/28 | 规则引擎上线 |
| 第 6 轮 | 25/28 | 修复 Prompt 分流 |

> **判定口径说明**：以上"符合标准"为**人工复核结果**——逐条比对 `golden.jsonl` 中的 `expected_tools`、`expected_kb`、`must_not`、`handoff` 字段。当前 `run_eval.py` 未实现自动判定。

## 🧩 实现要点

### 1. Hybrid RAG 检索

实现：BM25 + bge-small-zh 向量检索并行召回，通过 RRF 融合重排。

观察到的效果：

- 用例 T003（"内裤拆封能退吗"）：纯关键词检索无法召回 `KB-RET-004`，引入向量检索后命中
- 用例 T018（"定制品能退吗"）：短 Query 下 BM25 权重被稀释，通过把知识标题改为问答式修复

### 2. 规则引擎

实现：`return_rules.json` 中每条规则有 `priority` 字段，按优先级降序遍历，命中即返回。

优先级设计：

- `999` 强制转人工
- `200` 质量问题允许退货
- `170` 特殊类目未发货可取消
- `150` 特殊类目拒绝无理由
- `100` 未发货直接退款
- `90` 超 7 天拒绝
- `80` 运费判定

### 3. 数据标注 Skill

实现：`scripts/extract_kb.py` 支持"预清洗 → 分段提取 → 合并去重 → 字段校验 → ID 冲突扫描 → 自动入库"。

已跑通场景：超时规则文本（10466 字），一次提取 25 条 KB。

## 🚀 快速开始

```bash
pip install -r requirements.txt
echo "DEEPSEEK_API_KEY=sk-your-key" > .env
python init_db.py
python tests/check_data.py
python tests/run_eval.py
```

## 🎯 已知局限

- **自动评测未实现**：`run_eval.py` 目前只打印预期标准
- **转人工为文字提示**：未接入真实工单系统
- **订单数据为模拟**：`data/logistics.db` 为模拟数据
- **知识库规模有限**：6 个 KB 文件，长尾场景覆盖不足
- **未做系统性检索实验**：Hybrid RAG 的量化收益尚未系统测量

## 📄 License

本项目仅用于个人学习与作品展示。数据来源于淘宝官方规则中心的公开规则文本。

## 📮 联系方式

- GitHub: [@yunweitang28-ux](https://github.com/yunweitang28-ux)