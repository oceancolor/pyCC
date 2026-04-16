# 原始 TS: tools/NotebookReadTool/NotebookReadTool.ts (推断，源码中未独立存在)
"""
NotebookReadTool — 读取 Jupyter Notebook (.ipynb) 文件内容。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..tool import Tool as ToolBase, ToolUseContext
ToolResult = dict  # compat alias


class NotebookReadTool(ToolBase):
    """Read a Jupyter Notebook file and return its cells."""

    name: str = "NotebookRead"
    description: str = (
        "Read a Jupyter Notebook (.ipynb) file. Returns all cells with their "
        "type (code/markdown), source content, and outputs. Useful for "
        "understanding the structure and content of notebook files."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "The absolute path to the .ipynb notebook file.",
                }
            },
            "required": ["notebook_path"],
        }

    def run(self, notebook_path: str, **kwargs: Any) -> ToolResult:
        """Read and format a Jupyter notebook."""
        path = Path(notebook_path)

        if not path.exists():
            return ToolResult(
                content=[{"type": "text", "text": f"Error: File not found: {notebook_path}"}],
                is_error=True,
            )

        if path.suffix != ".ipynb":
            return ToolResult(
                content=[{"type": "text", "text": f"Error: Not a notebook file: {notebook_path}"}],
                is_error=True,
            )

        try:
            with open(path, "r", encoding="utf-8") as f:
                nb = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return ToolResult(
                content=[{"type": "text", "text": f"Error reading notebook: {e}"}],
                is_error=True,
            )

        cells = nb.get("cells", [])
        formatted = self._format_cells(cells)
        return ToolResult(
            content=[{"type": "text", "text": formatted}]
        )

    def _format_cells(self, cells: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for i, cell in enumerate(cells):
            cell_type = cell.get("cell_type", "unknown")
            source = cell.get("source", [])
            if isinstance(source, list):
                source = "".join(source)
            outputs = cell.get("outputs", [])

            parts.append(f"## Cell {i + 1} [{cell_type}]")
            parts.append(source or "(empty)")

            if outputs:
                parts.append("### Outputs")
                for out in outputs:
                    out_type = out.get("output_type", "")
                    if out_type == "stream":
                        text = "".join(out.get("text", []))
                        parts.append(f"[stream] {text}")
                    elif out_type in ("execute_result", "display_data"):
                        data = out.get("data", {})
                        if "text/plain" in data:
                            plain = "".join(data["text/plain"])
                            parts.append(f"[result] {plain}")
                    elif out_type == "error":
                        parts.append(f"[error] {out.get('ename')}: {out.get('evalue')}")
            parts.append("")

        return "\n".join(parts) if parts else "Notebook has no cells."
