# Graph Report - web_agent  (2026-07-06)

## Corpus Check
- 60 files · ~32,406 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 470 nodes · 715 edges · 33 communities (25 shown, 8 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 52 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 32|Community 32]]

## God Nodes (most connected - your core abstractions)
1. `AgentLoopOrchestrator` - 20 edges
2. `ensure_venv()` - 13 edges
3. `my_first_agent` - 12 edges
4. `团队 SQL 开发规范` - 12 edges
5. `三 Agent 架构与 Handoff 协议` - 11 edges
6. `CursorAgentLoopOrchestrator` - 10 edges
7. `_fmt_num()` - 10 edges
8. `_load_board()` - 9 edges
9. `_save_board()` - 9 edges
10. `Agent 协作闭环` - 9 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `ensure_venv()`  [INFERRED]
  .cursor/hooks/run_hook.py → src/bootstrap/venv.py
- `main()` --calls--> `print_python_install_guide()`  [INFERRED]
  .cursor/hooks/run_hook.py → src/bootstrap/venv.py
- `main()` --calls--> `venv_python_path()`  [INFERRED]
  .cursor/hooks/run_hook.py → src/bootstrap/venv.py
- `main()` --calls--> `extract_sql_metadata()`  [INFERRED]
  .cursor/hooks/before_mcp_analysis_audit.py → .cursor/hooks/analysis_common.py
- `health()` --calls--> `get_api_key()`  [INFERRED]
  src/web/app.py → src/core/cursor_config.py

## Import Cycles
- None detected.

## Communities (33 total, 8 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.14
Nodes (16): classify_intent(), AnalysisType, 分析意图识别（与 agent-loop 路由一致）。, analyze_status(), _get_job(), get_report(), list_history(), AgentLoopOrchestrator (+8 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (35): append_analysis_intent_log(), append_analysis_query_log(), extract_sql_metadata(), 数据分析 Hook 公共模块：意图识别与 SQL 审计。, _extract_query(), _extract_tool_info(), _is_mysql_readonly_query(), main() (+27 more)

### Community 2 - "Community 2"
Cohesion: 0.21
Nodes (23): append_result(), assign_task(), _board_path(), _boards_dir(), complete_task(), create_task(), _ensure_rework_fields(), _find_task() (+15 more)

### Community 3 - "Community 3"
Cohesion: 0.15
Nodes (12): audit_board_handover(), classify_analysis_intent(), D13HistoricalAuditTest, D13IntegrationTest, expect_agent_loop(), Any, D13 集成测试：五类任务路由 + 三 Agent 交接验证。, 失败修复类：verifier request_rework → builder 修复 → verifier 通过。 (+4 more)

### Community 4 - "Community 4"
Cohesion: 0.14
Nodes (14): codegraph, mysql-local, task-board, MYSQL_ALLOW_WRITES, MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT (+6 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (35): 10.1 月度趋势模板, 10.2 探库检查模板, 10. 附录：快速模板, 11. 版本与反馈, 1.1 目标, 1.2 基本原则, 1.3 环境安全（强制）, 1. 总则 (+27 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (25): adminBtn, adminDialog, adminForm, adminMsg, cancelAdmin, emptyState, fetchHistory(), hideLoading() (+17 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (26): _append_bootstrap_log(), main(), Path, Hook 启动器：自举 .venv 后用项目虚拟环境执行指定 Hook 脚本。  Hook 必须继承 stdin（Cursor 传入 JSON），因此使用, _venv_ready(), 项目环境自举：虚拟环境检测、创建与依赖安装。, main(), 项目环境初始化 CLI。  用法（在项目根目录）：   python src/bootstrap/setup.py   py -3 src/bootst (+18 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (19): Agent 协作闭环, MCP 分工, task-board 工具, 主 Agent 执行步骤, 失败处理, ⚠️ 强制规则（主 Agent 必读）, 统一报告结构, 适用场景 (+11 more)

### Community 9 - "Community 9"
Cohesion: 0.22
Nodes (8): Builder Agent, 工作流程（verifier 回修委派）, 工作流程（首次实现）, 报告结构（必须遵守）, 数据分析规范, 约束, 职责, 输出要求

### Community 10 - "Community 10"
Cohesion: 0.22
Nodes (8): Verifier Agent, 委派 builder 时的 Task 提示词模板, 工作流程, 报告结构验收（权威引用）, 约束, 职责, 输出格式（返回主 Agent）, 验收清单（T1/T2 补充）

### Community 12 - "Community 12"
Cohesion: 0.07
Nodes (28): 1. 初始化环境, 1. 进入项目目录, 2. 初始化环境（推荐）, 2. 启动 Web 服务, 3. 配置 MySQL, 3. 配置 MySQL 与 Cursor API Key, 4. 使用流程, 4. 在 Cursor 中启用 MCP (+20 more)

### Community 13 - "Community 13"
Cohesion: 0.08
Nodes (25): 10. 变更记录, 1.1 设计原则, 1. 系统架构, 2. Agent 职责矩阵, 3.1 标准任务拆分, 3.2 交接时序, 3.3 主 Agent → planner-agent, 3.4 planner-agent 输出 (+17 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (35): BackgroundTasks, BaseModel, apply_config(), _ensure_data_dir(), load_config(), public_config(), Any, save_config() (+27 more)

### Community 16 - "Community 16"
Cohesion: 0.36
Nodes (10): _append_log(), _extract_file_path(), _format_file(), _format_json(), _format_python(), _format_sql(), _format_text(), _log_dir() (+2 more)

### Community 17 - "Community 17"
Cohesion: 0.36
Nodes (10): _allow_writes(), describe_table(), execute_query(), _format_result(), get_connection(), _get_db_config(), list_tables(), 本地 MySQL MCP 服务，通过 stdio 与 Cursor 通信。 (+2 more)

### Community 18 - "Community 18"
Cohesion: 0.40
Nodes (10): _allow_writes(), describe_table(), execute_query(), _format_result(), get_connection(), _get_db_config(), list_tables(), Any (+2 more)

### Community 19 - "Community 19"
Cohesion: 0.29
Nodes (6): Planner Agent, 工作流程, 报告结构（权威引用）, 约束, 职责, 输出格式

### Community 20 - "Community 20"
Cohesion: 0.29
Nodes (6): 1. 分析概要, 2. 核心结论（3~5 条 bullet，先结论后细节）, 3. 关键指标, 4. 详细分析, 5. 业务建议, 6. 数据说明与局限

### Community 21 - "Community 21"
Cohesion: 0.50
Nodes (3): PYTHONIOENCODING, PYTHONUTF8, run_hook.sh script

### Community 22 - "Community 22"
Cohesion: 0.50
Nodes (3): PYTHONIOENCODING, PYTHONUTF8, run-mcp.sh script

### Community 32 - "Community 32"
Cohesion: 0.14
Nodes (14): 1. 项目目标, 2.1 分析类（走 agent-loop）, 2.2 非分析类（不走 agent-loop）, 2. 典型使用场景, 3. 流程时序, 4. 已实现能力, 5.1 有效做法, 5.2 待改进项 (+6 more)

## Knowledge Gaps
- **154 isolated node(s):** `run_hook.sh script`, `PYTHONUTF8`, `PYTHONIOENCODING`, `MYSQL_HOST`, `MYSQL_PORT` (+149 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `my_first_agent` connect `Community 12` to `Community 8`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Why does `三 Agent 架构与 Handoff 协议` connect `Community 13` to `Community 8`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `ensure_venv()` (e.g. with `main()` and `main()`) actually correct?**
  _`ensure_venv()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `数据分析 Hook 公共模块：意图识别与 SQL 审计。`, `Hook 公共模块：危险意图检测与 mcp-guard 日志。`, `从 stdin 读取 hook JSON；兼容 Windows BOM / 编码损坏 / 空输入。` to the rest of the system?**
  _187 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.14264264264264265 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.09413067552602436 - nodes in this community are weakly interconnected._
- **Should `Community 4` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._