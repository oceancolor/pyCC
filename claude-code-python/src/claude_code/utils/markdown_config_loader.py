"""
markdown_config_loader.py
加载和解析 Markdown 格式的配置文件（CLAUDE.md 系列）。
支持 YAML frontmatter 元数据 + 正文内容。
移植自 markdownConfigLoader.ts + frontmatterParser.ts 的核心逻辑。
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# 尝试导入 PyYAML（标准 YAML 解析），不强依赖
try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# frontmatter 分隔符正则：--- 开头行到下一个 ---
_FRONTMATTER_REGEX = re.compile(
    r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?",
    re.DOTALL,
)

# YAML 中需要加引号的特殊字符
_YAML_SPECIAL = re.compile(r'[{}[\]*&#!|>%@`]|: ')


@dataclass
class FrontmatterData:
    """CLAUDE.md 文件的 frontmatter 元数据。"""
    description: Optional[str] = None
    allowed_tools: Optional[list[str]] = None
    model: Optional[str] = None
    version: Optional[str] = None
    argument_hint: Optional[str] = None
    when_to_use: Optional[str] = None
    hide_from_slash_command_tool: Optional[str] = None
    skills: Optional[str] = None
    user_invocable: Optional[str] = None
    paths: Optional[list[str]] = None
    shell: Optional[str] = None
    context: Optional[str] = None
    agent: Optional[str] = None
    effort: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrontmatterData":
        """从解析出的 YAML dict 构建 FrontmatterData。"""
        obj = cls()
        mapping = {
            "description": "description",
            "model": "model",
            "version": "version",
            "argument-hint": "argument_hint",
            "when_to_use": "when_to_use",
            "hide-from-slash-command-tool": "hide_from_slash_command_tool",
            "skills": "skills",
            "user-invocable": "user_invocable",
            "shell": "shell",
            "context": "context",
            "agent": "agent",
            "effort": "effort",
        }
        for yaml_key, attr in mapping.items():
            val = data.get(yaml_key)
            if val is not None:
                setattr(obj, attr, str(val) if not isinstance(val, str) else val)

        # allowed-tools 支持字符串或列表
        tools_val = data.get("allowed-tools")
        if tools_val is not None:
            if isinstance(tools_val, list):
                obj.allowed_tools = [str(t) for t in tools_val]
            elif isinstance(tools_val, str):
                obj.allowed_tools = [t.strip() for t in tools_val.split(",") if t.strip()]

        # paths 支持字符串（逗号分隔）或列表
        paths_val = data.get("paths")
        if paths_val is not None:
            if isinstance(paths_val, list):
                obj.paths = [str(p) for p in paths_val]
            elif isinstance(paths_val, str):
                obj.paths = [p.strip() for p in paths_val.split(",") if p.strip()]

        # 其余未识别的 key 放入 extra
        known_keys = set(mapping.keys()) | {"allowed-tools", "paths"}
        for k, v in data.items():
            if k not in known_keys:
                obj.extra[k] = v

        return obj


@dataclass
class MarkdownConfig:
    """解析后的 Markdown 配置文件结构。"""
    file_path: str
    frontmatter: FrontmatterData
    content: str                    # 去掉 frontmatter 后的正文
    raw: str                        # 原始文件内容

    @property
    def description(self) -> str:
        """优先返回 frontmatter.description，否则从正文提取第一行。"""
        if self.frontmatter.description:
            return self.frontmatter.description
        return extract_description_from_markdown(self.content)


def _parse_yaml(text: str) -> Optional[dict[str, Any]]:
    """解析 YAML 文本，返回 dict 或 None。"""
    if not _HAS_YAML:
        return _parse_yaml_simple(text)
    try:
        result = _yaml.safe_load(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    return None


def _quote_problematic_values(text: str) -> str:
    """对 YAML 中含特殊字符的值加引号（简单启发式修复）。"""
    lines = []
    for line in text.splitlines():
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            value = value.strip()
            if value and not value.startswith('"') and not value.startswith("'"):
                if _YAML_SPECIAL.search(value):
                    value = '"' + value.replace('"', '\\"') + '"'
                    lines.append(f"{key}: {value}")
                    continue
        lines.append(line)
    return "\n".join(lines)


def _parse_yaml_simple(text: str) -> Optional[dict[str, Any]]:
    """不依赖 PyYAML 的极简 YAML key:value 解析（仅支持扁平结构）。"""
    result: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            result[key] = value or None
    return result if result else None


def parse_frontmatter(markdown: str, source_path: str = "") -> tuple[FrontmatterData, str]:
    """
    解析 Markdown 文本的 YAML frontmatter。

    Args:
        markdown: 完整 Markdown 文本
        source_path: 文件路径（用于错误日志，可选）

    Returns:
        (FrontmatterData, content_without_frontmatter)
    """
    match = _FRONTMATTER_REGEX.match(markdown)
    if not match:
        return FrontmatterData(), markdown

    frontmatter_text = match.group(1) or ""
    content = markdown[match.end():]

    raw_data = _parse_yaml(frontmatter_text)
    if raw_data is None:
        # 尝试修复再解析
        fixed = _quote_problematic_values(frontmatter_text)
        raw_data = _parse_yaml(fixed)

    if raw_data is None:
        raw_data = {}

    return FrontmatterData.from_dict(raw_data), content


def extract_description_from_markdown(
    content: str,
    default_description: str = "Custom item",
) -> str:
    """
    从 Markdown 正文提取描述：取第一个非空行，去掉标题前缀 #。
    """
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed:
            header_match = re.match(r"^#+\s+(.+)$", trimmed)
            text = header_match.group(1) if header_match else trimmed
            return text[:97] + "..." if len(text) > 100 else text
    return default_description


def load_markdown_config(path: str | Path) -> MarkdownConfig:
    """
    同步加载并解析一个 Markdown 配置文件。

    Args:
        path: 文件路径

    Returns:
        MarkdownConfig 对象
    """
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    frontmatter, content = parse_frontmatter(raw, str(path))
    return MarkdownConfig(
        file_path=str(path),
        frontmatter=frontmatter,
        content=content,
        raw=raw,
    )


async def load_markdown_config_async(path: str | Path) -> MarkdownConfig:
    """
    异步加载并解析一个 Markdown 配置文件。

    Args:
        path: 文件路径

    Returns:
        MarkdownConfig 对象
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, load_markdown_config, path)


async def load_markdown_configs_from_dir(
    directory: str | Path,
    recursive: bool = True,
    timeout: float = 3.0,
) -> list[MarkdownConfig]:
    """
    异步扫描目录，加载所有 .md 文件。

    Args:
        directory: 目录路径
        recursive: 是否递归子目录
        timeout: 超时秒数

    Returns:
        MarkdownConfig 列表
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []

    pattern = "**/*.md" if recursive else "*.md"
    md_files = list(directory.glob(pattern))

    async def _load(p: Path) -> Optional[MarkdownConfig]:
        try:
            return await load_markdown_config_async(p)
        except Exception:
            return None

    tasks = [_load(f) for f in md_files]
    try:
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=timeout)
    except asyncio.TimeoutError:
        return []

    return [r for r in results if r is not None]
