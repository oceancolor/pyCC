# 原始 TS: ink/repl (React/Ink REPL → prompt_toolkit)
"""
Interactive REPL for Claude Code Python.
使用 prompt_toolkit 实现多行输入、历史记录、快捷键。
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Optional, List, Dict, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings

from .state.session_state import SessionState
from .context import AgentContext, set_context
from .utils.session_storage import SessionRecord, save_session, append_message
from .utils.cost import format_cost
from .utils.tokens import estimate_messages_tokens, is_context_near_limit

# ── ANSI 颜色常量 ───────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"

# ── 内置 REPL 命令 ──────────────────────────────────────────────
BUILTIN_COMMANDS = {
    "/help":    "显示帮助信息",
    "/clear":   "清除对话历史",
    "/status":  "显示当前 session 状态",
    "/cost":    "显示 token 用量和费用",
    "/compact": "压缩对话历史（保留最近10条）",
    "/model":   "切换模型（用法：/model claude-opus-4-5）",
    "/exit":    "退出",
    "/quit":    "退出",
}

PROMPT_STYLE = Style.from_dict({
    "prompt":     "ansicyan bold",
    "rprompt":    "ansiblue",
})


def _make_toolbar(ctx: AgentContext):
    """底部状态栏"""
    s = ctx.session
    tokens = s.total_tokens
    elapsed = int(s.elapsed_seconds)
    cost_str = format_cost(s.input_tokens, s.output_tokens, s.model) if hasattr(s, 'model') else ""
    warn = " ⚠️  context 接近上限" if is_context_near_limit(tokens) else ""
    return HTML(
        f" 🦀 <ansiblue>{s.model}</ansiblue>"
        f" | tokens: <ansigreen>{tokens:,}</ansigreen>"
        f" | {elapsed}s"
        f"{(' | ' + cost_str) if cost_str else ''}"
        f"<ansiyellow>{warn}</ansiyellow>"
    )


def _print_welcome(model: str) -> None:
    print(f"\n{CYAN}{BOLD}Claude Code{RESET} {DIM}(Python port){RESET}")
    print(f"{DIM}Model: {model} | /help for commands | Ctrl+C to abort | /exit to quit{RESET}\n")


def _print_help() -> None:
    print(f"\n{BOLD}内置命令：{RESET}")
    for cmd, desc in BUILTIN_COMMANDS.items():
        print(f"  {CYAN}{cmd:<12}{RESET} {desc}")
    print(f"\n{DIM}多行输入：行尾加 \\ 或输入空行继续{RESET}\n")


def _handle_builtin(cmd: str, ctx: AgentContext) -> bool:
    """处理 / 命令，返回 True 表示已处理"""
    parts = cmd.strip().split(maxsplit=1)
    verb = parts[0].lower()

    if verb in ("/exit", "/quit"):
        print(f"\n{DIM}Goodbye 👋{RESET}\n")
        sys.exit(0)

    if verb == "/help":
        _print_help()
        return True

    if verb == "/clear":
        ctx.session.messages.clear()
        ctx.session.input_tokens = 0
        ctx.session.output_tokens = 0
        ctx.session.iteration = 0
        print(f"{GREEN}✓ 对话历史已清除{RESET}")
        return True

    if verb == "/status":
        s = ctx.session
        print(f"\n{BOLD}Session 状态{RESET}")
        print(f"  model:    {s.model}")
        print(f"  messages: {len(s.messages)}")
        print(f"  tokens:   in={s.input_tokens:,}  out={s.output_tokens:,}")
        print(f"  elapsed:  {int(s.elapsed_seconds)}s")
        print(f"  iter:     {s.iteration}")
        print()
        return True

    if verb == "/cost":
        s = ctx.session
        cost = format_cost(s.input_tokens, s.output_tokens, s.model)
        print(f"\n  input:  {s.input_tokens:,} tokens")
        print(f"  output: {s.output_tokens:,} tokens")
        print(f"  cost:   {cost}\n")
        return True

    if verb == "/compact":
        from .utils.compact import compact_messages
        before = len(ctx.session.messages)
        ctx.session.messages = compact_messages(ctx.session.messages)
        after = len(ctx.session.messages)
        print(f"{GREEN}✓ 压缩完成：{before} → {after} 条消息{RESET}")
        return True

    if verb == "/model":
        if len(parts) > 1:
            ctx.session.model = parts[1].strip()
            print(f"{GREEN}✓ 切换到模型：{ctx.session.model}{RESET}")
        else:
            print(f"当前模型：{ctx.session.model}")
        return True

    return False


async def _run_turn(user_input: str, ctx: AgentContext) -> str:
    """执行一轮对话，返回 assistant 回复文本"""
    import anthropic

    ctx.session.add_message("user", user_input)
    ctx.session.iteration += 1

    # 构建工具列表
    tools_json = []
    for tool in ctx.tools:
        if hasattr(tool, "input_schema"):
            tools_json.append({
                "name": tool.name,
                "description": getattr(tool, "description", ""),
                "input_schema": tool.input_schema(),
            })

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    messages_api = [
        {"role": m["role"], "content": m["content"]}
        for m in ctx.session.messages
        if m["role"] in ("user", "assistant")
    ]

    kwargs: Dict[str, Any] = {
        "model": ctx.session.model,
        "max_tokens": 8192,
        "messages": messages_api,
    }
    if ctx.session.system_prompt:
        kwargs["system"] = ctx.session.system_prompt
    if tools_json:
        kwargs["tools"] = tools_json

    # 流式输出
    full_text = ""
    tool_uses = []

    print(f"\n{CYAN}●{RESET} ", end="", flush=True)

    with client.messages.stream(**kwargs) as stream:
        for event in stream:
            if hasattr(event, "type"):
                if event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "text"):
                        print(delta.text, end="", flush=True)
                        full_text += delta.text
                elif event.type == "content_block_start":
                    block = event.content_block
                    if hasattr(block, "type") and block.type == "tool_use":
                        tool_uses.append({
                            "id": block.id,
                            "name": block.name,
                            "input": {},
                        })
                elif event.type == "input_json_delta":
                    # tool input streaming
                    pass

        final = stream.get_final_message()

    print()  # 换行

    # 更新 usage
    if hasattr(final, "usage"):
        ctx.session.update_usage(
            final.usage.input_tokens,
            final.usage.output_tokens,
        )

    # 处理 tool_use（简化版，执行后回传结果）
    if final.stop_reason == "tool_use" and ctx.tools:
        tool_results = []
        for block in final.content:
            if hasattr(block, "type") and block.type == "tool_use":
                tool = ctx.get_tool(block.name)
                if tool:
                    print(f"\n{YELLOW}⚙ 调用工具：{block.name}{RESET}")
                    try:
                        result = await tool.call(block.input, None)
                        result_text = str(result) if not isinstance(result, str) else result
                    except Exception as e:
                        result_text = f"Error: {e}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })
                    print(f"{DIM}{result_text[:200]}{'...' if len(result_text) > 200 else ''}{RESET}")

        if tool_results:
            # 追加 assistant 消息 + tool_result，继续对话
            ctx.session.add_message("assistant", [b.__dict__ for b in final.content])
            ctx.session.add_message("user", tool_results)
            return await _run_turn("", ctx)  # 递归继续（空 user input 表示 tool 回传）

    # 正常结束：保存 assistant 消息
    ctx.session.add_message("assistant", full_text or "[no text response]")
    return full_text


async def run_repl(
    model: str = "claude-opus-4-5",
    system_prompt: Optional[str] = None,
    debug: bool = False,
) -> None:
    """启动交互式 REPL"""
    import uuid

    # 初始化 session 和 context
    session = SessionState(
        session_id=str(uuid.uuid4()),
        model=model,
        system_prompt=system_prompt,
        cwd=os.getcwd(),
    )
    ctx = AgentContext(session=session)
    set_context(ctx)

    # 注册工具
    from .tools.tool_registry import build_default_registry
    registry = build_default_registry()
    ctx.tools = registry.all_tools()

    _print_welcome(model)

    # 历史文件
    history_path = os.path.expanduser("~/.claude/repl_history")
    os.makedirs(os.path.dirname(history_path), exist_ok=True)

    prompt_session: PromptSession = PromptSession(
        history=FileHistory(history_path),
        auto_suggest=AutoSuggestFromHistory(),
        style=PROMPT_STYLE,
        bottom_toolbar=lambda: _make_toolbar(ctx),
        mouse_support=False,
    )

    while True:
        try:
            user_input = await prompt_session.prompt_async(
                HTML("<prompt>❯ </prompt>"),
            )
        except KeyboardInterrupt:
            print(f"\n{DIM}(Ctrl+C — 输入 /exit 退出){RESET}")
            continue
        except EOFError:
            print(f"\n{DIM}EOF — 退出{RESET}\n")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # 内置命令
        if user_input.startswith("/"):
            _handle_builtin(user_input, ctx)
            continue

        # 调用模型
        try:
            await _run_turn(user_input, ctx)
            print()
        except KeyboardInterrupt:
            print(f"\n{YELLOW}⚠ 已中止{RESET}")
        except Exception as e:
            print(f"\n{RED}✗ 错误：{e}{RESET}")
            if debug:
                import traceback
                traceback.print_exc()
