"""
Ported from: commands/keybindings/keybindings.ts

/keybindings command — create (if absent) a keybindings config file from
a template and open it in the user's editor.  Falls back gracefully when
the keybinding customization feature flag is disabled.
"""
from __future__ import annotations

import os
from typing import Dict


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _is_keybinding_customization_enabled() -> bool:
    try:
        from claude_code.keybindings.load_user_bindings import (  # type: ignore[import]
            is_keybinding_customization_enabled,
        )
        return is_keybinding_customization_enabled()
    except ImportError:
        # Default to enabled in the Python port so the command is useful
        return True


def _get_keybindings_path() -> str:
    try:
        from claude_code.keybindings.load_user_bindings import get_keybindings_path  # type: ignore[import]
        return get_keybindings_path()
    except ImportError:
        return os.path.join(os.path.expanduser("~"), ".claude", "keybindings.json")


def _generate_keybindings_template() -> str:
    try:
        from claude_code.keybindings.template import generate_keybindings_template  # type: ignore[import]
        return generate_keybindings_template()
    except ImportError:
        return """\
{
  // Claude Code keybindings
  // Each entry maps a key sequence to a command action.
  // Example:
  //   { "key": "ctrl+k", "command": "clear" }
  "bindings": []
}
"""


async def _edit_file_in_editor(path: str) -> Dict[str, object]:
    """
    Open *path* in the user's $EDITOR.  Returns ``{"error": None}`` on success
    or ``{"error": <message>}`` if no editor was found.
    """
    try:
        from claude_code.utils.prompt_editor import edit_file_in_editor  # type: ignore[import]
        return await edit_file_in_editor(path)
    except ImportError:
        pass

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        return {"error": "No $EDITOR configured"}

    import subprocess
    try:
        subprocess.run([editor, path], check=True)
        return {"error": None}
    except FileNotFoundError:
        return {"error": f"Editor '{editor}' not found"}
    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Handle the /keybindings command.

    Creates a keybindings file (if it does not exist) from a template and
    opens it in the editor.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    if not _is_keybinding_customization_enabled():
        return {
            "type": "text",
            "value": (
                "Keybinding customization is not enabled. "
                "This feature is currently in preview."
            ),
        }

    keybindings_path = _get_keybindings_path()
    parent_dir = os.path.dirname(keybindings_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Create the file only if it does not already exist (mirrors 'wx' flag)
    file_exists = False
    try:
        # Open with O_EXCL — fails if the file already exists
        fd = os.open(keybindings_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(_generate_keybindings_template())
    except FileExistsError:
        file_exists = True

    result = await _edit_file_in_editor(keybindings_path)
    if result.get("error"):
        verb = "Opened" if file_exists else "Created"
        return {
            "type": "text",
            "value": (
                f"{verb} {keybindings_path}. "
                f"Could not open in editor: {result['error']}"
            ),
        }

    if file_exists:
        return {
            "type": "text",
            "value": f"Opened {keybindings_path} in your editor.",
        }
    else:
        return {
            "type": "text",
            "value": f"Created {keybindings_path} with template. Opened in your editor.",
        }
