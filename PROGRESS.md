# Claude Code Python 移植进度

**最后更新:** 2026-04-16 11:27 CST

## 总体指标

| 指标 | 值 |
|------|-----|
| Python 文件总数 | **1267** |
| Python 总代码行数 | **117,101 行** |
| 测试 | **48 passed** ✅ |
| TS 源文件数 | 1333 |
| 整体估算覆盖 | ~1050/1333（**~79%**）|
| 大实现文件（>500行） | **48 个** |
| stub 文件（<20行） | **537 个**（待推进） |

## 各模块覆盖率

| 模块 | Python | TypeScript | 覆盖率 |
|------|--------|-----------|--------|
| `utils/` | 570 | 549 | ✅ **103%** |
| `services/` | 120 | 128 | ✅ **93%** |
| `commands/` | 101 | 110 | ✅ **91%** |
| `tools/` | 154 | 149 | ✅ **103%** |

## 已完成的工具（tools/）

### 文件操作工具
- FileReadTool: cat-n 格式, limits 检查, 图片/notebook 支持
- FileEditTool: 精确字符串替换, quote 规范化, mtime 追踪
- FileWriteTool: 自动建目录, 覆写/新建
- GlobTool: ** 通配符, mtime 排序, 100 条限制
- GrepTool: ripgrep + Python fallback, 3 种 output_mode
- NotebookEditTool: replace/insert/delete

### Agent 工具
- AgentTool: 完整子模块（run_agent, resume_agent, load_agents_dir, fork_subagent, agent_memory 等）
- SleepTool, RemoteTriggerTool, ScheduleCronTool

### 任务/MCP 工具
- Task*Tool (Create/Get/List/Update/Stop/Output)
- MCP*Tool (mcp_tool, m_c_p_tool, list/read_mcp_resources)
- MCPAuthTool

### 其他工具
- ConfigTool: get/set settings
- LSPTool: go-to-def, find-refs, hover, symbols
- SkillTool, BriefTool, ToolSearchTool
- EnterPlanModeTool, ExitPlanModeTool, EnterWorktreeTool, ExitWorktreeTool
- SendMessageTool, SyntheticOutputTool
- WebFetchTool, WebSearchTool
- TodoReadTool, TodoWriteTool
- BashTool (完整 17 个子模块)
- PowerShellTool (完整子模块)

## 本轮新增（2026-04-16）

### agentic loop 核心
- `query.py` — 193→557行：thinking blocks、hooks、429/529重试、compact boundary
- `query_engine.py` — 112→525行：submit_message、interrupt、fork、ask/ask_text

### API 层
- `services/api/claude.py` — 229→845行：10个核心函数（cache_control、add_cache_breakpoints、strip_excess_media、message转换等）
- `services/api/errors.py` — 2→731行：完整错误分类体系、所有错误常量和helper

### 配置/权限层
- `utils/config.py` — 70→740行：GlobalConfig（60+字段）、get_global_config、save_global_config（原子写入）
- `utils/settings/types.py` — 1→499行：SettingsJson、Permissions、MCP server类型
- `utils/permissions/filesystem.py` — 1→715行：路径权限检查、危险路径检测
- `utils/permissions/yolo_classifier.py` — 1→673行：YOLO auto-mode分类器

### commands/ 关键命令
- `commands/context/context_noninteractive.py` — 1→390行（collectContextData、Markdown表格）
- `commands/compact/compact.py` — →326行（完整compaction流水线）
- `commands/branch/branch.py` — 1→339行（会话fork、transcript复制）
- `commands/mcp/add_command.py` — 新建404行（MCP服务器添加，stdio/sse/http+OAuth）
- `commands/review/review_remote.py` — 新建467行（ultrareview远程评审）

## 历史新增（2026-04-10）
- `tasks/local_main_session_task/` — LocalMainSessionTask（479行TS → Python）
- `cli/print.py` — CLI 打印核心（5594行TS → 965行Python）
- `bridge/bridge_main.py` — Bridge 主循环（2999行TS → 2631行Python）

## 剩余主要缺口

| 文件 | TS行数 | 现状 | 优先级 |
|------|--------|------|--------|
| `utils/hooks.ts` | 5022 | 313行facade（实现在hooks_execute.py等）| 中 |
| `commands/insights.ts` | 3200 | 7行stub | 低（复杂UI） |
| `utils/bash/ast.ts` | 2679 | 474行（17%）| 高 |
| `services/mcp/config.ts` | 1578 | 1行stub | 高 |
| `utils/ide.ts` | 1494 | 2行stub | 中 |
| `cli/print.ts` | 5594 | 965行（17%）| 中 |
| `services/mcp/client.ts` | 3348 | 已实现1979行 ✅ | 完成 |

## 工程结构
- 源码: `/root/.openclaw/workspace/claude-code-analysis/claude-code-source/`
- Python: `/root/.openclaw/workspace/claude-code-python/src/claude_code/`
- 测试: `/root/.openclaw/workspace/claude-code-python/tests/`
