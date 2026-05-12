"""
shell_completion.py - Shell completion utilities.

Port of TypeScript shellCompletion.ts.
"""

import re
from typing import Any, Dict, List, Optional


MAX_SHELL_COMPLETIONS = 15
SHELL_COMPLETION_TIMEOUT_MS = 1000
COMMAND_OPERATORS = {'|', '||', '&&', ';'}

ShellCompletionType = str  # 'command' | 'variable' | 'file'

SuggestionItem = Dict[str, Any]


def _is_command_operator(token: Any) -> bool:
    """Check if a parsed token is a command operator."""
    return (
        isinstance(token, dict)
        and 'op' in token
        and token['op'] in COMMAND_OPERATORS
    )


def _get_completion_type_from_prefix(prefix: str) -> ShellCompletionType:
    """Determine completion type based solely on prefix characteristics."""
    if prefix.startswith('$'):
        return 'variable'
    if prefix.startswith('/') or prefix.startswith('~') or prefix.startswith('.'):
        return 'file'
    if '/' in prefix:
        return 'file'
    return 'command'


def _find_last_string_token(tokens: List[Any]) -> Optional[Dict]:
    """Find the last string token and its index in parsed tokens."""
    for i in range(len(tokens) - 1, -1, -1):
        if isinstance(tokens[i], str):
            return {'token': tokens[i], 'index': i}
    return None


def _is_new_command_context(tokens: List[Any], current_token_index: int) -> bool:
    """Check if we're in a context that expects a new command."""
    if current_token_index == 0:
        return True
    if current_token_index > 0:
        prev_token = tokens[current_token_index - 1]
        return prev_token is not None and _is_command_operator(prev_token)
    return False


def _parse_input_context(input_str: str, cursor_offset: int) -> Dict:
    """Parse input to extract completion context."""
    from .shell_quote import try_parse_shell_command

    before_cursor = input_str[:cursor_offset]

    # Check for variable prefix
    var_match = re.search(r'\$[a-zA-Z_][a-zA-Z0-9_]*$', before_cursor)
    if var_match:
        return {'prefix': var_match.group(0), 'completionType': 'variable'}

    parse_result = try_parse_shell_command(before_cursor)

    if not parse_result['success']:
        tokens = before_cursor.split()
        prefix = tokens[-1] if tokens else ''
        is_first_token = len(tokens) == 1 and ' ' not in before_cursor
        completion_type = 'command' if is_first_token else _get_completion_type_from_prefix(prefix)
        return {'prefix': prefix, 'completionType': completion_type}

    last_token = _find_last_string_token(parse_result['tokens'])

    if not last_token:
        return {'prefix': '', 'completionType': 'command'}

    if before_cursor.endswith(' '):
        return {'prefix': '', 'completionType': 'file'}

    base_type = _get_completion_type_from_prefix(last_token['token'])

    if base_type in ('variable', 'file'):
        return {'prefix': last_token['token'], 'completionType': base_type}

    completion_type = (
        'command'
        if _is_new_command_context(parse_result['tokens'], last_token['index'])
        else 'file'
    )

    return {'prefix': last_token['token'], 'completionType': completion_type}


def _get_bash_completion_command(
    prefix: str,
    completion_type: ShellCompletionType,
) -> str:
    """Generate bash completion command using compgen."""
    from .shell_quote import quote

    if completion_type == 'variable':
        var_name = prefix[1:]  # Remove $
        return f"compgen -v {quote([var_name])} 2>/dev/null"
    elif completion_type == 'file':
        return (
            f"compgen -f {quote([prefix])} 2>/dev/null "
            f"| head -{MAX_SHELL_COMPLETIONS} "
            f"| while IFS= read -r f; do "
            f'[ -d "$f" ] && echo "$f/" || echo "$f "; done'
        )
    else:
        return f"compgen -c {quote([prefix])} 2>/dev/null"


def _get_zsh_completion_command(
    prefix: str,
    completion_type: ShellCompletionType,
) -> str:
    """Generate zsh completion command."""
    from .shell_quote import quote

    if completion_type == 'variable':
        var_name = prefix[1:]
        return f"print -rl -- ${{(k)parameters[(I){quote([var_name])}*]}} 2>/dev/null"
    elif completion_type == 'file':
        return (
            f"for f in {quote([prefix])}*(N[1,{MAX_SHELL_COMPLETIONS}]); "
            f"do [[ -d \"$f\" ]] && echo \"$f/\" || echo \"$f \"; done"
        )
    else:
        return f"print -rl -- ${{(k)commands[(I){quote([prefix])}*]}} 2>/dev/null"


async def _get_completions_for_shell(
    shell_type: str,
    prefix: str,
    completion_type: ShellCompletionType,
    abort_signal: Any,
) -> List[SuggestionItem]:
    """Get completions for the given shell type."""
    import asyncio
    import subprocess

    if shell_type == 'bash':
        command = _get_bash_completion_command(prefix, completion_type)
    elif shell_type == 'zsh':
        command = _get_zsh_completion_command(prefix, completion_type)
    else:
        return []

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(),
            timeout=SHELL_COMPLETION_TIMEOUT_MS / 1000,
        )

        lines = stdout.decode('utf-8', errors='replace').split('\n')
        return [
            {
                'id': text,
                'displayText': text,
                'description': None,
                'metadata': {'completionType': completion_type},
            }
            for text in lines
            if text.strip()
        ][:MAX_SHELL_COMPLETIONS]
    except Exception:
        return []


async def get_shell_completions(
    input_str: str,
    cursor_offset: int,
    abort_signal: Any = None,
) -> List[SuggestionItem]:
    """
    Get shell completions for the given input.
    Supports bash and zsh shells.
    """
    import sys

    shell_type = _detect_shell_type()

    if shell_type not in ('bash', 'zsh'):
        return []

    try:
        context = _parse_input_context(input_str, cursor_offset)

        if not context['prefix']:
            return []

        completions = await _get_completions_for_shell(
            shell_type,
            context['prefix'],
            context['completionType'],
            abort_signal,
        )

        return [
            {
                **suggestion,
                'metadata': {
                    **(suggestion.get('metadata') or {}),
                    'inputSnapshot': input_str,
                },
            }
            for suggestion in completions
        ]
    except Exception:
        return []


def _detect_shell_type() -> str:
    """Detect the current shell type."""
    import os
    shell = os.environ.get('SHELL', '')
    if 'zsh' in shell:
        return 'zsh'
    elif 'bash' in shell:
        return 'bash'
    return 'unknown'
