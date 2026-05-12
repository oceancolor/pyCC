"""
parser.py - Bash command parser using tree-sitter.

Port of TypeScript parser.ts.
"""

import asyncio
from typing import Any, Dict, List, Optional, Union

MAX_COMMAND_LENGTH = 10000

DECLARATION_COMMANDS = {
    'export', 'declare', 'typeset', 'readonly', 'local', 'unset', 'unsetenv'
}
ARGUMENT_TYPES = {'word', 'string', 'raw_string', 'number'}
SUBSTITUTION_TYPES = {'command_substitution', 'process_substitution'}
COMMAND_TYPES = {'command', 'declaration_command'}

# Sentinel for aborted parse
PARSE_ABORTED = object()

# Cache for tree-sitter availability
_tree_sitter_available: Optional[bool] = None


class Node:
    """Tree-sitter node representation."""
    def __init__(
        self,
        type: str,
        text: str,
        start_index: int,
        end_index: int,
        children: Optional[List['Node']] = None,
    ):
        self.type = type
        self.text = text
        self.start_index = start_index
        self.end_index = end_index
        self.children: List['Node'] = children or []


class ParsedCommandData:
    """Data from a parsed command."""
    def __init__(
        self,
        root_node: Node,
        env_vars: List[str],
        command_node: Optional[Node],
        original_command: str,
    ):
        self.root_node = root_node
        self.env_vars = env_vars
        self.command_node = command_node
        self.original_command = original_command


async def ensure_initialized() -> None:
    """Awaits parser initialization. Idempotent."""
    pass  # Python: tree-sitter init is synchronous


async def parse_command(command: str) -> Optional[Dict[str, Any]]:
    """
    Parse a command string using tree-sitter if available.
    Returns None if parsing fails or tree-sitter is unavailable.
    """
    if not command or len(command) > MAX_COMMAND_LENGTH:
        return None

    try:
        import tree_sitter_bash as ts_bash
        from tree_sitter import Language, Parser

        BASH_LANGUAGE = Language(ts_bash.language())
        parser = Parser(BASH_LANGUAGE)
        tree = parser.parse(command.encode('utf-8'))
        root = tree.root_node

        def to_node(n: Any) -> Node:
            children = [to_node(c) for c in n.children]
            return Node(
                type=n.type,
                text=n.text.decode('utf-8') if isinstance(n.text, bytes) else (n.text or ''),
                start_index=n.start_byte,
                end_index=n.end_byte,
                children=children,
            )

        root_node = to_node(root)
        command_node = find_command_node(root_node, None)
        env_vars = extract_env_vars(command_node)

        return {
            'root_node': root_node,
            'env_vars': env_vars,
            'command_node': command_node,
            'original_command': command,
        }
    except ImportError:
        return None
    except Exception:
        return None


async def parse_command_raw(command: str) -> Union[Node, None, object]:
    """
    Raw parse — returns Node, None, or PARSE_ABORTED.
    """
    if not command or len(command) > MAX_COMMAND_LENGTH:
        return None

    try:
        result = await parse_command(command)
        if result is None:
            return None
        return result['root_node']
    except Exception:
        return PARSE_ABORTED


def find_command_node(node: Node, parent: Optional[Node]) -> Optional[Node]:
    """Find the command node in the AST."""
    if node.type in COMMAND_TYPES:
        return node

    if node.type == 'variable_assignment' and parent:
        for child in parent.children:
            if child.type in COMMAND_TYPES and child.start_index > node.start_index:
                return child
        return None

    if node.type == 'pipeline':
        for child in node.children:
            result = find_command_node(child, node)
            if result:
                return result
        return None

    if node.type == 'redirected_statement':
        for child in node.children:
            if child.type in COMMAND_TYPES:
                return child
        return None

    for child in node.children:
        result = find_command_node(child, node)
        if result:
            return result

    return None


def extract_env_vars(command_node: Optional[Node]) -> List[str]:
    """Extract environment variable assignments from a command node."""
    if not command_node or command_node.type != 'command':
        return []

    env_vars = []
    for child in command_node.children:
        if child.type == 'variable_assignment':
            env_vars.append(child.text)
        elif child.type in ('command_name', 'word'):
            break
    return env_vars


def extract_command_arguments(command_node: Node) -> List[str]:
    """Extract command arguments from a command node."""
    if command_node.type == 'declaration_command':
        first_child = command_node.children[0] if command_node.children else None
        if first_child and first_child.text in DECLARATION_COMMANDS:
            return [first_child.text]
        return []

    args = []
    found_command_name = False

    for child in command_node.children:
        if child.type == 'variable_assignment':
            continue

        if child.type == 'command_name' or (not found_command_name and child.type == 'word'):
            found_command_name = True
            args.append(child.text)
            continue

        if child.type in ARGUMENT_TYPES:
            args.append(_strip_quotes(child.text))
        elif child.type in SUBSTITUTION_TYPES:
            break

    return args


def _strip_quotes(text: str) -> str:
    """Strip surrounding quotes from a string."""
    if (len(text) >= 2
            and ((text[0] == '"' and text[-1] == '"')
                 or (text[0] == "'" and text[-1] == "'"))):
        return text[1:-1]
    return text


def split_command_with_operators(command: str) -> List[str]:
    """Split a command by pipe and other operators."""
    import shlex
    try:
        # Simple split on operators
        parts = []
        current = []
        for token in shlex.split(command):
            if token in ('|', '&&', '||', ';'):
                if current:
                    parts.append(' '.join(current))
                    current = []
                parts.append(token)
            else:
                current.append(token)
        if current:
            parts.append(' '.join(current))
        return parts
    except Exception:
        return [command]


def build_parsed_command_from_root(command: str, root: Node) -> 'IParsedCommand':
    """Build a ParsedCommand from a pre-parsed AST root."""
    from .parsed_command import RegexParsedCommand
    from .tree_sitter_analysis import analyze_command

    # For now, return regex fallback (tree-sitter full implementation is complex)
    return RegexParsedCommand(command)
