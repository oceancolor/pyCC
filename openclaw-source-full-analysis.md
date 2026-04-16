# OpenClaw 源码全模块深挖报告（2026.4.4 最新版）

> 分析时间：2026-04-05
> 源码版本：2026.4.4（commit: 4954d02）
> 代码规模：约 60 万行 TypeScript
> 仓库：https://github.com/openclaw/openclaw

---

## 一、总体架构图

```
┌──────────────────────────────────────────────────────────────┐
│                   Channel Plugins（渠道层）                    │
│  Telegram │ WhatsApp │ Discord │ Slack │ Signal │ Feishu     │
│  iMessage │ WeChat │ IRC │ Matrix │ Line │ ... 21+渠道        │
└───────────────────────┬──────────────────────────────────────┘
                        │ inbound message
                        ▼ createChannelInboundDebouncer
┌──────────────────────────────────────────────────────────────┐
│                   Gateway（服务层）                            │
│  server.impl.ts     ← HTTP/WS 服务器 + plugin 管理           │
│  session-utils.ts   ← session 生命周期（1431行）              │
│  cron/timer.ts      ← 定时调度引擎                           │
│  hooks/             ← Internal Hook 系统（5种事件类型）       │
│  acp/manager.core   ← ACP 控制平面（1997行）                 │
└───────────────────────┬──────────────────────────────────────┘
                        │ dispatch turn
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                   Agents（运行时层）                           │
│  pi-embedded-runner  ← 主对话循环（2098行）                   │
│  subagent-registry   ← Sub-agent 持久化管理                  │
│  auth-profiles/      ← 多 Profile 认证轮转                   │
│  bash-tools.exec     ← Shell 执行 + 沙箱（1656行）           │
│  sandbox             ← Docker/SSH/Browser 沙箱               │
│  compaction          ← 上下文压缩                            │
└───────────────────────┬──────────────────────────────────────┘
                        │ embed / recall
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                   Infrastructure（基础设施层）                 │
│  memory-host-sdk     ← 向量记忆（6种 embedding provider）    │
│  context-engine      ← 可插拔上下文引擎                      │
│  security/audit      ← 安全审计（11个检查类别）               │
│  plugins/hooks.ts    ← 28个 HookRunner 函数                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 二、模块1：pi-embedded-runner/run/attempt.ts（2098行）

### 核心：runEmbeddedAttempt + failover 重试

**对话循环主流程：**
```
1. resolveContext → 加载 AGENTS.md / SOUL.md / USER.md / MEMORY.md
2. buildPrompt → runBeforePromptBuild hook（插件可修改系统提示）
3. resolveAuthProfileOrder() → 找当前可用的 auth profile
4. 主流程循环 for await (event of pi.runTurn()):
   ├─ text_delta → update draft stream（流式 typing 效果）
   ├─ tool_call → runBeforeToolCall → 执行 → runAfterToolCall
   └─ error → streamError（超时/网络/auth）
5. runAgentEnd hook（全局分析完整对话记录）
```

**failover 设计（attempt < 2 的两次尝试）：**
- 第一次 turn 失败 + 无输出 + 可重试错误 → `retryFreshHandle = true` → 换新 handle 重试
- 第二次失败 → 直接抛出 AcpRuntimeError
- `LiveSessionModelSwitchError` → session 中切换模型不中断，透明 failover

**eventGate { open: true } 防超时污染：**
```typescript
// turn 超时后关门
eventGate.open = false

// 事件仍从 stream 流出，但被 gate 过滤掉
// 防止超时后的延迟事件污染下一个 turn 的状态
if (!eventGate.open) continue
```

**ACP_TURN_TIMEOUT_GRACE_MS 宽限期：**
- 实际等待 = turnTimeoutMs + GRACE
- 给 runtime 机会自行完成（网络延迟等）
- 超时后 `cleanupTimedOutTurn()` 才真正发中断信号

**taskProgressSummary 实时追踪：**
- background task (mode === 'prompt') 专用
- 每个 text_delta 都追加到 summary
- `resolveBackgroundTaskTerminalResult(progressSummary)` 提取结构化 terminalOutcome

---

## 三、模块2：ACP 控制平面（manager.core.ts，1997行）

### 架构：SessionActorQueue + RuntimeCache 两层并发控制

**SessionActorQueue（串行化保证）：**
```typescript
withSessionActor(sessionKey, async () => {
  // 同一 session 的 turn 严格串行
  // 新 turn 等上一个 turn 完成才启动
})
```

**RuntimeCache（连接池）：**
- 持有与 ACP harness（Claude Code/Codex/Cursor 等）的连接
- 空闲超时驱逐（resolveRuntimeIdleTtlMs）
- `ensureRuntimeHandle()` → 有则复用，无则新建

**oneshot vs session 模式：**
| 模式 | 说明 | turn 结束后 |
|------|------|------------|
| oneshot | 一次性任务 | runtime.close() + 清除缓存 |
| session | 持久会话 | reconcileRuntimeSessionIdentifiers() 保持活跃 |

**Background Task 记录生命周期：**
```
createBackgroundTaskRecord → markBackgroundTaskRunning（含 progressSummary）
→ markBackgroundTaskTerminal（status: succeeded/failed, terminalSummary）
```

---

## 四、模块3：subagent-registry.ts 持久化恢复

### 三层生命周期 + 孤儿恢复状态机

**三层存储：**
```
in-memory Map → persistSubagentRunsToDisk (JSON) → orphan-recovery (重启后)
```

**孤儿恢复决策树：**
```
cleanupCompletedAt? → 跳过
announceRetryCount >= MAX? → finalizeResumedAnnounceGiveUp('retry-limit')
endedAt 超过 ANNOUNCE_EXPIRY_MS? → finalizeResumedAnnounceGiveUp('expiry')
suppressAnnounceForSteerRestart? → 跳过 announce（等 steer 替换）
endedAt > 0（已结束）→ startSubagentAnnounceCleanupFlow
else（未结束）→ waitForSubagentCompletion(runId, waitTimeoutMs)
```

**steer-restart 机制（#47711 动态 import）：**
- `scheduleOrphanRecovery` 通过动态 import 延迟加载（不增加启动内存）
- SIGUSR1 热重载后，被 steer 中断的 run 需要特殊处理（不 announce，等替换）

**sweeper 节能设计：**
- 只有存在有 `archiveAtMs` 的 run 时才启动 sweeper
- 无需归档的 run 清除后 `stopSweeper()`，不保留空转定时器

**resolveSubagentRunOrphanReason 判断维度：**
- `stale-running`：run 在 store 里是运行状态，但进程已不存在
- `missing-child-session`：child session key 查不到对应 session
- `timeout`：run 超过最大 timeout 还在运行

---

## 五、模块4：auth-profiles/order.ts 轮转排序

### Round-Robin + Cooldown Partition 算法

**排序优先级（降序）：**
1. preferredProfile（用户显式指定，始终排第一）
2. 无 cooldown 的 profile（可用状态）
   - 按类型：`oauth > token > api_key`
   - 按 lastUsed：**最旧的先用**（这才是真正的 round-robin）
3. 有 cooldown 的 profile（按 cooldown 到期时间，最快恢复先用）

**重要：lastGood 故意不参与排序**
```typescript
// lastGood is NOT prioritized - that would defeat round-robin
// round-robin 的意义是均匀分摊负载，不是总用"上次成功的"
```

**clearExpiredCooldowns 保护机制：**
- 每次 `resolveAuthProfileOrder()` 调用前执行
- 防止 cooldown 永久累积（网络恢复后自动清零）

**配置漂移修复（allBaseProfilesMissing）：**
- 场景：用户迁移账号，旧 profileId 消失，但 credentials 还在
- 检测：baseOrder 里所有 profileId 都不在 store 中
- 修复：扫描 store 里该 provider 的所有 profile，用 storeProfiles 兜底

---

## 六、模块5：memory-host-sdk 向量记忆

### 6种 Embedding Provider + QMD 语义索引

**Provider 选择策略（auto 模式）：**
```
REMOTE_EMBEDDING_PROVIDER_IDS = ["openai", "gemini", "voyage", "mistral"]
（Ollama 故意不加入 auto——假设用户没有 Ollama 是合理的）

canAutoSelectLocal():
  - modelPath 存在 AND 是本地文件路径（非 hf: / http: 前缀）
  - 才允许 local 参与 auto 选择
```

**DEFAULT_LOCAL_MODEL：**
`hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/embeddinggemma-300m-qat-Q8_0.gguf`
- 300M 参数，Q8_0 量化，约 300MB
- 完全本地运行（node-llama-cpp），无网络依赖
- hf: 前缀 = 从 HuggingFace 自动下载

**Gemini 向量的特殊能力：**
- `outputDimensionality`：可选 768 / 1536 / 3072 维
- `taskType`：任务类型提示（RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY / CLASSIFICATION 等）
- 比 OpenAI text-embedding-3 多了「任务感知」维度

**QMD（Query Metadata）系统：**
- 独立的命令行二进制（通过 `runCliCommand` 调用）
- `qmd-scope.ts` — channel 维度范围控制（private/group/all）
- `extractKeywords` + `isQueryStopWordToken` — 关键词提取
- `sessionPathForFile` — session 文件路径管理（支持按 session 范围查询）
- 暗示 OpenClaw 使用了 QMD（量子多维度？）协议做语义搜索

---

## 七、模块6：security/audit.ts（安全审计系统）

### 11类检查 + 3级严重度

**模块化动态加载（避免启动内存膨胀）：**
```typescript
// 深度检查、渠道检查都是运行时动态 import
const { runDeepAudit } = await import('./audit.deep.runtime.js')
const { collectChannelFindings } = await import('./audit-channel.collect.runtime.js')
```

**11类安全检查：**
| 类别 | 代表检查项 |
|------|-----------|
| Filesystem | 关键目录权限（state-dir/config 的 owner/mode）|
| Gateway Config | 监听地址、allowFrom 白名单、trusted proxy |
| Dangerous Flags | 高风险配置字段（insecure/dangerous 标记）|
| Browser Control | 浏览器控制端点暴露范围 + loopback SSRF |
| Logging | 日志级别、敏感数据脱敏 |
| Elevated | bypassPermissions 使用范围 |
| Exec Runtime | 沙箱模式（off/docker/ssh）|
| Risky Safe-Bins | 白名单可执行文件风险评估 |
| Open Exec Surface | 暴露的执行路径数量 |
| SSRF | isBlockedHostnameOrIp + private network policy |
| Channel | 各渠道特定安全设置 |

**关键：isBlockedHostnameOrIp**
- 与 Claude Code 的 ssrfGuard.ts 思路完全一致
- 阻断私有网段 + link-local（169.254.0.0/16 AWS 元数据）
- IPv4-mapped IPv6 解包检查（`::ffff:a9fe:a9fe` → 169.254.169.254）

---

## 八、模块7：cron/service/timer.ts（定时调度引擎）

### 关键常量 + 防 thundering herd 设计

**核心常量：**
| 常量 | 值 | 用途 |
|------|---|------|
| MAX_TIMER_DELAY_MS | 60,000 | setInterval 最大间隔（防止睡过头）|
| MIN_REFIRE_GAP_MS | 2,000 | 同一 job 最小重触发间隔（防 spin-loop）|
| DEFAULT_MISSED_JOB_STAGGER_MS | 5,000 | 错过 job 的错峰延迟 |
| DEFAULT_MAX_MISSED_JOBS_PER_RESTART | 5 | 重启后最多补跑数 |
| DEFAULT_FAILURE_ALERT_AFTER | 2 | 连续失败次数告警阈值 |
| DEFAULT_FAILURE_ALERT_COOLDOWN_MS | 3,600,000 | 告警冷却期（1小时）|

**executeJobCoreWithTimeout 超时控制：**
```typescript
Promise.race([
  executeJobCore(state, job, runAbortController.signal),
  new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      runAbortController.abort(timeoutErrorMessage())  // 通知 job
      reject(new Error(timeoutErrorMessage()))          // 触发 race
    }, jobTimeoutMs)
  })
])
// finally: clearTimeout 防定时器泄漏
```

**startup catchup 防雪崩：**
- gateway 重启后扫描错过的 job
- 不超过 5 个（DEFAULT_MAX_MISSED_JOBS_PER_RESTART）
- 每个延迟 5s（DEFAULT_MISSED_JOB_STAGGER_MS）
- 结果：最多 25s 内完成所有补跑，不会同时并发爆发

**resolveRunConcurrency 可配置并发：**
```typescript
// 默认 1（串行）
// 可配置 maxConcurrentRuns（需 > 0 且有限）
```

---

## 九、模块8：plugins/hooks.ts（28个 HookRunner）

### HookRunner：插件的完整 AI 生命周期切面

**按阶段分组的 28 个 hook：**

**Agent 生命周期（10个）：**
```
runBeforeModelResolve   → 拦截/修改模型选择（插件可强制用特定模型）
runBeforePromptBuild    → 修改系统提示构建
runBeforeAgentStart     → agent 第一次启动前
runBeforeAgentReply     → 每次回复前（可拦截）
runLlmInput             → 修改发给模型的消息列表
runLlmOutput            → 修改模型返回的响应
runAgentEnd             → 对话结束后（完整记录可用）
runBeforeCompaction     → 压缩前（可注入额外上下文）
runAfterCompaction      → 压缩后（可验证结果）
runBeforeReset          → context reset 前（可保存重要信息）
```

**消息生命周期（5个）：**
```
runMessageReceived     → 入站消息处理后
runBeforeDispatch      → 路由决策前（可改变发送目标）
runMessageSending      → 出站前（最后机会修改内容）
runMessageSent         → 出站后（不可撤回，仅记录）
runInboundClaim        → 渠道声明入站消息（多渠道路由）
```

**工具生命周期（4个）：**
```
runBeforeToolCall      → 工具调用前（可修改参数，可拦截）
runAfterToolCall       → 工具调用后（可修改结果）
runToolResultPersist   → 工具结果写入存储前
runBeforeMessageWrite  → 消息写入前
```

**Sub-agent 生命周期（4个）：**
```
runSubagentSpawning         → spawn 前（可决定是否允许）
runSubagentDeliveryTarget   → 决定 subagent 结果交付目标
runSubagentSpawned          → spawn 后
runSubagentEnded            → subagent 结束后
```

**系统（5个）：**
```
runSessionStart / runSessionEnd
runGatewayStart / runGatewayStop
runBeforeInstall
```

**vs Claude Code 的对比：**
| 维度 | Claude Code Hooks | OpenClaw HookRunner |
|------|------------------|---------------------|
| 数量 | 27 种事件名 | 28 个函数 |
| 类型系统 | Shell 脚本协议（JSON stdout）| TypeScript 强类型 |
| 扩展方式 | 外部进程（command/agent/http）| Plugin SDK 内部注册 |
| 串行/并行 | 可配置并行 | 各函数内串行调用注册的 handlers |
| 拦截能力 | exit 2 阻断 | 函数返回修改后的对象 |

---

## 十、模块9（补充）：channels 渠道层核心设计

### DraftStreamLoop：流式 typing 效果

```typescript
// throttleMs 控制更新频率（避免 API 频率限制）
// inFlightPromise：同一时刻只有一个 sendOrEditStreamMessage 在飞
// pendingText：最新内容（非队列，每次覆盖）
// timer：到达 throttleMs 才触发 flush

update(text) → 更新 pendingText
  ├─ 有 inFlight → schedule（throttle）
  ├─ 超过 throttleMs → 立即 flush
  └─ 否则 → schedule

flush() → while 循环消费 pendingText（直到停止或发送失败）
```

这个设计和 Claude Code 的 `pendingToolUseSummary`（Haiku 火力隐藏）有相似之处：**总是用最新状态，不排队，减少不必要的更新次数。**

### inbound-debounce：防止连续输入触发多次

- 有 media → 不 debounce（立即处理附件）
- 是 control command（/help、/status 等）→ 不 debounce
- 普通文本 → createChannelInboundDebouncer（防连续消息触发多次对话）

---

## 十一、与 Claude Code 的完整对比表

| 设计维度 | Claude Code | OpenClaw |
|---------|-------------|----------|
| **进程模型** | 短会话 CLI，每次对话新进程 | 常驻 daemon，单进程多用户 |
| **对话循环** | 自研 queryLoop（1729行）| pi-embedded-runner（依赖 pi）|
| **失败重试** | withRetry + 指数退避 | attempt < 2 + retryFreshHandle |
| **State 管理** | 全量替换（不可变）| 对象引用 + 事件驱动 |
| **Auth** | 单 API key | Auth Profile 轮转（round-robin）|
| **记忆存储** | Markdown 文件 | 向量数据库（LanceDB）|
| **记忆检索** | 文件名匹配 | 语义向量搜索 + QMD 关键词 |
| **Sub-agent 状态** | in-memory | 磁盘持久化 + 孤儿恢复 |
| **沙箱** | 无 | Docker / SSH / Browser |
| **Hook 协议** | Shell 脚本 JSON | TypeScript 强类型 28函数 |
| **渠道** | CLI + VS Code | 21+ 消息渠道 |
| **ACP** | 无 | 完整控制平面（1997行）|
| **定时任务** | 无 | 完整 cron 引擎 |
| **安全审计** | 23道Bash检查 | 11类系统安全审计 |
| **配置 Schema** | 简单 JSON | Zod 强类型（26K行 generated）|

---

## 十二、最值得借鉴的 8 个工程设计

1. **eventGate 防超时污染**：turn 超时后关门，让 stream 继续流但不处理，防止延迟事件污染下一个 turn。比 abort + catch 更优雅。

2. **Auth Profile Round-Robin**：`lastGood 不参与排序`，才是真正的 round-robin。OAuth > token > api_key 的类型优先级让授权方式有自然降级路径。

3. **孤儿恢复 + SIGUSR1 动态 import**：`scheduleOrphanRecovery` 延迟加载（`void import('./subagent-orphan-recovery.js')`），不增加 gateway 启动时内存，best-effort 失败被静默忽略。

4. **startup catchup 防雪崩**：限制 5 个 + 5s 错峰，让「补跑错过的 cron 任务」有明确的资源上界，不会在重启时产生 thundering herd。

5. **canAutoSelectLocal 的负向约束**：`auto` embedding 主动排除 Ollama（不能假设用户有 Ollama）和 hf: 前缀路径（不能假设用户有下载权限），只允许已存在的本地文件参与 auto 选择。

6. **DraftStreamLoop 的 pending 覆盖设计**：流式 typing 不用队列，用覆盖（pendingText = text），配合 throttleMs 控制频率，永远发最新内容而非历史积压。

7. **28个强类型 HookRunner**：比 Claude Code 的 shell 脚本协议有更好的 IDE 支持、类型检查、错误隔离。hook 函数返回修改后的对象（而非 exit code），更自然地表达「变换」语义。

8. **SecurityAuditSeverity 三级 + 动态加载**：审计报告有 info/warn/critical 三级，集成进 `/status`；深度检查模块动态 import，不影响 gateway 启动时间和内存。

---

*分析文件路径：`/root/.openclaw/workspace/openclaw-source/`*  
*本报告归档：`/root/.openclaw/workspace/openclaw-source-full-analysis.md`*
