import sqlite3

conn = sqlite3.connect("../data/logistics.db")
conn.row_factory = sqlite3.Row  # 让查询结果可以按列名访问
cursor = conn.cursor()

# 查订单 2026001 的物流轨迹
cursor.execute("""
SELECT o.order_id, o.status, o.carrier, o.logistics_no,
       t.trace_time, t.node, t.location
FROM orders o
JOIN logistics_traces t ON o.logistics_no = t.logistics_no
WHERE o.order_id = ?
ORDER BY t.trace_time
""", ("2026001",))

for row in cursor.fetchall():
    print(dict(row))

conn.close()