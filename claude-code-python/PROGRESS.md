# Migration Progress

## Overview
Python port of Claude Code TypeScript source.
Source: `/root/.openclaw/workspace/claude-code-analysis/claude-code-source/`
Target: `/root/.openclaw/workspace/claude-code-python/`

Last updated: 2026-04-08

---

## Phase 1: Project Structure ✅ COMPLETE
- [x] `pyproject.toml` — project config, dependencies
- [x] Directory structure: `src/claude_code/{types,constants,utils,tools,services,commands,cli}/`
- [x] `README.md`

---

## Phase 2: Types ✅ COMPLETE
| TS File | Python File | Status |
|---------|-------------|--------|
| `types/command.ts` | `types/command.py` | ✅ |
| `types/ids.ts` | `types/ids.py` | ✅ |
| `types/permissions.ts` | `types/permissions.py` | ✅ Full port incl. all discriminated unions |
| `types/plugin.ts` | `types/plugin.py` | ✅ Full port incl. get_plugin_error_message() |

---

## Phase 3: Constants ✅ COMPLETE
| TS File | Python File | Status |
|---------|-------------|--------|
| `constants/common.ts` | `constants/common.py` | ✅ |
| `constants/product.ts` | `constants/product.py` | ✅ |
| `constants/messages.ts` | `constants/messages.py` | ✅ |
| `constants/files.ts` | `constants/files.py` | ✅ |
| `constants/tools.ts` | `constants/tools.py` | ✅ |

---

## Phase 4: Utils (partial)
| TS File | Python File | Status |
|---------|-------------|--------|
| `utils/envUtils.ts` | `utils/env_utils.py` | ✅ |
| `utils/errors.ts` | `utils/errors.py` | ✅ |
| `utils/file.ts` | `utils/file.py` | ✅ (partial) |
| `utils/format.ts` | `utils/format.py` | ✅ |
| `utils/Shell.ts` | `utils/shell.py` | ✅ (core exec) |
| `utils/ShellCommand.ts` | `utils/shell_command.py` | ✅ (types) |
| `utils/model/model.ts` | `utils/model/__init__.py` | ⚠️ partial |
| `utils/path.ts` | `utils/path.py` | ✅ |
| `utils/git.ts` | `utils/git.py` | ✅ (partial) |
| `utils/log.ts` | `utils/log.py` | ✅ |
| `utils/messages.ts` | `utils/messages.py` | ✅ |
| `utils/settings/*.ts` | `utils/settings.py` | ✅ (partial) |
| `utils/stringUtils.ts` | `utils/string_utils.py` | ✅ |
| `utils/array.ts` | `utils/array.py` | ✅ |
| `utils/cwd.ts` | `utils/cwd.py` | ✅ |
| `utils/json.ts` | `utils/json_utils.py` | ✅ |
| 530+ other utils files | — | 🔲 TODO |

---

## Phase 5: Tools ✅ (core tools complete)
| TS Tool | Python File | Status |
|---------|-------------|--------|
| `BashTool` | `tools/bash_tool.py` | ✅ |
| `FileReadTool` | `tools/file_read_tool.py` | ✅ |
| `FileEditTool` | `tools/file_edit_tool.py` | ✅ |
| `FileWriteTool` | `tools/file_write_tool.py` | ✅ |
| `GrepTool` | `tools/grep_tool.py` | ✅ (rg + fallback) |
| `GlobTool` | `tools/glob_tool.py` | ✅ |
| `TodoWriteTool` | `tools/todo_write_tool.py` | ✅ |
| `WebFetchTool` | `tools/web_fetch_tool.py` | ✅ |
| `WebSearchTool` | `tools/web_search_tool.py` | ⚠️ stub |
| `AgentTool` | `tools/agent_tool.py` | ⚠️ stub |
| `SleepTool` | `tools/agent_tool.py` | ✅ |
| `NotebookEditTool` | `tools/notebook_edit_tool.py` | ✅ |
| 131 other tools | — | 🔲 TODO stubs |

---

## Phase 6: Services (partial)
| TS File | Python File | Status |
|---------|-------------|--------|
| `services/api/client.ts` | `services/api/__init__.py` | ✅ (direct Anthropic only) |
| `services/tokenEstimation.ts` | `services/token_estimation.py` | ✅ |
| `services/query.ts` | `services/query.py` | ✅ (basic loop) |
| Bedrock client | — | 🔲 TODO (requires boto3) |
| Vertex AI client | — | 🔲 TODO (requires google-auth-library) |

---

## Phase 7: Commands (stub)
| TS Commands | Python File | Status |
|------------|-------------|--------|
| All 101 commands | `commands/__init__.py` | ⚠️ 24 stubs registered |

---

## Phase 8: CLI entrypoint
| TS File | Python File | Status |
|---------|-------------|--------|
| `entrypoints/cli.tsx` | `main.py` | ⚠️ Basic CLI + print mode |
| Interactive REPL | — | 🔲 TODO (React/Ink → prompt_toolkit/textual) |

---

## Test Coverage
- 23 unit tests, all passing ✅
- Test file: `tests/test_basic.py`

---

## File Count
- Python files: 43 (src/) + 1 (tests/)
- TS source files (reference): ~1100+

---

## TODOs (Not Yet Ported)
- [ ] Interactive REPL (React/Ink → TODO: prompt_toolkit or textual)
- [ ] Full agentic query loop with streaming
- [ ] Bedrock API provider (requires boto3)
- [ ] Vertex AI provider (requires google-auth-library)
- [ ] MCP server integration
- [ ] Full config file system (settings merge, schema validation)
- [ ] Session persistence
- [ ] OAuth / Claude.ai authentication
- [ ] AgentTool subagent spawning
- [ ] Background tasks
- [ ] LSP integration
- [ ] Plugin system
- [ ] Settings sync
- [ ] Hooks system
- [ ] 530+ remaining utility files
- [ ] 131 remaining tool implementations
- [ ] Full command implementations (24 stubs, need logic)

---

## Notes
- All files include `原始 TS:` comment header pointing to source TS file
- Bun-specific APIs (`bun:bundle feature()`) → Python env var checks
- Native NAPI modules → TODO stubs
- React/Ink UI → TODO stubs
- Tool name mapping: Read/Edit/Write (matches TS source, NOT FileRead/FileEdit/FileWrite)
