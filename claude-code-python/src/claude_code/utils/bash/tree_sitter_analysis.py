"""
tree_sitter_analysis.py - Tree-sitter AST analysis utilities for bash command security validation.

Port of TypeScript treeSitterAnalysis.ts.
"""

from typing import Any, Dict, List, Optional, Tuple


class QuoteContext:
    """Quote context information from the AST."""
    def __init__(
        self,
        with_double_quotes: str,
        fully_unquoted: str,
        unquoted_keep_quote_chars: str,
    ):
        self.with_double_quotes = with_double_quotes
        self.fully_unquoted = fully_unquoted
        self.unquoted_keep_quote_chars = unquoted_keep_quote_chars


class CompoundStructure:
    """Compound command structure."""
    def __init__(
        self,
        has_compound_operators: bool,
        has_pipeline: bool,
        has_subshell: bool,
        has_command_group: bool,
        operators: List[str],
        segments: List[str],
    ):
        self.has_compound_operators = has_compound_operators
        self.has_pipeline = has_pipeline
        self.has_subshell = has_subshell
        self.has_command_group = has_command_group
        self.operators = operators
        self.segments = segments


class DangerousPatterns:
    """Dangerous patterns found in the command."""
    def __init__(
        self,
        has_command_substitution: bool,
        has_process_substitution: bool,
        has_parameter_expansion: bool,
        has_heredoc: bool,
        has_comment: bool,
    ):
        self.has_command_substitution = has_command_substitution
        self.has_process_substitution = has_process_substitution
        self.has_parameter_expansion = has_parameter_expansion
        self.has_heredoc = has_heredoc
        self.has_comment = has_comment


class TreeSitterAnalysis:
    """Complete tree-sitter analysis of a command."""
    def __init__(
        self,
        quote_context: QuoteContext,
        compound_structure: CompoundStructure,
        has_actual_operator_nodes: bool,
        dangerous_patterns: DangerousPatterns,
    ):
        self.quote_context = quote_context
        self.compound_structure = compound_structure
        self.has_actual_operator_nodes = has_actual_operator_nodes
        self.dangerous_patterns = dangerous_patterns


class _Node:
    """Internal tree-sitter node representation."""
    def __init__(self, data: Any):
        self._data = data

    @property
    def type(self) -> str:
        return getattr(self._data, 'type', '')

    @property
    def text(self) -> str:
        t = getattr(self._data, 'text', b'')
        if isinstance(t, bytes):
            return t.decode('utf-8', errors='replace')
        return t or ''

    @property
    def start_index(self) -> int:
        return getattr(self._data, 'start_byte', 0)

    @property
    def end_index(self) -> int:
        return getattr(self._data, 'end_byte', 0)

    @property
    def children(self) -> List['_Node']:
        children = getattr(self._data, 'children', [])
        return [_Node(c) for c in children if c]


Span = Tuple[int, int]


def _collect_quote_spans(node: _Node, out: Dict[str, List[Span]], in_double: bool) -> None:
    """Single-pass collection of all quote-related spans."""
    ntype = node.type

    if ntype == 'raw_string':
        out['raw'].append((node.start_index, node.end_index))
        return
    if ntype == 'ansi_c_string':
        out['ansiC'].append((node.start_index, node.end_index))
        return
    if ntype == 'string':
        if not in_double:
            out['double'].append((node.start_index, node.end_index))
        for child in node.children:
            _collect_quote_spans(child, out, True)
        return
    if ntype == 'heredoc_redirect':
        is_quoted = False
        for child in node.children:
            if child.type == 'heredoc_start':
                first = child.text[0] if child.text else ''
                is_quoted = first in ("'", '"', '\\')
                break
        if is_quoted:
            out['heredoc'].append((node.start_index, node.end_index))
            return

    for child in node.children:
        _collect_quote_spans(child, out, in_double)


def _build_position_set(spans: List[Span]) -> set:
    """Build a set of all character positions covered by the given spans."""
    positions = set()
    for start, end in spans:
        for i in range(start, end):
            positions.add(i)
    return positions


def _drop_contained_spans(spans: List[Tuple]) -> List[Tuple]:
    """Drop spans fully contained within another span."""
    return [
        s for i, s in enumerate(spans)
        if not any(
            j != i
            and other[0] <= s[0]
            and other[1] >= s[1]
            and (other[0] < s[0] or other[1] > s[1])
            for j, other in enumerate(spans)
        )
    ]


def _remove_spans(command: str, spans: List[Span]) -> str:
    """Removes spans from a string."""
    if not spans:
        return command

    sorted_spans = sorted(_drop_contained_spans(list(spans)), key=lambda s: s[0], reverse=True)
    result = command
    for start, end in sorted_spans:
        result = result[:start] + result[end:]
    return result


def _replace_spans_keep_quotes(
    command: str,
    spans: List[Tuple[int, int, str, str]],
) -> str:
    """Replaces spans with just the quote delimiters."""
    if not spans:
        return command

    sorted_spans = sorted(_drop_contained_spans(list(spans)), key=lambda s: s[0], reverse=True)
    result = command
    for start, end, open_q, close_q in sorted_spans:
        result = result[:start] + open_q + close_q + result[end:]
    return result


def extract_quote_context(root_node: Any, command: str) -> QuoteContext:
    """Extract quote context from the tree-sitter AST."""
    node = _Node(root_node)
    spans_dict: Dict[str, List[Span]] = {'raw': [], 'ansiC': [], 'double': [], 'heredoc': []}
    _collect_quote_spans(node, spans_dict, False)

    single_quote_spans = spans_dict['raw']
    ansi_c_spans = spans_dict['ansiC']
    double_quote_spans = spans_dict['double']
    quoted_heredoc_spans = spans_dict['heredoc']
    all_quote_spans = single_quote_spans + ansi_c_spans + double_quote_spans + quoted_heredoc_spans

    single_quote_set = _build_position_set(single_quote_spans + ansi_c_spans + quoted_heredoc_spans)
    double_quote_delim_set = set()
    for start, end in double_quote_spans:
        double_quote_delim_set.add(start)
        double_quote_delim_set.add(end - 1)

    with_double_quotes = ''
    for i, ch in enumerate(command):
        if i in single_quote_set:
            continue
        if i in double_quote_delim_set:
            continue
        with_double_quotes += ch

    fully_unquoted = _remove_spans(command, all_quote_spans)

    spans_with_quote_chars: List[Tuple[int, int, str, str]] = []
    for start, end in single_quote_spans:
        spans_with_quote_chars.append((start, end, "'", "'"))
    for start, end in ansi_c_spans:
        spans_with_quote_chars.append((start, end, "$'", "'"))
    for start, end in double_quote_spans:
        spans_with_quote_chars.append((start, end, '"', '"'))
    for start, end in quoted_heredoc_spans:
        spans_with_quote_chars.append((start, end, '', ''))

    unquoted_keep_quote_chars = _replace_spans_keep_quotes(command, spans_with_quote_chars)

    return QuoteContext(
        with_double_quotes=with_double_quotes,
        fully_unquoted=fully_unquoted,
        unquoted_keep_quote_chars=unquoted_keep_quote_chars,
    )


def extract_compound_structure(root_node: Any, command: str) -> CompoundStructure:
    """Extract compound command structure from the AST."""
    node = _Node(root_node)
    operators: List[str] = []
    segments: List[str] = []
    has_subshell = False
    has_command_group = False
    has_pipeline = False

    def walk_top_level(n: _Node) -> None:
        nonlocal has_subshell, has_command_group, has_pipeline

        for child in n.children:
            ct = child.type
            if ct == 'list':
                for list_child in child.children:
                    lct = list_child.type
                    if lct in ('&&', '||'):
                        operators.append(lct)
                    elif lct in ('list', 'redirected_statement'):
                        # Wrap in a new node structure to recurse
                        walk_top_level(list_child)
                    elif lct == 'pipeline':
                        has_pipeline = True
                        segments.append(list_child.text)
                    elif lct == 'subshell':
                        has_subshell = True
                        segments.append(list_child.text)
                    elif lct == 'compound_statement':
                        has_command_group = True
                        segments.append(list_child.text)
                    else:
                        segments.append(list_child.text)
            elif ct == ';':
                operators.append(';')
            elif ct == 'pipeline':
                has_pipeline = True
                segments.append(child.text)
            elif ct == 'subshell':
                has_subshell = True
                segments.append(child.text)
            elif ct == 'compound_statement':
                has_command_group = True
                segments.append(child.text)
            elif ct in ('command', 'declaration_command', 'variable_assignment'):
                segments.append(child.text)
            elif ct == 'redirected_statement':
                found_inner = False
                for inner in child.children:
                    if inner.type == 'file_redirect':
                        continue
                    found_inner = True
                    walk_top_level(inner)
                if not found_inner:
                    segments.append(child.text)
            elif ct == 'negated_command':
                segments.append(child.text)
                walk_top_level(child)
            elif ct in ('if_statement', 'while_statement', 'for_statement',
                        'case_statement', 'function_definition'):
                segments.append(child.text)
                walk_top_level(child)

    walk_top_level(node)

    if not segments:
        segments.append(command)

    return CompoundStructure(
        has_compound_operators=len(operators) > 0,
        has_pipeline=has_pipeline,
        has_subshell=has_subshell,
        has_command_group=has_command_group,
        operators=operators,
        segments=segments,
    )


def has_actual_operator_nodes(root_node: Any) -> bool:
    """Check whether the AST contains actual operator nodes (;, &&, ||)."""
    node = _Node(root_node)

    def walk(n: _Node) -> bool:
        if n.type in (';', '&&', '||'):
            return True
        if n.type == 'list':
            return True
        for child in n.children:
            if walk(child):
                return True
        return False

    return walk(node)


def extract_dangerous_patterns(root_node: Any) -> DangerousPatterns:
    """Extract dangerous pattern information from the AST."""
    node = _Node(root_node)
    has_cmd_sub = False
    has_proc_sub = False
    has_param_exp = False
    has_heredoc = False
    has_comment = False

    def walk(n: _Node) -> None:
        nonlocal has_cmd_sub, has_proc_sub, has_param_exp, has_heredoc, has_comment

        nt = n.type
        if nt == 'command_substitution':
            has_cmd_sub = True
        elif nt == 'process_substitution':
            has_proc_sub = True
        elif nt == 'expansion':
            has_param_exp = True
        elif nt == 'heredoc_redirect':
            has_heredoc = True
        elif nt == 'comment':
            has_comment = True

        for child in n.children:
            walk(child)

    walk(node)

    return DangerousPatterns(
        has_command_substitution=has_cmd_sub,
        has_process_substitution=has_proc_sub,
        has_parameter_expansion=has_param_exp,
        has_heredoc=has_heredoc,
        has_comment=has_comment,
    )


def analyze_command(root_node: Any, command: str) -> TreeSitterAnalysis:
    """Perform complete tree-sitter analysis of a command."""
    return TreeSitterAnalysis(
        quote_context=extract_quote_context(root_node, command),
        compound_structure=extract_compound_structure(root_node, command),
        has_actual_operator_nodes=has_actual_operator_nodes(root_node),
        dangerous_patterns=extract_dangerous_patterns(root_node),
    )
