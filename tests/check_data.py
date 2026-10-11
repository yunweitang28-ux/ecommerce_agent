import json
import os

# 动态计算项目根目录（当前文件在 tests/ 下，往上找两级就是项目根目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def check_json(relative_path, name):
    # 拼接成绝对路径
    filepath = os.path.join(BASE_DIR, relative_path)
    if not os.path.exists(filepath):
        print(f"❌ {name} 文件不存在: {filepath}")
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"✅ {name} 加载成功，共 {len(data)} 条数据。")
            return data
    except Exception as e:
        print(f"❌ {name} 加载失败，错误原因: {e}")
        return None

if __name__ == "__main__":
        print("开始检查数据文件...")
        # 物流场景
        check_json('data/kb/logistics_kb.json', '物流知识库 (KB)')
        check_json('data/rules/logistics_rules.json', '物流规则库 (Rule)')
        # 退货场景
        check_json('data/kb/return_kb.json', '退货知识库 (KB)')
        check_json('data/rules/return_rules.json', '退货规则库 (Rule)')
        # ✅ 新增：争议处理场景
        check_json('data/kb/dispute_kb.json', '争议处理知识库 (KB)')
        # 新增：发货场景
        check_json('data/kb/shipping_kb.json', '发货规范知识库 KB')
        # ✅ 新增：评价场景
        check_json('data/kb/review_kb.json', '评价知识库 (KB)')