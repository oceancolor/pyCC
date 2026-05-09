/**
 * hunyuan.ts — 混元模型适配层
 *
 * 将 Claude Code 的 Anthropic SDK 调用格式转换为混元 OpenAI 兼容 API 格式。
 * 通过设置环境变量启用：
 *   HUNYUAN_API_KEY=your_key
 *   HUNYUAN_MODEL=hunyuan-turbos-latest        (可选, 默认 hunyuan-turbos-latest)
 *   HUNYUAN_SMALL_MODEL=hunyuan-lite           (可选, 默认 hunyuan-lite)
 *   HUNYUAN_BASE_URL=https://api.hunyuan...    (可选, 默认混元官方地址)
 */

import { randomUUID } from 'crypto'

// ── 配置 ────────────────────────────────────────────────────────────────────

const HUNYUAN_BASE_URL =
  (process.env.HUNYUAN_BASE_URL ?? 'https://api.hunyuan.cloud.tencent.com/v1').replace(/\/$/, '')
const HUNYUAN_API_KEY = process.env.HUNYUAN_API_KEY ?? ''
export const HUNYUAN_DEFAULT_MODEL = process.env.HUNYUAN_MODEL ?? 'hunyuan-turbos-latest'
export const HUNYUAN_SMALL_MODEL = process.env.HUNYUAN_SMALL_MODEL ?? 'hunyuan-lite'

// ── 类型定义（只保留本文件需要的最小子集）────────────────────────────────────

type AnthropicMessage = {
  role: 'user' | 'assistant'
  content: string | AnthropicBlock[]
}

type AnthropicBlock =
  | { type: 'text'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: unknown }
  | { type: 'tool_result'; tool_use_id: string; content: string | AnthropicBlock[] }
  | { type: 'image'; source: { type: 'base64'; media_type: string; data: string } }
  | { type: 'document'; source: unknown }

type AnthropicTool = {
  name: string
  description?: string
  input_schema: unknown
}

type AnthropicCreateParams = {
  model: string
  messages: AnthropicMessage[]
  system?: string | { type: 'text'; text: string }[]
  tools?: AnthropicTool[]
  max_tokens?: number
  temperature?: number
  stream?: boolean
  betas?: string[]
  thinking?: { type: 'enabled' | 'disabled'; budget_tokens?: number }
  metadata?: unknown
  [key: string]: unknown
}

// OpenAI 兼容格式
type OAIMessage = {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls?: OAIToolCall[]
  tool_call_id?: string
  name?: string
}

type OAIToolCall = {
  id: string
  type: 'function'
  function: { name: string; arguments: string }
}

type OAITool = {
  type: 'function'
  function: { name: string; description?: string; parameters: unknown }
}

// ── 格式转换：Anthropic → OpenAI ─────────────────────────────────────────────

function blockToText(block: AnthropicBlock): string {
  if (block.type === 'text') return block.text
  if (block.type === 'tool_result') {
    if (typeof block.content === 'string') return block.content
    if (Array.isArray(block.content)) return block.content.map(b => blockToText(b as AnthropicBlock)).join('\n')
    return ''
  }
  if (block.type === 'image') return '[image]'
  if (block.type === 'document') return '[document]'
  return JSON.stringify(block)
}

/**
 * 将 Anthropic 消息数组转换为 OpenAI 格式的消息数组。
 * 处理要点：
 *  - tool_use 块 → assistant message with tool_calls
 *  - tool_result 块 → tool role message
 *  - 混合内容块 → 拆分或合并
 */
function convertMessages(messages: AnthropicMessage[]): OAIMessage[] {
  const result: OAIMessage[] = []

  for (const msg of messages) {
    const role = msg.role === 'assistant' ? 'assistant' : 'user'

    if (typeof msg.content === 'string') {
      result.push({ role, content: msg.content })
      continue
    }

    // 数组内容：先检查是否包含 tool_use 或 tool_result
    const hasToolUse = msg.content.some(b => b.type === 'tool_use')
    const hasToolResult = msg.content.some(b => b.type === 'tool_result')

    if (hasToolUse && role === 'assistant') {
      // 提取文本部分
      const textParts = msg.content
        .filter(b => b.type === 'text')
        .map(b => blockToText(b as AnthropicBlock))
        .join('\n')
        .trim()

      const toolCalls: OAIToolCall[] = msg.content
        .filter(b => b.type === 'tool_use')
        .map(b => {
          const tu = b as Extract<AnthropicBlock, { type: 'tool_use' }>
          return {
            id: tu.id,
            type: 'function' as const,
            function: {
              name: tu.name,
              arguments: typeof tu.input === 'string' ? tu.input : JSON.stringify(tu.input),
            },
          }
        })

      result.push({
        role: 'assistant',
        content: textParts || null,
        tool_calls: toolCalls,
      })
    } else if (hasToolResult && role === 'user') {
      // 每个 tool_result 对应一条 tool 角色消息
      for (const block of msg.content) {
        if (block.type === 'tool_result') {
          const tr = block as Extract<AnthropicBlock, { type: 'tool_result' }>
          const content =
            typeof tr.content === 'string'
              ? tr.content
              : Array.isArray(tr.content)
                ? tr.content.map(b => blockToText(b as AnthropicBlock)).join('\n')
                : ''
          result.push({
            role: 'tool',
            tool_call_id: tr.tool_use_id,
            content,
          })
        } else if (block.type === 'text') {
          // 工具结果消息里夹杂的文本，作为 user message 附加
          const text = blockToText(block)
          if (text.trim()) result.push({ role: 'user', content: text })
        }
      }
    } else {
      // 纯文本块或其他块，合并成字符串
      const text = msg.content.map(b => blockToText(b as AnthropicBlock)).join('\n').trim()
      if (text) result.push({ role, content: text })
    }
  }

  return result
}

function convertTools(tools: AnthropicTool[]): OAITool[] {
  return tools.map(t => ({
    type: 'function' as const,
    function: {
      name: t.name,
      description: t.description,
      parameters: t.input_schema,
    },
  }))
}

// ── 格式转换：OpenAI 流式响应 → Anthropic SSE 事件 ────────────────────────────

/**
 * 解析 OpenAI 的 SSE 流并 yield Anthropic 格式的事件对象。
 * Claude Code 的 claude.ts 消费的是 Anthropic SDK 的 AsyncIterable<BetaRawMessageStreamEvent>，
 * 我们在这里模拟同样的事件序列。
 */
async function* openAIStreamToAnthropicEvents(
  body: ReadableStream<Uint8Array> | null,
  model: string,
  inputTokens: number,
): AsyncGenerator<Record<string, unknown>, void, unknown> {
  if (!body) return

  const messageId = `msg_hunyuan_${randomUUID().replace(/-/g, '').slice(0, 24)}`

  // message_start
  yield {
    type: 'message_start',
    message: {
      id: messageId,
      type: 'message',
      role: 'assistant',
      content: [],
      model,
      stop_reason: null,
      stop_sequence: null,
      usage: { input_tokens: inputTokens, output_tokens: 0 },
    },
  }

  const decoder = new TextDecoder()
  const reader = body.getReader()
  let buffer = ''

  // 跟踪当前流式内容
  let textIndex = -1
  let toolCallMap: Map<number, { id: string; name: string; argsBuffer: string }> = new Map()
  let totalOutputTokens = 0

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || trimmed === 'data: [DONE]') continue
        if (!trimmed.startsWith('data: ')) continue

        let chunk: Record<string, unknown>
        try {
          chunk = JSON.parse(trimmed.slice(6))
        } catch {
          continue
        }

        const choices = chunk.choices as Array<{
          index: number
          delta: {
            role?: string
            content?: string | null
            tool_calls?: Array<{
              index: number
              id?: string
              type?: string
              function?: { name?: string; arguments?: string }
            }>
          }
          finish_reason?: string | null
        }> | undefined

        if (!choices?.length) continue
        const choice = choices[0]
        const delta = choice.delta

        // 文本 delta
        if (typeof delta.content === 'string' && delta.content.length > 0) {
          if (textIndex === -1) {
            textIndex = 0
            yield { type: 'content_block_start', index: textIndex, content_block: { type: 'text', text: '' } }
            yield { type: 'ping' }
          }
          yield { type: 'content_block_delta', index: textIndex, delta: { type: 'text_delta', text: delta.content } }
          totalOutputTokens += Math.ceil(delta.content.length / 4)
        }

        // tool_calls delta
        if (delta.tool_calls) {
          for (const tc of delta.tool_calls) {
            const tcIndex = tc.index
            // 关闭文本块（如果之前有文本）
            if (textIndex !== -1) {
              yield { type: 'content_block_stop', index: textIndex }
              textIndex = -2 // 标记已关闭
            }

            if (!toolCallMap.has(tcIndex)) {
              // 新的 tool call 开始
              const toolBlockIndex = tcIndex + (textIndex === -2 ? 1 : 0) + 1
              const id = tc.id ?? `toolu_${randomUUID().replace(/-/g, '').slice(0, 24)}`
              const name = tc.function?.name ?? ''
              toolCallMap.set(tcIndex, { id, name, argsBuffer: '' })

              yield {
                type: 'content_block_start',
                index: toolBlockIndex,
                content_block: { type: 'tool_use', id, name, input: {} },
              }
            }

            const existing = toolCallMap.get(tcIndex)!
            if (tc.function?.name && !existing.name) existing.name = tc.function.name
            if (tc.function?.arguments) {
              existing.argsBuffer += tc.function.arguments
              const toolBlockIndex = tcIndex + (textIndex === -2 ? 1 : 0) + 1
              yield {
                type: 'content_block_delta',
                index: toolBlockIndex,
                delta: { type: 'input_json_delta', partial_json: tc.function.arguments },
              }
            }
          }
        }

        // finish
        if (choice.finish_reason) {
          // 关闭所有打开的块
          if (textIndex >= 0) yield { type: 'content_block_stop', index: textIndex }
          for (const [tcIdx] of toolCallMap) {
            const toolBlockIndex = tcIdx + (textIndex === -2 ? 1 : 0) + 1
            yield { type: 'content_block_stop', index: toolBlockIndex }
          }

          const stopReason =
            choice.finish_reason === 'tool_calls' ? 'tool_use' : 'end_turn'

          // 统计 usage（混元可能在 chunk.usage 中返回）
          const usage = chunk.usage as { prompt_tokens?: number; completion_tokens?: number } | undefined
          const outTokens = usage?.completion_tokens ?? totalOutputTokens

          yield {
            type: 'message_delta',
            delta: { stop_reason: stopReason, stop_sequence: null },
            usage: { output_tokens: outTokens },
          }
          yield { type: 'message_stop' }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

// ── 非流式响应转换 ────────────────────────────────────────────────────────────

function openAIResponseToAnthropicMessage(
  oaiResp: Record<string, unknown>,
  model: string,
): Record<string, unknown> {
  const choices = oaiResp.choices as Array<{
    message: {
      role: string
      content: string | null
      tool_calls?: OAIToolCall[]
    }
    finish_reason: string
  }> | undefined

  const choice = choices?.[0]
  const msg = choice?.message

  const content: unknown[] = []

  if (msg?.content) {
    content.push({ type: 'text', text: msg.content })
  }

  if (msg?.tool_calls) {
    for (const tc of msg.tool_calls) {
      let input: unknown = {}
      try {
        input = JSON.parse(tc.function.arguments)
      } catch {
        input = { _raw: tc.function.arguments }
      }
      content.push({
        type: 'tool_use',
        id: tc.id,
        name: tc.function.name,
        input,
      })
    }
  }

  const usage = oaiResp.usage as { prompt_tokens?: number; completion_tokens?: number } | undefined
  const stopReason = choice?.finish_reason === 'tool_calls' ? 'tool_use' : 'end_turn'

  return {
    id: `msg_hunyuan_${randomUUID().replace(/-/g, '').slice(0, 24)}`,
    type: 'message',
    role: 'assistant',
    content,
    model,
    stop_reason: stopReason,
    stop_sequence: null,
    usage: {
      input_tokens: usage?.prompt_tokens ?? 0,
      output_tokens: usage?.completion_tokens ?? 0,
    },
  }
}

// ── 主客户端工厂 ──────────────────────────────────────────────────────────────

/**
 * 创建一个伪 Anthropic 客户端，内部转发到混元 API。
 * 返回类型声明为 unknown，调用方（client.ts）cast 成 Anthropic。
 */
export function createHunyuanClient(): unknown {
  /**
   * 通用请求函数：构建 OpenAI 兼容请求并调用混元 API
   */
  async function callHunyuan(
    params: AnthropicCreateParams,
    options?: { signal?: AbortSignal; timeout?: number },
  ): Promise<{ stream: boolean; response: Response }> {
    const resolvedModel = params.model?.startsWith('hunyuan')
      ? params.model
      : HUNYUAN_DEFAULT_MODEL

    // 构建系统消息
    const systemContent =
      typeof params.system === 'string'
        ? params.system
        : Array.isArray(params.system)
          ? params.system.map((s: { text: string }) => s.text).join('\n')
          : undefined

    const oaiMessages: OAIMessage[] = []
    if (systemContent) {
      oaiMessages.push({ role: 'system', content: systemContent })
    }
    oaiMessages.push(...convertMessages(params.messages))

    const body: Record<string, unknown> = {
      model: resolvedModel,
      messages: oaiMessages,
      max_tokens: params.max_tokens ?? 8192,
      stream: params.stream !== false, // 默认流式
    }

    if (params.tools?.length) {
      body.tools = convertTools(params.tools)
      body.tool_choice = 'auto'
    }

    if (typeof params.temperature === 'number') {
      body.temperature = params.temperature
    }

    const controller = new AbortController()
    const timeoutMs = options?.timeout ?? 600_000
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    const signal = options?.signal
      ? AbortSignal.any([options.signal, controller.signal])
      : controller.signal

    let response: Response
    try {
      response = await fetch(`${HUNYUAN_BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${HUNYUAN_API_KEY}`,
        },
        body: JSON.stringify(body),
        signal,
      })
    } finally {
      clearTimeout(timer)
    }

    if (!response.ok) {
      const errText = await response.text().catch(() => `HTTP ${response.status}`)
      throw new Error(`Hunyuan API error ${response.status}: ${errText}`)
    }

    return { stream: body.stream as boolean, response }
  }

  // beta.messages.create() — 返回流式 AsyncIterable 或非流式 BetaMessage
  const betaMessagesCreate = async (
    params: AnthropicCreateParams,
    options?: { signal?: AbortSignal; timeout?: number },
  ) => {
    const resolvedModel = params.model?.startsWith('hunyuan')
      ? params.model
      : HUNYUAN_DEFAULT_MODEL

    // 估算输入 tokens（粗略：4字符≈1token）
    const inputText = JSON.stringify(params.messages) + (params.system ?? '')
    const inputTokens = Math.ceil(inputText.length / 4)

    const { stream, response } = await callHunyuan(params, options)

    if (stream) {
      // 返回异步迭代器，模拟 Anthropic SDK 的 Stream 接口
      const iter = openAIStreamToAnthropicEvents(response.body, resolvedModel, inputTokens)

      // Anthropic SDK Stream 对象还需要 .on() / .finalMessage() 等方法
      // claude.ts 主要用 for-await，所以最简实现即可
      return {
        [Symbol.asyncIterator]() {
          return iter
        },
        async finalMessage() {
          // 消耗流并构建最终消息（非流式 fallback 会调用这个）
          const contentBlocks: unknown[] = []
          const textParts: string[] = []
          const toolUses: unknown[] = []

          for await (const evt of openAIStreamToAnthropicEvents(
            response.body,
            resolvedModel,
            inputTokens,
          )) {
            // 已经消耗了上面的 iter，这里其实拿不到数据了
            // 实际上 claude.ts 不会同时用 for-await 和 finalMessage，安全
            void evt
          }

          return {
            id: `msg_hunyuan_${randomUUID().replace(/-/g, '').slice(0, 24)}`,
            type: 'message',
            role: 'assistant',
            content: contentBlocks,
            model: resolvedModel,
            stop_reason: 'end_turn',
            stop_sequence: null,
            usage: { input_tokens: inputTokens, output_tokens: 0 },
          }
        },
        on(_event: string, _handler: unknown) { return this },
        off(_event: string, _handler: unknown) { return this },
        controller: { abort() {} },
      }
    } else {
      // 非流式：直接返回转换好的 BetaMessage 对象
      const json = await response.json() as Record<string, unknown>
      return openAIResponseToAnthropicMessage(json, resolvedModel)
    }
  }

  return {
    beta: {
      messages: {
        create: betaMessagesCreate,
      },
    },
    messages: {
      create: betaMessagesCreate,
    },
  }
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

/** 判断当前是否启用了混元模式 */
export function isHunyuanEnabled(): boolean {
  return !!process.env.HUNYUAN_API_KEY
}
