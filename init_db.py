import sqlite3
import os

DB_PATH = "data/logistics.db"

# 如果已存在，先删掉，方便反复调试
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. 建订单表（新增 4 个字段：amount / is_free_shipping / signed_time / refund_status）
cursor.execute("""
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    user_id TEXT,
    status TEXT,
    logistics_no TEXT,
    carrier TEXT,
    created_at TEXT,
    shipped_at TEXT,
    estimated_delivery TEXT,
    address TEXT,
    amount REAL,
    is_free_shipping INTEGER,
    signed_time TEXT,
    refund_status TEXT DEFAULT '无'
)
""")

# 2. 建物流轨迹表
cursor.execute("""
CREATE TABLE logistics_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    logistics_no TEXT,
    trace_time TEXT,
    node TEXT,
    location TEXT
)
""")

# 3. 建工单表
cursor.execute("""
CREATE TABLE tickets (
    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT,
    reason TEXT,
    status TEXT DEFAULT '待处理',
    created_at TEXT
)
""")

# 4. 插订单数据（10 个字段：order_id, user_id, status, logistics_no, carrier,
#    created_at, shipped_at, estimated_delivery, address, amount,
#    is_free_shipping, signed_time, refund_status）
orders = [
    # 2026001：运输中，未签收，包邮
    ("2026001", "U001", "运输中", "SF123456", "顺丰",
     "2026-10-01 09:00", "2026-10-01 18:00", "2026-10-05", "深圳市南山区",
     199.00, 1, None, "无"),
    # 2026002：派送中，未签收，包邮
    ("2026002", "U002", "派送中", "SF123457", "顺丰",
     "2026-10-02 10:00", "2026-10-02 20:00", "2026-10-04", "广州市天河区",
     89.00, 1, None, "无"),
    # 2026003：已签收（10-01），非包邮
    ("2026003", "U003", "已签收", "YT888001", "圆通",
     "2026-09-28 08:00", "2026-09-28 15:00", "2026-10-01", "北京市朝阳区",
     45.00, 0, "2026-10-01 14:00", "无"),
    # 2026004：异常（派送失败），未签收，包邮
    ("2026004", "U004", "异常", "JD666002", "京东",
     "2026-09-30 11:00", "2026-09-30 19:00", "2026-10-03", "上海市浦东新区",
     299.00, 1, None, "无"),
    # 2026005：已发货，未签收，包邮
    ("2026005", "U005", "已发货", "ZT555003", "中通",
     "2026-10-03 14:00", "2026-10-03 21:00", "2026-10-07", "杭州市西湖区",
     68.00, 1, None, "无"),
]
cursor.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", orders)

# 5. 插物流轨迹
traces = [
    ("SF123456", "2026-10-01 18:00", "已揽收", "深圳"),
    ("SF123456", "2026-10-02 08:00", "到达广州转运中心", "广州"),
    ("SF123456", "2026-10-03 09:00", "运输中", "广州→深圳"),
    ("SF123457", "2026-10-02 20:00", "已揽收", "广州"),
    ("SF123457", "2026-10-03 10:00", "派送中", "广州天河"),
    ("YT888001", "2026-09-28 15:00", "已揽收", "北京"),
    ("YT888001", "2026-09-30 10:00", "派送中", "北京朝阳"),
    ("YT888001", "2026-10-01 14:00", "已签收", "北京朝阳"),
    ("JD666002", "2026-09-30 19:00", "已揽收", "上海"),
    ("JD666002", "2026-10-01 09:00", "派送失败", "上海浦东"),
    ("ZT555003", "2026-10-03 21:00", "已揽收", "杭州"),
]
cursor.executemany(
    "INSERT INTO logistics_traces (logistics_no, trace_time, node, location) VALUES (?,?,?,?)",
    traces
)

conn.commit()
conn.close()
print("数据库初始化完成：logistics.db（含金额、包邮、签收时间、退款状态）")