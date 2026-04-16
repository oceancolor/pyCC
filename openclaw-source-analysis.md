# OpenClaw 最新版源码架构分析（2026.4.4）

> 分析时间：2026-04-05
> 源码版本：2026.4.4（commit: 4954d02）
> 代码规模：460,787 行 TypeScript（src/ 目录），不含 extensions
> 仓库：https://github.com/openclaw/openclaw

---

## 一、整体规模与目录结构

```
openclaw/
├── src/                    ~595K 行 TS（含测试）
│   ├── agents/             267,589 行  ← 最大子系统（AI 运行时）
│   ├── gateway/            122,265 行  ← HTTP/WS 服务器
│   ├── security/            14,561 行  ← 安全审计
│   ├── channels/            29,015 行  ← 消息渠道抽象
│   ├── hooks/                9,137 行  ← Hook 系统
│   ├── memory-host-sdk/      9,797 行  ← 向量记忆引擎
│   ├── cron/                ~5,000 行  ← 定时任务
│   ├── acp/                 ~8,000 行  ← ACP 协议（sub-agent）
│   ├── config/             ~35,000 行  ← 配置系统
│   └── ...
├── extensions/             94 个扩展插件（渠道 + 模型提供商）
├── packages/               4 个内部包（plugin-sdk 等）
└── skills/                 内置 skills
```

**对比 Claude Code：** OpenClaw 是 60 万行级别，Claude Code 是 6 万行级别，前者是后者 10x。OpenClaw 是通用 AI 助手平台，Claude Code 是专用编程工具。

---

## 二、核心架构：三层设计

```
┌──────────────────────────────────────────────────────────┐
│  Layer 3: Channel Plugins（消息渠道）                      │
│  Telegram / WhatsApp / Discord / Slack / Signal /        │
│  WeChat / Feishu / iMessage / ... 共 21+ 渠道            │
└──────────────────────┬───────────────────────────────────┘
                       │ inbound message
┌──────────────────────▼───────────────────────────────────┐
│  Layer 2: Gateway（HTTP/WS 服务器）                        │
│  server.impl.ts - 启动/路由/Plugin 管理                  │
│  hooks.ts       - Hook 系统（外部事件注入）               │
│  cron/          - 定时任务调度                            │
│  session-utils  - session 管理                           │
└──────────────────────┬───────────────────────────────────┘
                       │ enqueue / dispatch
┌──────────────────────▼───────────────────────────────────┐
│  Layer 1: Agents（AI 运行时）                              │
│  pi-embedded-runner   - 主对话循环（最复杂）              │
│  subagent-registry    - sub-agent 生命周期管理            │
│  auth-profiles        - 多 provider 认证轮转              │
│  bash-tools           - Shell 执行（含 sandbox）          │
│  compaction           - 上下文压缩                        │
│  memory-host-sdk      - 向量语义记忆                      │
└──────────────────────────────────────────────────────────┘
```

---

## 三、与 Claude Code 的架构对比

| 维度 | Claude Code | OpenClaw |
|------|-------------|----------|
| 定位 | 专用编程助手 | 通用个人 AI 助手平台 |
| 规模 | ~6 万行 TS | ~60 万行 TS |
| AI 运行时 | queryLoop（自研） | pi-embedded-runner（依赖 @mariozechner/pi-coding-agent）|
| 消息渠道 | 仅 CLI + VS Code | 21+ 渠道（Telegram/WhatsApp/Discord 等）|
| 模型支持 | 仅 Claude | 28+ Provider（OpenAI/Gemini/Ollama/DeepSeek 等）|
| Sub-agent | AgentTool + spawnMultiAgent | subagent-registry（持久化状态）|
| 记忆系统 | 文件型 Memory（markdown）| 向量数据库（memory-lancedb + embeddings）|
| 沙箱 | 无（bash 直接执行）| Docker + SSH + browser sandbox |
| 安全审计 | 23道Bash检查 | security/audit.ts（1468行，全面系统级审计）|
| 配置系统 | JSON + MDM | Zod schema（26K行 generated）|
| 定时任务 | 无 | cron service（完整调度引擎）|
| ACP 协议 | 无 | 完整 ACP（控制平面 + 代理协议）|
| 扩展机制 | MCP 工具 | Plugin SDK + 94个扩展 |

---

## 四、关键设计决策分析

### 4.1 pi-embedded-runner：最复杂的单文件（2098行）

**架构要点：**
- 依赖外部包 `@mariozechner/pi-coding-agent`（pi 是 OpenClaw 底层 AI Agent 引擎）
- `run/attempt.ts` 是单次对话尝试的执行单元
- 支持 **failover**：认证失败自动轮换到下一个 auth profile
- `LiveSessionModelSwitchError`：session 进行中可以切换模型，不中断对话
- `compaction-safety-timeout`：压缩过程有超时保护，防止永久阻塞

**关键：多 Provider 支持的设计代价**

因为支持 28+ 个 AI Provider（OpenAI/Anthropic/Gemini/Ollama/DeepSeek...），每次 API 调用前需要：
1. `resolveAuthProfileOrder()` — 找到可用的 auth profile
2. `normalizeProviderId()` — 统一 provider ID 格式
3. `applyAuthHeaderOverride()` — 覆盖认证头
4. `ensureOpenClawModelsJson()` — 同步模型配置

这是 Claude Code 不需要的复杂度（Claude Code 只有一个 Provider）。

### 4.2 subagent-registry：持久化 Sub-agent 状态

与 Claude Code 的 in-memory subagent 不同，OpenClaw 的 subagent-registry 有**磁盘持久化**：

```typescript
persistSubagentRunsToDisk()   // 写到磁盘
restoreSubagentRunsFromDisk() // 重启恢复
reconcileOrphanedRun()        // 处理孤儿运行（进程崩溃后的残留）
```

**设计理由：** OpenClaw 作为常驻 daemon 运行，gateway 重启不应该让用户的 sub-agent 任务丢失。这是 Claude Code 不需要考虑的问题（Claude Code 是短会话工具）。

**孤儿恢复机制：**
- `ANNOUNCE_EXPIRY_MS`：超过这个时间没有 announce 的 run 被视为孤儿
- `MAX_ANNOUNCE_RETRY_COUNT`：重试上限
- `reconcileOrphanedRestoredRuns()`：gateway 启动时扫描并恢复

### 4.3 memory-host-sdk：向量语义记忆

Claude Code 的记忆是文件型（markdown），检索靠文件名匹配。OpenClaw 的记忆系统：

```
memory-host-sdk/
├── engine-embeddings.ts   ← 向量化引擎
├── engine-foundation.ts   ← 基础存储
├── engine-qmd.ts          ← QMD (Query Metadata) 索引
├── engine-storage.ts      ← 持久化
├── engine.ts              ← 组合接口
├── query.ts               ← 语义搜索
└── multimodal.ts          ← 多模态记忆（含图片）
```

可选后端（`memory-lancedb` extension）：使用 LanceDB 向量数据库。支持多模态记忆（图片也可以被语义搜索到）。

**这是两个产品对「记忆」理解的本质差异：**
- Claude Code：「记忆」= 用户偏好和项目决策的文本快照
- OpenClaw：「记忆」= 可语义检索的知识库，支持向量相似度搜索

### 4.4 Security Audit：系统级安全审计

`src/security/audit.ts`（1468行）提供的不是 Claude Code 那种「命令注入检测」，而是**系统安全态势感知**：

- **SSRF 检测**：`isBlockedHostnameOrIp()` — 与 Claude Code 思路一致
- **危险配置标记**：`collectEnabledInsecureOrDangerousFlags()` — 扫描用户配置里的高风险选项
- **文件权限审计**：`inspectPathPermissions()` — 检查关键文件的权限设置
- **Safe bins 验证**：`listRiskyConfiguredSafeBins()` — 检测被用户标记为安全但可能危险的可执行文件
- **沙箱状态**：`resolveSandboxConfigForAgent()` — 检查是否启用了沙箱

Severity 三级：`info | warn | critical`，整合进 `/status` 命令的输出。

### 4.5 Cron Service：完整的定时调度引擎

Claude Code 没有内置 cron（只有 Hook 系统）。OpenClaw 有完整的调度引擎：

```typescript
const MAX_TIMER_DELAY_MS = 60_000    // 最大 check 间隔 60s
const MIN_REFIRE_GAP_MS = 2_000      // 防止 spin-loop：同一 job 最小重触发间隔
const DEFAULT_MISSED_JOB_STAGGER_MS = 5_000  // gateway 重启后错过的 job 错峰执行
const DEFAULT_MAX_MISSED_JOBS_PER_RESTART = 5  // 重启后最多补跑 5 个错过的 job
const DEFAULT_FAILURE_ALERT_AFTER = 2   // 失败 2 次后开始告警
```

**MIN_REFIRE_GAP_MS 防 spin-loop 的设计：** 如果 `computeJobNextRunAtMs` 返回的时间戳在「刚刚完成」之前（浮点精度问题或 DST 切换），会产生无限触发循环。2秒的硬性下限是安全网，不影响正常调度但能打破循环。

### 4.6 ACP 协议：标准化 AI Agent 控制平面

ACP (Agent Control Protocol) 是 OpenClaw 独有的，Claude Code 没有对应系统：

```
src/acp/
├── control-plane/manager.core.ts   (1997行) ← ACP 控制平面核心
├── translator.ts                   (1404行) ← ACP ↔ OpenClaw 事件翻译
├── client.ts                              ← ACP 客户端
├── persistent-bindings.*                  ← 持久绑定（agent harness）
├── approval-classifier.ts                 ← 批准决策分类器
└── policy.ts                              ← ACP 权限策略
```

**ACP 的意义：** 允许外部 AI agent（Claude Code、Codex、Cursor 等）通过标准协议接入 OpenClaw 的 Gateway，使用 OpenClaw 的工具池和记忆系统，同时保持各自的 LLM 决策层独立。这是 OpenClaw 作为「平台」而非「产品」的核心体现。

### 4.7 Plugin SDK：与 Claude Code MCP 的对比

Claude Code 用 MCP（Model Context Protocol）接入外部工具。OpenClaw 有自己的 Plugin SDK：

```
extensions/ 下的每个目录 = 一个 plugin
每个 plugin 可以：
  - 提供消息渠道（channel plugin）
  - 提供 AI 模型（provider plugin）
  - 提供工具（tool plugin）
  - 提供记忆后端（memory plugin）
  - 组合以上任意能力
```

94个内置扩展覆盖了：
- 21+ 消息渠道（Telegram、WhatsApp、Discord、Feishu 等）
- 28+ AI Provider（Anthropic、OpenAI、Google、Ollama、DeepSeek 等）
- 多种工具（browser、diffs、diagnostics-otel、speech 等）

**这是两个产品最大的架构分歧：**
- Claude Code：MCP 为开放标准，第三方扩展；Claude Code 本身是轻量核心
- OpenClaw：内置大量扩展，以 Platform 为核心设计目标

### 4.8 Auth Profiles：多 Provider 认证轮转

`src/agents/auth-profiles.ts` 是 OpenClaw 独有的复杂系统：

**关键设计：**
- 支持多个 auth profile，每个 profile 对应一个 API key / OAuth token
- `resolveAuthProfileOrder()` 决定使用哪个 profile
- 使用失败自动标记 `markAuthProfileFailure()`
- 恢复后标记 `markAuthProfileGood()`
- `cooldown-auto-expiry`：冷却期自动到期，不需要手动恢复
- `chutes`（CHUTES）：Chutes.ai 的特殊 OAuth 流程
- `round-robin`：不依赖 lastGood 的轮询排序

**这解决了 Claude Code 没有的问题：** 用户可能有多个 Anthropic API key（个人 + 公司），或者同时配置了 Anthropic + OpenAI + 本地 Ollama。当一个 Provider 限流或故障时，自动切到下一个。

---

## 五、启动链分析

```
openclaw.mjs (wrapper)
  └─ entry.ts
      ├─ normalizeWindowsArgv
      ├─ enableCompileCache (Node.js V8 编译缓存)
      ├─ parseCliProfileArgs + applyCliProfileEnv
      ├─ buildCliRespawnPlan
      ├─ attachChildProcessBridge
      └─ openclaw gateway / agent / message ...

gateway 启动（server.impl.ts）：
  1. loadConfig + migrateLegacyConfig
  2. applyConfigOverrides
  3. runChannelPluginStartupMaintenance (所有渠道 plugin 维护)
  4. ensureControlUiAssetsBuilt
  5. initSubagentRegistry (恢复持久化 subagent)
  6. registerSkillsChangeListener
  7. startHeartbeatRunner
  8. scheduleGatewayUpdateCheck
  9. server.listen (WebSocket + HTTP)
```

**关键差异（vs Claude Code）：**
- Claude Code 启动是一次性 CLI，每次对话都是新进程
- OpenClaw 启动一次作为 daemon 常驻，所有对话复用同一个进程
- 因此 OpenClaw 有「restart sentinel」`server-restart-sentinel.ts` 机制和 SIGUSR1 热重载

---

## 六、值得深入研究的文件列表

| 文件 | 行数 | 为何重要 |
|------|------|----------|
| `src/agents/pi-embedded-runner/run/attempt.ts` | 2098 | 对话循环核心 |
| `src/acp/control-plane/manager.core.ts` | 1997 | ACP 控制平面 |
| `src/gateway/server-methods/chat.ts` | 1978 | 聊天消息处理 |
| `src/tasks/task-registry.ts` | 1975 | 任务管理系统 |
| `src/agents/bash-tools.exec.ts` | 1656 | Shell 执行 |
| `src/gateway/session-utils.ts` | 1431 | session 管理 |
| `src/security/audit.ts` | 1468 | 安全审计 |
| `src/config/schema.base.generated.ts` | 26796 | 配置 schema（生成）|

---

## 七、总结

OpenClaw 和 Claude Code 虽然都是 TypeScript + LLM，但设计哲学完全不同：

**Claude Code 的哲学：** 极致轻量、专注编程、深度优化 API 成本和 token 利用率。

**OpenClaw 的哲学：** 通用平台、多 Provider/多渠道、持久化状态、可扩展插件体系。

OpenClaw 更像是一个「AI 助手操作系统」——它管理 AI 的身份、记忆、工具、权限和调度，任何 AI agent 都可以接入（通过 ACP 协议）。

**对工程师最有参考价值的设计：**
1. **Sub-agent 持久化恢复**：daemon 模式下的孤儿运行处理
2. **Auth Profile 轮转**：多 Provider 故障自动切换
3. **Plugin SDK 架构**：94个内置扩展的统一接入方式
4. **向量记忆系统**：比文件型记忆更强大的语义检索
5. **ACP 协议**：标准化 AI Agent 控制平面

---

*分析文件：`/root/.openclaw/workspace/openclaw-source/`（已 clone）*  
*详细文件分析可按需继续深挖任意子目录。*
