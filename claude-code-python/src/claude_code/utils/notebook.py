"""Jupyter notebook utilities for Claude Code."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

LARGE_OUTPUT_THRESHOLD = 10_000


@dataclass
class NotebookOutputImage:
    image_data: str
    media_type: str  # "image/png" | "image/jpeg"


@dataclass
class NotebookCellSourceOutput:
    output_type: str
    text: Optional[str] = None
    image: Optional[NotebookOutputImage] = None


@dataclass
class NotebookCellSource:
    cell_type: str   # "code" | "markdown" | "raw"
    source: str
    cell_id: str
    language: Optional[str] = None
    execution_count: Optional[int] = None
    outputs: Optional[List[NotebookCellSourceOutput]] = None



def _is_large_outputs(outputs: List[Optional[NotebookCellSourceOutput]]) -> bool:
    size = 0
    for o in outputs:
        if o is None:
            continue
        size += len(o.text or "") + len(
            (o.image.image_data if o.image else "") or ""
        )
        if size > LARGE_OUTPUT_THRESHOLD:
            return True
    return False


def _process_output_text(text: Union[str, List[str], None]) -> str:
    if not text:
        return ""
    raw = "".join(text) if isinstance(text, list) else text
    # Truncate very long outputs (mirrors BashTool formatOutput)
    if len(raw) > LARGE_OUTPUT_THRESHOLD:
        half = LARGE_OUTPUT_THRESHOLD // 2
        return raw[:half] + "\n... [truncated] ...\n" + raw[-half:]
    return raw


def _extract_image(data: Dict[str, Any]) -> Optional[NotebookOutputImage]:
    for mime_type in ("image/png", "image/jpeg"):
        if isinstance(data.get(mime_type), str):
            return NotebookOutputImage(
                image_data=re.sub(r"\s", "", data[mime_type]),
                media_type=mime_type,
            )
    return None


def _process_output(output: Dict[str, Any]) -> Optional[NotebookCellSourceOutput]:
    output_type = output.get("output_type", "")

    if output_type == "stream":
        return NotebookCellSourceOutput(
            output_type=output_type,
            text=_process_output_text(output.get("text")),
        )

    if output_type in ("execute_result", "display_data"):
        data: Dict[str, Any] = output.get("data") or {}
        return NotebookCellSourceOutput(
            output_type=output_type,
            text=_process_output_text(data.get("text/plain")),
            image=_extract_image(data),
        )

    if output_type == "error":
        traceback = output.get("traceback") or []
        combined = (
            f"{output.get('ename', '')}: {output.get('evalue', '')}\n"
            + "\n".join(traceback)
        )
        return NotebookCellSourceOutput(
            output_type=output_type,
            text=_process_output_text(combined),
        )

    return None


def _process_cell(
    cell: Dict[str, Any],
    index: int,
    code_language: str,
    include_large_outputs: bool,
) -> NotebookCellSource:
    cell_id = cell.get("id") or f"cell-{index}"
    source_raw = cell.get("source", "")
    source = "".join(source_raw) if isinstance(source_raw, list) else source_raw
    cell_type = cell.get("cell_type", "code")
    cell_data = NotebookCellSource(cell_type=cell_type, source=source, cell_id=cell_id)
    if cell_type == "code":
        cell_data.language = code_language
        cell_data.execution_count = cell.get("execution_count") or None
    raw_outputs: List[Dict[str, Any]] = cell.get("outputs") or []
    if cell_type == "code" and raw_outputs:
        outputs = [_process_output(o) for o in raw_outputs]
        if not include_large_outputs and _is_large_outputs(outputs):
            cell_data.outputs = [NotebookCellSourceOutput(
                output_type="stream",
                text=(f"Outputs are too large to include. Use bash with: "
                      f"cat <notebook_path> | python3 -c \""
                      f"import json,sys; "
                      f"print(json.load(sys.stdin)['cells'][{index}]['outputs'])\""),
            )]
        else:
            cell_data.outputs = [o for o in outputs if o is not None]
    return cell_data


def read_notebook(
    notebook_path: str,
    cell_id: Optional[str] = None,
) -> List[NotebookCellSource]:
    """Read and parse a .ipynb file. If cell_id given, return only that cell."""
    path = Path(notebook_path).expanduser().resolve()
    content = path.read_text(encoding="utf-8")
    notebook: Dict[str, Any] = json.loads(content)

    language: str = (
        (notebook.get("metadata") or {})
        .get("language_info", {})
        .get("name", "python")
    )

    cells: List[Dict[str, Any]] = notebook.get("cells") or []

    if cell_id is not None:
        for idx, cell in enumerate(cells):
            if (cell.get("id") or f"cell-{idx}") == cell_id:
                return [_process_cell(cell, idx, language, True)]
        raise ValueError(f'Cell with ID "{cell_id}" not found in notebook')

    return [_process_cell(cell, i, language, False) for i, cell in enumerate(cells)]


def notebook_to_text(notebook_cells: List[NotebookCellSource]) -> str:
    """
    Extract all cell contents as a single text string.

    Code cells include their outputs; markdown/raw cells are plain text.
    """
    parts: List[str] = []

    for cell in notebook_cells:
        header = f"[{cell.cell_type.upper()} cell {cell.cell_id}]"
        if cell.cell_type == "code" and cell.language:
            header += f" ({cell.language})"
        parts.append(header)
        parts.append(cell.source)

        if cell.outputs:
            for out in cell.outputs:
                if out.text:
                    parts.append(f"--- output ---\n{out.text}")
                if out.image:
                    parts.append(f"--- image ({out.image.media_type}) ---")

        parts.append("")  # blank line between cells

    return "\n".join(parts)


def parse_cell_id(cell_id: str) -> Optional[int]:
    """Parse a 'cell-N' style cell ID into its integer index."""
    match = re.match(r"^cell-(\d+)$", cell_id)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return None
