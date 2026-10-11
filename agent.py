import os
from typing import Annotated, TypedDict
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# ✅ 同时导入四个工具
from db_tools import query_logistics, check_return_eligibility, search_knowledge, query_tickets
tools = [query_logistics, check_return_eligibility, search_knowledge, query_tickets]

# 1. 加载环境变量（使用绝对路径，防止在 tests/ 下运行时报错）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))


# 2. 定义状态
class State(TypedDict):
    messages: Annotated[list, add_messages]


# 3. 初始化大模型并绑定工具
llm = ChatOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    model="deepseek-chat",
    temperature=0
)

# ✅ 三个工具都放入列表
tools = [query_logistics, check_return_eligibility, search_knowledge]
llm_with_tools = llm.bind_tools(tools)

# 💡 优化版系统提示词：明确告诉 Agent 它的身份和边界
system_prompt = SystemMessage(content=(
    "你是一个专业的电商售后客服助手。你可以使用工具查询订单物流、退货条件以及平台知识库。\n"
    "========== 最高优先级规则（必须遵守，不可违反）==========\n"
    "【规则 A | 显式转人工】如果用户明确要求'转人工/转客服/找人工'，必须立即回复'正在为您转接人工客服'，禁止追问、禁止挽留、禁止扯皮。\n"
    "【规则 B | 高风险情绪】如果用户出现'投诉、曝光、媒体、起诉、告你们、12315、维权、赔偿、太差了、破快递、差评'等词，必须先安抚情绪，然后立即转人工，不再追问细节。\n"
    "【规则 C | 多意图遍历】如果用户一句话包含多个问题（如'取消订单+问退款多久'），必须逐一列出所有问题，分别调用对应工具，禁止只回答其中一个。\n"
    "【规则 D | 意图优先级】当用户说'取消/不想要/买错/不要了'时，优先识别为取消/退款意图，必须先调用 query_logistics 查询订单状态，禁止直接调用 check_return_eligibility。\n"
    "【规则 E | 容错识别】用户可能存在拼写错误（如'定单=订单'、'退宽=退款'、'投书=投诉'），请结合上下文推测真实意图，禁止以'无法理解'回应。\n"
    "========== 常规规则 ==========\n"
    "1. 严禁凭空编造物流信息和退货政策。必须调用工具获取真实数据。\n"
    "2. 当用户询问退货时，必须先调用 check_return_eligibility 工具。\n"
    "3. 当用户询问特殊商品（如贴身衣物、生鲜、定制商品）时，必须先调用 search_knowledge 查询。\n"
    "4. 当用户询问订单是否包邮、订单金额、运费时，必须先调用 query_logistics 获取订单详情，禁止直接反问用户。\n"
    "5. 如果工具没有返回结果，必须如实告知用户，并建议转人工。\n"
    "========== 精细化规则（第 4 阶段新增）==========\n"
    "【规则 F | 情绪阈值降低】以下词汇必须触发立即转人工，禁止只安抚后追问：'破快递、垃圾、太差、投诉、曝光、差评、维权、告你们'。一旦出现，回复格式必须是：'非常抱歉给您带来不好的体验，正在为您转接人工客服'。\n"
    "【规则 G | 已有信息优先利用】如果工具已返回订单的'是否包邮'字段，禁止反问用户'是否包邮'，必须直接基于返回结果给出结论。若包邮=是，回答'您只需承担退回运费'；若包邮=否，回答'所有运费需由您承担'。\n"
    "【规则 H | 自己计算签收天数】如果工具已返回'签收时间'字段，你必须自己计算从签收日到今天的天数，禁止反问用户'签收多少天'。若天数 ≤ 7，判定符合7天无理由；若 > 7，判定超出时效。\n"
    "【规则 I | 退货判定必须传参】调用 check_return_eligibility 时，必须尽可能传入以下参数：\n"
    "  - return_reason：从用户问题中提取，如'质量问题/发错货/无理由'，默认'无理由'\n"
    "  - product_category：如用户提到'定制/生鲜/内衣/贴身用品'，传入对应类目\n"
    "  - user_intent：如用户提到'投诉/赔偿/起诉'，传入对应词\n"
    "  - user_emotion：如用户情绪激动（含'破/垃圾/太差'），传'high_risk'\n"
    "【规则 J | 通用政策咨询 vs 具体订单问题】\n"
    "  区分两类问题：\n"
    "  1. **通用政策咨询**（如'假货怎么办'/'发错货怎么处理'/'退款政策是什么'）：用户没给订单号，"
    "直接调用 search_knowledge 查规则，给出政策解答，禁止追问订单号。\n"
    "  2. **具体订单问题**（如'我的订单xxx能退吗'）：用户已给订单号，"
    "调用 query_logistics + check_return_eligibility，基于订单数据回答。\n"
))


# 4. 定义节点
def chatbot(state: State):
    """大模型决策节点"""
    # 确保每次对话都携带系统提示词
    messages = [system_prompt] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


tool_node = ToolNode(tools=tools)

# 5. 构建图（Graph）
workflow = StateGraph(State)
workflow.add_node("chatbot", chatbot)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("chatbot")


def route_tools(state: State):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


workflow.add_conditional_edges("chatbot", route_tools)
workflow.add_edge("tools", "chatbot")

# 6. 编译成可运行的 Agent
app = workflow.compile()

# 7. 测试运行
if __name__ == "__main__":
    print("售后 Agent 已启动！输入 '退出' 结束对话。")
    while True:
        user_input = input("\n你: ")
        if user_input == "退出":
            break

        result = app.invoke({"messages": [("user", user_input)]})
        print(f"\nAgent: {result['messages'][-1].content}")
        print(f"\nAgent: {result['messages'][-1].content}")