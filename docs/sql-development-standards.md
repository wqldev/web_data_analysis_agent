# 团队 SQL 开发规范

> 适用范围：MySQL 数据分析、报表开发、ETL 取数脚本  
> 版本：v1.0  
> 维护：数据团队

---

## 1. 总则

### 1.1 目标

- 保证 SQL **可读、可复现、可审查**
- 降低口径不一致、性能事故、误删误改等风险
- 让分析结论能追溯到**明确的表、字段、时间范围与过滤条件**

### 1.2 基本原则

| 原则 | 说明 |
|------|------|
| **口径优先** | 先定义指标含义，再写 SQL |
| **只读默认** | 探索与分析阶段默认只执行 `SELECT` / `SHOW` / `DESCRIBE` |
| **小步验证** | 先抽样、再聚合、最后全量 |
| **可追溯** | 每条交付 SQL 应附带数据来源、时间范围、关键假设 |
| **简单优先** | 能用清晰 JOIN + GROUP BY 解决的，不堆嵌套子查询 |

### 1.3 环境安全（强制）

- **生产库探索**：仅通过 MCP / 只读账号查询，禁止 `INSERT` / `UPDATE` / `DELETE` / `DROP` / `ALTER` / `CREATE` / `TRUNCATE`
- **写操作**：必须在变更工单中说明，经负责人**文字确认**后，由 DBA 或专用账号在受控环境执行
- **禁止**在 Shell / Python 脚本中硬编码写操作连接生产库

---

## 2. 命名规范

### 2.1 对象命名

| 对象 | 规范 | 示例 |
|------|------|------|
| 数据库 | 小写 + 下划线 | `ysl_data` |
| 表名 | 小写 + 下划线；含业务域前缀 | `aop_ysl_202501_202509` |
| 字段名 | 与源系统保持一致；含空格时用反引号 | `` `Order Date` ``、`` `Final Price` `` |
| CTE | 语义化 snake_case | `order_base`、`monthly_sales` |
| 临时结果别名 | 简短且有意义 | `gmv`、`order_cnt`、`aov` |

### 2.2 脚本文件命名

```
{域}_{主题}_{粒度}_{YYYYMMDD}.sql
```

示例：

- `ysl_sales_monthly_trend_20250702.sql`
- `ysl_user_segment_s05_202501.sql`

### 2.3 指标命名（对外输出）

| 指标 | 推荐英文名 | 中文说明 |
|------|-----------|----------|
| GMV | `gmv` / `sales_amt` | 行级金额汇总，未扣退款 |
| 订单数 | `order_cnt` | 去重订单号计数 |
| 客单价 | `aov` | GMV ÷ 订单数 |
| 用户数 | `user_cnt` | 去重用户标识计数 |

**同一报表内指标名必须统一**，禁止混用 `sales` / `amount` / `gmv` 指代同一口径。

---

## 3. SQL 书写格式

### 3.1 基本排版

- 关键字**大写**：`SELECT`、`FROM`、`WHERE`、`GROUP BY`、`ORDER BY`
- 每个主要子句**独占一行**
- 逗号放在字段**行首**（便于 diff 与增删字段）
- 嵌套不超过 **3 层**；超过则拆 CTE

```sql
SELECT
    DATE_FORMAT(order_date, '%Y-%m') AS month
  , COUNT(DISTINCT order_id)         AS order_cnt
  , ROUND(SUM(amount), 2)            AS gmv
FROM order_base
WHERE order_date BETWEEN '2025-04-01' AND '2025-09-30'
GROUP BY 1
ORDER BY 1;
```

### 3.2 必须使用 schema 限定

```sql
-- ✅ 推荐
SELECT *
FROM ysl_data.aop_ysl_202501_202509
LIMIT 10;

-- ❌ 避免（环境切换易查错库）
SELECT * FROM aop_ysl_202501_202509;
```

### 3.3 字段与特殊字符

- 含空格、括号、韩文等特殊字符的字段名，**必须**用反引号包裹
- 禁止 `SELECT *` 作为最终交付 SQL（探索阶段可用）

```sql
STR_TO_DATE(`Order Date`, '%d-%m-%Y')                          AS order_date
, CAST(REPLACE(`Final Price`, ',', '') AS DECIMAL(18,2))       AS amount
, COUNT(DISTINCT `Original Order Number`)                      AS order_cnt
```

---

## 4. 数据类型与口径处理

### 4.1 日期字段

**写 SQL 前必须先确认格式**（`DESCRIBE` + 抽样 5 行）。

| 场景 | 写法 |
|------|------|
| `dd-mm-yyyy` 文本日期 | `STR_TO_DATE(\`Order Date\`, '%d-%m-%Y')` |
| 标准 `DATE` / `DATETIME` | 直接使用，必要时 `DATE(col)` |
| 月份聚合 | `DATE_FORMAT(order_date, '%Y-%m')` |

**时间范围必须写清闭区间**：

```sql
WHERE STR_TO_DATE(`Order Date`, '%d-%m-%Y')
      BETWEEN '2025-04-01' AND '2025-09-30'
```

### 4.2 金额字段

- 含千分位逗号的文本金额，先清洗再 CAST
- 统一精度：`DECIMAL(18,2)`
- 汇总结果对外展示时再 `ROUND(..., 2)`

```sql
CAST(REPLACE(`Final Price`, ',', '') AS DECIMAL(18,2)) AS amount
```

### 4.3 计数与去重

| 指标 | 规范 |
|------|------|
| 订单数 | `COUNT(DISTINCT order_id)`，字段名以探库确认为准 |
| 用户/客户数 | 先确认唯一标识字段；不可用 B2B 渠道账户代替 C 端用户 |
| 行数 | `COUNT(*)` 仅表示明细行，**不等于**订单数 |

### 4.4 空值与赠品

- `NULL` 与空字符串分开处理：`NULLIF(TRIM(col), '')`
- 赠品行（如 `Final Price = 0` 或 `Type = 'PLV'`）是否计入 GMV，**必须在 SQL 注释或报告第 6 节说明**

---

## 5. 查询结构规范

### 5.1 推荐结构：CTE 分层

```sql
WITH order_base AS (
    SELECT
        STR_TO_DATE(`Order Date`, '%d-%m-%Y')                      AS order_date
      , `Original Order Number`                                    AS order_id
      , CAST(REPLACE(`Final Price`, ',', '') AS DECIMAL(18,2))     AS amount
      , `Mall`                                                     AS channel
      , `Type`                                                     AS product_type
    FROM ysl_data.aop_ysl_202501_202509
    WHERE STR_TO_DATE(`Order Date`, '%d-%m-%Y')
          BETWEEN '2025-04-01' AND '2025-09-30'
      AND CAST(REPLACE(`Final Price`, ',', '') AS DECIMAL(18,2)) > 0
)
, monthly AS (
    SELECT
        DATE_FORMAT(order_date, '%Y-%m') AS month
      , COUNT(DISTINCT order_id)         AS order_cnt
      , ROUND(SUM(amount), 2)            AS gmv
    FROM order_base
    GROUP BY 1
)
SELECT
    month
  , order_cnt
  , gmv
  , ROUND(gmv / order_cnt, 2)          AS aov
FROM monthly
ORDER BY month;
```

**分层建议**：

1. `*_base`：清洗、过滤、字段标准化
2. `*_agg`：聚合
3. 最外层：派生指标（比率、环比等）

### 5.2 JOIN 规范

- 优先 `INNER JOIN`；需要保留主表全量时用 `LEFT JOIN` 并说明原因
- JOIN 条件必须**可解释**（业务键，而非随意字段）
- 大表 JOIN 前先在各侧过滤时间范围，减少中间结果集

```sql
-- ✅ 先过滤再 JOIN
FROM filtered_orders o
INNER JOIN dim_product p ON o.sku_code = p.sku_code

-- ❌ 全表 JOIN 后再过滤
FROM orders o
INNER JOIN dim_product p ON o.sku_code = p.sku_code
WHERE o.order_date >= '2025-04-01'
```

### 5.3 禁止使用

| 反模式 | 原因 |
|--------|------|
| 无 `WHERE` 的全表扫描（探索除外） | 性能差、易误读全量 |
| 隐式类型转换导致索引失效 | 如 `WHERE date_col = '20250401'` 而列是 DATE |
| `NOT IN (子查询含 NULL)` | 结果可能为空，改用 `NOT EXISTS` |
| 在 `WHERE` 对列做函数包裹 | 导致无法走索引；改过滤条件写法或加派生列 |
| 重复计算同一复杂表达式 | 提取到 CTE 或子查询 |

---

## 6. 性能规范

### 6.1 探索阶段

```sql
-- 第一步：看结构和样本
DESCRIBE ysl_data.aop_ysl_202501_202509;

SELECT *
FROM ysl_data.aop_ysl_202501_202509
LIMIT 10;

-- 第二步：看数据量与日期范围
SELECT
    COUNT(*)                                              AS row_cnt
  , MIN(STR_TO_DATE(`Order Date`, '%d-%m-%Y'))            AS min_date
  , MAX(STR_TO_DATE(`Order Date`, '%d-%m-%Y'))            AS max_date
FROM ysl_data.aop_ysl_202501_202509;
```

### 6.2 生产取数

- 大表聚合必须带**时间分区条件**
- 避免 `SELECT DISTINCT` 大范围去重；优先 `GROUP BY` 业务键
- 结果集超过 10 万行时，评估是否需要落表或分批导出
- 使用 `EXPLAIN` 检查是否出现 `ALL` 全表扫描（需优化时）

### 6.3 窗口函数

- 仅在需要排名、环比、累计时引入窗口函数
- `PARTITION BY` 粒度必须与业务口径一致

```sql
NTILE(5) OVER (ORDER BY user_gmv DESC) AS value_quintile
```

---

## 7. 注释与文档

### 7.1 文件头注释（必填）

每个交付 SQL 文件顶部应包含：

```sql
/*
 * 用途：近半年 Naver 渠道月度销售趋势
 * 作者：zhangsan
 * 日期：2025-07-02
 * 数据源：ysl_data.aop_ysl_202501_202509
 * 时间范围：2025-04-01 ~ 2025-09-30
 * 关键口径：
 *   - GMV = SUM(Final Price)，仅 YFG 付费行
 *   - 订单数 = COUNT(DISTINCT Original Order Number)
 * 变更记录：
 *   - 2025-07-02 初版
 */
```

### 7.2 行内注释

- 解释**业务规则**，不解释 SQL 语法本身
- 非显而易见的过滤条件必须注释原因

```sql
AND `Type` = 'YFG'   -- PLV 为赠品行，Final Price=0，不计入 GMV
```

---

## 8. 审查清单（Code Review）

提交 SQL 前，作者自查；审查人逐项核对：

- [ ] 是否只读（分析/探索场景）
- [ ] 表名是否带 schema
- [ ] 时间范围是否明确且与需求一致
- [ ] 金额、日期字段是否已清洗
- [ ] 订单/用户计数是否使用正确的去重键
- [ ] 赠品行、退款、取消订单的处理是否说明
- [ ] 是否存在 `SELECT *` 作为最终交付
- [ ] 指标命名是否与团队统一
- [ ] 是否可在空表/小样本上先验证逻辑
- [ ] 关键数字是否可被他人独立复算

---

## 9. 常见业务口径参考（YSL 订单明细）

> 以下为本项目常用口径，新表接入时需重新探库确认，**不可盲目套用**。

| 口径项 | 字段 / 写法 |
|--------|------------|
| 下单日期 | `STR_TO_DATE(\`Order Date\`, '%d-%m-%Y')` |
| 订单号 | `` `Original Order Number` `` |
| 行级金额 | `` CAST(REPLACE(`Final Price`, ',', '') AS DECIMAL(18,2)) `` |
| 渠道 | `` `Mall` `` |
| 品类 | `` `Type` ``（YFG 付费 / PLV 赠品） |
| 近半年 | 以库内 `MAX(order_date)` 为锚点，向前 6 个自然月 |

---

## 10. 附录：快速模板

### 10.1 月度趋势模板

```sql
WITH order_base AS (
    SELECT
        STR_TO_DATE(`Order Date`, '%d-%m-%Y')                  AS order_date
      , `Original Order Number`                                AS order_id
      , CAST(REPLACE(`Final Price`, ',', '') AS DECIMAL(18,2)) AS amount
    FROM ysl_data.aop_ysl_202501_202509
    WHERE STR_TO_DATE(`Order Date`, '%d-%m-%Y')
          BETWEEN @start_date AND @end_date
)
SELECT
    DATE_FORMAT(order_date, '%Y-%m')  AS month
  , COUNT(DISTINCT order_id)        AS order_cnt
  , ROUND(SUM(amount), 2)           AS gmv
  , ROUND(SUM(amount) / COUNT(DISTINCT order_id), 2) AS aov
FROM order_base
GROUP BY 1
ORDER BY 1;
```

### 10.2 探库检查模板

```sql
-- 表是否存在、行数、日期范围、关键字段空值率
SELECT
    COUNT(*)                                                   AS row_cnt
  , COUNT(DISTINCT `Original Order Number`)                    AS order_cnt
  , MIN(STR_TO_DATE(`Order Date`, '%d-%m-%Y'))                 AS min_date
  , MAX(STR_TO_DATE(`Order Date`, '%d-%m-%Y'))                 AS max_date
  , SUM(CASE WHEN `Final Price` IS NULL THEN 1 ELSE 0 END)     AS null_price_cnt
FROM ysl_data.aop_ysl_202501_202509;
```

---

## 11. 版本与反馈

- 规范随项目表结构、业务口径变化而更新
- 发现口径冲突或规范遗漏，请在团队频道提出，由数据负责人合并修订

**变更记录**

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2025-07-02 | 初版，覆盖 MySQL 分析取数通用规范与 YSL 项目口径 |
