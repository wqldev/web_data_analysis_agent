import pymysql
conn = pymysql.connect(host='localhost',port=3306,user='root',password='123456',database='mysql_dataset_test',cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()
cur.execute("""
SELECT DATE_FORMAT(o.order_date, '%Y-%m') AS m,
  COUNT(DISTINCT o.order_id) AS cnt,
  SUM(oi.quantity * oi.unit_price * (1 - oi.discount)) AS amt
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'Completed'
  AND o.order_date > DATE_SUB((SELECT MAX(order_date) FROM orders), INTERVAL 6 MONTH)
  AND o.order_date <= (SELECT MAX(order_date) FROM orders)
GROUP BY m ORDER BY m
""")
print('KPI window by month:', cur.fetchall())
conn.close()
