"""
NotebookEditTool — edit a Jupyter notebook cell.
Ported from NotebookEditTool/NotebookEditTool.ts.
"""
from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional

NOTEBOOK_EDIT_TOOL_NAME = "NotebookEdit"
DESCRIPTION = "Replace the contents of a specific cell in a Jupyter notebook."


class NotebookEditTool:
    name = NOTEBOOK_EDIT_TOOL_NAME
    description = DESCRIPTION
    is_read_only = False

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {"type": "string"},
                "new_source": {"type": "string"},
                "cell_number": {"type": "integer", "minimum": 0},
                "cell_type": {"type": "string", "enum": ["code", "markdown"]},
                "edit_mode": {"type": "string", "enum": ["replace", "insert", "delete"]},
            },
            "required": ["notebook_path", "new_source"],
        }

    async def call(self, input: Dict[str, Any], context: Any = None) -> dict:
        nb_path = input.get("notebook_path", "")
        new_source = input.get("new_source", "")
        cell_number = input.get("cell_number", 0)
        cell_type = input.get("cell_type", "code")
        edit_mode = input.get("edit_mode", "replace")

        path = os.path.abspath(os.path.expanduser(nb_path))
        if not os.path.exists(path):
            return {"text": f"Error: Notebook not found: {nb_path}"}
        if not path.endswith(".ipynb"):
            return {"text": f"Error: Not a notebook: {nb_path}"}

        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)

        cells = nb.get("cells", [])
        idx = int(cell_number)

        if edit_mode == "delete":
            if idx >= len(cells):
                return {"text": f"Error: Cell index {idx} out of range (notebook has {len(cells)} cells)"}
            cells.pop(idx)
        elif edit_mode == "insert":
            new_cell = {
                "cell_type": cell_type,
                "source": list(new_source),
                "metadata": {},
                "outputs": [] if cell_type == "code" else None,
            }
            if new_cell["outputs"] is None:
                del new_cell["outputs"]
            cells.insert(idx, new_cell)
        else:  # replace
            if idx >= len(cells):
                return {"text": f"Error: Cell index {idx} out of range (notebook has {len(cells)} cells)"}
            cells[idx]["source"] = list(new_source)
            if cell_type:
                cells[idx]["cell_type"] = cell_type

        nb["cells"] = cells
        with open(path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1)

        return {"text": f"Successfully edited cell {idx} in {nb_path}"}
