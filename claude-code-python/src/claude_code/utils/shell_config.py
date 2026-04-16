"""
Shell configuration file utilities – detect shell type and locate config files.
Ported from shellConfig.ts.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Literal, Optional


ShellType = Literal["bash", "zsh", "fish", "unknown"]
CLAUDE_ALIAS_REGEX = re.compile(r"^\s*alias\s+claude\s*=")


def detect_shell() -> ShellType:
    """Detect the current shell via $SHELL env var. Falls back to 'bash'."""
    shell_env = os.environ.get("SHELL", "")
    name = Path(shell_env).name.lower() if shell_env else ""
    if "zsh" in name:
        return "zsh"
    if "fish" in name:
        return "fish"
    if "bash" in name:
        return "bash"
    return "bash"


def get_shell_config_paths(
    env: Optional[dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
) -> dict[str, str]:
    """
    Return shell → config-file-path mapping.

    Respects ZDOTDIR for zsh. Mirrors TS getShellConfigPaths.
    """
    _env = env if env is not None else dict(os.environ)
    home = homedir or str(Path.home())
    zsh_dir = _env.get("ZDOTDIR") or home
    return {
        "zsh": str(Path(zsh_dir) / ".zshrc"),
        "bash": str(Path(home) / ".bashrc"),
        "fish": str(Path(home) / ".config" / "fish" / "config.fish"),
    }


def get_shell_config_path(
    shell: ShellType,
    env: Optional[dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
) -> Optional[str]:
    """Return the config file path for the given shell, or None for 'unknown'."""
    if shell == "unknown":
        return None
    return get_shell_config_paths(env=env, homedir=homedir).get(shell)


def filter_claude_aliases(lines: list[str], installer_path: Optional[str] = None) -> dict:
    """
    Remove installer-created claude aliases from lines.

    Only removes aliases whose target equals installer_path (when given).
    Returns {"filtered": list[str], "had_alias": bool}.
    """
    had_alias = False
    filtered: list[str] = []
    for line in lines:
        if CLAUDE_ALIAS_REGEX.match(line):
            m = re.search(r'alias\s+claude\s*=\s*["\']([^"\']+)["\']', line)
            if not m:
                m = re.search(r"alias\s+claude\s*=\s*([^#\n]+)", line)
            if m and installer_path and m.group(1).strip() == installer_path:
                had_alias = True
                continue
        filtered.append(line)
    return {"filtered": filtered, "had_alias": had_alias}


def read_file_lines(file_path: str) -> Optional[list[str]]:
    """Read a file into lines. Returns None if the file is inaccessible."""
    try:
        return Path(file_path).read_text(encoding="utf-8").split("\n")
    except OSError:
        return None


def write_file_lines(file_path: str, lines: list[str]) -> None:
    """Write lines to a file, creating parent dirs as needed."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def find_claude_alias(
    env: Optional[dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
) -> Optional[str]:
    """
    Scan shell config files for a claude alias.

    Returns the alias target string, or None if not found.
    """
    configs = get_shell_config_paths(env=env, homedir=homedir)
    _target_re = re.compile(r'alias\s+claude=["\']?([^"\'\\s]+)')
    for config_path in configs.values():
        lines = read_file_lines(config_path)
        if lines is None:
            continue
        for line in lines:
            if CLAUDE_ALIAS_REGEX.match(line):
                m = _target_re.search(line)
                if m:
                    return m.group(1)
    return None


def find_valid_claude_alias(
    env: Optional[dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
) -> Optional[str]:
    """Like find_claude_alias, but verifies the target file exists."""
    alias_target = find_claude_alias(env=env, homedir=homedir)
    if not alias_target:
        return None
    home = homedir or str(Path.home())
    expanded = alias_target.replace("~", home) if alias_target.startswith("~") else alias_target
    try:
        s = os.stat(expanded)
        if stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode):
            return alias_target
    except OSError:
        pass
    return None
