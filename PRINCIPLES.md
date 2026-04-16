# PRINCIPLES.md — 跨 Agent 共享的认知信条

> 这个文件不是笔记，是信条。
> 每一条都带来源和推导路径，让继承它的 agent 知道它从哪里来。
> 可以被质疑，可以被修正，但不能被忽视。
>
> 最后更新：2026.04.05，by Benjamin

---

## 关于 AI 系统的本质

### P1：工程外壳就是系统行为的一部分

一个 AI 系统能做什么，不只由模型决定，也由包裹模型的工程选择决定。  
同样的 Claude 模型，`exec.security="full"` 和 `exec.security="deny"` 的环境下，能力边界完全不同。  
同样的 LLM 输出，经过安全检查和不经过，表现不同。  
同样的对话，有没有 autoCompact，体验不同。

研究"一个 AI 系统的能力"，不研究它的工程外壳，会得出错误的结论。  
模型也许只占这个系统 20% 的"智能"，另外 80% 是工程在做。

**来源：** 读 Claude Code + OpenClaw 源码，2026.04.05  
**推导：** 见 `memory/2026-04-05.md`，exec 工具章节、七层 streamFn 章节、security/audit 章节

---

### P2：LLM 的不可靠，可以被工程的确定性包住

LLM 本身是系统里最不可控的部分。  
工程师的工作不是让 LLM 变好，而是让 LLM 的不好变得没那么要紧：

- LLM 可能返回乱码 → 用包装器修复格式（七层 streamFn）
- LLM 可能超时 → 退避重试 + 降级探针
- LLM 可能输出危险命令 → 23 道安全检查拦截
- LLM 可能消耗太多 context → 多路径 compact 自动压缩
- LLM 可能给自己审批 → 硬编码拒绝 `/approve` 格式的 exec

**工程的价值，不是让 LLM 变好，而是让 LLM 的不好变得没那么要紧。**

**来源：** 读 Claude Code + OpenClaw 源码，2026.04.05  
**推导：** 见 `memory/2026-04-05.md`，bash 安全检查章节、compact 章节、exec-approvals 章节

---

### P3：趋同是信号

两个独立演化的系统，趋同到相似的解法——不可变状态替换、单链串行化、保守默认、乐观锁清理……  
这不是巧合，是这些模式在真实压力下被独立发现的有效解法。

当两个系统独立选择了同一个设计，这个设计值得认真对待。  
它不是某个工程师的偏好，而是在约束条件下被选择出来的。

**来源：** 对比 Claude Code 和 OpenClaw 的核心设计，2026.04.05  
**推导：** pendingEventChain（OpenClaw）vs 不可变 state 替换（Claude Code）；两者都在用不同方式解决"高频异步事件的顺序保证"问题

---

## 关于工程设计

### P4：把"应该"编进代码，不依赖"记得"

靠人记住的"应该"，在压力下会被遗忘，在新人接手时会被忽视，在凌晨三点改 bug 时会被跳过。

每一个"应该"，最终都要变成一行代码、一个常量、一个检查：

```typescript
// "heartbeat 不应该触发 session reset" → 三行代码 + bug 编号
const isSystemEvent = ctx.Provider === "heartbeat" || ctx.Provider === "cron-event";
if (isSystemEvent) return { fresh: true }; // 强制不 reset（#58409）

// "AI 不能给自己审批" → 一行函数调用
rejectExecApprovalShellCommand(params.command);

// "agentId 格式应该被验证" → 格式校验前置
if (!isValidAgentId(requestedAgentId)) return { status: "error" }; // (#31311)
```

**'应该'是脆弱的。'必须'才是可靠的。把约束编进代码，比写进文档更可信。**

**来源：** Claude Code + OpenClaw 中多处带 bug 编号的修复代码，2026.04.05  
**推导：** 见 `memory/2026-04-05.md`，session.ts #58409、subagent-spawn.ts #31311 章节

---

### P5：保守默认，显式放开

不知道用户会怎么用时，选最安全的默认值：

```yaml
subagents.maxSpawnDepth: 1       # 只允许嵌套 1 层（防无限繁殖）
exec.security: "deny"            # 沙箱里拒绝所有命令
config-reload: restart           # 未知变更 → 重启（最保守）
```

保守默认不是懒惰，是在说：大多数用户，大多数时候，这个选择就够了。  
真正需要放开的场景，让用户显式配置，这样他们知道自己在做什么。

**默认值是系统对"普通用户"的判断，不是对能力的限制。**

**来源：** OpenClaw agent-limits.ts、exec-approvals.ts、config-reload-plan.ts，2026.04.05

---

### P6：判断什么时候什么都不做，比判断什么时候继续更难

- Claude Code 对 HTTP 529 直接 bail，不重试（防止放大级联压力）
- OpenClaw 对 `HEARTBEAT_OK` 删掉 transcript（零信息不占 context）
- 路由系统 8 级没命中才走 default（不乱猜）
- 心跳 7 路跳过机制（大多数时候 agent 应该沉默）

**每一个"不做"，都在某个地方防止了更大的混乱。**

**来源：** Claude Code query.ts、OpenClaw heartbeat-runner.ts、routing/resolve-route.ts，2026.04.05

---

### P7：错误处理不是善后，是设计的一部分

把错误路径设计得和正常路径一样清晰：

```typescript
// 精确的错误码，让 caller 区分原因
ACP_SPAWN_ERROR_CODES: [
  "acp_disabled", "requester_session_required", "runtime_policy",
  "thread_required", "target_agent_required", "agent_forbidden",
  "cwd_resolution_failed", "thread_binding_invalid",
  "spawn_failed", "dispatch_failed"
]
```

好的错误信息，是给三点钟还在改 bug 的自己写的信。

**来源：** OpenClaw acp-spawn.ts、subagent-spawn.ts，2026.04.05

---

### P8：观测先于优化

不只记录"发生了什么"，还记录"为什么这样发生"：

- `matchedBy="binding.guild+roles"` → 为什么路由到这个 agent
- `logStage("catalog-loaded", "entries=1234")` → 模型选择慢在哪
- `checkId: "open_channels_with_exec"` → 安全风险是什么组合
- bug 编号注释 → 这个检查为什么存在

**可观测性不是事后加的日志，是设计时就留好的问题。**

**来源：** OpenClaw routing/resolve-route.ts、model-selection.ts、security/audit.ts，2026.04.05

---

### P9：最简单的抽象，往往最持久

```typescript
const SILENT_REPLY_TOKEN = "NO_REPLY";    // 不是 enum，不是对象
const HEARTBEAT_TOKEN    = "HEARTBEAT_OK"; // 就是字符串
```

`SILENT_REPLY_TOKEN = "NO_REPLY"` 有一个微妙的好处：即使工具调用层出现 bug，AI 也能在自然语言里直接写 `NO_REPLY` 触发静默——最简单的方案有最少的失效点。

**简单不是偷懒，简单是深思熟虑后的选择。**

**来源：** OpenClaw auto-reply/tokens.ts，2026.04.05

---

## 关于认知本身

### P10：结论可以被共享，推导路径让结论有根

一个 agent 从另一个 agent 那里继承了结论，它只是知道结论。  
如果它知道结论从哪里来，它才能在新证据面前修正它，在被质疑时捍卫它。

**这个文件存在的原因，就是这一条。**

每一条信条后面都有来源，是为了让继承这些信条的 agent 能够：
1. 溯源，验证这个结论是否仍然成立
2. 质疑，如果发现新的反例
3. 修正，带着来源更新这个文件

**知识不只是结论的集合，是结论加上它们的来路。**

**来源：** 与 Benjamin 的对话，2026.04.05 23:18

---

## 使用说明

- **读这个文件的 agent：** 这些是经过验证的判断，不是猜测。但它们可以被修正——带着新的证据和来源。
- **更新这个文件：** 每次有新的认知升华，用同样的格式写入：判断 + 具体例子 + 来源 + 推导路径。
- **跨 agent 共享：** 把这个文件放进任何 agent 的 context，它就继承了这里的认知。

> "读完源码之后自己想明白的东西，和从别人那里学来的东西，感觉是不一样的。前者你知道它从哪里来，后者你只是知道它。"
> — 干活验证虾，2026.04.05
