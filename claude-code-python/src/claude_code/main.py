"""
Main CLI entrypoint
原始 TS: src/entrypoints/cli.tsx + src/main.tsx

commander/yargs → click
bun:bundle feature() → TODO stubs
React/Ink REPL UI → TODO stub
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

import click

from claude_code._version import __version__


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="claude", message="%(version)s (Claude Code Python)")
@click.option("--model", "-m", envvar="ANTHROPIC_MODEL", help="Model to use")
@click.option("--debug", is_flag=True, default=False, help="Enable debug output")
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose output")
@click.option("--no-interactive", is_flag=True, default=False, help="Run in non-interactive mode")
@click.option("--print", "-p", "print_mode", is_flag=True, default=False, help="Print mode: one-shot query")
@click.option("--output-format", type=click.Choice(["text", "json", "stream-json"]), default="text")
@click.option("--max-turns", type=int, default=None, help="Maximum number of turns")
@click.argument("query", nargs=-1, required=False)
@click.pass_context
def cli(
    ctx: click.Context,
    model: Optional[str],
    debug: bool,
    verbose: bool,
    no_interactive: bool,
    print_mode: bool,
    output_format: str,
    max_turns: Optional[int],
    query: tuple[str, ...],
) -> None:
    """
    Claude Code - AI coding assistant

    Start an interactive session or run a one-shot query.
    """
    if ctx.invoked_subcommand is not None:
        return

    if query or print_mode:
        # Non-interactive one-shot mode
        query_str = " ".join(query) if query else ""
        if not query_str:
            click.echo("Error: query required in print mode", err=True)
            sys.exit(1)
        asyncio.run(_run_print_mode(query_str, model=model, debug=debug, verbose=verbose))
    else:
        # Interactive REPL mode
        from claude_code.repl import run_repl
        asyncio.run(run_repl(
            model=model or "claude-opus-4-5",
            debug=debug,
        ))


async def _run_print_mode(
    query: str,
    *,
    model: Optional[str] = None,
    debug: bool = False,
    verbose: bool = False,
    max_turns: Optional[int] = None,
) -> None:
    """
    Run a single query in print/non-interactive mode.
    原始 TS: headless query execution
    TODO: Wire up full tool loop
    """
    from claude_code.services.api import get_anthropic_client, get_main_loop_model
    from claude_code.utils.model import get_main_loop_model as _get_model

    model_name = model or _get_model()

    try:
        client = get_anthropic_client(model=model_name)
    except (ValueError, NotImplementedError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if debug:
        click.echo(f"Using model: {model_name}", err=True)

    try:
        response = client.messages.create(
            model=model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": query}],
        )
        text_blocks = [
            block.text
            for block in response.content
            if hasattr(block, "text")
        ]
        click.echo("\n".join(text_blocks))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("version")
def version_cmd() -> None:
    """Print version information."""
    click.echo(f"{__version__} (Claude Code Python)")


@cli.command("doctor")
def doctor() -> None:
    """Check the health of Claude Code installation."""
    click.echo("Claude Code Python port - health check")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        click.echo(f"✓ ANTHROPIC_API_KEY is set ({api_key[:8]}...)")
    else:
        click.echo("✗ ANTHROPIC_API_KEY is not set")
    click.echo(f"Python: {sys.version}")
    click.echo(f"Version: {__version__}")


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
