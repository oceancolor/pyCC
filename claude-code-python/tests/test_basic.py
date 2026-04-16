"""
Basic tests for the Python port.
"""
import pytest
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestConstants:
    def test_binary_extensions(self):
        from claude_code.constants.files import BINARY_EXTENSIONS, has_binary_extension, is_binary_content
        assert ".png" in BINARY_EXTENSIONS
        assert ".jpg" in BINARY_EXTENSIONS
        assert ".py" not in BINARY_EXTENSIONS
        assert has_binary_extension("image.png")
        assert not has_binary_extension("script.py")

    def test_is_binary_content(self):
        from claude_code.constants.files import is_binary_content
        assert not is_binary_content(b"Hello, World!")
        assert is_binary_content(b"\x00\x01\x02\x03")  # null byte = binary

    def test_product_urls(self):
        from claude_code.constants.product import (
            PRODUCT_URL,
            CLAUDE_AI_BASE_URL,
            get_claude_ai_base_url,
            get_remote_session_url,
        )
        assert PRODUCT_URL.startswith("https://")
        assert get_claude_ai_base_url() == CLAUDE_AI_BASE_URL
        url = get_remote_session_url("test_session_123")
        assert "test_session_123" in url

    def test_tool_names(self):
        from claude_code.constants.tools import (
            BASH_TOOL_NAME,
            FILE_READ_TOOL_NAME,
            FILE_EDIT_TOOL_NAME,
            FILE_WRITE_TOOL_NAME,
            GREP_TOOL_NAME,
            GLOB_TOOL_NAME,
        )
        assert BASH_TOOL_NAME == "Bash"
        assert FILE_READ_TOOL_NAME == "Read"
        assert FILE_EDIT_TOOL_NAME == "Edit"
        assert FILE_WRITE_TOOL_NAME == "Write"
        assert GREP_TOOL_NAME == "Grep"
        assert GLOB_TOOL_NAME == "Glob"


class TestUtils:
    def test_format_file_size(self):
        from claude_code.utils.format import format_file_size
        assert format_file_size(0) == "0 bytes"
        assert format_file_size(512) == "512 bytes"
        assert format_file_size(1024) == "1KB"
        assert format_file_size(1536) == "1.5KB"
        assert format_file_size(1024 * 1024) == "1MB"

    def test_format_duration(self):
        from claude_code.utils.format import format_duration
        assert format_duration(0) == "0s"
        assert format_duration(5000) == "5s"
        assert format_duration(65000) == "1m 5s"

    def test_truncate(self):
        from claude_code.utils.format import truncate
        assert truncate("hello", 10) == "hello"
        assert truncate("hello world", 8) == "hello..."

    def test_add_line_numbers(self):
        from claude_code.utils.file import add_line_numbers
        result = add_line_numbers("line1\nline2\nline3", start=1)
        assert "1\t" in result
        assert "2\t" in result
        assert "3\t" in result

    def test_is_abort_error(self):
        from claude_code.utils.errors import AbortError, is_abort_error
        e = AbortError("test")
        assert is_abort_error(e)
        assert not is_abort_error(ValueError("other"))

    def test_env_truthy(self):
        from claude_code.utils.env_utils import is_env_truthy
        assert is_env_truthy("1")
        assert is_env_truthy("true")
        assert is_env_truthy("yes")
        assert not is_env_truthy("0")
        assert not is_env_truthy("false")
        assert not is_env_truthy(None)

    def test_parse_env_vars(self):
        from claude_code.utils.env_utils import parse_env_vars
        result = parse_env_vars(["KEY1=value1", "KEY2=value2"])
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_parse_env_vars_invalid(self):
        from claude_code.utils.env_utils import parse_env_vars
        with pytest.raises(ValueError):
            parse_env_vars(["INVALID_NO_EQUALS"])


class TestTypes:
    def test_session_id(self):
        from claude_code.types.ids import SessionId, as_session_id
        sid = as_session_id("my-session-id")
        assert sid == "my-session-id"
        assert isinstance(sid, str)

    def test_agent_id_validation(self):
        from claude_code.types.ids import to_agent_id
        # Valid agent IDs
        valid = to_agent_id("a1234567890abcdef")
        assert valid is not None

        # Invalid
        invalid = to_agent_id("not-an-agent-id")
        assert invalid is None

    def test_permission_allow_decision(self):
        from claude_code.types.permissions import PermissionAllowDecision
        d = PermissionAllowDecision()
        assert d.behavior == "allow"

    def test_plugin_error_message(self):
        from claude_code.types.plugin import PluginErrorGeneric, get_plugin_error_message
        e = PluginErrorGeneric(error="Something went wrong")
        msg = get_plugin_error_message(e)
        assert "Something went wrong" in msg


class TestTools:
    def test_bash_tool_schema(self):
        from claude_code.tools.bash_tool import BashTool
        tool = BashTool()
        schema = tool.input_schema()
        assert schema["type"] == "object"
        assert "command" in schema["properties"]
        assert "command" in schema["required"]

    def test_file_read_tool_schema(self):
        from claude_code.tools.file_read_tool import FileReadTool
        tool = FileReadTool()
        schema = tool.input_schema()
        assert "file_path" in schema["required"]

    def test_file_edit_tool_schema(self):
        from claude_code.tools.file_edit_tool import FileEditTool
        tool = FileEditTool()
        schema = tool.input_schema()
        assert "old_string" in schema["required"]
        assert "new_string" in schema["required"]

    def test_glob_tool_schema(self):
        from claude_code.tools.glob_tool import GlobTool
        tool = GlobTool()
        schema = tool.input_schema()
        assert "pattern" in schema["required"]

    @pytest.mark.asyncio
    async def test_file_write_and_read(self, tmp_path):
        from claude_code.tools.file_write_tool import FileWriteTool
        from claude_code.tools.file_read_tool import FileReadTool
        from claude_code.tool import ToolUseContext

        write_tool = FileWriteTool()
        read_tool = FileReadTool()
        ctx = ToolUseContext()

        test_file = str(tmp_path / "test.txt")
        content = "Hello from Python port!\nLine 2\nLine 3"

        # Write
        result = await write_tool.call(
            {"file_path": test_file, "content": content}, ctx
        )
        assert "Successfully wrote" in result["text"]

        # Read
        result = await read_tool.call({"file_path": test_file}, ctx)
        assert "Hello from Python port!" in result["text"]
        assert "1\t" in result["text"]  # line numbers

    @pytest.mark.asyncio
    async def test_file_edit(self, tmp_path):
        from claude_code.tools.file_write_tool import FileWriteTool
        from claude_code.tools.file_edit_tool import FileEditTool
        from claude_code.tool import ToolUseContext

        write_tool = FileWriteTool()
        edit_tool = FileEditTool()
        ctx = ToolUseContext()

        test_file = str(tmp_path / "test.txt")
        original = "Hello World\nSecond line"

        # Write original
        await write_tool.call({"file_path": test_file, "content": original}, ctx)

        # Edit
        result = await edit_tool.call(
            {
                "file_path": test_file,
                "old_string": "Hello World",
                "new_string": "Hello Python",
            },
            ctx,
        )
        assert "Successfully edited" in result["text"]

        # Verify
        with open(test_file) as f:
            content = f.read()
        assert "Hello Python" in content

    @pytest.mark.asyncio
    async def test_glob_tool(self, tmp_path):
        from claude_code.tools.glob_tool import GlobTool
        from claude_code.tool import ToolUseContext

        # Create some test files
        (tmp_path / "a.py").write_text("# Python file")
        (tmp_path / "b.py").write_text("# Another Python file")
        (tmp_path / "c.txt").write_text("Text file")

        tool = GlobTool()
        ctx = ToolUseContext()

        result = await tool.call(
            {"pattern": "*.py", "path": str(tmp_path)}, ctx
        )
        assert "a.py" in result["text"]
        assert "b.py" in result["text"]
        assert "c.txt" not in result["text"]
