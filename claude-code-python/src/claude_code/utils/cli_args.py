# 原始 TS: utils/cliArgs.ts
"""CLI 参数解析工具"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ParsedArgs:
    query: Optional[str] = None
    model: Optional[str] = None
    print_mode: bool = False
    debug: bool = False
    verbose: bool = False
    no_interactive: bool = False
    output_format: str = "text"
    max_turns: Optional[int] = None
    resume: Optional[str] = None
    system_prompt: Optional[str] = None
    version: bool = False
    help: bool = False
    subcommand: Optional[str] = None
    extra: List[str] = field(default_factory=list)


def parse_args(argv: Optional[List[str]] = None) -> ParsedArgs:
    """简单的 CLI 参数解析（不依赖 click）"""
    args = argv if argv is not None else sys.argv[1:]
    result = ParsedArgs()
    i = 0
    positional = []
    while i < len(args):
        a = args[i]
        if a in ("--version", "-v", "-V"):
            result.version = True
        elif a in ("--help", "-h"):
            result.help = True
        elif a in ("--print", "-p"):
            result.print_mode = True
        elif a == "--debug":
            result.debug = True
        elif a in ("--verbose", "--no-interactive"):
            setattr(result, a.lstrip("-").replace("-", "_"), True)
        elif a in ("--model", "-m") and i + 1 < len(args):
            i += 1
            result.model = args[i]
        elif a == "--resume" and i + 1 < len(args):
            i += 1
            result.resume = args[i]
        elif a == "--system-prompt" and i + 1 < len(args):
            i += 1
            result.system_prompt = args[i]
        elif a == "--max-turns" and i + 1 < len(args):
            i += 1
            try:
                result.max_turns = int(args[i])
            except ValueError:
                pass
        elif a.startswith("-"):
            result.extra.append(a)
        else:
            positional.append(a)
        i += 1

    if positional:
        # 第一个非选项参数可能是子命令
        known_subcommands = {"doctor", "version", "config", "login", "logout", "help",
                              "clear", "status", "cost", "compact", "resume", "bug"}
        if positional[0] in known_subcommands:
            result.subcommand = positional[0]
            result.extra.extend(positional[1:])
        else:
            result.query = " ".join(positional)

    return result
