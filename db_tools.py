import os
import json
import sqlite3
from langchain_core.tools import tool

# 1. 动态获取项目根目录，并定义数据库和规则文件的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'logistics.db')
RULES_PATH = os.path.join(BASE_DIR, 'data', 'rules', 'return_rules.json')


# 2. 物流查询工具
@tool
def query_logistics(order_id: str) -> str:
    """当用户询问物流状态、快递到哪了、什么时候能送到、订单是否包邮、订单金额、签收时间、退款状态时，使用此工具。需要传入订单号。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
                   SELECT o.order_id,
                          o.logistics_no,
                          o.carrier,
                          o.status,
                          o.amount,
                          o.is_free_shipping,
                          o.signed_time,
                          o.refund_status,
                          t.trace_time,
                          t.node,
                          t.location
                   FROM orders o
                            LEFT JOIN logistics_traces t ON o.logistics_no = t.logistics_no
                   WHERE o.order_id = ?
                   ORDER BY t.trace_time DESC LIMIT 5
                   """, (order_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return f"抱歉，没有找到订单号为 {order_id} 的订单信息，请确认订单号是否正确。"

    latest = rows[0]
    result = f"订单 {order_id}：状态={latest['status']}；承运商={latest['carrier']}；"
    result += f"金额={latest['amount']}元；包邮={'是' if latest['is_free_shipping'] else '否'}；"
    if latest['signed_time']:
        result += f"签收时间={latest['signed_time']}；"
    else:
        result += f"签收时间=未签收；"
    result += f"退款状态={latest['refund_status']}；"
    result += f"最新轨迹：{latest['trace_time']} {latest['node']} {latest['location']}。"
    return result

# 3. 退货规则判定工具
import json
import os
import sqlite3
from datetime import datetime
from langchain_core.tools import tool


def _match_condition(field_values: dict, cond: dict) -> bool:
    """判断单个条件是否满足"""
    field = cond.get("field")
    op = cond.get("op")
    expected = cond.get("value")
    actual = field_values.get(field)

    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == "<":
        return actual is not None and actual < expected
    if op == "<=":
        return actual is not None and actual <= expected
    if op == ">":
        return actual is not None and actual > expected
    if op == ">=":
        return actual is not None and actual >= expected
    if op == "in":
        return actual in expected if actual is not None else False
    if op == "not_in":
        return actual not in expected if actual is not None else False
    return False


def _match_rule(field_values: dict, rule: dict) -> bool:
    """判断规则是否命中"""
    conditions = rule.get("conditions", {})
    if "all" in conditions:
        return all(_match_condition(field_values, c) for c in conditions["all"])
    if "any" in conditions:
        return any(_match_condition(field_values, c) for c in conditions["any"])
    return False


def _load_order(order_id: str) -> dict:
    """从数据库读订单信息"""
    if not os.path.exists(DB_PATH):
        return {}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
                   SELECT order_id, status, signed_time, is_free_shipping, amount, refund_status
                   FROM orders
                   WHERE order_id = ?
                   """, (order_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def _calc_days_since_signed(signed_time: str) -> int:
    """计算签收天数"""
    if not signed_time:
        return -1
    try:
        signed_dt = datetime.strptime(signed_time, "%Y-%m-%d %H:%M")
        return max(0, (datetime.now() - signed_dt).days)
    except Exception:
        return -1


@tool
def check_return_eligibility(
        order_id: str,
        days_since_signed: int = -1,
        return_reason: str = "无理由",
        product_category: str = "",
        product_condition: str = "完好",
        user_intent: str = "",
        user_emotion: str = "",
) -> str:
    """当用户询问退货、退款、换货条件、运费归属、或确认能否退货时使用此工具。

    Args:
        order_id: 订单号
        days_since_signed: 签收天数（不传则从订单签收时间自动计算）
        return_reason: 退货原因，如 无理由/质量问题/发错货/假冒品牌
        product_category: 商品类目，如 定制/生鲜/内衣/贴身用品
        product_condition: 商品状态，完好/不完好
        user_intent: 用户意图关键词，如 投诉/赔偿/退款
        user_emotion: 用户情绪，normal/high_risk

    Returns:
        规则判定结果，包含 decision、action、reply_template
    """
    order = _load_order(order_id)
    if not order:
        return f"未找到订单 {order_id}，请确认订单号是否正确。"

    if days_since_signed < 0:
        days_since_signed = _calc_days_since_signed(order.get("signed_time"))

    field_values = {
        "order.status": order.get("status"),
        "days_since_signed": days_since_signed,
        "order.is_free_shipping": order.get("is_free_shipping"),
        "order.amount": order.get("amount"),
        "order.refund_status": order.get("refund_status"),
        "product.category": product_category,
        "product.condition": product_condition,
        "return_reason": return_reason,
        "user_intent": user_intent,
        "user_emotion": user_emotion,
    }

    if not os.path.exists(RULES_PATH):
        return "规则库文件缺失，请转人工。"
    with open(RULES_PATH, encoding="utf-8") as f:
        rules = json.load(f)
    rules.sort(key=lambda r: r.get("priority", 0), reverse=True)

    for rule in rules:
        if _match_rule(field_values, rule):
            kb_ref = rule.get("kb_reference")
            ref_str = f"（依据：{kb_ref}）" if kb_ref else ""
            return (
                f"【判定结果】{rule['decision']}\n"
                f"【动作】{rule['action']}\n"
                f"【话术】{rule['reply_template']}{ref_str}"
            )

    return (
        f"未匹配到明确的退货规则。订单 {order_id} 状态：{order.get('status')}，"
        f"签收天数：{days_since_signed}。建议转人工进一步核实。"
    )
# 4. 知识库检索工具
import jieba
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import numpy as np

# 初始化向量模型（只需加载一次，放在函数外面）
# 第一次运行会下载模型，之后会从缓存读取
embedding_model = SentenceTransformer('BAAI/bge-small-zh-v1.5')


@tool
def search_knowledge(query: str) -> str:
    """当用户咨询售后政策、退货规则、特殊类目规定、争议处理、运费问题等，使用此工具查询知识库。"""
    kb_dir = os.path.join(BASE_DIR, 'data', 'kb')
    if not os.path.exists(kb_dir):
        return "知识库文件夹缺失，请转人工。"

    # 1. 动态读取所有知识库文件并合并
    kb_list = []
    for filename in os.listdir(kb_dir):
        if filename.endswith('.json'):
            filepath = os.path.join(kb_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    kb_list.extend(json.load(f))
            except Exception as e:
                print(f"⚠️ 加载 {filename} 失败: {e}")

    if not kb_list:
        return "知识库为空，请转人工。"

    # 2. 准备检索文本（将标题、场景、条件拼接）
    corpus = []
    for kb in kb_list:
        text = f"{kb.get('title', '')} {kb.get('scene', '')} {' '.join(kb.get('conditions', []))}"
        corpus.append(text)

    # --- 路线 A: BM25 关键词检索 ---
    tokenized_corpus = [list(jieba.cut(text)) for text in corpus]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = list(jieba.cut(query))
    bm25_scores = bm25.get_scores(tokenized_query)

    # --- 路线 B: 向量语义检索 ---
    # 将知识库和用户问题转化为向量
    corpus_embeddings = embedding_model.encode(corpus, normalize_embeddings=True)
    query_embedding = embedding_model.encode(query, normalize_embeddings=True)
    # 计算余弦相似度
    vector_scores = np.dot(corpus_embeddings, query_embedding)

    # --- 路线 C: RRF（倒数排名融合）合并结果 ---
    # RRF 的核心思想：综合两个不同算法的排名，排名越靠前，得分越高
    rrf_scores = {}
    k = 60  # RRF 平滑常数
    for idx in range(len(kb_list)):
        rrf_scores[idx] = 0

    # BM25 排名加分
    bm25_ranked_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)
    for rank, idx in enumerate(bm25_ranked_indices):
        rrf_scores[idx] += 1.0 / (k + rank + 1)

    # 向量排名加分
    vector_ranked_indices = sorted(range(len(vector_scores)), key=lambda i: vector_scores[i], reverse=True)
    for rank, idx in enumerate(vector_ranked_indices):
        rrf_scores[idx] += 1.0 / (k + rank + 1)

    # 3. 根据 RRF 总分选出 Top 3
    final_ranked_indices = sorted(rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True)[:3]

    results = []
    for idx in final_ranked_indices:
        kb = kb_list[idx]
        # 过滤掉得分为 0 的（完全无关的）
        if rrf_scores[idx] > 0:
            results.append(f"【{kb['id']}】{kb['title']}：{kb['policy']}（来源：{kb['source']}）")

    if results:
        return "\n".join(results)

    return "未找到相关政策，建议转人工核实。"


@tool
def query_tickets(order_id: str) -> str:
    """当用户询问退款进度、工单状态、售后处理进度时，使用此工具。需要传入订单号。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
                   SELECT ticket_id, reason, status, created_at
                   FROM tickets
                   WHERE order_id = ?
                   ORDER BY created_at DESC
                   """, (order_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return f"订单 {order_id} 目前没有工单记录，也没有退款/售后处理记录。"

    result = f"订单 {order_id} 的工单记录：\n"
    for r in rows:
        result += f"- 工单 {r['ticket_id']}：{r['reason']}（状态：{r['status']}，创建于 {r['created_at']}）\n"
    return result