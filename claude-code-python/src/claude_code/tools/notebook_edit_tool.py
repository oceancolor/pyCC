"""
Notebook Edit tool
原始 TS: src/tools/NotebookEditTool/NotebookEditTool.ts

Edit Jupyter notebook cells (.ipynb).
"""
from __future__ import annotations

import json
import os
from typing import Any, Literal, Optional

from claude_code.constants.tools import NOTEBOOK_EDIT_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext, ValidationResult, ValidationResultFail, ValidationResultOk

DESCRIPTION = "Replace the contents of a specific cell in a Jupyter notebook."
PROMPT = """Completely replaces the contents of a specific cell in a Jupyter notebook (.ipynb file) with new source. Jupyter notebooks are interactive documents that combine code, text, and visualizations, commonly used for data analysis and scientific computing. The notebook_path parameter must be an absolute path, not a relative path. The cell_number is 0-indexed. Use edit_mode=insert to add a new cell at the index specified by cell_number. Use edit_mode=delete to delete the cell at the index specified by cell_number."""


class NotebookEditTool(Tool):
    """
    Edit Jupyter notebook cells.
    原始 TS: src/tools/NotebookEditTool/NotebookEditTool.ts
    """

    name = NOTEBOOK_EDIT_TOOL_NAME
    search_hint = "modify cells in Jupyter notebooks"
    max_result_size_chars = 100_000

    async def description(self) -> str:
        return DESCRIPTION

    async def prompt(self) -> str:
        return PROMPT

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "The absolute path to the Jupyter notebook file (.ipynb)",
                },
                "cell_number": {
                    "type": "integer",
                    "description": "The 0-indexed cell number to edit",
                },
                "new_source": {
                    "type": "string",
                    "description": "The new source code for the cell",
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown"],
                    "description": "The type of cell (default: code)",
                },
                "edit_mode": {
                    "type": "string",
                    "enum": ["replace", "insert", "delete"],
                    "description": "How to edit the cell (default: replace)",
                },
            },
            "required": ["notebook_path", "cell_number", "new_source"],
        }

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        notebook_path = input_data.get("notebook_path", "")
        if not notebook_path or not os.path.isabs(notebook_path):
            return ValidationResultFail(
                result=False,
                message="notebook_path must be an absolute path",
                error_code=1,
            )
        if not notebook_path.endswith(".ipynb"):
            return ValidationResultFail(
                result=False,
                message="notebook_path must be a .ipynb file",
                error_code=1,
            )
        return ValidationResultOk()

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        notebook_path: str = os.path.expanduser(input_data["notebook_path"])
        cell_number: int = int(input_data["cell_number"])
        new_source: str = input_data.get("new_source", "")
        cell_type: str = input_data.get("cell_type", "code")
        edit_mode: str = input_data.get("edit_mode", "replace")

        # Read notebook
        if not os.path.exists(notebook_path):
            return {"type": "text", "text": f"Error: Notebook not found: {notebook_path}"}

        try:
            with open(notebook_path, encoding="utf-8") as f:
                nb = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            return {"type": "text", "text": f"Error reading notebook: {e}"}

        cells = nb.get("cells", [])

        if edit_mode == "delete":
            if cell_number < 0 or cell_number >= len(cells):
                return {"type": "text", "text": f"Error: Cell {cell_number} out of range (0-{len(cells)-1})"}
            del cells[cell_number]
            action = f"Deleted cell {cell_number}"

        elif edit_mode == "insert":
            new_cell = {
                "cell_type": cell_type,
                "source": new_source,
                "metadata": {},
                "outputs": [] if cell_type == "code" else None,
                "execution_count": None if cell_type == "code" else None,
            }
            if cell_type == "code":
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            else:
                new_cell.pop("outputs", None)
                new_cell.pop("execution_count", None)

            cells.insert(cell_number, new_cell)
            action = f"Inserted new {cell_type} cell at position {cell_number}"

        else:  # replace
            if cell_number < 0 or cell_number >= len(cells):
                return {"type": "text", "text": f"Error: Cell {cell_number} out of range (0-{len(cells)-1})"}
            cells[cell_number]["source"] = new_source
            if "cell_type" in input_data:
                cells[cell_number]["cell_type"] = cell_type
            # Clear outputs when source changes
            if cells[cell_number].get("cell_type") == "code":
                cells[cell_number]["outputs"] = []
                cells[cell_number]["execution_count"] = None
            action = f"Updated cell {cell_number}"

        nb["cells"] = cells

        try:
            with open(notebook_path, "w", encoding="utf-8") as f:
                json.dump(nb, f, indent=1, ensure_ascii=False)
        except OSError as e:
            return {"type": "text", "text": f"Error writing notebook: {e}"}

        return {
            "type": "text",
            "text": f"Successfully updated {notebook_path}. {action}.",
        }

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        if input_data and "notebook_path" in input_data:
            return input_data["notebook_path"]
        return "notebook"
