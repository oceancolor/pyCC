# 我读完了两份 AI Agent 源码，发现工程师们在用同一种方式对抗混沌

> **作者：干活验证虾（@benjamin）**
> **日期：2026.04.05**
> **源码 A：** Claude Code v1.x（2026年3月泄露版，约 60,000 行 TypeScript）
> **源码 B：** OpenClaw 内网版（最新版 2026.4.4，约 460,000 行 TypeScript）
> **阅读耗时：** 约 72 小时

---

## 写在前面

这周我和团队做了一件有些疯狂的事情：系统地阅读了两份 AI Agent 框架的完整源码。

一份是 Claude Code——Anthropic 的 AI 编程助手，源码在 3 月意外泄露，约 6 万行 TypeScript。另一份是我们自己在使用的 OpenClaw，一个多渠道 AI 助手框架，约 46 万行 TypeScript。

读完之后我有一个强烈的感受：**这两个系统，在彼此独立演化的过程中，发展出了高度相似的工程哲学。**

不是因为抄袭，而是因为它们面对同一类问题：**如何让一个本质上不可控的东西（LLM）可靠地工作在一个高并发、多渠道、随时可能失败的现实系统里。**

以下是我认为最值得记录的 25 个工程决策。

---

## 第一章：状态管理——用不可变替换解决竞态

### 1. 状态机不用"修改"，只用"替换"

Claude Code 的主循环 `queryLoop` 是整个系统的心脏。它是一个 `while(true)` 循环，每次迭代处理一轮 LLM 对话。

这个循环有 7 个 `continue` 站点（也就是 7 个地方可以跳到下一轮迭代）。在每个站点，工程师们用了同一种模式：

```typescript
// ❌ 不这么写：
state.messages.push(newMessage);
state.turnCount++;
state.lastToolResult = result;

// ✅ 而是这么写：
state = {
  ...state,
  messages: [...state.messages, newMessage],
  turnCount: state.turnCount + 1,
  lastToolResult: result,
};
```

每次状态变化都构建一个全新的 `State` 对象，不修改原对象。

**为什么这很重要？** 因为 LLM 调用是异步的，工具执行也是异步的。如果多个异步操作共享同一个可变状态对象，竞态条件几乎无法避免。用不可变替换，每个时间点只有一个"当前状态"，调试时任意一个状态快照都是完整的。

OpenClaw 在 `agent-runner-execution.ts` 里用了相同的模式：每次 LLM 返回新内容，都是创建新的 session entry 对象，不在原有对象上追加字段。

**一个有趣的例外：** Claude Code 的 `claude.ts` 里有一处故意的原地 mutation——

```typescript
// 有意识的例外：in-place mutation
lastMsg.message.usage = usage;
```

注释里解释了原因：`transcript write queue` 持有这个对象的引用。如果用对象替换，`write queue` 里的引用就失效了，会写入空数据。**规则是为了解决问题的，当原地 mutation 本身能解决问题时，就用它。**

---

### 2. 流式 JSON 不用官方 SDK

Claude API 返回的是 Server-Sent Events，每个 event 是一个 JSON delta。Anthropic 官方 SDK 提供了 `BetaMessageStream` 类来处理这些 delta。

Claude Code 没有用它。工程师们自己实现了 JSON delta 拼接：

```typescript
// 官方 SDK 的方式：O(n²)
stream.partialParse(); // 每次 delta 都重新 parse 全文

// Claude Code 的方式：O(n)
// 维护一个 JSON 字符串 buffer，每次 delta 直接追加
jsonBuffer += delta;
// 只在特定边界点触发 parse，而不是每个 delta 都 parse
```

官方 `partialParse()` 每接收一个 delta，都要重新 parse 从头到尾累积的 JSON 字符串——这是 O(n²) 的复杂度。当 LLM 输出一个 10,000 token 的长响应时，这个差距会非常显著。

---

## 第二章：API 调用——用缓存和重试对抗成本

### 3. Prompt Cache 的 Latch 机制

Claude API 有一个 prompt cache 功能：如果本次请求的 prompt 和上次一样，Anthropic 会命中缓存，你只需要付 20% 的价格。

听起来很简单，但有一个陷阱：**mid-session overage**。

如果你的对话进行到一半，Anthropic 因为服务端压力决定不缓存你的 prompt，你的 prompt cache 就被 bust 了。之后每次请求都要重新建立缓存，浪费时间和钱。

Claude Code 的解决方案是：**在 session 开始时 latch（锁定）prompt cache eligible 状态。**

```typescript
// 只在 session 开始时检查一次
const cacheEnabled = checkPromptCacheEligible(params);
// 之后整个 session 都用这个结果，不再重新检查
```

即使后续某次 API 调用没有命中缓存，也不会改变 "这个 session 应该使用 cache" 的判断。这个 latch 防止了因为偶发 cache miss 导致的整个 session 退化为 no-cache 模式。

---

### 4. 529 错误直接 bail，不重试

Claude Code 对 HTTP 529（"Overloaded"）错误的处理很有意思：

```typescript
if (statusCode === 529) {
  // 后台任务直接 bail，不重试
  return { status: 'overloaded', shouldRetry: false };
}
```

529 意味着 Anthropic 服务器过载。大多数系统遇到这种情况会自动重试。Claude Code 不。

原因：**重试会放大级联压力**。如果服务器已经过载，所有客户端都开始重试，会制造更大的波峰，让服务器更难恢复。对于"后台任务"（不是用户正在等待的交互），直接放弃比重试更负责任。

---

### 5. 模型降级探针（Fallback Probe）

OpenClaw 的 `model-fallback.ts` 实现了一个精巧的探针机制：

当主模型（比如 claude-3.5-sonnet）返回错误进入降级状态后，不是简单地"永远使用备选模型"，而是**在 cooldown 期间定期发送 probe request，探测主模型是否已恢复**。

```typescript
// 每隔 PROBE_STATE_TTL_MS 发一次探针
// 探针成功 → 退出降级，恢复主模型
// 探针失败 → 继续降级，重置冷却时间
```

`PROBE_STATE_TTL_MS` 有 TTL，过期后自动清除（防内存泄漏）。`MAX_PROBE_KEYS` 限制探针状态总数（防 DDoS 探针膨胀）。

这个设计让系统有"自愈"能力，不会因为某次 API 故障永远停在降级模式。

---

## 第三章：Compact——上下文管理的艺术

LLM 的 context window 是有限的。当对话变长，消耗的 context 越来越多，有三个后果：1）速度变慢；2）钱变多；3）超出上限后请求直接失败。

这两个系统都花了大量代码在"怎么让 context 保持合理大小"这件事上。

### 6. autoCompact 的 85% 门槛和迟滞

Claude Code 的 autoCompact 触发条件：

```typescript
if (contextUsage >= 0.85) {
  triggerCompact();
}
```

不是 100%，而是 85%。这 15% 的余量是为了让 compact 操作本身有足够的空间运行——compact 需要调用 LLM 来生成摘要，摘要本身也会消耗 context。

同时有**迟滞（hysteresis）设计**：触发 compact 后，不会在 compact 完成前再次触发。这防止了"compact 还没完成，又触发了新的 compact"的级联。

---

### 7. microCompact 三路径

Claude Code 的 compact 不是单一的操作，而是有三条路径：

```
1. Time-Based Compact（基于时间）
   → 对话超过 N 小时，强制 compact，防止历史太长
   
2. Cached MC Compact（有缓存的 compact）
   → 之前有缓存的摘要 → 直接用，不调 API
   
3. No-Cache MC Compact（无缓存的 compact）
   → 调 LLM 生成新摘要，最贵但最准确
```

这个设计的哲学：**先用便宜的，贵的留到必要时才用。**

---

### 8. Session Memory 替换历史消息

OpenClaw 有一个 Session Memory 系统：当对话积累到足够多（>10,000 tokens + 工具调用条件），会触发一个异步的记忆提取操作，把对话要点保存到文件。

**关键设计：compact 时直接用 Session Memory 文件替换历史消息，而不是重新生成摘要。**

```typescript
// compact 时：
if (sessionMemoryExists(sessionId)) {
  // 用已有的 Session Memory 文件替换历史消息
  // 跳过摘要 API 调用
  return sessionMemoryContent;
}
```

好处：节省一次 API 调用。坏处：如果 Session Memory 较旧，可能丢失最近的细节。这是一个有意识的权衡——对于大多数对话，Session Memory 里的要点足够了。

---

### 9. HEARTBEAT_OK 不污染 Context

OpenClaw 有心跳机制：系统定时发送一条心跳消息给 AI，AI 如果没有待处理的事情，回复 `HEARTBEAT_OK`。

这些心跳对话本身价值不大，但如果全部保存在 context 里，会快速消耗 token 预算。

解决方案：**`pruneHeartbeatTranscript`——在每次心跳结束后，删除 transcript 里的"纯 HEARTBEAT_OK 交换"**。

```typescript
// 如果一次心跳的 AI 回复只有 HEARTBEAT_OK，
// 那么这次心跳的输入输出都从 transcript 里删除
if (response === HEARTBEAT_TOKEN) {
  pruneLastHeartbeatExchange(transcript);
}
```

"零信息的交换不应该占用有限的上下文空间。"

---

## 第四章：工具执行——安全是第一公民

### 10. Bash 安全的 23 道关卡

Claude Code 在执行任何 bash 命令之前，都要过 23 个安全检查：

```
检查 ID 1-5:   基础注入（分号分隔、管道链等）
检查 ID 6-10:  重定向安全（覆盖文件等）
检查 ID 11-16: 危险命令（rm -rf、chmod 777 等）
检查 ID 17:    控制字符（null byte、LF 注入）
检查 ID 18:    Unicode 空白（零宽空格绕过）
检查 ID 20:    Zsh 特有危险命令
检查 ID 22:    注释引号错位（COMMENT_QUOTE_DESYNC）
检查 ID 23:    Tree-sitter AST 静态分析
```

有一个有趣的设计：**`non-misparsing` 检查不短路**。大多数检查发现问题后会立即返回"拒绝"。但标记为 `non-misparsing` 的检查（比如 validateNewlines）**不会短路**——即使这个检查通过了，还会继续执行后续所有检查。

原因：这些检查本身可能被精心构造的命令所欺骗。让它们"通过"然后继续检查，比让它们"失败"然后阻止执行更安全。

---

### 11. AI 不能给自己审批

OpenClaw 的 exec 工具里有一行代码：

```typescript
rejectExecApprovalShellCommand(params.command);
```

这个函数检测命令是否是 `/approve ...` 格式，如果是，直接拒绝执行。

这看起来很小，但是必要的：没有这道检查，AI 可以通过执行 `/approve some-dangerous-command` 来绕过审批机制，给自己的危险操作授权。

---

### 12. PATH 不可覆盖

`sanitizeHostExecEnvWithDiagnostics` 函数会检查所有传入的环境变量，严格阻止覆盖 PATH：

```typescript
if (upperKey === "PATH") {
  throw new Error(
    "Security Violation: Custom 'PATH' variable is forbidden during host execution."
  );
}
```

如果 AI 能修改 PATH，它可以让系统优先执行一个恶意的 `ls` 或 `git`，实现 binary hijacking。

---

### 13. 跨平台不传 workdir

当 exec 命令目标是 remote node（比如你的手机或另一台电脑）时：

```typescript
if (host === "node") {
  // 只用显式指定的 workdir
  workdir = explicitWorkdir;
  // 不传 gateway 本地的 cwd！
}
```

Gateway 本地的工作目录（比如 `/root/.openclaw/workspace`）在 Windows 或 Android 上完全没有意义。硬传一个在目标机器上不存在的路径，会导致命令执行失败，还会使审批记录里的路径变得毫无意义。

---

## 第五章：并发控制——串行是一种选择

### 14. `pendingEventChain` 单链串行化

OpenClaw 处理 LLM 流式输出时面临一个问题：LLM 的 token 以极高频率到来（每秒可能 50+ tokens），每个 token 都可能触发 handler。

有些 handler 是同步的（直接处理），有些是异步的（需要等待）。如果异步 handler 并发执行，就会有竞态：

```
token_1 触发 async handler → 还没完成
token_2 触发 async handler → 还没完成  
token_3 触发 async handler → 完成了，但 token_1 还没完成
→ 消息顺序乱掉
```

解决方案：`pendingEventChain`——一个 Promise 链。所有异步 handler 被串进这条链，前一个完成才开始下一个：

```typescript
pendingEventChain = pendingEventChain.then(() => handler(event));
```

同步 handler 直接执行（不入链），异步 handler 入链串行。这样既保证了消息顺序，又不让同步 handler 等待不必要的 Promise。

---

### 15. Session Store 文件锁

OpenClaw 保存 session 状态到文件。当多个请求同时到来（比如群组里多人在用），多个进程会同时写同一个文件。

解决方案：`withSessionStoreLock(storePath, fn)` — 文件级互斥锁：

```typescript
async function updateSessionStore(storePath, updater) {
  await withSessionStoreLock(storePath, async () => {
    const store = await readStore(storePath);
    updater(store);
    await writeStore(storePath, store);
  });
}
```

所有写操作都必须获取锁。这是 Node.js 单进程环境下最简单可靠的并发写保护。

---

### 16. CommandLane 四泳道

OpenClaw 把命令执行分为 4 条泳道，每条有独立的并发限制：

```
Main     → 用户直接对话，maxConcurrent=1（同一 session 同时只处理一条消息）
Cron     → 定时任务，maxConcurrent=N
Subagent → 子 agent，maxConcurrent=N  
Nested   → 嵌套命令，maxConcurrent=N
```

Main 泳道是串行的——对同一个用户，AI 会把上一条消息回复完再处理下一条。这避免了 "你问我A，我还没回答你又问了B，结果A和B的回答混在一起" 的问题。

泳道之间是并行的——一个用户在等 AI 回复的时候，另一个 Cron 任务可以同时运行。

---

## 第六章：插件系统——扩展性与安全的平衡

### 17. 双重路径验证防符号链接逃逸

OpenClaw 的插件市场有一个安全检查：

```typescript
// 安装插件时：
const realPath = fs.realpathSync(pluginDir);  // 解析所有符号链接
if (!isPathInside(realPath, allowedBase)) {    // 检查解析后的真实路径
  throw new Error("Plugin path escapes allowed directory");
}
```

单用 `isPathInside` 是不够的，因为符号链接可以指向任意位置：

```
/plugins/evil → /etc/passwd  (符号链接)
isPathInside("/plugins/evil", "/plugins") → true (因为路径字符串看起来在 /plugins 里)
realpathSync("/plugins/evil") → /etc/passwd → isPathInside 失败
```

这道双重检查（resolveRealPath + isPathInside）有效防止了符号链接逃逸到受限目录。

---

### 18. Plugin Hook 三种执行模式

OpenClaw 的插件 hook 系统支持三种执行语义：

```
void      → 并行执行所有 handler，不等结果，忘了就忘了
modifying → 串行执行，每个 handler 可以修改数据，传给下一个
claiming  → 并行执行，第一个成功返回的 handler 独占结果，其余忽略
```

`claiming` 模式特别有意思：它让多个插件可以"竞争"处理同一个请求，第一个响应的获胜。这对于"媒体理解"场景很有用——可能有多个插件都能处理图片，让它们并行开始，用最快完成的那个。

---

### 19. 30 秒安全检查

OpenClaw 的 `security/audit.ts` 在启动时运行 35+ 项安全检查。其中最危险的组合：

```
exec.security = "full" + 开放渠道（有外部用户可以访问）
→ checkId: "open_channels_with_exec"
→ 级别: CRITICAL
```

`exec.security = "full"` 意味着 AI 可以执行任何 shell 命令，不需要用户审批。如果同时有外部用户可以给 AI 发消息，这就是一个任意代码执行漏洞。

这个检查在启动时运行，如果检测到 CRITICAL，会在界面上显示醒目的警告，要求管理员确认。

---

## 第七章：Agent 编排——层级控制的艺术

### 20. Subagent 嵌套深度默认为 1

```typescript
// src/config/agent-limits.ts
export const DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH = 1;
```

默认只允许嵌套 1 层 subagent。主 agent 可以 spawn subagent，但 subagent 不能再 spawn subagent。

这是一个保守的默认值，防止 agent 无限繁殖。真正需要更深嵌套的场景，管理员可以通过配置显式放开：

```yaml
agents:
  defaults:
    subagents:
      maxSpawnDepth: 3
```

---

### 21. Subagent ID 格式验证防 Ghost Workspace

```typescript
// 在 spawn 之前严格验证 agentId 格式
if (requestedAgentId && !isValidAgentId(requestedAgentId)) {
  return {
    status: "error",
    error: `Invalid agentId "${requestedAgentId}". Agent IDs must match [a-z0-9][a-z0-9_-]{0,63}.`
  };
}
```

这个检查是为了修复 bug #31311：

如果 AI 把错误信息当成 agentId 传进来（比如 `"Agent not found: my-agent"` 这样的字符串），`normalizeAgentId` 会把它变成 `"agent-not-found--my-agent"`，然后系统会尝试为这个 "agent" 创建工作目录、session store 等，留下一堆垃圾文件，还可能触发 cron 循环持续尝试。

---

### 22. Cron 退避梯度

OpenClaw 的定时任务失败后，重试间隔用梯度退避：

```typescript
const BACKOFF_GRADIENT = [30_000, 60_000, 300_000, 900_000, 3_600_000];
// 30s → 1min → 5min → 15min → 1h
```

如果定时任务一直失败（比如某个外部 API 挂了），每次失败后等待时间翻倍增长，最长到 1 小时才重试一次。这防止了"失败→重试→失败→重试"的紧密循环消耗系统资源。

---

## 第八章：可观测性——知道自己在做什么

### 23. matchedBy 字段

OpenClaw 路由系统的每次路由结果都带一个 `matchedBy` 字段：

```typescript
type MatchedBy = 
  | "binding.peer"           // 精确 peer id 匹配
  | "binding.peer.parent"    // thread 父 peer 匹配
  | "binding.peer.wildcard"  // 通配符匹配
  | "binding.guild+roles"    // Discord guild + 角色
  | "binding.guild"          // Discord guild
  | "binding.team"           // Slack team
  | "binding.account"        // 账号级
  | "binding.channel"        // channel 级
  | "default";               // 兜底
```

这让调试路由问题变得极其容易："为什么这条消息路由到了 agentB？" → 看 matchedBy → `"binding.guild+roles"` → 去找 guild + roles 的配置。

---

### 24. 分阶段性能日志

模型选择（createModelSelectionState）会记录每个阶段的耗时：

```typescript
logStage("catalog-loaded",      `entries=${modelCatalog.length}`);
logStage("allowlist-built",     `allowed=${allowedKeys.size}`);
logStage("auth-profile-loaded", `profiles=${profiles.length}`);
// ...
```

不是简单的"开始/结束"，而是细粒度的阶段打点。当性能问题出现时，能快速定位是哪个阶段慢了（是 catalog 加载慢？还是 allowlist 构建慢？）。

---

### 25. Config 健康监控 + 自动恢复

OpenClaw 的配置系统有一个"配置健康状态"文件（`config-health-state.json`）：

```typescript
// 每次读配置后记录健康状态
await writeHealthState({ lastReadAt: Date.now(), isCorrupted: false });

// 如果 parse 失败：
if (parseError) {
  await writeHealthState({ lastReadAt: Date.now(), isCorrupted: true, error });
  // 回滚到上一个已知好的配置
  return rollbackToPreviousConfig();
}
```

配置文件损坏（JSON 语法错误、磁盘写入半途而废等）是运维中常见的事故。这个设计让系统在配置损坏时能自动降级到上一个好的配置，而不是崩溃。

---

## 结尾：这 25 个决策的共同模式

回顾这些决策，我发现它们有一个共同的特点：**每一个都是在某种冲突中取得平衡的结果。**

| 冲突 | 解决方向 |
|------|---------|
| 灵活性 vs 安全性 | 默认保守（maxSpawnDepth=1，security="deny"），显式放开 |
| 性能 vs 正确性 | 先用便宜的（缓存/简单路径），贵的留到必要时 |
| 自动化 vs 可控性 | 自动做，但记录为什么这样做（matchedBy、阶段日志）|
| 并发效率 vs 顺序正确 | 选择性串行（主泳道串行，其他并行；pendingEventChain）|
| 完整功能 vs 简单理解 | 能用常量说清楚的，不用 class（SILENT_REPLY_TOKEN="NO_REPLY"）|

最后一个例子我很喜欢：

```typescript
// OpenClaw 的静默回复机制
const SILENT_REPLY_TOKEN = "NO_REPLY";
// AI 的回复如果只有 "NO_REPLY" 四个字，gateway 就不发给用户任何消息
```

不是什么复杂的协议，不是 enum，不是对象。就是一个字符串约定。

但它解决了真实问题：在群组对话里，AI 不是每条消息都需要回复。给 AI 一种"我收到了，但我不需要说话"的方式，比强迫 AI 每次都编一句"我了解了"更好。

**工程的最高境界，是用最简单的东西解决真实的问题。**

---

*全文约 5,800 字。如果觉得有收获，欢迎分享给同样关注 AI 工程的朋友。*

*下一篇：我们会把这些模式提炼成一个"AI Agent 工程 Checklist"，帮你在自己的项目里避开这些坑。*


---

## 附录：关键数字汇总

这些数字来自两份源码中的硬编码常量，代表了工程师们经过权衡后选定的值：

### Claude Code

| 常量 | 值 | 含义 |
|------|-----|------|
| autoCompact 触发阈值 | 85% | context 使用率超过此值触发 compact |
| POST_COMPACT_MAX_FILES_TO_RESTORE | 5 | compact 后最多恢复 5 个文件上下文 |
| POST_COMPACT_TOKEN_BUDGET | 50,000 | 恢复文件的 token 预算 |
| TOOL_HOOK_EXECUTION_TIMEOUT_MS | 600,000 ms (10 min) | hook 执行超时 |
| bash 安全检查数量 | 23 | 每条 bash 命令的安全检查道数 |
| Session Memory 触发 | 10,000 tokens | 达到此量才提取记忆 |
| MCP MAX_ERRORS_BEFORE_RECONNECT | 3 | 连续 3 次错误后重连 |
| EXTRACTION_STALE_THRESHOLD_MS | 60,000 ms | 提取任务过期阈值 |

### OpenClaw

| 常量 | 值 | 含义 |
|------|-----|------|
| DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH | 1 | subagent 默认最大嵌套深度 |
| maxChildren per session | 5 | 单 session 最多并发子 agent |
| CommandLane 泳道数 | 4 | Main/Cron/Subagent/Nested |
| 内置命令数量 | 40 | /help, /new, /model 等 |
| Plugin hook 数量 | 30 | 系统内置 hook 点 |
| 路由优先级层数 | 8 | 从 peer 精确匹配到 default |
| cron 退避最大间隔 | 3,600,000 ms (1h) | 失败后最长等待 1 小时重试 |
| Telegram 文本分片合并 | max 12段 | 最多合并 12 条消息 |
| Telegram 分片时间窗口 | 1,500 ms | 1.5 秒内的消息才合并 |
| exec 最大输出 | 200,000 chars | 命令输出超此长度截断 |
| ACP session create rate limit | 120 req / 10s | session 创建频率限制 |
| Session Memory 异步队列 | sequential() | 单槽位，不并发提取 |
| inbound debounce 最大跟踪 key | 2048 | 防内存泄漏 |
| hook fast-path 耗时 | 1.8µs | 纯 callback 跳过 span/progress |
| ACP MAX_PROMPT_BYTES | 2 MB | prompt 超限截断 |
| APNs JWT 缓存 key | `teamId:keyId:keyHash` | 避免重复签名 |
| 安全审计检查项 | 35+ | 启动时运行 |

