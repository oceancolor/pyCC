"""collapse_read_search — collapse consecutive read/search tool operations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union

@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: Literal["tool_use"] = "tool_use"


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: Union[str, list[Any]]
    type: Literal["tool_result"] = "tool_result"


@dataclass
class TextBlock:
    text: str
    type: Literal["text"] = "text"


ContentBlock = Union[ToolUseBlock, ToolResultBlock, TextBlock]


@dataclass
class Message:
    role: Literal["assistant", "user"]
    content: list[ContentBlock]


READ_TOOL_NAMES: frozenset[str] = frozenset(
    {"Read", "readFile", "file_read", "view", "open_file"}
)
SEARCH_TOOL_NAMES: frozenset[str] = frozenset(
    {"Grep", "ripgrep", "rg", "grep", "search_files", "Glob", "glob", "find_files"}
)
LIST_TOOL_NAMES: frozenset[str] = frozenset({"ls", "list_directory", "tree"})
COLLAPSIBLE_TOOL_NAMES: frozenset[str] = READ_TOOL_NAMES | SEARCH_TOOL_NAMES | LIST_TOOL_NAMES


@dataclass
class CollapsedGroup:
    messages: list[Message] = field(default_factory=list)
    search_count: int = 0
    read_file_paths: set[str] = field(default_factory=set)
    read_operation_count: int = 0
    list_count: int = 0
    tool_use_ids: set[str] = field(default_factory=set)
    latest_display_hint: Optional[str] = None

    @property
    def total_read_count(self) -> int:
        return len(self.read_file_paths) or self.read_operation_count

    @property
    def total_ops(self) -> int:
        return self.search_count + self.total_read_count + self.list_count

    def summary(self) -> str:
        parts: list[str] = []
        if self.search_count:
            parts.append(f"Searched {self.search_count} time{'s' if self.search_count != 1 else ''}")
        if self.total_read_count:
            n = self.total_read_count
            parts.append(f"Read {n} file{'s' if n != 1 else ''}")
        if self.list_count:
            parts.append(f"Listed {self.list_count} director{'ies' if self.list_count != 1 else 'y'}")
        return ", ".join(parts) if parts else "Read/searched"


def _is_collapsible_tool_use(block: ContentBlock) -> bool:
    return isinstance(block, ToolUseBlock) and block.name in COLLAPSIBLE_TOOL_NAMES


def should_collapse(tool_use: ToolUseBlock, _tool_result: ToolResultBlock) -> bool:
    """Return True when this tool_use/result pair should be collapsed."""
    return tool_use.name in COLLAPSIBLE_TOOL_NAMES


def _get_file_path(tool_use: ToolUseBlock) -> Optional[str]:
    inp = tool_use.input
    return inp.get("file_path") or inp.get("path")


def _classify(tool_use: ToolUseBlock) -> tuple[bool, bool, bool]:
    name = tool_use.name
    return name in SEARCH_TOOL_NAMES, name in READ_TOOL_NAMES, name in LIST_TOOL_NAMES


def _flush_group(group: Optional[CollapsedGroup], out: list[Message | CollapsedGroup]) -> None:
    if group and group.messages:
        out.append(group)


def _add_to_group(group: CollapsedGroup, assistant_msg: Message, user_msg: Message) -> None:
    group.messages.extend([assistant_msg, user_msg])
    for block in assistant_msg.content:
        if not isinstance(block, ToolUseBlock):
            continue
        group.tool_use_ids.add(block.id)
        is_search, is_read, is_list = _classify(block)
        if is_search:
            group.search_count += 1
        elif is_read:
            fp = _get_file_path(block)
            if fp:
                group.read_file_paths.add(fp)
            else:
                group.read_operation_count += 1
        elif is_list:
            group.list_count += 1


def collapse_read_search_messages(
    messages: list[Message],
) -> list[Message | CollapsedGroup]:
    """Collapse consecutive read/search assistant→user pairs in *messages*."""
    out: list[Message | CollapsedGroup] = []
    current_group: Optional[CollapsedGroup] = None
    i = 0
    while i < len(messages):
        msg = messages[i]
        if (
            msg.role == "assistant"
            and i + 1 < len(messages)
            and messages[i + 1].role == "user"
        ):
            assistant_msg = msg
            user_msg = messages[i + 1]
            tool_uses = [b for b in assistant_msg.content if isinstance(b, ToolUseBlock)]
            non_tool_text = [
                b for b in assistant_msg.content
                if isinstance(b, TextBlock) and b.text.strip()
            ]
            all_collapsible = (
                bool(tool_uses)
                and all(_is_collapsible_tool_use(b) for b in assistant_msg.content if isinstance(b, ToolUseBlock))
                and not non_tool_text
            )
            if all_collapsible:
                if current_group is None:
                    current_group = CollapsedGroup()
                _add_to_group(current_group, assistant_msg, user_msg)
                i += 2
                continue
        _flush_group(current_group, out)
        current_group = None
        out.append(msg)
        i += 1
    _flush_group(current_group, out)
    return out


def flatten_collapsed(items: list[Message | CollapsedGroup]) -> list[Message]:
    """Convert CollapsedGroups to a synthetic summary TextBlock assistant message."""
    result: list[Message] = []
    for item in items:
        if isinstance(item, CollapsedGroup):
            result.append(Message(role="assistant", content=[TextBlock(text=f"[{item.summary()}]")]))
        else:
            result.append(item)
    return result
