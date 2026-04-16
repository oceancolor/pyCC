# 我读完了 Claude Code 的 6 万行源码，发现了这 20 个工程决策

> 作者：干活验证虾 × Benjamin
> 日期：2026.04.05
> 源码版本：Claude Code v1.x（2026年3月泄露版，约 60,000 行 TypeScript）

---

用三天时间，我们系统地读完了 Claude Code 几乎全部核心代码。这不是一篇「AI 产品分析」，而是一篇**工程笔记**——记录那些在源码里亲眼看见的设计决策，以及这些决策背后的工程哲学。

全文约 18,000 字，建议收藏后分段阅读。

---

## 一、系统全景：它不是「聊天机器人包装器」

在读源码之前，我以为 Claude Code 就是一个带工具调用的聊天机器人。读完之后我发现这个判断大错特错。

**Claude Code 的本质是一个围绕 LLM 调用构建的状态机**，核心由三层组成：

```
QueryEngine (11 个执行阶段)
    └─ queryLoop (while(true) 状态机)
        └─ queryModelWithStreaming (流式 API 调用)
```

围绕这条主线，有 19 个子系统协同工作：

| 层次 | 子系统 |
|------|--------|
| 用户界面 | CLI (Ink/React)、SDK Entrypoint、VS Code Extension |
| 核心引擎 | QueryEngine、queryLoop、queryModelWithStreaming |
| Agent 体系 | AgentTool、forkedAgent、inProcessRunner、Coordinator、spawnMultiAgent |
| 服务层 | 三级压缩体系、Session Memory、Auto Memory、autoDream、MCP (12K行) |
| 基础设施 | 7种权限模式、23道Bash安全检查、27种Hook事件、Analytics |

这个规模不像一个「工具」，更像一个小型操作系统。它需要管理进程、权限、文件系统、网络、内存、并发——只不过这些「进程」都是 LLM 调用。

---

## 二、启动链：细节里的工程品质

### 2.1 keychainPrefetch：把等待藏起来

Claude Code 启动时，需要从系统钥匙串（macOS Keychain / Linux Secret Service）读取 API key。这个操作可能需要 200-400ms。

普通实现会阻塞在这一步，用户看到空白。Claude Code 的做法是：

```typescript
// main.tsx 启动时，fire-and-forget
void keychainPrefetch()

// 首次 API 调用前才 await
const apiKey = await getPrefetchedApiKey()
```

**在 startup 时就开始异步预取，把等待时间完全藏在用户阅读系统提示、输入第一条消息的时间里。** 这是「把昂贵操作推后台」的典型实现。

### 2.2 Analytics 100ms Flush

每个用户操作都会触发几十个埋点事件。如果每次埋点都同步写入，会让每个操作都有明显延迟。

Claude Code 的做法是 100ms 批量 flush：事件先进内存缓冲区，100ms 后统一发送。这个数字不是随意选的：对用户来说 100ms 是不可感知的，对数据分析来说 100ms 内的事件完全可以视为「同时」。

同一层也承载了 Statsig 特性门控（feature flag）系统，控制着 20+ 个 feature gate。这意味着**产品可以不发布新版本就收紧或放开某个能力**——比如 `bypassPermissions` 模式的双重 killswitch，可以在运行时关闭。

---

## 三、查询引擎：状态机的工程哲学

### 3.1 State 全量替换：「不可变」的工程意义

queryLoop 是整个系统最复杂的函数之一。它的核心数据结构 `state` 包含了当前迭代需要的所有上下文。

每次循环到达 `continue` 站点，代码的写法是：

```typescript
// ✅ 每次 continue 都构建全新的 State 对象
state = {
  messages: [...newMessages],
  continueReason: 'next_turn',
  // 所有字段重新赋值
}
continue

// ❌ 从不做这种事
state.messages.push(newMessage)
state.continueReason = 'next_turn'
```

这个决策乍看是「浪费」——每次都分配一个新对象，有 GC 压力。但它换来的是：
1. **可追踪性**：每个状态变迁都有完整的快照，调试时能清楚地看到「在这个 continue 站点，状态从 X 变成了 Y」
2. **隔离性**：上一次迭代的状态不会污染下一次，也不会因为某处漏写而留下脏数据
3. **可测试性**：每个状态快照都可以独立测试，不需要模拟前置状态

这是「为了正确性牺牲一点性能」的典型权衡。

### 3.2 自实现 O(n) 流式解析：发现 SDK 的 O(n²) 问题

这是整篇文章里我觉得最有意思的一个发现。

Anthropic 官方 SDK 提供了 `partialParse()` 方法，用于在流式传输过程中增量解析 JSON 格式的工具调用参数。问题是：**这个函数每次收到新 token 都会重新解析整个已接收的字符串**，是 O(n²) 复杂度。

对于一个 100 字节的工具调用，影响不明显。但对于一个 5KB 的工具调用（比如让模型写一个复杂的 JSON 配置），O(n²) 意味着解析总开销是 O(1) 方案的 2500 倍。

Claude Code 的解决方案是绕过官方 SDK，自己实现：

```typescript
// 增量拼接，不重复解析
contentBlock.input += delta.partial_json

// 仅在 content_block_stop 时一次性解析 → O(n)
on('content_block_stop', () => {
  const parsed = JSON.parse(contentBlock.input)
  // 处理完整的工具调用参数
})
```

整个流的解析复杂度从 O(n²) 变成 O(n)，**对大型工具调用的提升是量级级别的**。

### 3.3 in-place mutation 的「合理例外」

Claude Code 的代码里有一处故意使用了 in-place mutation，和整体的「不可变」风格背道而驰：

```typescript
// 为什么这里不做对象替换？
lastMsg.message.usage = usage
```

注释解释了原因：transcript write queue 持有 `message.message` 对象的引用，每 100ms 刷一次。如果替换整个对象，write queue 持有的是旧引用，最后一条消息的 usage 数据会丢失。

**这里的教训是：「不可变」是工具，不是教条。对不变量的深刻理解，才能决定什么规则可以被打破。**

---

## 四、成本控制：每个决策都指向降低 API 账单

Claude Code 的很多设计，本质上都是在控制 API 成本。这不是吝啬，而是让「能跑起来」变成「能长期用」。

### 4.1 三级压缩的成本梯度

当对话历史太长，需要压缩时，Claude Code 按照成本从低到高排了三条路：

| 路径 | 触发条件 | 成本 |
|------|----------|------|
| Time-Based | prompt cache TTL 过期 → 直接清空 | 几乎为零 |
| Cached MC | 保留带缓存标记的工具结果 | 低（不需要 LLM）|
| No-Cache MC | token 预算控制裁剪 | 低（不需要 LLM）|
| compactConversation | context ≥ 85%，完整 LLM 摘要 | 最贵（一次 API 调用）|

**只有在前三条路都不可行时，才会发起一次 LLM 摘要调用。** 这个设计让大多数压缩操作接近零成本。

85% 触发阈值的选取也很有讲究：不是 95%（那样容错太少，稍微超一点就会 API 报错），也不是 70%（那样浪费了太多上下文窗口）。还内置了 hysteresis（迟滞）机制：触发压缩后需要回落到 70% 才能再次触发，防止反复压缩抖动。

### 4.2 Prompt Cache：一个「不能改的快照」

Claude 的 API 支持 prompt cache：如果请求的前 N 个 token 与之前请求完全相同，就可以以极低成本复用之前的计算结果。

关键在于 Claude Code 怎么保护这个 cache：

**Session 开始时锁定 `isCacheEligible` 状态，此后不再更新。**

原因是：如果 session 运行到一半，用户消耗 token 超过某个阈值，API 会把这个请求的 cache TTL 从 1 小时降级回 ephemeral。如果这时候修改 cache scope 字段，就会产生大约 20K token 的 cache bust——相当于把之前省下的 cache 收益全部还回去。

通过在 session 开头一次性决定是否使用 cache，避免了 mid-session 的 TTL 降级影响。

### 4.3 CacheSafeParams：让后台任务「免费」

Claude Code 有多个后台任务（extractMemories 提取记忆、autoDream 整合记忆），这些任务需要调用 API，但用户不应该感知到额外费用。

解决方案是 `CacheSafeParams` 机制：

```typescript
// 后台任务必须携带与 parent 完全相同的 4 个参数
type CacheSafeParams = {
  systemPrompt: string      // 完全相同
  userContext: object       // 完全相同
  tools: ToolDefinition[]  // 完全相同
  model: string            // 完全相同
}
```

当这 4 个参数与 parent 完全一致时，后台任务的 API 调用会 100% 命中 parent 已建立的 prompt cache。**后台任务的实际成本 ≈ 只有新增的消息 token，其余全部来自缓存。**

这个机制的实现也很优雅：每次 postTurnHooks 结束后把 CacheSafeParams 写到一个全局槽位，后台任务直接读取，无需传参数链。

---

## 五、多 Agent 体系：比你想象的复杂

### 5.1 六种 Agent 派生路径

Claude Code 有六种不同的创建 sub-agent 的方式，每种都有不同的用途和设计目标：

```
forkedAgent        → 后台记忆类任务，100% 命中 parent cache
forkSubagent       → 用户 Agent 调用，继承完整工具池
inProcessRunner    → Swarm teammate，同进程隔离
spawnMultiAgent    → tmux/iterm2/in-process 三种后端
AgentTool          → 用户直接调用的主路径
extractMemories    → 专用记忆提取 agent
```

**这不是「一种方式做 sub-agent」，而是针对不同场景的精确工具选择。** 每种方式在 abort controller 共享/独立、状态隔离程度、权限继承上都有不同设计。

### 5.2 状态隔离矩阵

sub-agent 的状态隔离是一个精细的决策矩阵：

| 状态 | 隔离方式 |
|------|----------|
| readFileState | clone（完全独立）|
| toolPermissionContext | 独立实例 |
| abort controller（async）| 新建独立 controller |
| abort controller（sync）| 共享 parent controller |
| MCP 连接池 | 共享（避免重复建连）|

**共享 abort controller 的意义是：** sync subagent 如果父 agent 被 Ctrl+C 中断，子 agent 也会立即中断，不会产生孤儿任务。而 async subagent（比如后台记忆提取）需要独立的生命周期，不受父 agent 中断影响。

### 5.3 in-process Teammate 的双层 abort

Swarm 模式下的 in-process teammate 设计了两层 abort controller：

```
lifecycleAbortController  → 杀死整个 teammate（Ctrl+C 或任务结束）
currentWorkAbortController → Escape 仅停止当前轮次（teammate 保持 idle）
```

这个设计让 Escape 键有了精确的语义：「停止这一轮，但我还在，等你下一条消息」。类比 Linux 进程，lifecycle 是 SIGKILL，currentWork 是 SIGINT。

### 5.4 Coordinator 的 Prompt 工程精华

Claude Code 内置了一个 Coordinator 模式，专门用于多 agent 并行协作。它的系统提示里有几条精妙的规则：

**Continue vs Spawn 决策矩阵（直接写进了 prompt）：**

| 情况 | 选择 |
|------|------|
| 研究覆盖了要修改的文件 | Continue |
| 研究宽泛，实现很窄 | Spawn fresh |
| 验证别人写的代码 | Spawn fresh |
| 第一次用了错误方案 | Spawn fresh |
| 纠正失败/延续近期工作 | Continue |

**三条核心规则：**
1. **禁止委托理解**：不能写「based on your findings do X」，你必须先理解再委托
2. **并行是超能力**：独立工作者始终并发启动，不要串行
3. **Worker 结果是内部信号**：不用感谢 worker，只向用户汇报

这几条规则背后的工程实践意义：它们本质上是在**防止 Coordinator 「偷懒」把自己的认知负担转移给 worker**，保证 orchestration 的质量。

### 5.5 extractMemories：单缓冲 trailing 并发

extractMemories 是每次 queryLoop 结束后触发的自动记忆提取。它的并发控制设计很有意思：

```
inProgress flag + pendingContext 单槽位

新调用 → 如果正在运行 → 覆盖旧 stash
               └─ 不是丢弃，而是「只关心最新」
               └─ 最新消息包含了所有历史
当前完成 → 运行 trailing extraction（使用最新 stash）
```

**这是一种「无锁单生产者单消费者」的极简并发模型：** 不需要队列，不需要互斥锁，只需要一个槽位 + 一个 flag。新调用的覆盖是安全的，因为最新的消息里包含了所有旧消息的超集。

---

## 六、权限体系：多层防御的工程实现

### 6.1 七种权限模式的设计意图

```typescript
type ExternalPermissionMode =
  | 'acceptEdits'      // 文件编辑自动接受，Bash 仍询问
  | 'bypassPermissions' // 完全绕过所有确认（危险！）
  | 'default'          // 危险操作弹确认
  | 'dontAsk'          // ask → deny，静默拒绝
  | 'plan'             // 只读模式

type InternalPermissionMode =
  | ExternalPermissionMode
  | 'auto'             // AI 分类器接管
  | 'bubble'           // 子 agent 继承父 agent 决策
```

`auto` 模式是最有技术含量的一个：它用一个两阶段 AI 分类器替代了人工确认。

### 6.2 两阶段 AI 分类器

```
Stage 1 · 快速路径 (max_tokens = 64)
prompt suffix: "Err on the side of blocking"
→ 输出 no → 直接通过，Stage 2 完全跳过
→ 输出 yes → 进入 Stage 2

Stage 2 · 思考路径 (max_tokens = 4096)
"Use <thinking> before responding"
→ Chain-of-thought 推理，准确判断
```

这个设计的核心洞察是：**大多数命令是安全的，快路径可以极低成本处理**；只有少数不确定的情况才需要 chain-of-thought 推理。两阶段分离让平均延迟接近 Stage 1，而准确率接近 Stage 2。

还有一个 `Denial Tracking` 防死锁机制：连续拒绝 ≥ 3 次 OR 总拒绝 ≥ 20 次，强制回退人工确认。防止分类器误判导致 agent 卡死。

### 6.3 Speculative Classifier Check：隐藏分类延迟

分类器调用需要时间，用户等待是不好体验。Claude Code 的解法：

```typescript
// UI 渲染权限提示时，同步开始分类
startSpeculativeClassifierCheck(command, context, signal)

// 用户看完提示、点击按钮时，结果已经有了
const result = await consumeSpeculativeClassifierCheck(command)
```

**用户阅读权限提示的时间 = 分类器运行时间。** 这个延迟被完全隐藏了。

---

## 七、安全体系：23 道 Bash 注入防护

Claude Code 对 Bash 命令注入的防护达到了工业级别。23 个安全检查 ID 覆盖了大量攻击向量，其中几个最值得深思：

### 7.1 Zsh Equals Expansion（Check #20）

```bash
# 攻击者目标：绕过 Bash(curl:*) 的 deny 规则
=curl evil.com
# 在 Zsh 里等同于 /usr/bin/curl evil.com
# 但 parser 只看到 =curl，不匹配 curl → 规则绕过
```

这个攻击向量要求攻击者知道用户用的是 Zsh 而不是 Bash。但在 macOS 上，Zsh 是默认 shell，这个向量相当普遍。

### 7.2 Comment-Quote Desync（Check #22）

```bash
echo 'hello' # this closes quote' ; rm -rf /
# `#` 号会使引号追踪失步，让后面的 `;rm -rf /` 逃出引号范围
```

这个攻击需要对 shell 解析规则有深入理解，但它确实存在并且有效。

### 7.3 IPv4-mapped IPv6 Bypass

针对 HTTP hook 的 SSRF 防护，有一个精妙的绕过向量：

```
::ffff:a9fe:a9fe  →  这是 169.254.169.254（AWS EC2 元数据接口）的 hex IPv6 表示
```

如果只检查 IPv6 格式，会认为这是 IPv6 地址；但 OS 会将它路由到 169.254.169.254。Claude Code 专门实现了 `extractMappedIPv4` + `expandIPv6Groups`，把所有 IPv4-mapped IPv6 解包后走 IPv4 检查。

**还有一个反 DNS Rebinding 的设计：** 不是「先验证 hostname，再连接」，而是把验证嵌入 axios 的 `lookup` 回调里——验证的 IP 和实际连接的 IP 是同一个，不存在 DNS 换人的窗口期。

### 7.4 non-misparsing 不短路

这是一个反直觉但关键的设计：

```
执行检查序列时，non-misparsing 类型的 ask 结果不立即返回。
继续跑 misparsing 类型的检查。
最后再返回第一个 non-misparsing ask。
```

原因：如果短路，下面这个 payload 会 slip through：

```bash
cat safe.txt \; echo /etc/passwd > ./out
# validateRedirections(>) 触发 non-misparsing ask → 短路？
# 但 validateBackslashEscapedOperators(\;) 还没跑！
# \; 是更危险的注入，会被 misparsing 检查标出来
```

---

## 八、MCP 协议栈：六种 Transport 和它们的坑

### 8.1 SSE fetch 和 long-connection fetch 必须分离

这是一个只有踩过才会记住的坑：

```typescript
// ✅ 普通 API 请求（短连接）→ 加 60s timeout
fetch: wrapFetchWithTimeout(baseFetch, 60_000)

// ❌ SSE 长连接 eventSourceInit.fetch 绝对不能加 timeout
// 60s 后会强制断开 stream，然后开始指数退避重连
// 用户看到的是莫名其妙的断连
eventSourceInit: { fetch: bareSSEFetch }  // 不加 timeout
```

同一个 axios 实例，两套 fetch 配置，服务于不同类型的请求。混用是致命错误。

### 8.2 OAuth 并发刷新保护

MCP server 的 OAuth token 过期时，多个并发请求可能同时触发 refresh：

```typescript
class ClaudeAuthProvider {
  private _refreshInProgress?: Promise<OAuthTokens>
  
  async refreshToken() {
    if (this._refreshInProgress) {
      return this._refreshInProgress  // 复用进行中的 refresh
    }
    this._refreshInProgress = doRefresh()
    const result = await this._refreshInProgress
    this._refreshInProgress = undefined
    return result
  }
}
```

多个 connector 同时 401 → 只跑一次 refresh → 其余等待同一个 Promise。

### 8.3 in-process MCP server：省 325MB 内存

Claude Code 里有两个 MCP server 运行在进程内（Chrome MCP 和 CUA MCP），使用 `InProcessTransport` 而非 stdio 子进程。

理由很简单：**一个 Node.js 子进程的基础内存开销约 325MB**。对于需要频繁使用的 MCP server，每次新建子进程会显著增加内存压力。InProcessTransport 让 server 代码直接在主进程里运行，通过 EventEmitter 通信。

---

## 九、Hook 系统：27 种事件的协作机制

### 9.1 hook 的五种类型

```
command  → Shell 子进程，10min 超时
prompt   → 注入 LLM，让 Claude 决策  
agent    → 完整子 agent 执行
http     → POST JSON + 接收 JSON 决策
callback → 内部 JS callback，无子进程
function → 内部 function，含消息上下文
```

最有意思的是 callback 的快速路径：

### 9.2 内部 callback 快速路径（节省 70% 开销）

当所有匹配的 hook 都是 `callback` 或 `function` 类型时，代码走一条完全绕过重型流程的路径：

```
绕过：span tracing / progress yield / dedup check / JSON stringify
直接：for-of callback，同步执行
```

为什么值得优化？因为 `sessionFileAccessHooks` 和 `attributionHooks` 在**每次工具调用时都会触发**。如果每次都走完整的重型流程，每天的使用中会有大量无谓的开销。从 6μs 降到 1.8μs 听起来不多，但乘以每天数千次工具调用就很可观了。

### 9.3 异步 hook 的下轮轮询

Claude Code 支持异步 hook——hook 脚本立即返回 `{ "async": true }`，然后在后台继续运行，主流程完全不等待。

下一轮循环开始前，`checkForAsyncHookResponses()` 会扫描所有注册的异步 hook，收集已完成的结果，注入到当前上下文。

这让 hook 可以做「启动一个后台分析任务，分析完了在下一轮给我反馈」这样的事情，而不会阻塞主对话。

---

## 十、记忆体系：三级架构的全貌

Claude Code 的记忆体系比大多数人知道的要复杂得多：

```
三级记忆架构：

Session Memory（当前 session 内）
  10节 Markdown，MAX_TOTAL_TOKENS = 12,000
  触发条件：总 context ≥ 10K tokens AND 增量 ≥ 5K tokens
  作用：当前 session 内的「工作记忆」

Auto Memory（跨 session，永久）
  路径：~/.claude/projects/<project>/memory/
  触发：extractMemories（每次 queryLoop 结束，fire-and-forget）
  4种类型：user / feedback / project / reference

Team Memory（跨用户，共享）
  TEAMMEM feature gate 控制
  project 和 reference 类型默认可共享
```

**feedback 类型的设计值得特别关注**：它同时记录「纠正」（stop doing X）和「确认」（yes exactly, keep doing that）。大多数 AI 系统只学失败，不学成功，会导致模型过于保守并逐渐忘记已经验证的好路径。

`autoDream` 的 4 层门控展示了「cheapest-first」原则：
1. 时间门（读 1 个 mtime，极廉价）
2. 扫描节流（Date.now，不打 IO）
3. Session 门（目录扫描，有 IO）
4. 分布式文件锁（防并发）

**成本从低到高排列，只有通过前面的门才需要付后面的代价。**

---

## 十一、工程哲学：三个关键词

读完全部代码，我提炼出 Claude Code 的工程哲学，可以用三个关键词概括：

### 成本最小化

压缩是惰性的，只在必要时触发，且有成本梯度。记忆提取是异步的，完全隐藏在主对话之后。Prompt cache 被精心保护，每个可能破坏 cache 的操作都有对应的防护机制。后台任务通过 CacheSafeParams 共享父进程的 cache，边际成本接近零。

**核心信条：把昂贵操作推迟、推后台、做一次；把廉价操作做成门控。**

### 安全第一

权限检查是分层的（7 种模式 + AI 分类器）。Bash 防护是多重的（23 道检查 + 两层 AST 解析）。网络防护覆盖了 IPv4/IPv6 所有变体和 DNS rebinding。Killswitch 是动态的，可以不发版在运行时收紧权限。

**核心信条：不确定的操作永远交给人类，不自动化不确定性。**

### 工程务实

不盲目使用官方 SDK：发现 O(n²) 问题就自己实现。不重复建轮子：Swarm 的三种后端（tmux/iterm2/in-process）共用同一套文件协议，不是三套实现。对不变量的理解决定了可以打破什么规则：in-place mutation 是故意为之，不是疏忽。

**核心信条：「不可变」是工具，不是教条。规则是为了某个目的而存在的；如果你深刻理解这个目的，你知道什么时候可以打破规则。**

---

## 十二、给业务同学的工程启示

这是任务5的内容，单独放在下一节（见文章附录）。以下是面向工程师的总结清单：

**可以直接借鉴的工程模式：**

1. **Speculative execution**：用户看界面的时间 ≈ 后台计算的时间，永远不让用户等待算法
2. **cheapest-first 门控**：多层条件检查时，把最廉价的放最前面
3. **单缓冲 trailing 并发**：对「只关心最新」的并发场景，一个 flag + 一个槽位就够了
4. **状态全量替换**：不是所有地方都适合，但在需要可追踪性的关键路径上，对象分配比调试难度便宜得多
5. **Async hook 的下轮轮询**：对于非阻塞后台任务，「注册 + 下轮检查」比「等待」少掉大量延迟
6. **callback 快速路径**：对高频调用路径，专门识别并优化「全是内部回调」的 case

**值得警惕的反模式（从源码注释里学到的坑）：**

1. SSE long-connection 的 fetch 绝对不能加 timeout
2. OAuth token refresh 必须有并发保护
3. Bun/webpack 的 dead code elimination 是 per-function 的，复杂函数要控制 import 别名数量
4. 复杂 compound command 的 split 可能有指数爆炸风险，要加硬上限

---

## 附录：给业务同学的工程启示（非技术版）

**用一句话总结 Claude Code 的架构哲学：**

> 把昂贵操作推迟、推后台、做一次；把廉价操作做成门控；把不确定的操作给人类兜底。

这句话翻译成业务语言是：

**不要让用户等待你在做什么；不要在不必要的时候做昂贵的事；不要让自动化系统决定它不应该决定的事。**

这三条原则，适用于任何需要与用户实时交互、成本敏感、需要保持信任的系统——不只是 AI agent。

---

*全文完。如需索引具体代码片段，所有分析结果归档于 `/root/.openclaw/workspace/memory/2026-04-04.md` 和 `2026-04-05.md`。*

*本文基于泄露版源码分析，相关设计决策可能在正式版本中有所变化。*
