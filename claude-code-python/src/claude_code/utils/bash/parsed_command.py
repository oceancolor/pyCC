"""
parsed_command.py - Parsed command interface and implementations.

Port of TypeScript ParsedCommand.ts.
"""

import re
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .tree_sitter_analysis import TreeSitterAnalysis


class OutputRedirection:
    """Represents an output redirection."""
    def __init__(self, target: str, operator: str):
        self.target = target
        self.operator = operator  # '>' or '>>'


class IParsedCommand:
    """Interface for parsed command implementations."""

    @property
    def original_command(self) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.original_command

    def get_pipe_segments(self) -> List[str]:
        raise NotImplementedError

    def without_output_redirections(self) -> str:
        raise NotImplementedError

    def get_output_redirections(self) -> List[OutputRedirection]:
        raise NotImplementedError

    def get_tree_sitter_analysis(self) -> Optional['TreeSitterAnalysis']:
        raise NotImplementedError


class RegexParsedCommand(IParsedCommand):
    """
    Regex-based fallback implementation using shell-quote parser.
    Used when tree-sitter is not available.
    """

    def __init__(self, command: str):
        self._original_command = command

    @property
    def original_command(self) -> str:
        return self._original_command

    def __str__(self) -> str:
        return self._original_command

    def get_pipe_segments(self) -> List[str]:
        try:
            from .parser import split_command_with_operators
            parts = split_command_with_operators(self._original_command)
            segments: List[str] = []
            current_segment: List[str] = []

            for part in parts:
                if part == '|':
                    if current_segment:
                        segments.append(' '.join(current_segment))
                        current_segment = []
                else:
                    current_segment.append(part)

            if current_segment:
                segments.append(' '.join(current_segment))

            return segments if segments else [self._original_command]
        except Exception:
            return [self._original_command]

    def without_output_redirections(self) -> str:
        if '>' not in self._original_command:
            return self._original_command
        cmd, redirections = _extract_output_redirections(self._original_command)
        return cmd if redirections else self._original_command

    def get_output_redirections(self) -> List[OutputRedirection]:
        _, redirections = _extract_output_redirections(self._original_command)
        return redirections

    def get_tree_sitter_analysis(self) -> None:
        return None


def _extract_output_redirections(command: str) -> Tuple[str, List[OutputRedirection]]:
    """Extract output redirections from a command string."""
    redirections: List[OutputRedirection] = []
    # Simple regex-based extraction of >> and > redirections
    pattern = re.compile(r'\s*(>>?)\s*(\S+)')
    result = command
    offset = 0

    for m in pattern.finditer(command):
        op = m.group(1)
        target = m.group(2)
        if not target.startswith('&'):
            redirections.append(OutputRedirection(target=target, operator=op))

    if redirections:
        # Remove redirections from command (simple approach)
        result = re.sub(r'\s*>>?\s*\S+', '', command).strip()

    return result, redirections


class ParsedCommand:
    """
    ParsedCommand provides methods for working with shell commands.
    Uses tree-sitter when available for quote-aware parsing,
    falls back to regex-based parsing otherwise.
    """

    _last_cmd: Optional[str] = None
    _last_result: Optional[IParsedCommand] = None

    @classmethod
    async def parse(cls, command: str) -> Optional[IParsedCommand]:
        """
        Parse a command string and return a ParsedCommand instance.
        Returns None if parsing fails completely.
        """
        if command == cls._last_cmd and cls._last_result is not None:
            return cls._last_result

        cls._last_cmd = command
        result = await cls._do_parse(command)
        cls._last_result = result
        return result

    @classmethod
    async def _do_parse(cls, command: str) -> Optional[IParsedCommand]:
        if not command:
            return None

        # Attempt tree-sitter parse
        try:
            from .parser import parse_command, build_parsed_command_from_root
            data = await parse_command(command)
            if data:
                return build_parsed_command_from_root(command, data['root_node'])
        except Exception:
            pass

        # Fallback to regex implementation
        return RegexParsedCommand(command)
