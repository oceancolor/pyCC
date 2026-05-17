"""GrepTool prompt constants. Ported from GrepTool/prompt.ts"""

GREP_TOOL_NAME = "Grep"

# Keep references as plain strings to avoid circular imports with AgentTool/BashTool.
_AGENT_TOOL_NAME = "Task"
_BASH_TOOL_NAME = "Bash"


def get_description() -> str:
    return (
        f"A powerful search tool built on ripgrep\n\n"
        f"  Usage:\n"
        f"  - ALWAYS use {GREP_TOOL_NAME} for search tasks. NEVER invoke `grep` or `rg` as a "
        f"{_BASH_TOOL_NAME} command. The {GREP_TOOL_NAME} tool has been optimized for correct "
        f"permissions and access.\n"
        f'  - Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")\n'
        f'  - Filter files with glob parameter (e.g., "*.js", "**/*.tsx") or type parameter '
        f'(e.g., "js", "py", "rust")\n'
        f'  - Output modes: "content" shows matching lines, "files_with_matches" shows only '
        f'file paths (default), "count" shows match counts\n'
        f"  - Use {_AGENT_TOOL_NAME} tool for open-ended searches requiring multiple rounds\n"
        f"  - Pattern syntax: Uses ripgrep (not grep) - literal braces need escaping "
        f"(use `interface\\{{\\}}` to find `interface{{}}` in Go code)\n"
        f"  - Multiline matching: By default patterns match within single lines only. For "
        f"cross-line patterns like `struct \\{{[\\s\\S]*?field`, use `multiline: true`\n"
    )
