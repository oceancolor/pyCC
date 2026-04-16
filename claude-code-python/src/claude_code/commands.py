"""
Command registry. Ported from commands.ts (754 lines → core).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

_command_registry: Optional[Dict[str, Any]] = None


def _load_commands() -> Dict[str, Any]:
    registry: Dict[str, Any] = {}

    # Import each command module lazily
    def _try_import(name: str, module_path: str, attr: str = "default"):
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cmd = getattr(mod, attr, None)
            if cmd is not None:
                cmd_name = getattr(cmd, "name", name)
                registry[cmd_name] = cmd
        except ImportError:
            pass
        except Exception:
            pass

    # Core commands
    _try_import("clear", "claude_code.commands.clear.clear")
    _try_import("compact", "claude_code.commands.compact.compact")
    _try_import("model", "claude_code.commands.model.index", "model_cmd")
    _try_import("commit", "claude_code.commands.commit", "CommitCommand")
    _try_import("review", "claude_code.commands.review", "ReviewCommand")
    _try_import("init", "claude_code.commands.init", "InitCommand")
    _try_import("advisor", "claude_code.commands.advisor", "AdvisorCommand")

    return registry


def get_commands() -> Dict[str, Any]:
    global _command_registry
    if _command_registry is None:
        _command_registry = _load_commands()
    return _command_registry


def get_command(name: str) -> Optional[Any]:
    return get_commands().get(name)


def has_command(name: str) -> bool:
    return name in get_commands()


def builtin_command_names() -> List[str]:
    return list(get_commands().keys())


def find_command(name: str) -> Optional[Any]:
    """Find command by name or alias."""
    cmds = get_commands()
    if name in cmds:
        return cmds[name]
    # Search aliases
    for cmd in cmds.values():
        aliases = getattr(cmd, "aliases", [])
        if name in (aliases or []):
            return cmd
    return None


def get_skill_tool_commands() -> List[Any]:
    """Return commands that can be used as skills."""
    return [
        cmd for cmd in get_commands().values()
        if getattr(cmd, "is_skill", False)
    ]
