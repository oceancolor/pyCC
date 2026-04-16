"""
Prompt editor utilities — open a text prompt in the user's $EDITOR.
Port of promptEditor.ts.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Editor command overrides (add wait flags for GUI editors)
# ---------------------------------------------------------------------------

_EDITOR_OVERRIDES: dict[str, str] = {
    "code": "code -w",         # VS Code: wait for file to close
    "subl": "subl --wait",     # Sublime Text: wait for file to close
    "atom": "atom --wait",     # Atom
    "idea": "idea --wait",     # IntelliJ IDEA
}

# Known GUI editors (open in separate window)
_GUI_EDITORS = {"code", "subl", "atom", "idea", "webstorm", "pycharm"}


def get_editor_command() -> Optional[str]:
    """Return the editor command from ``$VISUAL``, ``$EDITOR``, or a default.

    Returns *None* if no editor can be determined.
    """
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return editor.strip()
    # Fallback defaults by platform
    defaults = ["nano", "vi", "notepad"]
    for cmd in defaults:
        import shutil
        if shutil.which(cmd):
            return cmd
    return None


def _is_gui_editor(editor: str) -> bool:
    base = Path(editor).name.split()[0].lower()
    return base in _GUI_EDITORS


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class EditorResult:
    content: Optional[str]
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Core editor invocation
# ---------------------------------------------------------------------------

def edit_file_in_editor(file_path: str) -> EditorResult:
    """Open *file_path* in the user's configured editor and return the result.

    Returns ``EditorResult(content=None)`` when no editor is configured or
    the file does not exist.
    """
    if not os.path.exists(file_path):
        return EditorResult(content=None, error=f"File not found: {file_path}")

    editor = get_editor_command()
    if not editor:
        return EditorResult(content=None, error="No editor configured")

    # Apply override (e.g., add --wait flag)
    base_cmd = editor.split()[0]
    editor_cmd = _EDITOR_OVERRIDES.get(base_cmd, editor)
    full_cmd = f'{editor_cmd} "{file_path}"'

    try:
        result = subprocess.run(full_cmd, shell=True)
        if result.returncode != 0:
            return EditorResult(
                content=None,
                error=f"{base_cmd} exited with code {result.returncode}",
            )
        content = Path(file_path).read_text(encoding="utf-8")
        return EditorResult(content=content)
    except Exception as exc:
        logger.debug("edit_file_in_editor error: %s", exc)
        return EditorResult(content=None, error=str(exc))


# ---------------------------------------------------------------------------
# Prompt editor (temp-file based)
# ---------------------------------------------------------------------------

def open_prompt_in_editor(
    initial_text: str = "",
    suffix: str = ".txt",
) -> EditorResult:
    """Write *initial_text* to a temp file, open in ``$EDITOR``, return result.

    Strips a single trailing newline that most editors append automatically.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, encoding="utf-8", delete=False
    )
    try:
        tmp.write(initial_text)
        tmp.flush()
        tmp.close()

        result = edit_file_in_editor(tmp.name)
        if result.content is None:
            return result

        # Strip single trailing newline (common editor behaviour)
        content = result.content
        if content.endswith("\n") and not content.endswith("\n\n"):
            content = content[:-1]

        return EditorResult(content=content)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def edit_prompt_in_editor(
    current_prompt: str,
    pasted_contents: Optional[dict[int, object]] = None,
) -> EditorResult:
    """Open *current_prompt* for editing (convenience wrapper).

    *pasted_contents* is accepted for API compatibility but not expanded —
    the full pasted-content re-collapse pipeline lives in the React layer.
    """
    return open_prompt_in_editor(initial_text=current_prompt)
