# OpenClaw 源码深挖完整报告 v2（2026.4.4）
> 任务B独立报告，不与 Claude Code 对比
> 分析时间：2026-04-05
> 覆盖模块：15个核心模块

---

## 一、架构全景

```
┌─────────────────────────────────────────────────────────────────┐
│                    入口 / 通道层                                  │
│  entry.ts → gateway/server.impl.ts → channels/                  │
│  21+ 渠道插件（Telegram/WhatsApp/Discord/Slack/WeChat/...）       │
└────────────────────────┬────────────────────────────────────────┘
                         │ inbound debounce + status reactions
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    调度 / 控制面                                   │
│  ACP manager.core（1997行）                                       │
│  ├─ SessionActorQueue     → 同 session 串行化                     │
│  ├─ RuntimeCache          → 连接池 + 空闲驱逐                    │
│  └─ activeTurnBySession   → 当前 turn 状态追踪                   │
│                                                                  │
│  cron/timer.ts            → 定时调度（startup catchup 防雪崩）    │
│  infra/heartbeat-runner.ts→ 定时心跳（transcript prune）         │
└────────────────────────┬────────────────────────────────────────┘
                         │ execute turn
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent 运行时                                    │
│  pi-embedded-runner/attempt.ts（2098行）                          │
│  ├─ failover（attempt < 2）                                       │
│  ├─ eventGate（防超时污染）                                       │
│  ├─ runLlmInput/Output hook                                      │
│  └─ taskProgressSummary（background task）                        │
│                                                                  │
│  auth-profiles/order.ts → Round-Robin + Cooldown Partition       │
│  subagent-registry.ts   → 3层持久化 + 孤儿恢复                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ embed / recall / sandbox
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    基础设施层                                      │
│  memory-host-sdk    → LanceDB + 6种 Embedding Provider            │
│  context-engine     → 可插拔上下文引擎                            │
│  security/audit.ts  → 11类安全审计（3级 severity）               │
│  plugins/loader.ts  → Jiti 懒编译 + 安全扫描 + provenance 追踪   │
│  plugins/hooks.ts   → 28个强类型 HookRunner                      │
│  infra/exec-approvals.ts → 3级安全（deny/allowlist/full）        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、渠道层（src/channels/）

### 2.1 ChannelPlugin 4大适配器

```typescript
interface ChannelPlugin {
  id: ChatChannelId;                    // 动态字符串（非枚举）
  capabilities: ChannelCapabilities;   // 能力声明
  messaging: ChannelMessagingAdapter;  // 消息发送
  threading?: ChannelThreadingAdapter; // 线程管理（可选）
  security?: ChannelSecurityAdapter;   // 安全策略（可选）
}
```

**ChannelCapabilities 关键字段：**
| 字段 | 说明 | 支持渠道示例 |
|------|------|------------|
| `canReact` | emoji 反应 | Discord/Slack/Telegram |
| `hasNativeThreading` | 原生线程 | Discord/Slack |
| `supportsStreamingMessages` | 流式输出 | Discord/Telegram |
| `inlineButtons` | 内嵌按钮 | Telegram/Discord |
| `canSendEphemeral` | 临时消息 | Slack |
| `canSendPolls` | 投票 | Telegram/Discord |

### 2.2 StatusReactionController（状态反馈设计）

**状态序列：**
```
queued → thinking → [tool 执行] → done/error
                 ↘ coding/web（专用状态）
                 ↘ stallSoft(10s) → stallHard(30s)（卡住检测）
                 ↘ compacting（压缩进行中）
```

**关键设计：**
- `scheduleEmoji`：中间状态 debounce 700ms，避免 thinking→tool→done 快速切换产生多次 API 调用
- `enqueue(fn)`：串行化 Promise chain，防止并发 reaction API 调用
- 去重：`emoji === currentEmoji || emoji === pendingEmoji` → 跳过，但仍 reset stall timer
- 终止状态（done/error）→ **立即执行**，不等 debounce

**工具分类：**
```
coding: exec, process, read, write, edit, bash → 👨💻
web: web_search, web_fetch, browser → ⚡
others: 🔥
```

### 2.3 inbound-debounce.ts（防抖系统）

**三层顺序保证：**
```
keyChains Map → 同 key 任务严格串行（后来的不超越先来的）
buffers Map   → timer 触发的 flush
enqueueReservedKeyTask → 预占槽位防止 immediate 超越 timer
```

**防御性设计：**
- `maxTrackedKeys = 2048`：防止 buffers Map 无限增长（DDoS 防护）
- `shouldDebounce(item)`：每个 item 可自定义是否参与防抖
- `resolveDebounceMs(item)`：每个 item 可自定义 debounce 时长
- map 饱和时 fallback 到 immediate keyed work（不丢弃，只是不 debounce）

### 2.4 ThreadBindingPolicy

**ThreadBinding 生命周期：**
```
active → [idleTimeout] → idled → [maxAge] → expired
```

**replyToMode 三种：**
- `"off"`：不自动 reply-to（但可手动用 reply tag）
- `"first"`：只 reply-to 对话首条消息
- `"all"`：每条消息 reply-to（Twitter-style threading）

---

## 三、ACP 控制平面（src/acp/）

### 3.1 SessionActorQueue（底层 KeyedAsyncQueue）

```typescript
class SessionActorQueue {
  // 核心：pendingBySession 计数（可监控等待队列深度）
  getPendingCountForSession(actorKey: string): number  // 可监控
  getTotalPendingCount(): number                        // 全局等待数
  async run<T>(actorKey: string, op: () => Promise<T>) // 核心锁原语
}
```

**每 session 严格串行**：新 turn 必须等上一个 turn 完成才开始

### 3.2 RuntimeCache（连接池）

```typescript
class RuntimeCache {
  get(actorKey, { touch?: boolean }) // touch=true → 更新 lastTouchedAt（LRU）
  peek(actorKey)                     // touch=false，不更新 LRU
  collectIdleCandidates({ maxIdleMs }) // 空闲超时候选
  snapshot()                          // 点快照（含 idleMs，用于 observability）
}
```

**CachedRuntimeState 关键字段：**
```typescript
{
  runtime: AcpRuntime;
  handle: AcpRuntimeHandle;
  appliedControlSignature?: string; // undefined → 下次 turn 强制重新推送 controls
}
```

**persistRuntimeOptions 副作用：**
- cwd 变化 → clearCachedRuntimeState（强制重建连接）
- 其他变更 → appliedControlSignature = undefined（下次 turn 重推 controls）

### 3.3 超时清理双阶段

```
超时发生
  ↓
阶段1: abortController.abort() + runtime.cancel()
       └─ awaitCleanupWithGrace(ACP_TURN_TIMEOUT_CLEANUP_GRACE_MS)
          - 超时 → 异步继续等（detach），记 logVerbose，返回 false
  ↓
仅 oneshot 模式:
阶段2: runtime.close()
       └─ awaitCleanupWithGrace
          - 两阶段都成功 → clearCachedRuntimeStateIfHandleMatches（同步清除）
          - 任一失败 → Promise.allSettled([cancel, close]).then(清除)（异步清除）
```

### 3.4 ACP approval-classifier.ts

**7个 ApprovalClass 优先级：**
```
control_plane > exec_capable > mutating > interactive > readonly_scoped > readonly_search > other
```

**resolveToolNameForPermission 反注入设计：**
```
source1: _meta.toolName
source2: rawInput.tool/toolName/name
source3: title 冒号前

任何两源有值但不一致 → undefined（拒绝承认）
防止 title 篡改绕过权限检查
```

---

## 四、Agent 运行时（src/agents/）

### 4.1 pi-embedded-runner/attempt.ts（2098行）

**eventGate 防超时污染：**
```typescript
const eventGate = { open: true };
// turn 超时后：
eventGate.open = false;
// 事件仍从 stream 流出，但被过滤：
if (!eventGate.open) continue;
// 效果：延迟事件不会污染下一个 turn 的状态
```

**failover（attempt < 2）触发条件：**
1. attempt === 0（首次）
2. sawTurnOutput === false（无任何输出）
3. `isRecoverableAcpxExitError(error.message)`：匹配 `"acpx exited with code/signal"`

**Background Task 追踪：**
```
mode === 'prompt' → 启用 taskProgressSummary
每个 text_delta → 追加到 progressSummary
turn 结束 → resolveBackgroundTaskTerminalResult(progressSummary) → terminalOutcome
```

### 4.2 auth-profiles/order.ts Round-Robin

**排序逻辑（降序优先级）：**
1. preferredProfile（强制排第一）
2. 无 cooldown + 类型优先（oauth > token > api_key）+ **lastUsed 最旧的先用**
3. 有 cooldown（按 cooldown 到期时间升序）

**关键：lastGood 故意不参与排序**
- 理由：lastGood 优先 = 总用最近成功的 = 不是 round-robin
- 目标：均匀分摊负载

**配置漂移自动修复（allBaseProfilesMissing）：**
- 场景：用户迁移账号，profileId 消失，但 credentials 还在
- 修复：扫描 store 里该 provider 的所有 profile 作为 fallback

### 4.3 subagent-registry.ts 孤儿恢复

**决策树：**
```
cleanupCompletedAt → skip
announceRetryCount >= MAX → finalizeResumedAnnounceGiveUp('retry-limit')
endedAt 超过 ANNOUNCE_EXPIRY → finalizeResumedAnnounceGiveUp('expiry')
suppressAnnounceForSteerRestart → skip（等 steer 替换）
endedAt > 0（已结束）→ startSubagentAnnounceCleanupFlow
else（未结束）→ waitForSubagentCompletion
```

**动态 import 节省启动内存：**
```typescript
// 不影响 gateway 冷启动
void import('./subagent-orphan-recovery.js').then(({ scheduleOrphanRecovery }) => {
  scheduleOrphanRecovery(...)
}).catch(() => { /* best-effort */ })
```

---

## 五、基础设施层

### 5.1 memory-host-sdk 向量记忆

**6种 Embedding Provider：**
| Provider | 特点 |
|----------|------|
| openai | text-embedding-3-small/large |
| gemini | taskType + outputDimensionality（768/1536/3072）|
| voyage | voyage-3-large，code/法律专用模型 |
| mistral | mistral-embed |
| ollama | 本地 Ollama 服务 |
| local | node-llama-cpp GGUF，默认 embeddinggemma-300m（~300MB）|

**auto 选择的负向约束：**
- Ollama 不在 auto（不能假设用户有 Ollama）
- hf: / http: 前缀路径不在 auto（不能假设有下载权限）
- 只有已存在的本地文件才参与 auto

### 5.2 security/audit.ts（11类审计）

| 类别 | 代表检查项 |
|------|-----------|
| Filesystem | 关键目录 owner/mode |
| Gateway Config | 监听地址、allowFrom 白名单 |
| Dangerous Flags | insecure/dangerous 标记字段 |
| Browser Control | 端点暴露范围 |
| Logging | 敏感数据脱敏 |
| Elevated | bypassPermissions 范围 |
| Exec Runtime | 沙箱模式 |
| Risky Safe-Bins | 白名单可执行文件风险 |
| Open Exec Surface | 暴露执行路径数量 |
| SSRF | 私有网段 + IPv4-mapped IPv6 解包 |
| Channel | 各渠道安全设置 |

**动态加载设计：** 深度检查、渠道检查运行时动态 import，不影响启动性能

### 5.3 plugins/loader.ts（安全插件系统）

**Jiti 懒初始化：** 只有需要加载 TS 插件时才初始化（节省内存）

**activate=false 必须 cache=false：**
```typescript
// 快照加载（不激活）禁止缓存
// 防止存入"命令从未注册"的残缺 registry
```

**provenance 追踪 4 源：**
- bundled / installed / workspace / global
- 无 provenance 的 loaded plugin → warn（可能是直接 require）

**安装安全扫描（install-security-scan.runtime.ts）：**
```
critical findings → 阻断安装（security_scan_blocked）
warn findings     → 告警不阻断
scan failure      → 阻断安装（security_scan_failed）
```

### 5.4 infra/heartbeat-runner.ts

**pruneHeartbeatTranscript — 零信息 ACK 不污染 context：**
```typescript
// 1. heartbeat 前：captureTranscriptState → 记录文件大小
// 2. 运行：发给 AI，AI 回 HEARTBEAT_OK
// 3. 结果是 HEARTBEAT_OK → fs.truncate(path, preHeartbeatSize)
// 效果：HEARTBEAT_OK 轮次从 transcript 消失，不占 context window
```

**execFallbackText 保护：**
- exec 完成事件的回调内容永远不被 ACK 吞掉
- 即使 AI 回复看起来像 HEARTBEAT_OK，也强制显示给用户

### 5.5 infra/exec-approvals.ts

**三级安全 × 三级询问：**
```
ExecSecurity: deny | allowlist | full
ExecAsk:      off  | on-miss   | always
```

**ExecApprovalDecision + allowedDecisions：**
- 每个 approval request 可限制哪些 decision 可用（防止用户 allow-always 危险命令）
- DEFAULT_EXEC_APPROVAL_TIMEOUT_MS = 1,800,000（30分钟等待用户确认）

**normalizeExecApprovals 三步防腐：**
1. coerceAllowlistEntries — 兼容旧格式/损坏数据
2. ensureAllowlistIds — 补 UUID
3. stripAllowlistCommandText — 持久化时移除 commandText（只保留 pattern）

### 5.6 plugins/hooks.ts（28个 HookRunner）

**按阶段分类：**

| 阶段 | Hook 数量 | 关键 Hook |
|------|----------|---------|
| Agent 生命周期 | 10 | runLlmInput, runLlmOutput, runAgentEnd |
| 消息生命周期 | 5 | runMessageSending, runInboundClaim |
| 工具生命周期 | 4 | runBeforeToolCall, runAfterToolCall |
| Sub-agent 生命周期 | 4 | runSubagentSpawning, runSubagentEnded |
| 系统 | 5 | runGatewayStart, runBeforeInstall |

**Hook 函数语义：** 返回修改后的对象（变换语义），而非 exit code（通过/拒绝语义）

---

## 六、cron 调度引擎（src/cron/）

**关键常量：**
| 常量 | 值 | 作用 |
|------|---|------|
| MAX_TIMER_DELAY_MS | 60,000 | setInterval 最大间隔 |
| MIN_REFIRE_GAP_MS | 2,000 | 防 spin-loop |
| DEFAULT_MISSED_JOB_STAGGER_MS | 5,000 | 错过 job 错峰延迟 |
| DEFAULT_MAX_MISSED_JOBS_PER_RESTART | 5 | 重启补跑上限 |
| DEFAULT_FAILURE_ALERT_AFTER | 2 | 连续失败告警阈值 |
| DEFAULT_FAILURE_ALERT_COOLDOWN_MS | 3,600,000 | 告警冷却期 1h |

**startup catchup 防雪崩：** 最多 5 个 × 5s 错峰 = 25s 内完成所有补跑

---

## 七、关键工程决策总结

### 并发控制模式
1. **同 session 串行**：SessionActorQueue → KeyedAsyncQueue（每 key 独立队列）
2. **同 key 防抖**：inbound-debounce → keyChains Map（后来者等前者完成）
3. **最新覆盖**：DraftStreamLoop pendingText / heartbeat ack 截断

### 资源管理模式
1. **动态 import**：懒加载安全扫描模块、孤儿恢复模块（不增加冷启动开销）
2. **touch-based LRU**：RuntimeCache.get({ touch })
3. **unref timer**：heartbeat/cron timer 不阻止进程退出
4. **有上界的补跑**：MAX_MISSED_JOBS_PER_RESTART 防雪崩

### 安全防护模式
1. **三源一致性**：resolveToolNameForPermission（三处不一致则拒绝）
2. **负向约束**：canAutoSelectLocal（排除不确定存在的资源）
3. **防腐三步**：normalizeExecApprovals（coerce → ensureIds → strip）
4. **SSRF 解包**：IPv4-mapped IPv6 解包后再检查私有网段

### 可观测性模式
1. **pendingBySession 计数**：SessionActorQueue 队列深度监控
2. **idleMs 快照**：RuntimeCache.snapshot() 含空闲时长
3. **turnLatencyStats + errorCountsByCode**：ACP manager 内置延迟/错误统计
4. **SecurityAuditSeverity 三级**：info/warn/critical 集成进 /status

---

*报告归档：`/root/.openclaw/workspace/openclaw-source-full-report-v2.md`*
*memory 文件：`/root/.openclaw/workspace/memory/2026-04-05.md`*
