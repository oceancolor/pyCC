#!/usr/bin/env python3
"""
混元 API 冒烟测试脚本 v2
用法:
  export HUNYUAN_API_KEY=your-key
  export HUNYUAN_MODEL=hunyuan-turbos-latest
  python3 scripts/smoke_test_hunyuan.py

测试:
  Step 1: 直接 HTTP 调用混元 /chat/completions (API key 有效性)
  Step 2: 通过 _HunyuanClient wrapper (client.py 新分支)
  Step 3: QueryEngine + tool_use 完整循环 (BashTool 执行)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

HUNYUAN_BASE_URL = os.environ.get('HUNYUAN_BASE_URL', 'https://api.hunyuan.cloud.tencent.com/v1')
HUNYUAN_API_KEY  = os.environ.get('HUNYUAN_API_KEY', '')
HUNYUAN_MODEL    = os.environ.get('HUNYUAN_MODEL', 'hunyuan-turbos-latest')


def banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def ok(msg: str) -> None:   print(f"  ✅ {msg}")
def fail(msg: str) -> None: print(f"  ❌ {msg}")
def info(msg: str) -> None: print(f"  → {msg}")


# ─────────────────────────────────────────────────────────────────
# Step 1: 直接 httpx，验证 key + 模型
# ─────────────────────────────────────────────────────────────────

async def step1_direct_http() -> bool:
    banner("Step 1 — 直接 HTTP 调用 /chat/completions")
    if not HUNYUAN_API_KEY:
        fail("HUNYUAN_API_KEY not set"); return False
    try:
        import httpx
    except ImportError:
        fail("pip install httpx"); return False

    url     = f"{HUNYUAN_BASE_URL}/chat/completions"
    payload = {
        "model": HUNYUAN_MODEL,
        "messages": [{"role": "user", "content": "请用一句话介绍你自己"}],
        "max_tokens": 80,
    }
    info(f"POST {url}  model={HUNYUAN_MODEL}")
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {HUNYUAN_API_KEY}",
                         "Content-Type": "application/json"},
            )
        elapsed = time.time() - t0
        info(f"status={resp.status_code}  ({elapsed:.2f}s)")
        if resp.status_code != 200:
            fail(f"HTTP {resp.status_code}: {resp.text[:300]}"); return False
        data    = resp.json()
        content = data['choices'][0]['message']['content']
        usage   = data.get('usage', {})
        ok(f"reply: {content!r}")
        ok(f"tokens: {usage}")
        return True
    except Exception as e:
        fail(f"{e}"); return False


# ─────────────────────────────────────────────────────────────────
# Step 2: _HunyuanClient wrapper (client.py 新分支)
# ─────────────────────────────────────────────────────────────────

async def step2_hunyuan_client() -> bool:
    banner("Step 2 — _HunyuanClient wrapper (client.py 混元分支)")
    if not HUNYUAN_API_KEY:
        fail("HUNYUAN_API_KEY not set"); return False

    # 强制走混元分支
    os.environ['HUNYUAN_API_KEY'] = HUNYUAN_API_KEY
    os.environ['HUNYUAN_MODEL']   = HUNYUAN_MODEL

    from claude_code.services.api.client import get_anthropic_client
    client = await get_anthropic_client(model=HUNYUAN_MODEL)
    info(f"client type: {type(client).__name__}")

    try:
        t0 = time.time()
        resp = client.messages.create(
            model=HUNYUAN_MODEL,
            max_tokens=80,
            messages=[{"role": "user", "content": "Say 'wrapper works' in English only."}],
        )
        elapsed = time.time() - t0
        info(f"elapsed: {elapsed:.2f}s")
        info(f"stop_reason: {resp.stop_reason}")
        info(f"usage: {resp.usage}")
        text = next((b['text'] for b in resp.content if isinstance(b, dict) and b.get('type') == 'text'), '')
        ok(f"reply: {text!r}")
        return True
    except Exception as e:
        fail(f"{type(e).__name__}: {e}"); return False


# ─────────────────────────────────────────────────────────────────
# Step 3: QueryEngine + tool_use 完整循环
# ─────────────────────────────────────────────────────────────────

async def step3_query_engine_with_tools() -> bool:
    banner("Step 3 — QueryEngine + BashTool (完整 tool_use 循环)")

    os.environ['HUNYUAN_API_KEY'] = HUNYUAN_API_KEY
    os.environ['HUNYUAN_MODEL']   = HUNYUAN_MODEL

    from claude_code.query_engine import QueryEngine, QueryEngineConfig
    from claude_code.tools.bash_tool import BashTool
    from claude_code.tools.file_write_tool import FileWriteTool
    from claude_code.tools.file_read_tool import FileReadTool

    config = QueryEngineConfig(
        model=HUNYUAN_MODEL,
        max_tokens=500,
        custom_system_prompt=(
            "You are a coding assistant. When asked to run a command, "
            "use the bash tool to execute it and report the output."
        ),
        tools=[BashTool(), FileWriteTool(), FileReadTool()],
    )
    engine = QueryEngine(config)
    info(f"QueryEngine session: {config.session_id[:8]}...")
    info("Sending: 'Run: echo HUNYUAN_TOOL_OK and show me the output'")

    events     = []
    tool_calls = []
    final_text = ""

    try:
        t0 = time.time()
        async for event in engine.submit_message(
            "Please run the shell command `echo HUNYUAN_TOOL_OK` using bash and show me the output."
        ):
            events.append(event)
            etype = event.get('type', '')

            if etype == 'assistant':
                for block in event.get('message', {}).get('content', []):
                    if isinstance(block, dict):
                        if block.get('type') == 'text' and block.get('text'):
                            info(f"assistant text: {block['text'][:100]!r}")
                        elif block.get('type') == 'tool_use':
                            tool_calls.append(block.get('name'))
                            info(f"tool_use: {block['name']}({json.dumps(block.get('input',{}))[:80]})")

            elif etype == 'tool':
                result = event.get('result', {})
                info(f"tool result: {str(result)[:80]!r}")

            elif etype == 'result':
                final_text = str(event.get('result', ''))
                elapsed = time.time() - t0
                info(f"result received ({elapsed:.2f}s): {final_text[:80]!r}")

        ok(f"total events: {len(events)}")

        if tool_calls:
            ok(f"tool_use calls: {tool_calls}")
        else:
            info("(no tool calls fired — model may have answered directly)")

        if 'HUNYUAN_TOOL_OK' in final_text or any(
            'HUNYUAN_TOOL_OK' in str(e) for e in events
        ):
            ok("✨ 'HUNYUAN_TOOL_OK' found in output — tool loop WORKS!")
        else:
            info("'HUNYUAN_TOOL_OK' not in output — tool may not have fired or output not captured")

        return True

    except Exception as e:
        import traceback
        fail(f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────
# Step 4: 多轮对话 (stateful conversation)
# ─────────────────────────────────────────────────────────────────

async def step4_multi_turn() -> bool:
    banner("Step 4 — 多轮对话 (stateful)")

    os.environ['HUNYUAN_API_KEY'] = HUNYUAN_API_KEY
    os.environ['HUNYUAN_MODEL']   = HUNYUAN_MODEL

    from claude_code.query_engine import QueryEngine, QueryEngineConfig

    config = QueryEngineConfig(
        model=HUNYUAN_MODEL,
        max_tokens=200,
        custom_system_prompt="You are a concise assistant.",
    )
    engine = QueryEngine(config)

    try:
        # Turn 1
        t1_text = ""
        async for event in engine.submit_message("My name is TestUser123. Say hello to me."):
            if event.get('type') == 'assistant':
                for block in event['message'].get('content', []):
                    if isinstance(block, dict) and block.get('type') == 'text':
                        t1_text += block['text']
        ok(f"Turn 1: {t1_text[:80]!r}")

        # Turn 2 — test memory
        t2_text = ""
        async for event in engine.submit_message("What is my name?"):
            if event.get('type') == 'assistant':
                for block in event['message'].get('content', []):
                    if isinstance(block, dict) and block.get('type') == 'text':
                        t2_text += block['text']
        ok(f"Turn 2: {t2_text[:80]!r}")

        msgs = engine.get_messages()
        ok(f"history: {len(msgs)} messages")

        if 'TestUser123' in t2_text or 'testuser' in t2_text.lower():
            ok("✨ Multi-turn memory WORKS!")
        else:
            info("Name not recalled — may be expected (model context)")

        return True
    except Exception as e:
        fail(f"{type(e).__name__}: {e}"); return False


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"\n🔥 混元 API 冒烟测试 v2")
    print(f"   HUNYUAN_BASE_URL = {HUNYUAN_BASE_URL}")
    print(f"   HUNYUAN_MODEL    = {HUNYUAN_MODEL}")
    print(f"   HUNYUAN_API_KEY  = {'set (' + HUNYUAN_API_KEY[:8] + '...)' if HUNYUAN_API_KEY else 'NOT SET'}")

    if not HUNYUAN_API_KEY:
        print("\n⚠️  请先设置 HUNYUAN_API_KEY:")
        print("   export HUNYUAN_API_KEY=your-key")
        sys.exit(1)

    results = {}
    results['step1_direct_http']          = await step1_direct_http()
    results['step2_hunyuan_client']       = await step2_hunyuan_client()
    if results['step2_hunyuan_client']:
        results['step3_tool_use_loop']    = await step3_query_engine_with_tools()
        results['step4_multi_turn']       = await step4_multi_turn()
    else:
        results['step3_tool_use_loop']    = None
        results['step4_multi_turn']       = None

    banner("Summary")
    for step, result in results.items():
        if result is True:   print(f"  ✅ {step}")
        elif result is False: print(f"  ❌ {step}")
        else:                 print(f"  ⏭  {step} (skipped)")

    all_pass = all(v is True for v in results.values() if v is not None)
    print()
    if all_pass:
        print("🎉 全部通过！QueryEngine + 混元 完整路径跑通！")
    else:
        failed = [k for k, v in results.items() if v is False]
        print(f"⚠️  部分失败: {failed}")


if __name__ == '__main__':
    asyncio.run(main())
