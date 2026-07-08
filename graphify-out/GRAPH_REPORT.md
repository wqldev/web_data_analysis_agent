# Graph Report - .  (2026-07-08)

## Corpus Check
- Corpus is ~19,635 words - fits in a single context window. You may not need a graph.

## Summary
- 359 nodes · 646 edges · 25 communities (20 shown, 5 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 63 edges (avg confidence: 0.76)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Intent Classification & Rules|Intent Classification & Rules]]
- [[_COMMUNITY_Web Frontend UI|Web Frontend UI]]
- [[_COMMUNITY_Agent Architecture & Handoff Protocol|Agent Architecture & Handoff Protocol]]
- [[_COMMUNITY_Bootstrap & Environment Setup|Bootstrap & Environment Setup]]
- [[_COMMUNITY_Agent Loop Orchestrator|Agent Loop Orchestrator]]
- [[_COMMUNITY_Task Board MCP Server|Task Board MCP Server]]
- [[_COMMUNITY_Cursor Config & Orchestration|Cursor Config & Orchestration]]
- [[_COMMUNITY_LLM Client & Model Config|LLM Client & Model Config]]
- [[_COMMUNITY_Integration Tests|Integration Tests]]
- [[_COMMUNITY_Churn Builder Script|Churn Builder Script]]
- [[_COMMUNITY_SQLite Client|SQLite Client]]
- [[_COMMUNITY_MySQL MCP Server|MySQL MCP Server]]
- [[_COMMUNITY_Builder Analysis Script|Builder Analysis Script]]
- [[_COMMUNITY_MySQL Client Library|MySQL Client Library]]
- [[_COMMUNITY_MySQL to SQLite Export|MySQL to SQLite Export]]
- [[_COMMUNITY_Task Board Unit Tests|Task Board Unit Tests]]
- [[_COMMUNITY_MCP Shell Runner Scripts|MCP Shell Runner Scripts]]
- [[_COMMUNITY_Setup Shell Scripts|Setup Shell Scripts]]
- [[_COMMUNITY_MCP Launcher|MCP Launcher]]
- [[_COMMUNITY_Web Shell Runner|Web Shell Runner]]
- [[_COMMUNITY_Core Module Init|Core Module Init]]

## God Nodes (most connected - your core abstractions)
1. `AgentLoopOrchestrator` - 24 edges
2. `Handoff Protocol` - 14 edges
3. `ensure_venv()` - 12 edges
4. `start_analyze()` - 11 edges
5. `_save_board()` - 10 edges
6. `_fmt_num()` - 10 edges
7. `load_config()` - 9 edges
8. `_load_board()` - 9 edges
9. `analyze_sync()` - 9 edges
10. `main()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `ensure_board()` --calls--> `_boards_dir()`  [INFERRED]
  scripts/builder_analysis.py → src/mcp/task_board_server.py
- `ensure_board()` --calls--> `_save_board()`  [INFERRED]
  scripts/builder_analysis.py → src/mcp/task_board_server.py
- `main()` --calls--> `append_result()`  [INFERRED]
  scripts/builder_analysis.py → src/mcp/task_board_server.py
- `main()` --calls--> `complete_task()`  [INFERRED]
  scripts/builder_analysis.py → src/mcp/task_board_server.py
- `mysql-local MCP` --enforces--> `Read-Only Default Principle`  [INFERRED]
  README.md → docs/sql-development-standards.md

## Import Cycles
- None detected.

## Communities (25 total, 5 thin omitted)

### Community 0 - "Intent Classification & Rules"
Cohesion: 0.09
Nodes (39): BackgroundTasks, BaseModel, InfoQueryType, classify_info_query(), classify_intent(), is_ddl_request(), AnalysisType, 分析意图识别（与 agent-loop 路由一致）。 (+31 more)

### Community 1 - "Web Frontend UI"
Cohesion: 0.06
Nodes (36): adminBtn, adminDialog, adminForm, adminMsg, cancelAdmin, clearGeneralAnswer, completeDialog, completeIcon (+28 more)

### Community 2 - "Agent Architecture & Handoff Protocol"
Cohesion: 0.08
Nodes (35): Board Status Machine, Builder Agent, Design Principles, Failure Handling, Handoff Protocol, Hooks and Audit, Main Agent, MCP Tool Contract (+27 more)

### Community 3 - "Bootstrap & Environment Setup"
Cohesion: 0.16
Nodes (21): 项目环境自举：虚拟环境检测、创建与依赖安装。, main(), 项目环境初始化 CLI。  用法（在项目根目录）：   python src/bootstrap/setup.py   py -3 src/bootst, _deps_installed(), ensure_venv(), find_system_python(), _log(), print_python_install_guide() (+13 more)

### Community 4 - "Agent Loop Orchestrator"
Cohesion: 0.24
Nodes (6): AgentLoopOrchestrator, _fmt_num(), _now_iso(), _pct_change(), AnalysisType, Any

### Community 5 - "Task Board MCP Server"
Cohesion: 0.21
Nodes (23): append_result(), assign_task(), _board_path(), _boards_dir(), complete_task(), create_task(), _ensure_rework_fields(), _find_task() (+15 more)

### Community 6 - "Cursor Config & Orchestration"
Cohesion: 0.17
Nodes (14): _ensure_data_dir(), get_api_key(), get_model(), load_config(), public_config(), Any, save_config(), _build_mcp_servers() (+6 more)

### Community 7 - "LLM Client & Model Config"
Cohesion: 0.19
Nodes (17): chat_completion(), Any, 通用 LLM API 客户端（替换 cursor-sdk）。支持 OpenAI 兼容接口。, 调用 OpenAI 兼容的聊天补全 API，返回回复文本。, test_api_connection(), _ensure_data_dir(), get_api_base(), get_api_key() (+9 more)

### Community 8 - "Integration Tests"
Cohesion: 0.16
Nodes (12): audit_board_handover(), classify_analysis_intent(), D13HistoricalAuditTest, D13IntegrationTest, expect_agent_loop(), Any, D13 集成测试：五类任务路由 + 三 Agent 交接验证。, 失败修复类：verifier request_rework → builder 修复 → verifier 通过。 (+4 more)

### Community 9 - "Churn Builder Script"
Cohesion: 0.26
Nodes (14): ensure_tasks(), fmt_num(), main(), now_iso(), Builder-agent: 用户流失分析 T1~T3 执行脚本。, run_t1(), run_t2(), run_t3() (+6 more)

### Community 10 - "SQLite Client"
Cohesion: 0.25
Nodes (13): Row, _allow_writes(), _convert_mysql_sql(), describe_table(), execute_query(), _format_result(), get_connection(), _get_db_path() (+5 more)

### Community 11 - "MySQL MCP Server"
Cohesion: 0.33
Nodes (11): _allow_writes(), describe_table(), execute_query(), _format_result(), get_connection(), _get_db_config(), list_tables(), Any (+3 more)

### Community 12 - "Builder Analysis Script"
Cohesion: 0.35
Nodes (10): build_report(), compute_mom(), ensure_board(), fmt_mom(), fmt_money(), fmt_yoy(), json_default(), main() (+2 more)

### Community 13 - "MySQL Client Library"
Cohesion: 0.40
Nodes (10): _allow_writes(), describe_table(), execute_query(), _format_result(), get_connection(), _get_db_config(), list_tables(), Any (+2 more)

### Community 14 - "MySQL to SQLite Export"
Cohesion: 0.29
Nodes (9): clean_line(), convert_create_sql(), export(), mysql_type_to_sqlite(), 将 MySQL 数据导出到 SQLite .db 文件。, Split column definitions respecting nested parentheses., Clean a MySQL column definition line for SQLite., Convert MySQL CREATE TABLE to SQLite-compatible syntax. (+1 more)

### Community 16 - "MCP Shell Runner Scripts"
Cohesion: 0.50
Nodes (3): PYTHONIOENCODING, PYTHONUTF8, run-mcp.sh script

## Knowledge Gaps
- **37 isolated node(s):** `run-mcp.sh script`, `PYTHONUTF8`, `PYTHONIOENCODING`, `run-web.sh script`, `setup.sh script` (+32 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AgentLoopOrchestrator` connect `Agent Loop Orchestrator` to `Intent Classification & Rules`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `main()` connect `Builder Analysis Script` to `Task Board MCP Server`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `AgentLoopOrchestrator` (e.g. with `analyze_sync()` and `AnalyzeRequest`) actually correct?**
  _`AgentLoopOrchestrator` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `ensure_venv()` (e.g. with `main()` and `main()`) actually correct?**
  _`ensure_venv()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `start_analyze()` (e.g. with `classify_info_query()` and `classify_intent()`) actually correct?**
  _`start_analyze()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Builder-agent SQL analysis for near-half-year sales trend.`, `将 MySQL 数据导出到 SQLite .db 文件。`, `Split column definitions respecting nested parentheses.` to the rest of the system?**
  _89 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Intent Classification & Rules` be split into smaller, more focused modules?**
  _Cohesion score 0.09082125603864734 - nodes in this community are weakly interconnected._