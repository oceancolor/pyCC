# Claude Code Python Port

A Python port of [Claude Code](https://github.com/anthropics/claude-code) — an AI coding assistant CLI.

## Status

🚧 **Work in Progress** — Initial port from TypeScript source.

## Installation

```bash
pip install -e ".[dev]"
```

Or with uv:
```bash
uv pip install -e ".[dev]"
```

## Quick Start

```bash
# Set API key
export ANTHROPIC_API_KEY=your-api-key

# One-shot query
claude "explain this codebase"

# Check health
claude doctor
```

## Architecture

```
src/claude_code/
├── main.py           # CLI entrypoint (click)
├── tool.py           # Tool base class
├── types/            # Type definitions (from TS types/)
│   ├── command.py    # Command types
│   ├── ids.py        # Branded ID types
│   ├── permissions.py
│   └── plugin.py
├── constants/        # Constants (from TS constants/)
│   ├── common.py     # Date/time utilities
│   ├── files.py      # Binary extensions
│   ├── messages.py
│   ├── product.py    # URLs
│   └── tools.py      # Tool names
├── utils/            # Utilities (from TS utils/)
│   ├── env_utils.py  # Environment variables
│   ├── errors.py     # Error classes
│   ├── file.py       # File operations
│   ├── format.py     # Display formatting
│   ├── shell.py      # Shell execution
│   └── model/        # Model utilities
├── tools/            # Tool implementations
│   ├── bash_tool.py
│   ├── file_read_tool.py
│   ├── file_edit_tool.py
│   ├── file_write_tool.py
│   ├── grep_tool.py
│   └── glob_tool.py
├── services/         # Service layer
│   └── api/          # Anthropic client
├── commands/         # Slash commands
└── cli/              # CLI output handling
```

## TypeScript → Python Mapping

| TypeScript | Python |
|-----------|--------|
| `interface` / `type` | `@dataclass` / `TypedDict` |
| `type union` | `Union` / `Literal` |
| `async/await` | `async/await` (asyncio) |
| `Promise<T>` | `Coroutine[Any, Any, T]` |
| `zod schema` | `pydantic BaseModel` |
| `chalk` | `rich` |
| `execa` | `asyncio.subprocess` |
| `commander` | `click` |
| `lodash.memoize` | `functools.lru_cache` |
| React/Ink components | TODO stub |
| `bun:bundle feature()` | env variable checks |

## Development

```bash
# Run tests
pytest

# Type check
mypy src/

# Lint
ruff check src/
```
