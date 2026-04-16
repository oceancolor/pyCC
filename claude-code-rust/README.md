# Claude Code Rust Port

A Rust reimplementation of Claude Code's TypeScript source.

## Project Structure

```
claude-code-rust/
├── Cargo.toml            # workspace configuration
├── README.md
└── crates/
    ├── claude-types/     # Core type definitions (TS: types/)
    ├── claude-constants/ # Constants (TS: constants/)
    ├── claude-utils/     # Utility functions (TS: utils/)
    ├── claude-tools/     # Tool implementations (TS: tools/)
    ├── claude-services/  # Service layer (TS: services/)
    ├── claude-commands/  # Command layer (TS: commands/)
    └── claude-cli/       # CLI entrypoint (TS: cli/ + entrypoints/)
```

## Development Status

See [PROGRESS.md](PROGRESS.md) for detailed progress tracking.

## Building

```bash
cargo build
```

## Running

```bash
cargo run -p claude-cli
```

## Source Reference

Original TypeScript source: `claude-code-analysis/claude-code-source/`
