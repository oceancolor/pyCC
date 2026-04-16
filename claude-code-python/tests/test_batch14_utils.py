"""
Tests for batch 14: heap_dump_service, analyze_context_core, theme.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# heap_dump_service
# ---------------------------------------------------------------------------

class TestHeapDumpService:
    def test_imports(self):
        from claude_code.utils.heap_dump_service import (
            HeapDumpConfig,
            HeapDumpResult,
            MemoryDiagnostics,
            trigger_heap_dump,
        )

    def test_config_defaults(self):
        from claude_code.utils.heap_dump_service import HeapDumpConfig
        cfg = HeapDumpConfig()
        assert cfg.top_n_frames == 20
        assert cfg.include_traceback is True

    def test_trigger_heap_dump_success(self, tmp_path):
        from claude_code.utils.heap_dump_service import trigger_heap_dump
        result = trigger_heap_dump(output_dir=str(tmp_path))
        assert result.success is True
        assert result.diag_path is not None
        assert result.snapshot_path is not None
        assert os.path.exists(result.diag_path)
        assert os.path.exists(result.snapshot_path)

    def test_dump_writes_valid_json(self, tmp_path):
        import json
        from claude_code.utils.heap_dump_service import trigger_heap_dump
        result = trigger_heap_dump(output_dir=str(tmp_path))
        with open(result.diag_path) as f:
            data = json.load(f)
        assert "timestamp" in data
        assert "heap_used_bytes" in data
        assert "platform" in data

    def test_trigger_heap_dump_bad_dir(self):
        from claude_code.utils.heap_dump_service import trigger_heap_dump, HeapDumpConfig
        # Should return success=False on permission error; or succeed by creating dir
        # We just check it doesn't raise
        result = trigger_heap_dump(output_dir="/tmp/_test_heap_dump_batch14")
        # Cleanup
        import shutil
        shutil.rmtree("/tmp/_test_heap_dump_batch14", ignore_errors=True)
        assert result.success is True  # /tmp is writable


# ---------------------------------------------------------------------------
# analyze_context_core
# ---------------------------------------------------------------------------

class TestAnalyzeContextCore:
    def test_imports(self):
        from claude_code.utils.analyze_context_core import (
            ContextAnalysis,
            analyze_context,
            get_context_summary,
        )

    def test_empty_messages(self):
        from claude_code.utils.analyze_context_core import analyze_context
        result = analyze_context([])
        assert result.total_tokens == 0
        assert result.message_count == 0

    def test_simple_user_message(self):
        from claude_code.utils.analyze_context_core import analyze_context
        messages = [{"type": "user", "message": {"role": "user", "content": "Hello world"}}]
        result = analyze_context(messages)
        assert result.user_messages_tokens > 0
        assert result.total_tokens == result.user_messages_tokens

    def test_assistant_message(self):
        from claude_code.utils.analyze_context_core import analyze_context
        messages = [
            {"type": "assistant", "message": {"role": "assistant", "content": "I can help you."}}
        ]
        result = analyze_context(messages)
        assert result.assistant_tokens > 0

    def test_tool_call_counted_separately(self):
        from claude_code.utils.analyze_context_core import analyze_context
        messages = [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
                        {"type": "text", "text": "Running..."},
                    ],
                },
            }
        ]
        result = analyze_context(messages)
        assert result.tool_calls_tokens > 0
        assert result.assistant_tokens > 0

    def test_tool_result_counted_separately(self):
        from claude_code.utils.analyze_context_core import analyze_context
        messages = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "file1.py"},
                        {"type": "text", "text": "Looks good"},
                    ],
                },
            }
        ]
        result = analyze_context(messages)
        assert result.tool_results_tokens > 0
        assert result.user_messages_tokens > 0

    def test_get_context_summary_format(self):
        from claude_code.utils.analyze_context_core import analyze_context, get_context_summary
        messages = [
            {"type": "user", "message": {"role": "user", "content": "Hello!"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "Hi there!"}},
        ]
        analysis = analyze_context(messages)
        summary = get_context_summary(analysis)
        assert "Context Analysis" in summary
        assert "Total tokens" in summary
        assert "%" in summary

    def test_total_is_sum_of_parts(self):
        from claude_code.utils.analyze_context_core import analyze_context
        messages = [
            {"type": "user", "message": {"role": "user", "content": "What is Python?"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "Python is a language."}},
        ]
        result = analyze_context(messages)
        expected = (
            result.tool_results_tokens
            + result.tool_calls_tokens
            + result.user_messages_tokens
            + result.assistant_tokens
            + result.attachment_tokens
        )
        assert result.total_tokens == expected

    def test_sdk_style_messages(self):
        """Accept raw Anthropic SDK dicts with 'role' keys."""
        from claude_code.utils.analyze_context_core import analyze_context
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = analyze_context(messages)
        assert result.total_tokens > 0


# ---------------------------------------------------------------------------
# theme
# ---------------------------------------------------------------------------

class TestTheme:
    def test_imports(self):
        from claude_code.utils.theme import (
            ColorTheme,
            BUILT_IN_THEMES,
            get_theme,
            get_current_theme,
            set_theme,
        )

    def test_built_in_themes_present(self):
        from claude_code.utils.theme import BUILT_IN_THEMES
        assert "dark" in BUILT_IN_THEMES
        assert "light" in BUILT_IN_THEMES
        assert "claude" in BUILT_IN_THEMES

    def test_theme_has_colors(self):
        from claude_code.utils.theme import BUILT_IN_THEMES
        for name, theme in BUILT_IN_THEMES.items():
            assert theme.name == name
            assert len(theme.colors) > 0

    def test_color_format(self):
        from claude_code.utils.theme import BUILT_IN_THEMES
        for theme in BUILT_IN_THEMES.values():
            for key, value in theme.colors.items():
                assert value.startswith("rgb(") or value.startswith("ansi:"), (
                    f"{theme.name}.{key} has unexpected format: {value}"
                )

    def test_get_theme_known(self):
        from claude_code.utils.theme import get_theme
        t = get_theme("light")
        assert t.name == "light"

    def test_get_theme_fallback(self):
        from claude_code.utils.theme import get_theme
        t = get_theme("nonexistent")
        assert t.name == "dark"

    def test_get_color(self):
        from claude_code.utils.theme import get_theme
        t = get_theme("dark")
        color = t.get("text")
        assert color == "rgb(255,255,255)"

    def test_get_color_missing_key(self):
        from claude_code.utils.theme import get_theme
        t = get_theme("dark")
        assert t.get("__does_not_exist__", "fallback") == "fallback"

    def test_set_and_get_current_theme(self):
        from claude_code.utils.theme import set_theme, get_current_theme
        set_theme("light")
        assert get_current_theme().name == "light"
        set_theme("dark")  # restore
        assert get_current_theme().name == "dark"

    def test_set_theme_invalid(self):
        from claude_code.utils.theme import set_theme
        with pytest.raises(ValueError):
            set_theme("unknown_theme_xyz")

    def test_themes_are_independent(self):
        """Mutating one theme's colors must not affect others."""
        from claude_code.utils.theme import BUILT_IN_THEMES
        dark_text_before = BUILT_IN_THEMES["dark"].colors["text"]
        BUILT_IN_THEMES["light"].colors["text"] = "MUTATED"
        assert BUILT_IN_THEMES["dark"].colors["text"] == dark_text_before
        # Restore
        BUILT_IN_THEMES["light"].colors["text"] = "rgb(0,0,0)"
