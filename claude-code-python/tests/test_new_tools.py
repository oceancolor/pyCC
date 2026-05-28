"""
集成测试 — FileMoveTool / NotebookReadTool / Task*Tool 补全验证

覆盖：
- 接口完整性 (description / prompt / input_schema / call 都已实现)
- FileMoveTool: 移动、不可覆盖错误、强制覆盖、源不存在
- NotebookReadTool: 正常读取、缺失文件、非 .ipynb 文件
- TaskCreateTool → TaskGetTool → TaskListTool → TaskUpdateTool → TaskStopTool 完整生命周期

运行：
    python3 -m pytest tests/test_new_tools.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))


# ══════════════════════════════════════════════════════════════════
# 通用：接口完整性
# ══════════════════════════════════════════════════════════════════

class TestInterfaceCompleteness:
    """所有补全的工具都必须满足 Tool 抽象接口，且可实例化。"""

    TOOL_CLASSES = [
        "claude_code.tools.file_move_tool.FileMoveTool",
        "claude_code.tools.notebook_read_tool.NotebookReadTool",
        "claude_code.tools.task_tool.TaskCreateTool",
        "claude_code.tools.task_tool.TaskGetTool",
        "claude_code.tools.task_tool.TaskListTool",
        "claude_code.tools.task_tool.TaskStopTool",
        "claude_code.tools.task_tool.TaskUpdateTool",
    ]

    def _load_cls(self, dotpath: str):
        import importlib
        module_path, cls_name = dotpath.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name)

    @pytest.mark.parametrize("dotpath", TOOL_CLASSES)
    def test_instantiatable(self, dotpath):
        cls = self._load_cls(dotpath)
        instance = cls()  # must not raise TypeError
        assert instance is not None

    @pytest.mark.parametrize("dotpath", TOOL_CLASSES)
    def test_has_name(self, dotpath):
        cls = self._load_cls(dotpath)
        t = cls()
        assert isinstance(t.name, str) and t.name, f"{dotpath} must have a non-empty name"

    @pytest.mark.parametrize("dotpath", TOOL_CLASSES)
    @pytest.mark.asyncio
    async def test_description_is_nonempty(self, dotpath):
        cls = self._load_cls(dotpath)
        t = cls()
        desc = await t.description()
        assert isinstance(desc, str) and len(desc) > 10

    @pytest.mark.parametrize("dotpath", TOOL_CLASSES)
    @pytest.mark.asyncio
    async def test_prompt_is_nonempty(self, dotpath):
        cls = self._load_cls(dotpath)
        t = cls()
        p = await t.prompt()
        assert isinstance(p, str) and len(p) > 20

    @pytest.mark.parametrize("dotpath", TOOL_CLASSES)
    def test_input_schema_is_valid(self, dotpath):
        cls = self._load_cls(dotpath)
        t = cls()
        schema = t.input_schema()
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema

    @pytest.mark.parametrize("dotpath", TOOL_CLASSES)
    def test_no_abstract_methods_remaining(self, dotpath):
        cls = self._load_cls(dotpath)
        abstract = getattr(cls, "__abstractmethods__", frozenset())
        assert not abstract, (
            f"{cls.__name__} still has abstract methods: {sorted(abstract)}"
        )

    @pytest.mark.parametrize("dotpath", TOOL_CLASSES)
    def test_in_default_tools_registry(self, dotpath):
        """工具应在 tools.__init__ 的 __all__ 中。"""
        import claude_code.tools as tools_pkg
        cls_name = dotpath.rsplit(".", 1)[1]
        assert cls_name in tools_pkg.__all__, (
            f"{cls_name} should be listed in tools.__all__"
        )


# ══════════════════════════════════════════════════════════════════
# FileMoveTool
# ══════════════════════════════════════════════════════════════════

class TestFileMoveTool:

    @pytest.fixture
    def tool(self):
        from claude_code.tools.file_move_tool import FileMoveTool
        return FileMoveTool()

    @pytest.mark.asyncio
    async def test_move_file(self, tool, tmp_path):
        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("hello")

        result = await tool.call({"source": str(src), "destination": str(dst)}, None)

        assert not result.get("is_error"), f"Should not error: {result}"
        assert dst.exists(), "Destination should exist"
        assert not src.exists(), "Source should be gone"
        assert dst.read_text() == "hello"

    @pytest.mark.asyncio
    async def test_move_to_subdir_auto_creates(self, tool, tmp_path):
        src = tmp_path / "file.txt"
        dst = tmp_path / "subdir" / "nested" / "file.txt"
        src.write_text("content")

        result = await tool.call({"source": str(src), "destination": str(dst)}, None)

        assert not result.get("is_error"), f"Should not error: {result}"
        assert dst.exists()

    @pytest.mark.asyncio
    async def test_no_overwrite_by_default(self, tool, tmp_path):
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("new")
        dst.write_text("existing")

        result = await tool.call({"source": str(src), "destination": str(dst)}, None)

        assert result.get("is_error"), "Should error when dest exists and overwrite=False"
        assert dst.read_text() == "existing", "Destination should be untouched"

    @pytest.mark.asyncio
    async def test_overwrite_true_replaces(self, tool, tmp_path):
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("new content")
        dst.write_text("old content")

        result = await tool.call(
            {"source": str(src), "destination": str(dst), "overwrite": True}, None
        )

        assert not result.get("is_error"), f"Should not error: {result}"
        assert dst.read_text() == "new content"

    @pytest.mark.asyncio
    async def test_source_not_found(self, tool, tmp_path):
        result = await tool.call(
            {"source": str(tmp_path / "ghost.txt"), "destination": str(tmp_path / "out.txt")},
            None,
        )
        assert result.get("is_error"), "Should error for missing source"

    @pytest.mark.asyncio
    async def test_move_directory(self, tool, tmp_path):
        src_dir = tmp_path / "src_dir"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("inside")
        dst_dir = tmp_path / "dst_dir"

        result = await tool.call({"source": str(src_dir), "destination": str(dst_dir)}, None)

        assert not result.get("is_error"), f"Should not error: {result}"
        assert (dst_dir / "file.txt").exists()

    @pytest.mark.asyncio
    async def test_rename_file(self, tool, tmp_path):
        src = tmp_path / "old_name.txt"
        dst = tmp_path / "new_name.txt"
        src.write_text("data")

        result = await tool.call({"source": str(src), "destination": str(dst)}, None)

        assert not result.get("is_error")
        assert dst.exists()
        assert dst.name == "new_name.txt"


# ══════════════════════════════════════════════════════════════════
# NotebookReadTool
# ══════════════════════════════════════════════════════════════════

class TestNotebookReadTool:

    @pytest.fixture
    def tool(self):
        from claude_code.tools.notebook_read_tool import NotebookReadTool
        return NotebookReadTool()

    def _write_notebook(self, path: Path, cells: list) -> None:
        nb = {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
              "metadata": {"kernelspec": {"name": "python3"}}}
        path.write_text(json.dumps(nb))

    @pytest.mark.asyncio
    async def test_read_code_cell(self, tool, tmp_path):
        nb = tmp_path / "test.ipynb"
        self._write_notebook(nb, [
            {"cell_type": "code", "source": ["x = 1\nprint(x)"], "outputs": []}
        ])
        result = await tool.call({"notebook_path": str(nb)}, None)
        assert "Cell 1" in result["text"]
        assert "x = 1" in result["text"]

    @pytest.mark.asyncio
    async def test_read_markdown_cell(self, tool, tmp_path):
        nb = tmp_path / "test.ipynb"
        self._write_notebook(nb, [
            {"cell_type": "markdown", "source": ["# Heading\nSome text."], "outputs": []}
        ])
        result = await tool.call({"notebook_path": str(nb)}, None)
        assert "markdown" in result["text"]
        assert "Heading" in result["text"]

    @pytest.mark.asyncio
    async def test_stream_output(self, tool, tmp_path):
        nb = tmp_path / "test.ipynb"
        self._write_notebook(nb, [{
            "cell_type": "code",
            "source": ['print("hello")'],
            "outputs": [{"output_type": "stream", "name": "stdout", "text": ["hello\n"]}],
        }])
        result = await tool.call({"notebook_path": str(nb)}, None)
        assert "hello" in result["text"]

    @pytest.mark.asyncio
    async def test_execute_result_output(self, tool, tmp_path):
        nb = tmp_path / "test.ipynb"
        self._write_notebook(nb, [{
            "cell_type": "code",
            "source": ["42"],
            "outputs": [{
                "output_type": "execute_result",
                "execution_count": 1,
                "data": {"text/plain": ["42"]},
                "metadata": {},
            }],
        }])
        result = await tool.call({"notebook_path": str(nb)}, None)
        assert "42" in result["text"]

    @pytest.mark.asyncio
    async def test_error_output(self, tool, tmp_path):
        nb = tmp_path / "test.ipynb"
        self._write_notebook(nb, [{
            "cell_type": "code",
            "source": ["1/0"],
            "outputs": [{
                "output_type": "error",
                "ename": "ZeroDivisionError",
                "evalue": "division by zero",
                "traceback": [],
            }],
        }])
        result = await tool.call({"notebook_path": str(nb)}, None)
        assert "ZeroDivisionError" in result["text"]

    @pytest.mark.asyncio
    async def test_empty_notebook(self, tool, tmp_path):
        nb = tmp_path / "empty.ipynb"
        self._write_notebook(nb, [])
        result = await tool.call({"notebook_path": str(nb)}, None)
        assert "no cells" in result["text"].lower()

    @pytest.mark.asyncio
    async def test_missing_file(self, tool, tmp_path):
        result = await tool.call({"notebook_path": str(tmp_path / "ghost.ipynb")}, None)
        assert result.get("is_error")
        assert "not found" in result["text"].lower()

    @pytest.mark.asyncio
    async def test_non_notebook_extension(self, tool, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("print('hi')")
        result = await tool.call({"notebook_path": str(f)}, None)
        assert result.get("is_error")

    @pytest.mark.asyncio
    async def test_multi_cell_ordering(self, tool, tmp_path):
        nb = tmp_path / "multi.ipynb"
        self._write_notebook(nb, [
            {"cell_type": "code", "source": ["first"], "outputs": []},
            {"cell_type": "markdown", "source": ["second"], "outputs": []},
            {"cell_type": "code", "source": ["third"], "outputs": []},
        ])
        result = await tool.call({"notebook_path": str(nb)}, None)
        text = result["text"]
        assert text.index("Cell 1") < text.index("Cell 2") < text.index("Cell 3")


# ══════════════════════════════════════════════════════════════════
# Task* Tools (full lifecycle)
# ══════════════════════════════════════════════════════════════════

class TestTaskTools:

    @pytest.fixture(autouse=True)
    def clear_task_store(self):
        """Each test gets a fresh task store."""
        from claude_code.tools.task_tool import _TASK_STORE
        _TASK_STORE.clear()
        yield
        _TASK_STORE.clear()

    @pytest.fixture
    def create(self):
        from claude_code.tools.task_tool import TaskCreateTool
        return TaskCreateTool()

    @pytest.fixture
    def get(self):
        from claude_code.tools.task_tool import TaskGetTool
        return TaskGetTool()

    @pytest.fixture
    def lst(self):
        from claude_code.tools.task_tool import TaskListTool
        return TaskListTool()

    @pytest.fixture
    def update(self):
        from claude_code.tools.task_tool import TaskUpdateTool
        return TaskUpdateTool()

    @pytest.fixture
    def stop(self):
        from claude_code.tools.task_tool import TaskStopTool
        return TaskStopTool()

    def _extract_task_id(self, result: dict) -> str:
        text = result.get("text", "")
        for line in text.splitlines():
            if line.startswith("task_id:"):
                return line.split(":", 1)[1].strip()
        raise ValueError(f"No task_id in result: {result}")

    # ── TaskCreateTool ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_returns_task_id(self, create):
        r = await create.call({"description": "test task", "prompt": "do stuff"}, None)
        assert not r.get("is_error"), f"Should not error: {r}"
        task_id = self._extract_task_id(r)
        assert task_id, "Should return a task_id"

    @pytest.mark.asyncio
    async def test_create_empty_description_errors(self, create):
        r = await create.call({"description": "", "prompt": "do stuff"}, None)
        assert r.get("is_error")

    @pytest.mark.asyncio
    async def test_create_empty_prompt_errors(self, create):
        r = await create.call({"description": "task", "prompt": ""}, None)
        assert r.get("is_error")

    @pytest.mark.asyncio
    async def test_create_multiple_tasks_unique_ids(self, create):
        ids = set()
        for i in range(5):
            r = await create.call({"description": f"task {i}", "prompt": "do it"}, None)
            ids.add(self._extract_task_id(r))
        assert len(ids) == 5, "All task IDs should be unique"

    # ── TaskGetTool ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_newly_created_task_is_pending(self, create, get):
        r = await create.call({"description": "get test", "prompt": "prompt"}, None)
        task_id = self._extract_task_id(r)

        gr = await get.call({"task_id": task_id}, None)
        assert "pending" in gr["text"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_errors(self, get):
        r = await get.call({"task_id": "nonexistent-id"}, None)
        assert r.get("is_error")

    @pytest.mark.asyncio
    async def test_get_shows_description(self, create, get):
        r = await create.call({"description": "UNIQUE_DESC_XYZ", "prompt": "prompt"}, None)
        task_id = self._extract_task_id(r)

        gr = await get.call({"task_id": task_id}, None)
        assert "UNIQUE_DESC_XYZ" in gr["text"]

    # ── TaskListTool ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_empty(self, lst):
        r = await lst.call({}, None)
        assert "no tasks" in r["text"].lower()

    @pytest.mark.asyncio
    async def test_list_shows_created_task(self, create, lst):
        r = await create.call({"description": "listed task", "prompt": "p"}, None)
        task_id = self._extract_task_id(r)

        lr = await lst.call({}, None)
        assert task_id in lr["text"]

    @pytest.mark.asyncio
    async def test_list_count(self, create, lst):
        for i in range(3):
            await create.call({"description": f"t{i}", "prompt": "p"}, None)

        lr = await lst.call({}, None)
        assert "3" in lr["text"] or lr["text"].count("  [") == 3

    # ── TaskUpdateTool ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_appends_message(self, create, get, update):
        r = await create.call({"description": "update test", "prompt": "p"}, None)
        task_id = self._extract_task_id(r)

        await update.call({"task_id": task_id, "message": "focus on X"}, None)

        gr = await get.call({"task_id": task_id}, None)
        assert "focus on X" in gr["text"]

    @pytest.mark.asyncio
    async def test_update_nonexistent_errors(self, update):
        r = await update.call({"task_id": "bad-id", "message": "msg"}, None)
        assert r.get("is_error")

    @pytest.mark.asyncio
    async def test_update_message_count_increments(self, create, update):
        r = await create.call({"description": "count test", "prompt": "p"}, None)
        task_id = self._extract_task_id(r)

        for i in range(3):
            ur = await update.call({"task_id": task_id, "message": f"msg {i}"}, None)
            assert str(i + 1) in ur["text"]

    # ── TaskStopTool ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_stop_changes_status(self, create, get, stop):
        r = await create.call({"description": "stop test", "prompt": "p"}, None)
        task_id = self._extract_task_id(r)

        await stop.call({"task_id": task_id}, None)

        gr = await get.call({"task_id": task_id}, None)
        assert "stopped" in gr["text"]

    @pytest.mark.asyncio
    async def test_stop_nonexistent_errors(self, stop):
        r = await stop.call({"task_id": "ghost"}, None)
        assert r.get("is_error")

    @pytest.mark.asyncio
    async def test_update_after_stop_errors(self, create, stop, update):
        r = await create.call({"description": "stop update", "prompt": "p"}, None)
        task_id = self._extract_task_id(r)

        await stop.call({"task_id": task_id}, None)
        ur = await update.call({"task_id": task_id, "message": "too late"}, None)
        assert ur.get("is_error")

    # ── Full lifecycle ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, create, get, lst, update, stop):
        """Create → Get (pending) → Update → Get (has message) → Stop → Get (stopped)"""
        # 1. Create
        cr = await create.call({"description": "lifecycle", "prompt": "full test"}, None)
        task_id = self._extract_task_id(cr)
        assert task_id

        # 2. Get — pending
        gr = await get.call({"task_id": task_id}, None)
        assert "pending" in gr["text"]

        # 3. List — appears
        lr = await lst.call({}, None)
        assert task_id in lr["text"]

        # 4. Update
        ur = await update.call({"task_id": task_id, "message": "step 1 done"}, None)
        assert not ur.get("is_error")

        # 5. Get — message visible
        gr2 = await get.call({"task_id": task_id}, None)
        assert "step 1 done" in gr2["text"]

        # 6. Stop
        sr = await stop.call({"task_id": task_id}, None)
        assert not sr.get("is_error")

        # 7. Get — stopped
        gr3 = await get.call({"task_id": task_id}, None)
        assert "stopped" in gr3["text"]
