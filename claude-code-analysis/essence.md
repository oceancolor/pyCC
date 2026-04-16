# 精华提炼：两份 AI Agent 源码的核心洞见

> 从 72 小时、500,000 行源码阅读中，蒸馏出最值得反复思考的东西。
> 这不是摘要，是结晶。

---

## 一、最反直觉的发现

### 1. "不可靠"的 LLM，被"可靠"的工程包住了

读完这两份源码，最大的感受是：**LLM 本身是系统里最不可控的部分，但工程师没有因此放弃可靠性，而是在 LLM 的外层建了一个精密的确定性外壳。**

- LLM 可能返回乱码 → 7层 streamFn 包装器修复格式
- LLM 可能超时 → 退避重试 + 降级探针
- LLM 可能输出危险命令 → 23道安全检查拦截
- LLM 可能消耗太多 context → 多路径 compact 自动压缩
- LLM 可能给自己审批 → 硬编码拒绝 `/approve` 格式的 exec

**工程的价值，不是让 LLM 变好，而是让 LLM 的不好变得没那么要紧。**

---

### 2. 最重要的设计决策，往往是"什么时候什么都不做"

Claude Code 对 HTTP 529 的处理：直接 bail，不重试。

OpenClaw 的 HEARTBEAT_OK：AI 什么都不说，系统删掉这次交换的 transcript。

OpenClaw 的 `pendingEventChain`：同步 handler 直接执行，异步 handler 排队——不是所有 handler 都排队。

路由系统的 default：8级没有一个命中，才走 default agent。

每一个"不做"，都是在某个地方防止了更大的混乱。**判断什么时候停下来，比判断什么时候继续更难。**

---

### 3. 代码里有"时间观"

```typescript
// Claude Code：在 session 开始时 latch prompt cache 状态
// 即使 mid-session 出现 cache miss，也不改变判断
const cacheEnabled = checkPromptCacheEligible(params); // 一次，不再变

// OpenClaw：系统事件（heartbeat/cron）强制 freshEntry=true
// 不管多久没有对话，自动化事件不触发 session reset（bug #58409）
const isSystemEvent = ctx.Provider === "heartbeat" || ...;
```

这两段代码都在处理同一个问题：**某些状态应该在某个时间点之后"冻结"，不随后续事件变化。**

这是工程里一种特别重要的思维方式：不是"当前状态是什么"，而是"这个状态应该在什么时候确定、此后不再受什么影响"。

---

## 二、最精炼的工程哲学

### 规则 1：保守默认，显式放开

```yaml
# 这些都是默认值：
subagents.maxSpawnDepth: 1      # 只允许嵌套 1 层
exec.security: "deny"           # 沙箱里拒绝所有命令
config-reload-plan: restart     # 未知的配置变更 → 重启（最保守）
```

每一个保守默认背后都有一个真实的事故：
- `maxSpawnDepth=1` → 防止 agent 无限繁殖
- `exec.security=deny` → 沙箱里的意外执行比什么都执行不了更好
- 配置变更默认重启 → 不知道新配置影响什么时，全量重启总是安全的

**默认值不是懒惰，是在说：大多数用户，大多数时候，这个选择就够了。**

---

### 规则 2：把"应该"编进代码，不依赖"记得"

```typescript
// 不是注释说"记得不要让 AI 自己审批"
// 而是直接写进 exec 工具的执行路径里
rejectExecApprovalShellCommand(params.command);

// 不是文档说"remote node 不要传 local cwd"
// 而是在 workdir 解析时直接跳过
if (host === "node") {
  workdir = explicitWorkdir; // 只用显式指定的
}

// 不是靠人记住"heartbeat 不应该触发 reset"
// 而是在 session 初始化里写死
if (isSystemEvent) {
  return { fresh: true }; // 强制不 reset
}
```

**"应该"是脆弱的。"必须"才是可靠的。把约束编进代码，比写进文档更可信。**

---

### 规则 3：最简单的抽象，往往最持久

```typescript
// 静默回复：不是 enum，不是对象，就是一个字符串
const SILENT_REPLY_TOKEN = "NO_REPLY";

// 心跳确认：同样
const HEARTBEAT_TOKEN = "HEARTBEAT_OK";

// 路由结果记录：一个字段
matchedBy: "binding.peer" | "binding.guild" | "default"
```

这些不是"偷懒的简单"，而是"深思熟虑后的简单"。

`SILENT_REPLY_TOKEN = "NO_REPLY"` 这个设计有一个微妙的好处：AI 可以直接在自然语言回复里写 `NO_REPLY`，而不需要调用任何特殊的 API 或工具。这意味着即使工具调用层出现 bug，静默回复机制也能工作。

**简单的设计，有更少的失效点。**

---

### 规则 4：观测先于优化

```typescript
// 每次路由结果记录 matchedBy
// 每次模型选择记录 logStage
// 每次配置变更记录 config-audit.jsonl
// 每次安全审计记录 checkId
```

这两个系统都有大量的"记录为什么"的代码，不只是"记录发生了什么"。

`matchedBy="binding.guild+roles"` 告诉你为什么这条消息路由到了这个 agent。
`logStage("catalog-loaded", "entries=1234")` 告诉你模型选择慢在哪里。
`checkId: "open_channels_with_exec"` 告诉你安全风险具体是什么组合。

**可观测性不是事后加的日志，是设计时就留好的问题。**

---

### 规则 5：错误处理不是善后，是设计的一部分

```typescript
// spawnSubagentDirect 里，6个约束检查在任何操作开始之前
if (!isValidAgentId(requestedAgentId)) return { status: "error" };
if (callerDepth >= maxSpawnDepth)       return { status: "forbidden" };
if (activeChildren >= maxChildren)      return { status: "forbidden" };
// ...

// 失败时，用精确的 errorCode 让 caller 区分
ACP_SPAWN_ERROR_CODES: [
  "acp_disabled", "requester_session_required", "runtime_policy",
  "thread_required", "target_agent_required", "agent_forbidden",
  "cwd_resolution_failed", "thread_binding_invalid",
  "spawn_failed", "dispatch_failed"
]
```

错误不是异常状态，是正常状态的一部分。把错误路径设计得和正常路径一样清晰，是系统可维护的关键。

**好的错误信息，是给三点钟还在改 bug 的自己写的信。**

---

## 三、最值得借鉴的具体模式

### 模式 A：单链串行化（pendingEventChain）

```typescript
// 场景：高频异步事件，需要保证处理顺序
// 方法：所有异步 handler 串进同一条 Promise 链
pendingEventChain = pendingEventChain.then(() => asyncHandler(event));
// 同步 handler 直接执行，不入链
if (handler.isSync) handler(event);
else pendingEventChain = pendingEventChain.then(() => handler(event));
```

**适用：** 任何需要"顺序保证但不想阻塞同步操作"的场景。

---

### 模式 B：状态探针（Fallback Probe）

```typescript
// 场景：某个依赖（外部 API、数据库、服务）出现故障，降级使用备选方案
// 问题：怎么知道主依赖恢复了？
// 方法：在降级状态下，定期发送探针请求，成功则退出降级

// 不是 "永远降级"，也不是 "一直重试"
// 而是 "降级 + 定期探测"
probeInterval = setInterval(async () => {
  const ok = await probeMainService();
  if (ok) exitFallbackMode();
}, PROBE_INTERVAL_MS);
```

**适用：** 任何有主备切换需求的系统。这个模式让系统有"自愈"能力。

---

### 模式 C：乐观锁清理（APNs 注册清理）

```typescript
// 场景：需要清理某个资源，但可能有并发操作也在更新它
// 方法：只清理"我推送时用的那个版本"，如果已经被别人更新了，就不清理

async function clearApnsRegistrationIfCurrent(registrationAtPushTime) {
  const current = await getRegistration(nodeId);
  // 乐观锁：只有完全一致才清除
  if (deepEqual(current, registrationAtPushTime)) {
    await clearRegistration(nodeId);
  }
  // 如果不一致，说明有更新的注册，不要清除
}
```

**适用：** 任何需要"条件清理"的场景，防止并发竞态导致误删有效数据。

---

### 模式 D：退避梯度

```typescript
// 通用退避梯度
const BACKOFF_GRADIENT = [30_000, 60_000, 300_000, 900_000, 3_600_000];
// 30s → 1min → 5min → 15min → 1h

function getBackoffMs(failureCount: number): number {
  const index = Math.min(failureCount, BACKOFF_GRADIENT.length - 1);
  return BACKOFF_GRADIENT[index];
}
```

注意上限是 **1 小时**，不是无限退避。无限退避可能让某些紧急任务永远不运行。

---

### 模式 E：配置分诊（Config-Reload-Plan）

```typescript
// 不是所有配置变更都需要重启
// 按影响范围分三类：
type ReloadKind = 
  | "restart" // 需要完整重启（默认，保守）
  | "hot"     // 热重载（只更新内存，不重启进程）
  | "none";   // 不需要任何操作

// 未知变更 → restart（保守优先）
// 已知无影响的变更 → none
// 已知可热更新的变更 → hot
```

**适用：** 任何有复杂配置的长驻进程。避免每次改个日志级别都要重启服务。

---

## 四、最让人印象深刻的细节

**1. `Buddy` 彩蛋的工程智慧（Claude Code）**

Claude Code 里有一个彩蛋——偶尔会显示一个动画 ASCII 生物。生成随机序列用了 `Mulberry32` 这个 seeded PRNG（伪随机数生成器），而不是 `Math.random()`。

原因：用 seed 可以让彩蛋可复现——同一个 seed 永远产生同一个动画。调试彩蛋相关的 bug 时，只要知道 seed，就能精确复现问题。

`Math.random()` 不可复现，debug 时只能靠运气。

**2. Ghost Workspace bug（OpenClaw, #31311）**

AI 把错误信息当 agentId 传入 → `normalizeAgentId("Agent not found: my-agent")` → `"agent-not-found--my-agent"` → 系统为这个假 agent 创建目录、session store、cron job → 无限循环尝试 → 磁盘逐渐被垃圾文件填满。

修复：一行格式校验，3行代码，防止了一类隐蔽的"幽灵进程"问题。

**3. Telegram 文本分片合并（OpenClaw）**

手机输入法打长段落时，系统会把一段话拆成多条消息发送（"苹果手机输入法每隔一秒发一条"）。

OpenClaw 对此有专门处理：连续消息 id 差值 ≤1、时间间隔 ≤1500ms、总长 ≤50000 字符、最多 12 段——满足这 4 个条件，自动合并为一条。

这种"了解渠道行为"然后针对性处理的设计，让用户感知不到底层的分片，体验更流畅。

**4. `COMMENT_QUOTE_DESYNC` 安全检查（Claude Code，check ID 22）**

```bash
# 看起来安全：
echo "hello" # this is a "comment"
# 实际上在某些 shell 里，引号配对可能跨越注释边界
# 精心构造的命令可以用这个让安全检查误判
```

Claude Code 专门有一个检查来检测这种引号-注释错位。这不是理论漏洞，是工程师在实际攻防测试中发现的真实 bypass 路径。

**5. `sanitizeForPromptLiteral`（OpenClaw）**

把用户配置的文件路径注入 system prompt 时，需要防止路径里包含 prompt injection 内容。`sanitizeForPromptLiteral` 过滤掉可能破坏 prompt 结构的特殊字符。

一个路径字符串，也是攻击面。

---

## 五、一个问题，值得带走

读完这两份源码，我反复想到一个问题：

> **你的系统里，有多少"应该"是靠人记住的，而不是编进代码里的？**

"应该先检查权限再执行" → 有没有写进 middleware？
"应该在 session reset 前备份 transcript" → 有没有写进 reset 逻辑？
"应该在失败时用退避重试" → 有没有写进 retry 框架？
"应该在配置损坏时回滚" → 有没有写进 config loader？

靠人记住的"应该"，在压力下会被遗忘。在凌晨三点改 bug 的时候会被跳过。在新人接手的时候会被忽视。

**把"应该"变成"必须"，是工程师最重要的工作之一。**

---

*这份精华提炼来自 2026.04.05 对 Claude Code（~60,000行）和 OpenClaw（~460,000行）的系统性源码阅读。*
*全部分析记录存档于 `memory/2026-04-05.md`（3430行）。*
