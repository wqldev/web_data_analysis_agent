# my_first_agent

基于 Cursor 的**三 Agent 协作数据分析**项目：主 Agent 调度 `planner-agent` → `builder-agent` → `verifier-agent`，通过 `task-board` MCP 跟踪任务状态，通过 `mysql-local` MCP 只读取数，形成可验收的 agent-loop 闭环。

**Web 产品（MVP）**：浏览器输入分析问题 → 后端执行 agent-loop → 展示六节 Markdown 报告，支持历史记录与管理员 MySQL 配置。

---

## Web 产品快速开始

### 1. 初始化环境

```powershell
.\scripts\setup.ps1
```

### 2. 启动 Web 服务

```powershell
.\scripts\run-web.cmd
```

浏览器打开：**http://127.0.0.1:8000**

### 3. 配置 MySQL 与 Cursor API Key

首次使用点击右上角 **管理员配置**：

1. **MySQL**：填写连接信息并测试连接（保存在 `data/mysql_config.json`）
2. **Cursor API Key**：在 Cursor Dashboard 获取；Web 通过 Cursor SDK 运行与 IDE 相同的 agent-loop

也可设置环境变量 `CURSOR_API_KEY`、`CURSOR_MODEL`（默认 composer-2.5）

### 4. 使用流程

1. 在输入框输入任意**分析类问题**（趋势/对比/归因/分群/假设均可）
2. 点击 **确定**——后端通过 **Cursor SDK** 运行 planner → builder → verifier（与 IDE 相同）
3. 观察进度：规划中 → 取数中 → 验收中（单次分析约 2~5 分钟）
4. 验收通过后展示六节 Markdown 报告

### Web API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/analyze/sync` | POST | 同步执行 agent-loop，返回报告 |
| `/api/history` | GET | 历史分析列表 |
| `/api/analyze/{board_id}/report` | GET | 获取指定报告 |
| `/api/admin/mysql-config` | GET/PUT | 读取/保存 MySQL 配置 |
| `/api/admin/test-connection` | POST | 测试数据库连接 |

---

## 功能概览

| 组件 | 路径 | 作用 |
|------|------|------|
| **agent-loop Skill** | `.cursor/skills/agent-loop/` | 识别分析类需求，强制走三 Agent 闭环 |
| **Subagents** | `.cursor/agents/` | planner / builder / verifier 分工 |
| **Rules** | `.cursor/rules/` | 路由约束、行为准则、graphify 规范 |
| **Hooks** | `.cursor/hooks/` | 文件编辑日志、Shell 拦截、MCP 审计、分析意图记录 |
| **task-board MCP** | `src/mcp/task_board_server.py` | 任务看板 CRUD + 回修记录 |
| **mysql-local MCP** | `src/mcp/server.py` | 只读 SQL 探库与取数 |
| **codegraph MCP** | `.cursor/mcp.json` | 代码知识图谱（可选） |

架构与 Agent 交接细节见 [docs/agent-handoff-protocol.md](docs/agent-handoff-protocol.md)。

---

## 环境要求

| 依赖 | 版本建议 | 说明 |
|------|----------|------|
| [Cursor](https://cursor.com) | 最新稳定版 | 需启用 Agent、MCP、Subagents、Hooks |
| Python | 3.10+ | MCP 服务与 Hook 脚本 |
| MySQL | 5.7+ / 8.x | 本地库 `mysql_dataset_test`（可在 `mcp.json` 中修改） |
| codegraph CLI | 可选 | 已在 `mcp.json` 中配置 |

---

## 快速开始

### 1. 进入项目目录

```powershell
cd <项目根目录>
```

### 2. 初始化环境（推荐）

**Windows：**

```powershell
.\scripts\setup.ps1
```

**macOS / Linux：**

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

脚本会自动：检测 Python 3.10+ → 创建 `.venv` → 安装 `src/mcp/requirements.txt` 依赖。

**若本机尚未安装 Python：**

| 平台 | 安装方式 |
|------|----------|
| Windows | [python.org](https://www.python.org/downloads/) 安装时勾选 **Add to PATH**；或 `winget install Python.Python.3.12` |
| macOS | `brew install python@3.12` |
| Linux | `sudo apt install python3.12 python3.12-venv python3-pip` |

安装 Python 后重新运行上述 setup 脚本即可。

**手动初始化（等价于 setup 脚本）：**

```powershell
py -3 src/bootstrap/setup.py
# 或
python src/bootstrap/setup.py
```

### 3. 配置 MySQL

编辑 `.cursor/mcp.json` 中 `mysql-local` 的环境变量：

```json
"MYSQL_HOST": "localhost",
"MYSQL_PORT": "3306",
"MYSQL_USER": "root",
"MYSQL_PASSWORD": "你的密码",
"MYSQL_DATABASE": "mysql_dataset_test",
"MYSQL_ALLOW_WRITES": "false"
```

### 4. 在 Cursor 中启用 MCP

1. 用 Cursor 打开本项目文件夹
2. 进入 **Settings → MCP**，确认 `task-board`、`mysql-local` 已连接（`codegraph` 为可选）
3. MCP 通过 `scripts/run-mcp.cmd` 启动，**首次连接时会自动创建 `.venv`**（若 setup 尚未运行）
4. 连接失败时查看 **MCP Logs**；常见原因：未安装 Python、MySQL 未启动、凭据错误

### 5. 验证 MCP

在 Cursor Agent 对话中可尝试：

- 「列出 task-board 当前有哪些任务」→ `list_tasks`
- 「测试 mysql 连接」→ `test_connection`

---

## 使用 agent-loop

当用户提出**数据分析 / 业务洞察**类问题时，主 Agent 应走三 Agent 闭环，而非直接查库作答。

### 触发示例

```
近半年的销售情况怎么样？
```

命中 `agent-loop` Skill 后，主 Agent 会：

1. 说明将按 planner → builder → verifier 执行
2. 调用 `create_task` 创建看板
3. 依次委派三个 Subagent
4. verifier 验收通过后，按六节结构向用户交付 builder 报告

### 执行流程

```
用户提问
  → 主 Agent：create_task → boards/<uuid>.json
  → Task(planner-agent)：拆分 T1~T4，assign_task，append_result 规划 JSON
  → Task(builder-agent)：mysql-local 探库/SQL，撰写六节报告
  → Task(verifier-agent)：对照 acceptance_criteria 验收
       ├─ passed → 主 Agent 交付报告
       └─ failed → request_rework → Task(builder-agent) 回修（最多 2 轮）
```

### 运行后检查

| 检查项 | 位置 |
|--------|------|
| 看板 JSON | `boards/<board_id>.json` |
| 终态 | `board.status = done` |
| 分析报告 | T3 的 `results`，或对话中的六节交付物 |
| Hook 日志 | `.cursor/hooks/logs/` |

### 不应走闭环的示例

以下由主 Agent 直接处理，不进入 agent-loop：

- 「帮我写一份 agent-loop 使用说明文档」
- 「给 task_board_server.py 增加单元测试」
- 「把变量名 sales_data 改成 salesData」

完整触发词与路由规则见 `.cursor/skills/agent-loop/SKILL.md` 与 `.cursor/rules/agent-loop-routing.mdc`。

---

## 项目结构

```
my_first_agent/
├── .cursor/
│   ├── agents/              # planner / builder / verifier
│   ├── hooks/               # Hook 脚本与 logs/
│   ├── hooks.json
│   ├── mcp.json
│   ├── rules/
│   └── skills/agent-loop/   # 闭环 Skill + report-template.md
├── boards/                  # task-board 持久化看板
├── data/                    # Web 运行时配置（mysql_config.json）
├── docs/
│   ├── agent-handoff-protocol.md
│   └── sql-development-standards.md
├── reports/
│   ├── integration-test-report.md
│   └── demo-retrospective.md
├── scripts/
│   ├── setup.ps1            # Windows 一键初始化
│   ├── setup.sh             # macOS/Linux 一键初始化
│   ├── run-mcp.cmd          # MCP 自举启动（Windows）
│   └── run-mcp.sh
├── src/
│   ├── bootstrap/           # 虚拟环境自举逻辑
│   ├── core/                # 配置、MySQL、意图识别
│   ├── web/                 # FastAPI + agent-loop 编排器
│   └── mcp/
│       ├── task_board_server.py
│       ├── server.py
│       ├── launcher.py
│       ├── run.py
│       ├── requirements.txt
│       ├── test_task_board.py
│       └── test_integration_d13.py
├── web/
│   └── static/              # Web 前端（index.html / app.js / styles.css）
```

---

## 运行测试

```powershell
# task-board 单元测试
.\.venv\Scripts\python.exe -m unittest src\mcp\test_task_board.py -v

# 集成测试：路由、三 Agent 交接、回修模拟
.\.venv\Scripts\python.exe src\mcp\test_integration_d13.py
```

测试报告见 [reports/integration-test-report.md](reports/integration-test-report.md)。

---

## MCP 工具

### task-board

| 工具 | 用途 |
|------|------|
| `create_task` | 创建看板或任务 |
| `assign_task` | 分配给 subagent |
| `append_result` | 记录执行/验收结果 |
| `list_tasks` | 查询看板状态 |
| `complete_task` | 标记任务完成 |
| `request_rework` | verifier 打回 builder（最多 2 轮） |

### mysql-local

| 工具 | 用途 |
|------|------|
| `test_connection` | 测试数据库连接 |
| `list_tables` | 列出表 |
| `describe_table` | 查看表结构 |
| `execute_query` | 只读 SQL（SELECT / SHOW / DESCRIBE） |

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [docs/agent-handoff-protocol.md](docs/agent-handoff-protocol.md) | 架构、Handoff 协议、失败处理 |
| [reports/demo-retrospective.md](reports/demo-retrospective.md) | 项目复盘与已知问题 |
| [reports/integration-test-report.md](reports/integration-test-report.md) | 集成测试结果 |
| [.cursor/skills/agent-loop/SKILL.md](.cursor/skills/agent-loop/SKILL.md) | 闭环调度与触发词 |
| [.cursor/skills/agent-loop/report-template.md](.cursor/skills/agent-loop/report-template.md) | 分析报告六节模板 |

---

## 环境自举说明

| 组件 | 启动方式 | 无 Python 时 |
|------|----------|--------------|
| **MCP** | `scripts/run-mcp.cmd` → `launcher.py` → `.venv` | 输出安装指引，MCP 连接失败 |
| **Hook** | `.cursor/hooks/run_hook.cmd` → `run_hook.py` → `.venv` | 写入 `hook-debug.log` 并跳过，不阻塞 Cursor |
| **手动初始化** | `scripts/setup.ps1` / `setup.sh` | 提示安装 Python 后重试 |

Hook 与 MCP **共用** 项目根目录下的 `.venv`，不再依赖系统 `python` 命令。

---

## 已知限制

- `before_submit_analysis` Hook 对「销售」「看看」等词可能产生审计日志假阳性，实际路由以主 Agent 语义判断为准
- 数据库写操作默认禁止（`MYSQL_ALLOW_WRITES=false`）
- macOS/Linux 下 Cursor Hook 需将 `hooks.json` 中的 `run_hook.cmd` 改为 `run_hook.sh`（当前默认 Windows）




## demo复盘：从零搭建一个 AI Agent 数据分析系统

一、项目背景
模拟日常业务数据分析工作中一个真实痛点：每次分析需求来了，都要手动写 SQL、调图表、整理报告，重复劳动占比很高，所以让 AI Agent 像人一样，按照"规划→执行→验收"的流程，自动完成整套数据分析。

二、架构设计
整个系统的核心是一个 三 Agent 协作闭环：

planner（规划拆解）
  → builder（探库取数 + 生成报告）
    → verifier（独立验收，不合格打回重修）
为了支撑这个流程，我搭建了两个 MCP（Model Context Protocol）服务：

|MCP服务	|      职责     |
|-------- |--------------|
task-board|任务看板，跟踪每个 Agent 的状态、结果、回修记录|
mysql-local|只读数据库连接，仅 builder 可以调用，确保数据安全|

这三个 Agent 通过看板协作，互不越权——planner 只负责拆任务，builder 只负责取数写报告，verifier 只负责挑毛病。模拟"需求评审→开发→测试"流程。

三、技术实现
3.1 IDE 阶段
在 Cursor IDE 中，写了一套 Skill 规则文件（.cursor/skills/agent-loop/），定义了：

哪些问题触发分析流程（趋势、对比、归因、分群、假设五大类，50+ 典型场景）
报告的六节固定结构（概要→结论→指标→分析→建议→说明）
失败处理机制（verifier 打回 builder 重新取数，最多回修 2 轮）
3.2 Web 化阶段
用 FastAPI + Cursor SDK 把这个流程搬到了浏览器上：

用户输入分析问题
  → FastAPI 后台异步执行 Cursor Agent
    → 前端轮询进度（规划中 → 取数中 → 验收中）
      → 验收通过后展示六节 Markdown 报告

几个关键点：
异步编排：用 BackgroundTasks 在后台跑 Agent，前端用 setInterval 轮询状态，不会阻塞 UI
意图分类：用正则规则区分"分析类问题"和"日常聊天"，分析类走 Agent 闭环，聊天类直通模型回答，避免浪费 API 额度
持久化容错：看板文件存磁盘，即使服务重启历史记录不丢

3.3 项目结构
src/
├── core/              # 配置、MySQL 客户端、意图识别
├── mcp/               # task-board + mysql-local MCP 服务
├── web/               # FastAPI 后端 + Agent 编排器
web/static/            # 前端 HTML/CSS/JS
boards/                # 看板持久化文件
