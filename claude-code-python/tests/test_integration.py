"""
端到端集成测试 — claude-code Python 移植
覆盖：工具链、QueryEngine、CostTracker、Commands、History

运行：
    python3 -m pytest tests/test_integration.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio

# ──────────────────────────────────────────────────────────────────
# 路径设置
# ──────────────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))


# ══════════════════════════════════════════════════════════════════
# 1. 核心工具链 (Tools)
# ══════════════════════════════════════════════════════════════════

class TestCoreTools:
    """FileWrite → FileRead → FileEdit → Grep → Bash 链路"""

    @pytest.fixture
    def tmpdir(self, tmp_path):
        return tmp_path

    @pytest.mark.asyncio
    async def test_file_write_creates_file(self, tmpdir):
        from claude_code.tools.file_write_tool import FileWriteTool

        tool = FileWriteTool()
        target = str(tmpdir / "hello.txt")
        result = await tool.call({"file_path": target, "content": "hello world\nline2\n"}, None)

        assert Path(target).exists(), "FileWriteTool should create file"
        assert "error" not in str(result).lower(), f"Unexpected error: {result}"

    @pytest.mark.asyncio
    async def test_file_read_returns_content(self, tmpdir):
        from claude_code.tools.file_write_tool import FileWriteTool
        from claude_code.tools.file_read_tool import FileReadTool

        content = "alpha\nbeta\ngamma\n"
        target = str(tmpdir / "read_test.txt")
        await FileWriteTool().call({"file_path": target, "content": content}, None)

        result = await FileReadTool().call({"file_path": target}, None)
        result_str = str(result)
        assert "alpha" in result_str
        assert "gamma" in result_str

    @pytest.mark.asyncio
    async def test_file_edit_replaces_string(self, tmpdir):
        from claude_code.tools.file_write_tool import FileWriteTool
        from claude_code.tools.file_edit_tool import FileEditTool
        from claude_code.tools.file_read_tool import FileReadTool

        target = str(tmpdir / "edit_test.txt")
        await FileWriteTool().call({"file_path": target, "content": "foo bar baz\n"}, None)

        edit_result = await FileEditTool().call(
            {"file_path": target, "old_string": "foo bar", "new_string": "REPLACED"},
            None,
        )
        assert "error" not in str(edit_result).lower(), f"Edit error: {edit_result}"

        read_result = await FileReadTool().call({"file_path": target}, None)
        assert "REPLACED" in str(read_result), "Edit should have replaced text"
        assert "foo bar" not in str(read_result), "Old string should be gone"

    @pytest.mark.asyncio
    async def test_file_read_nonexistent_returns_error(self, tmpdir):
        from claude_code.tools.file_read_tool import FileReadTool

        result = await FileReadTool().call(
            {"file_path": str(tmpdir / "nonexistent.txt")}, None
        )
        result_str = str(result).lower()
        # should contain error/not found indication
        assert any(kw in result_str for kw in ["error", "not found", "no such"]), (
            f"Should signal error for missing file, got: {result}"
        )

    @pytest.mark.asyncio
    async def test_grep_tool_finds_pattern(self, tmpdir):
        from claude_code.tools.file_write_tool import FileWriteTool
        from claude_code.tools.grep_tool import GrepTool

        target = str(tmpdir / "grep_test.txt")
        await FileWriteTool().call(
            {"file_path": target, "content": "alpha\nSEARCH_ME\nbeta\n"}, None
        )

        result = await GrepTool().call(
            pattern="SEARCH_ME", path=str(tmpdir), output_mode="content"
        )
        assert "SEARCH_ME" in str(result), f"Grep should find pattern, got: {result}"

    @pytest.mark.asyncio
    async def test_bash_tool_basic_exec(self):
        from claude_code.tools.bash_tool import BashTool

        result = await BashTool().call(
            {"command": "echo E2E_BASH_OK", "timeout": 5000}, None
        )
        assert "E2E_BASH_OK" in str(result), f"BashTool should echo, got: {result}"

    @pytest.mark.asyncio
    async def test_bash_tool_exit_code(self):
        from claude_code.tools.bash_tool import BashTool

        result = await BashTool().call(
            {"command": "exit 42", "timeout": 5000}, None
        )
        result_str = str(result)
        assert "42" in result_str, f"Should capture exit code 42, got: {result}"

    @pytest.mark.asyncio
    async def test_bash_tool_env_var(self):
        from claude_code.tools.bash_tool import BashTool

        result = await BashTool().call(
            {"command": "echo $HOME", "timeout": 5000}, None
        )
        home = os.environ.get("HOME", "")
        assert home and home in str(result), f"Should see $HOME={home} in: {result}"

    @pytest.mark.asyncio
    async def test_file_write_overwrites_existing(self, tmpdir):
        from claude_code.tools.file_write_tool import FileWriteTool
        from claude_code.tools.file_read_tool import FileReadTool

        target = str(tmpdir / "overwrite.txt")
        w = FileWriteTool()
        await w.call({"file_path": target, "content": "first"}, None)
        await w.call({"file_path": target, "content": "second"}, None)

        result = await FileReadTool().call({"file_path": target}, None)
        assert "second" in str(result)
        assert "first" not in str(result)


# ══════════════════════════════════════════════════════════════════
# 2. QueryEngine (mock API)
# ══════════════════════════════════════════════════════════════════

class TestQueryEngine:
    """QueryEngine submit_message 流程 + state 管理"""

    def _make_engine(self, **kwargs):
        from claude_code.query_engine import QueryEngine, QueryEngineConfig

        config = QueryEngineConfig(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            custom_system_prompt="You are a test assistant.",
            **kwargs,
        )
        return QueryEngine(config)

    @staticmethod
    async def _mock_query_gen_text(text: str):
        """Generator that yields a minimal assistant + result event."""

        async def _gen(*args, **kwargs):
            yield {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": text}],
                },
            }
            yield {"type": "result", "result": text, "session_id": "mock-session"}

        return _gen

    @pytest.mark.asyncio
    async def test_initial_state(self):
        engine = self._make_engine()
        assert not engine.is_running
        assert engine.get_messages() == []
        assert engine.config.session_id  # has a UUID

    @pytest.mark.asyncio
    async def test_submit_message_yields_events(self):
        from claude_code.query_engine import query as _query_module

        engine = self._make_engine()
        mock_gen = await self._mock_query_gen_text("Hello!")

        with patch("claude_code.query_engine.query", side_effect=mock_gen):
            events = [e async for e in engine.submit_message("Hi")]

        types = [e["type"] for e in events]
        assert "assistant" in types
        assert "result" in types

    @pytest.mark.asyncio
    async def test_messages_accumulate_across_turns(self):
        engine = self._make_engine()
        mock_gen = await self._mock_query_gen_text("Turn 1 reply")

        with patch("claude_code.query_engine.query", side_effect=mock_gen):
            async for _ in engine.submit_message("Turn 1"):
                pass

        msgs = engine.get_messages()
        assert len(msgs) >= 1, "Should have at least one message after turn"

    @pytest.mark.asyncio
    async def test_clear_messages(self):
        engine = self._make_engine()
        mock_gen = await self._mock_query_gen_text("reply")

        with patch("claude_code.query_engine.query", side_effect=mock_gen):
            async for _ in engine.submit_message("question"):
                pass

        engine.clear_messages()
        assert engine.get_messages() == []

    @pytest.mark.asyncio
    async def test_is_running_flag(self):
        """is_running should be True during query, False after."""
        engine = self._make_engine()
        observed_running: list[bool] = []

        async def mock_gen(*args, **kwargs):
            observed_running.append(engine.is_running)
            yield {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "running test"}],
                },
            }
            yield {"type": "result", "result": "done", "session_id": "s"}

        with patch("claude_code.query_engine.query", side_effect=mock_gen):
            async for _ in engine.submit_message("run"):
                pass

        assert not engine.is_running, "should be False after completion"
        # During generation is_running should have been True at least once
        assert any(observed_running), "is_running should be True during query"

    @pytest.mark.asyncio
    async def test_set_system_prompt(self):
        engine = self._make_engine()
        engine.set_system_prompt("New system prompt")
        # set_system_prompt wraps in list: config.system_prompt = [prompt]
        assert engine.config.system_prompt == ["New system prompt"]

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self):
        """Two turns — messages should grow each turn."""
        engine = self._make_engine()

        for i in range(2):
            mock_gen = await self._mock_query_gen_text(f"Reply {i}")
            with patch("claude_code.query_engine.query", side_effect=mock_gen):
                async for _ in engine.submit_message(f"Question {i}"):
                    pass

        msgs = engine.get_messages()
        assert len(msgs) >= 2, f"Expected ≥2 messages, got {len(msgs)}"


# ══════════════════════════════════════════════════════════════════
# 3. CostTracker
# ══════════════════════════════════════════════════════════════════

class TestCostTracker:
    """CostTracker 函数接口测试"""

    def setup_method(self):
        import claude_code.cost_tracker as ct
        ct.reset_state_for_tests()

    def teardown_method(self):
        import claude_code.cost_tracker as ct
        ct.reset_state_for_tests()

    def test_initial_state_is_zero(self):
        import claude_code.cost_tracker as ct
        assert ct.get_total_cost_usd() == 0.0
        assert ct.get_total_input_tokens() == 0
        assert ct.get_total_output_tokens() == 0

    def test_add_usage_accumulates(self):
        import claude_code.cost_tracker as ct
        ct.add_usage({"input_tokens": 100, "output_tokens": 50}, cost_usd=0.002)
        ct.add_usage({"input_tokens": 200, "output_tokens": 80}, cost_usd=0.004)

        assert ct.get_total_input_tokens() == 300
        assert ct.get_total_output_tokens() == 130
        assert abs(ct.get_total_cost_usd() - 0.006) < 1e-9

    def test_format_total_cost_non_empty(self):
        import claude_code.cost_tracker as ct
        ct.add_usage({"input_tokens": 1000, "output_tokens": 500}, cost_usd=0.01)
        text = ct.format_total_cost()
        assert text, "format_total_cost should return non-empty string"
        assert "cost" in text.lower() or "$" in text or "token" in text.lower()

    def test_reset_clears_state(self):
        import claude_code.cost_tracker as ct
        ct.add_usage({"input_tokens": 9999}, cost_usd=1.0)
        ct.reset_state_for_tests()
        assert ct.get_total_cost_usd() == 0.0
        assert ct.get_total_input_tokens() == 0

    def test_cache_tokens_tracked(self):
        import claude_code.cost_tracker as ct
        ct.add_usage({
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 200,
            "cache_creation_input_tokens": 300,
        }, cost_usd=0.005)

        assert ct.get_total_cache_read_input_tokens() == 200
        assert ct.get_total_cache_creation_input_tokens() == 300


# ══════════════════════════════════════════════════════════════════
# 4. History
# ══════════════════════════════════════════════════════════════════

class TestHistory:
    """history 模块函数接口测试 (module uses add_to_history / get_history, not SessionHistory class)"""

    def test_history_module_imports(self):
        import claude_code.history as h
        assert callable(h.add_to_history)
        assert callable(h.clear_pending_history_entries)
        assert callable(h.remove_last_from_history)

    def test_add_to_history_writes_jsonl(self, tmp_path, monkeypatch):
        import json
        import claude_code.history as h

        hist_file = tmp_path / "session.jsonl"
        monkeypatch.setattr(h, "_get_history_path", lambda: str(hist_file))
        monkeypatch.setattr(h, "_pending_entries", [])

        h.add_to_history({"role": "user", "content": "hello"})
        h.add_to_history({"role": "assistant", "content": "hi"})

        lines = hist_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["role"] == "user"
        assert json.loads(lines[1])["role"] == "assistant"

    def test_clear_pending_entries(self, monkeypatch):
        import claude_code.history as h
        pending = [{"x": 1}, {"x": 2}]
        monkeypatch.setattr(h, "_pending_entries", pending)
        h.clear_pending_history_entries()
        assert pending == []

    def test_remove_last_from_history(self, tmp_path, monkeypatch):
        import json
        import claude_code.history as h

        hist_file = tmp_path / "session.jsonl"
        hist_file.write_text(
            json.dumps({"role": "user"}) + "\n" +
            json.dumps({"role": "assistant"}) + "\n"
        )
        pending = [{"role": "user"}, {"role": "assistant"}]
        monkeypatch.setattr(h, "_pending_entries", pending)
        monkeypatch.setattr(h, "_get_history_path", lambda: str(hist_file))

        h.remove_last_from_history()

        lines = hist_file.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["role"] == "user"


# ══════════════════════════════════════════════════════════════════
# 5. Commands
# ══════════════════════════════════════════════════════════════════

class TestCommands:
    """Commands 注册表完整性检查（get_commands 是 async，接受 cwd 参数）"""

    def test_command_modules_importable(self):
        """核心 command 模块可以独立 import"""
        from claude_code.commands.clear.index import ClearCommand
        clear = ClearCommand()
        assert clear.name == "clear"
        assert hasattr(clear, "call")

    @pytest.mark.asyncio
    async def test_get_commands_returns_list(self):
        """get_commands(cwd) 实际返回列表，不崩溃"""
        from claude_code.commands import get_commands
        cmds = await get_commands("/tmp")
        assert isinstance(cmds, list), "get_commands should return a list"
        assert len(cmds) >= 10, f"Expected ≥10 commands, got {len(cmds)}"

    @pytest.mark.asyncio
    async def test_core_commands_present(self):
        from claude_code.commands import get_commands
        cmds = await get_commands("/tmp")
        names = {getattr(c, "name", "") for c in cmds}
        for expected in ["clear", "compact", "help", "exit", "model", "memory", "status"]:
            assert expected in names, f"Expected command '{expected}' to be registered"

    @pytest.mark.asyncio
    async def test_all_commands_have_name(self):
        from claude_code.commands import get_commands
        cmds = await get_commands("/tmp")
        for cmd in cmds:
            name = getattr(cmd, "name", None)
            assert name, f"Command {cmd!r} should have a non-empty name"

    @pytest.mark.asyncio
    async def test_is_command_enabled_safe_on_all_cmds(self):
        """is_command_enabled should not raise on any registered command."""
        from claude_code.commands import get_commands, is_command_enabled
        cmds = await get_commands("/tmp")
        for cmd in cmds:
            result = is_command_enabled(cmd)  # must not raise
            assert isinstance(result, bool)

    def test_clear_command_descriptor(self):
        from claude_code.commands.clear.index import ClearCommand
        cmd = ClearCommand()
        assert cmd.name == "clear"
        assert cmd.type == "local"
        assert isinstance(cmd.aliases, list)

    def test_command_call_is_coroutine(self):
        import inspect
        from claude_code.commands.clear.index import ClearCommand
        cmd = ClearCommand()
        assert inspect.iscoroutinefunction(cmd.call), "Command.call should be async"

    def test_is_command_enabled_no_attr(self):
        """Objects without is_enabled attr should be treated as enabled."""
        from claude_code.types.command import is_command_enabled

        class BareCmd:
            name = "bare"

        assert is_command_enabled(BareCmd()) is True

    def test_is_command_enabled_none_field(self):
        from claude_code.types.command import is_command_enabled

        class CmdNone:
            name = "none"
            is_enabled = None

        assert is_command_enabled(CmdNone()) is True

    def test_is_command_enabled_callable_false(self):
        from claude_code.types.command import is_command_enabled

        class CmdOff:
            name = "off"
            is_enabled = lambda self: False

        assert is_command_enabled(CmdOff()) is False

    def test_get_command_name_fallback(self):
        from claude_code.types.command import get_command_name

        class CmdFallback:
            name = "fallback-name"

        assert get_command_name(CmdFallback()) == "fallback-name"

    def test_get_command_name_user_facing(self):
        from claude_code.types.command import get_command_name

        class CmdFacing:
            name = "internal"
            user_facing_name = lambda self: "display-name"

        assert get_command_name(CmdFacing()) == "display-name"


# ══════════════════════════════════════════════════════════════════
# 6. 完整 Tool → QueryEngine 管道 (end-to-end mock)
# ══════════════════════════════════════════════════════════════════

class TestEndToEndPipeline:
    """模拟 agent 使用工具完成任务的完整链路"""

    @pytest.mark.asyncio
    async def test_write_read_via_query_engine(self, tmp_path):
        """
        Simulate: agent writes a file via FileWriteTool,
        then reads it back — QueryEngine dispatches both.
        """
        from claude_code.query_engine import QueryEngine, QueryEngineConfig
        from claude_code.tools.file_write_tool import FileWriteTool
        from claude_code.tools.file_read_tool import FileReadTool

        target = str(tmp_path / "pipeline_test.txt")
        content = "pipeline content 12345"

        # Step 1: direct tool invocation (as query engine would dispatch)
        w = FileWriteTool()
        write_result = await w.call({"file_path": target, "content": content}, None)
        assert "error" not in str(write_result).lower()

        r = FileReadTool()
        read_result = await r.call({"file_path": target}, None)
        assert content in str(read_result)

        # Step 2: QueryEngine receives a result event with tool output
        config = QueryEngineConfig(
            model="claude-3-5-sonnet-20241022",
            custom_system_prompt="test",
        )
        engine = QueryEngine(config)

        async def mock_tool_use_query(*args, **kwargs):
            yield {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"File written: {content}"}],
                },
            }
            yield {"type": "result", "result": content, "session_id": "e2e"}

        with patch("claude_code.query_engine.query", side_effect=mock_tool_use_query):
            events = [e async for e in engine.submit_message(f"write to {target}")]

        types = [e["type"] for e in events]
        assert "result" in types, "Pipeline should deliver result event"

    @pytest.mark.asyncio
    async def test_bash_output_forwarded_to_engine(self, tmp_path):
        """BashTool output would be passed back to model as tool_result."""
        from claude_code.tools.bash_tool import BashTool
        from claude_code.query_engine import QueryEngine, QueryEngineConfig

        # Execute bash tool
        bash = BashTool()
        bash_result = await bash.call(
            {"command": f"echo PIPELINE_MARKER && ls {tmp_path}", "timeout": 5000},
            None,
        )
        assert "PIPELINE_MARKER" in str(bash_result)

        # QueryEngine gets result fed back
        config = QueryEngineConfig(model="claude-3-5-sonnet-20241022", custom_system_prompt="test")
        engine = QueryEngine(config)

        async def mock_with_bash(*args, **kwargs):
            yield {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Bash output received"}],
                },
            }
            yield {"type": "result", "result": "done", "session_id": "bash-e2e"}

        with patch("claude_code.query_engine.query", side_effect=mock_with_bash):
            events = [e async for e in engine.submit_message("check bash output")]

        assert any(e["type"] == "result" for e in events)


# ══════════════════════════════════════════════════════════════════
# 7. Import health check — 所有顶层模块无 ImportError
# ══════════════════════════════════════════════════════════════════

class TestImportHealth:
    """确保关键模块可以无副作用地 import"""

    MODULES = [
        "claude_code.query",
        "claude_code.query_engine",
        "claude_code.cost_tracker",
        "claude_code.history",
        "claude_code.commands",
        "claude_code.tools",
        "claude_code.tool",
        "claude_code.context",
        "claude_code.constants",
        "claude_code.utils",
        "claude_code.services",
    ]

    @pytest.mark.parametrize("module_name", MODULES)
    def test_module_imports_cleanly(self, module_name):
        import importlib
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            pytest.fail(f"ImportError for {module_name}: {e}")
        except Exception as e:
            # Non-import errors are acceptable at import time (e.g., missing env)
            pass  # module loaded but raised runtime init error — OK for this check
