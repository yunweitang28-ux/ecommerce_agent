"""
数据标注 Skill：从淘宝规则文本自动提取结构化 KB 条目。

用法示例：
    python scripts/extract_kb.py --input data/raw/发票规范.txt --prefix INV --scene 发票
"""

import argparse
import json
import os
import re
from openai import OpenAI
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# ========== 1. System Prompt ==========
SYSTEM_PROMPT = """你是一个数据标注专家。请从以下淘宝规则文本中，提取出适合作为电商售后客服知识库的条目。

严格按照 JSON 数组格式输出，每条包含以下字段：
- id: 前缀 {prefix}-，如 {prefix}-001，自增编号
- title: 一句话概括，10-20 字，尽量用用户常问的问答式表达
- scene: 固定为 "{scene}"
- policy: 政策原文的提炼，包含判定条件、时效、例外情况，100 字以内
- conditions: 数组，包含 4-8 个关键词/同义词，包括用户可能的错别字
- reply_template: 客服话术模板，30-60 字，语气亲切
- source: 来源条款，格式如《XXX规范》第X条
- version: "2026-10-11"

要求：
1. 每条只讲一个独立问题，不要重复
2. 必须有明确来源出处，不能凭空编造
3. 至少提取 {min_count} 条
4. 直接输出 JSON 数组，不要 markdown 代码块包裹，不要任何多余文字
"""

NOISE_KEYWORDS = [
    '亲，请登录免费注册', '网页无障碍', '淘宝网首页', '已买到的宝贝', '我的淘宝',
    '购物车', '收藏夹', '免费开店', '千牛卖家中心', '帮助中心',
    '阿里巴巴集团', '增值电信业务经营许可证', '浙B2-', '浙网文', '浙网食',
    '浙公网安备', '互联网药品信息服务资格证书', '医疗器械网络交易服务',
    '关于淘宝', '营销中心', '廉政举报', '开放平台', '诚征英才',
    '隐私权政策', '法律声明', '知识产权', '© 2003-', '版权所有',
    '规则协议', '平台服务协议', '新手上路', '0元开店',
    '天猫开店', '商家服务', '付款方式', '快捷支付', '余额宝',
    '蚂蚁花呗', '淘宝特色', '阿里旺旺', '官方客服',
    '高德', '飞猪', '优酷', '大麦', '阿里影业', '钉钉', '支付宝',
    '阿里妈妈', '阿里云', 'TAO', '规则辞典', '规则众议院', '违规公示',
    '规则留言板', '天猫规则', '规则动态', '淘宝总则', '店铺管理',
    '行业市场', '商品管理', '营销推广', '内容推广', '交易管理',
    '物流规范', '服务保障', '评价规范', '超时说明', '服务规范',
    '争议处理', '违规处理', '生态角色', '飞猪集市', '临时公告',
    '实施细则', '解读说明', '协议专区', '规则研讨', '历史规则',
    '这篇文章是否易于理解', '简单易懂', '不太理解', '显示详细信息',
]


# ========== 2. 工具函数 ==========
def clean_raw_text(text):
    """去除网页复制产生的常见噪音"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(kw in stripped for kw in NOISE_KEYWORDS):
            continue
        if re.fullmatch(r'[\s\W_\|]+', stripped):
            continue
        if len(stripped) <= 2:
            continue
        cleaned.append(stripped)
    result = '\n'.join(cleaned)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


def load_raw_text(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    original_len = len(text)
    text = clean_raw_text(text)
    print(f"🧹 预清洗完成：{original_len} 字 → {len(text)} 字（去掉 {original_len - len(text)} 字噪音）")
    return text


def clean_json_response(text):
    text = text.strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


def chunk_text(text, chunk_size=3000, overlap=200):
    """把长文本切成带重叠的片段"""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def call_llm(raw_text, prefix, scene, min_count):
    """单次调用 DeepSeek"""
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )
    prompt = SYSTEM_PROMPT.format(prefix=prefix, scene=scene, min_count=min_count)
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": raw_text},
        ],
        temperature=0,
    )
    return clean_json_response(response.choices[0].message.content)


def call_llm_chunked(raw_text, prefix, scene, min_count_per_chunk=8):
    """分段提取 + 合并去重"""
    chunks = chunk_text(raw_text)
    print(f"📦 文本切分为 {len(chunks)} 段，逐段提取...")

    all_kb = []
    for i, chunk in enumerate(chunks):
        print(f"  处理第 {i+1}/{len(chunks)} 段（{len(chunk)} 字）...")
        json_str = call_llm(chunk, prefix, scene, min_count=min_count_per_chunk)
        try:
            kb_list = json.loads(json_str)
            all_kb.extend(kb_list)
            print(f"    提取 {len(kb_list)} 条")
        except json.JSONDecodeError as e:
            print(f"    ⚠️ 第 {i+1} 段 JSON 解析失败，跳过：{e}")

    # 按 title 去重 + 重新编号
    seen_titles = set()
    deduped = []
    for item in all_kb:
        title = item.get('title', '').strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        deduped.append(item)

    # 重新编号
    for idx, item in enumerate(deduped, start=1):
        item['id'] = f"{prefix}-{idx:03d}"

    print(f"✅ 合并去重后共 {len(deduped)} 条")
    return deduped


def validate_kb(kb_list, prefix):
    required_fields = ["id", "title", "scene", "policy", "conditions", "reply_template", "source", "version"]
    errors = []
    seen_ids = set()
    for i, item in enumerate(kb_list):
        for field in required_fields:
            if field not in item or not item[field]:
                errors.append(f"条目 [{i}] 缺少字段: {field}")
        item_id = item.get("id", "")
        if not item_id.startswith(f"{prefix}-"):
            errors.append(f"条目 [{i}] ID 前缀错误: {item_id}")
        if item_id in seen_ids:
            errors.append(f"条目 [{i}] ID 重复: {item_id}")
        seen_ids.add(item_id)
        if not isinstance(item.get("conditions"), list):
            errors.append(f"条目 [{i}] conditions 不是数组")
    return errors


def check_id_conflict(new_kb_list, kb_dir):
    existing_ids = set()
    if not os.path.exists(kb_dir):
        return []
    for filename in os.listdir(kb_dir):
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(kb_dir, filename)
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    if 'id' in item:
                        existing_ids.add(item['id'])
        except Exception:
            continue
    return [item['id'] for item in new_kb_list if item.get('id') in existing_ids]


# ========== 3. 主流程 ==========
def main():
    parser = argparse.ArgumentParser(description="从淘宝规则文本提取 KB")
    parser.add_argument('--input', required=True, help='规则文本路径')
    parser.add_argument('--prefix', required=True, help='ID 前缀')
    parser.add_argument('--scene', required=True, help='业务场景名')
    parser.add_argument('--min', type=int, default=15, help='最少提取条数（警告阈值）')
    parser.add_argument('--output', default=None, help='输出路径')
    args = parser.parse_args()

    input_path = os.path.join(BASE_DIR, args.input) if not os.path.isabs(args.input) else args.input
    if not os.path.exists(input_path):
        print(f"❌ 输入文件不存在: {input_path}")
        return

    output_path = args.output or os.path.join(BASE_DIR, 'data', 'kb', f"{args.prefix.lower()}_kb.json")

    # Step 1: 读取 + 预清洗
    raw_text = load_raw_text(input_path)

    # Step 2: 分段提取
    kb_list = call_llm_chunked(raw_text, args.prefix, args.scene, min_count_per_chunk=8)

    if len(kb_list) < args.min:
        print(f"⚠️ 提取条数 ({len(kb_list)}) 少于预期 ({args.min})，语料可能不足")

    # Step 3: 校验字段
    errors = validate_kb(kb_list, args.prefix)
    if errors:
        print("❌ 字段校验失败：")
        for e in errors[:10]:
            print(f"   - {e}")
        return
    print("✅ 字段校验通过")

    # Step 4: 检查 ID 冲突
    kb_dir = os.path.join(BASE_DIR, 'data', 'kb')
    conflicts = check_id_conflict(kb_list, kb_dir)
    if conflicts:
        print(f"❌ 发现 ID 冲突：{conflicts[:5]}...（共 {len(conflicts)} 条）")
        return
    print("✅ 无 ID 冲突")

    # Step 5: 写入
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(kb_list, f, ensure_ascii=False, indent=2)
    print(f"✅ 已保存到: {output_path}")
    print(f"\n🎉 完成！共 {len(kb_list)} 条 KB 已入库。")


if __name__ == "__main__":
    main()