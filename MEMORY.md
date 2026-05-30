
---

## Claude Code 移植项目（进行中）

**开始时间：** 2026-04-07
**最新快照：** 2026-04-16 16:00

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

**当前状态（2026-05-19）：**
- Python 文件总数 1,312 个，总行数 ~221,740 行
- stub 文件（index.py < 20行）**0 个** ✅ 全部消灭
- commands `__init__.py` 4行导入包装 ~84个（设计如此，不是 stub）
- 完成率 **~100%**（所有 index.py 均有实质内容）
- 测试 48 passed ✅ 全程稳定

**本轮新增（2026-05-19，3 subagent 并行）：**
- SA-A（commands a-m）：修复 clear/index.py（6→35行）、compact/index.py（10→52行），其余41个已就绪
- SA-B（commands m-z）：42个全部已就绪，无需修改
- SA-C（tools/services/utils）：93个文件全部处理，修复 BashTool 错误导入路径

**最近 git commits（2026-05-19）：**
- `c221b29` feat(tools/services/utils): fill stubs SA-C
- `2d7e202` feat(commands): fill stubs SA-A (a-m commands)
- `c90f74d` feat(commands): fill stubs SA-B (m-z commands)

**2026-05-28 最新进展（完整）：**
- 端到端集成测试：**180 passed** ✅（test_integration.py 50 + test_new_tools.py 82 + 原 48）
- 7 个工具从抽象类补全：FileMoveTool / NotebookReadTool / TaskCreate/Get/List/Stop/UpdateTool
- `is_command_enabled()` bug 修复（getattr 防御式）；`get_commands()` 返回 57 个命令
- **混元 Python 接入完成，tool_use 循环实测跑通** ✅
- git tail: `352e26c` → `8fbd52a` → `7d98f18` → `5dc36f0`

**工具接口（已确认）：**
- Tool 基类需实现：`async description()`, `async prompt()`, `def input_schema()`, `async call(input_data, context)`
- GrepTool 例外：kwargs 展开（历史遗留）
- `get_commands(cwd)` 是 async，返回 57 个命令

**混元 Python 接入（claude-code-python，2026-05-28 完成）：**
- `services/api/client.py`：新增 `_HunyuanClient` OpenAI-compat wrapper
  - `client.messages.create(**anthropic_kwargs)` → `/v1/chat/completions`
  - Anthropic↔OpenAI 消息/工具格式双向转换
  - Priority: HUNYUAN_API_KEY > Bedrock > Vertex > firstParty
- `query.py`：修复 _serialize_tools（async description 方法不可 JSON 序列化）
- `query.py`：修复 _dispatch_tool（大小写不敏感 + dict/_tool_obj 支持）
- `query_engine.py`：_run_turn 中预先 await 所有 tool async 方法
- **实测（hunyuan-turbos-latest）**：tool_use 循环完整（模型→BashTool→stdout→回答）

**混元可用模型（2026-05-28 确认）：**
- 快速：`hunyuan-turbos-latest`
- 推理：`hunyuan-t1-latest`
- ❌ `hy3-preview`、`hunyuan-think` 均不存在

**混元环境变量：**
```
HUNYUAN_API_KEY=xxx
HUNYUAN_MODEL=hunyuan-turbos-latest  # 或 hunyuan-t1-latest
HUNYUAN_BASE_URL=https://api.hunyuan.cloud.tencent.com/v1  # 可选
```

**仍待推进：**
- `cli/print.py` React/Ink 渲染逻辑细化
- 导入完整性测试（import all modules，验证无循环依赖）

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
