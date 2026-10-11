from datasets import load_dataset

# 下载数据集
dataset = load_dataset("Rahul-rr/Retail_chatbot")
print(dataset)

# 打印前 5 条数据看看长什么样
for i, sample in enumerate(dataset['train']):
    print(sample)
    if i >= 4:
        break