
---

## Claude Code 移植项目（进行中）

**开始时间：** 2026-04-07
**最新快照：** 2026-04-10 00:30

| 指标 | Python |
|------|--------|
| 文件数 | **1181** .py |
| 测试 | **48 passed** ✅ |
| 顶层文件 | ✅ 全覆盖（query.py, commands.py, tools.py, history.py, setup.py, cost_tracker.py 等） |
| utils | ~103% |
| services | ~93% |
| commands | ~91% |
| tools | ~103% |

**关键路径：**
- 源码：`claude-code-analysis/claude-code-source/`
- Python：`claude-code-python/src/claude_code/`

**已实现的核心架构文件：**
- `query.py`：完整工具循环、streaming events（assistant/tool_use/tool_result/final_response）
- `query_engine.py`：QueryEngine 类（stream/ask/clear/set_messages）
- `tools.py`：工具注册中心（get_all_base_tools/assemble_tool_pool/get_merged_tools）
- `commands.py`：命令注册中心（lazy import + alias 查找）
- `cost_tracker.py`：完整 cost 追踪（add_usage/format_total_cost/save_session）
- `history.py`：会话历史（JSONL + pasted text refs）
- `setup.py`：会话初始化
- FileReadTool/FileEditTool/FileWriteTool/GlobTool/GrepTool（完整实现）

**下一步：**
1. services/ 剩余 7%（api/ 边缘文件）
2. commands/ 剩余 9%（insights 3200行最大，暂跳）
3. tasks/ 子目录（LocalShellTask, LocalAgentTask, DreamTask 等）

---

## PRINCIPLES.md — 跨 Agent 共享的认知信条

**文件：** `/root/.openclaw/workspace/PRINCIPLES.md`
**建立时间：** 2026.04.05

**10条信条（P1-P10）：**
- P1：工程外壳就是系统行为的一部分
- P2：LLM 的不可靠，可以被工程的确定性包住
- P3：趋同是信号
- P4：把"应该"编进代码，不依赖"记得"
- P5：保守默认，显式放开
- P6：判断什么时候什么都不做，比判断什么时候继续更难
- P7：错误处理不是善后，是设计的一部分
- P8：观测先于优化
- P9：最简单的抽象，往往最持久
- P10：结论可以被共享，推导路径让结论有根
