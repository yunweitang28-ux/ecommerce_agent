import json
import os
import sys

# 动态计算项目根目录，确保能导入外层的 agent.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# 导入你的 Agent (假设你的 agent.py 里有一个能直接对话的函数)
# 如果调用方式不同，这里可能需要微调
try:
    from agent import app  # 假设你在 agent.py 里构建了 workflow
except ImportError as e:
    print(f"❌ 导入 agent 失败，请检查 agent.py 里是否有 'workflow' 变量。错误: {e}")
    exit()


def load_golden():
    filepath = os.path.join(BASE_DIR, 'data/eval/golden.jsonl')
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def run_evaluation():
    print("🚀 开始运行 Agent 评测...\n")
    test_cases = load_golden()
    passed = 0
    failed = 0

    for case in test_cases:
        print(f"--- 测试用例 {case['id']} ---")
        print(f"👤 用户: {case['user_query']}")

        # 构造 LangGraph 的初始状态
        initial_state = {"messages": [{"role": "user", "content": case['user_query']}]}

        try:
            # 执行 Agent 工作流
            final_state = app.invoke(initial_state)
            # 获取最后一条 AI 回复
            last_message = final_state["messages"][-1]
            # 兼容 langchain 的 Message 对象和普通字典
            ai_response = last_message.content if hasattr(last_message, 'content') else last_message.get('content',
                                                                                                         str(last_message))

            print(f"🤖 Agent: {ai_response}")

            # 非常粗糙的规则判定（后续可升级为 LLM-as-judge）
            # 这里我们先肉眼观察，不直接打分，因为你的 Agent 还没接检索工具
            print(f"🎯 预期工具: {case['expected_tools']}")
            print(f"🎯 预期 KB: {case['expected_kb']}")
            print(f"🎯 必答红牌: {case['must_not']}")
            print(f"🎯 是否转人工: {case['handoff']}")
            print(f"✅ 通过标准: {case['pass_criteria']}\n")

        except Exception as e:
            print(f"❌ Agent 运行报错: {e}\n")
            failed += 1

    print(f"==== 评测结束 ====")


if __name__ == "__main__":
    run_evaluation()