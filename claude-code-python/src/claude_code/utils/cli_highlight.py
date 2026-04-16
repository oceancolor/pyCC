# 原始 TS: utils/cliHighlight.ts
"""CLI 输出语法高亮（使用 rich 或 ANSI 手写）"""
from typing import Optional

try:
    from rich.syntax import Syntax
    from rich.console import Console
    _rich_available = True
except ImportError:
    _rich_available = False

_console = None


def _get_console():
    global _console
    if _console is None and _rich_available:
        from rich.console import Console
        _console = Console()
    return _console


def highlight_code(code: str, language: str = "python", theme: str = "monokai") -> str:
    """返回带 ANSI 颜色的代码字符串"""
    if not _rich_available:
        return code
    from rich.syntax import Syntax
    from rich.console import Console
    from io import StringIO
    buf = StringIO()
    c = Console(file=buf, force_terminal=True, width=120)
    c.print(Syntax(code, language, theme=theme))
    return buf.getvalue()


def print_code(code: str, language: str = "python") -> None:
    """直接打印高亮代码"""
    if _rich_available:
        c = _get_console()
        from rich.syntax import Syntax
        c.print(Syntax(code, language, theme="monokai"))
    else:
        print(code)


def highlight_json(data: str) -> str:
    return highlight_code(data, "json")


def highlight_bash(cmd: str) -> str:
    return highlight_code(cmd, "bash")
