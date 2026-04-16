# 原始 TS: utils/jetbrains.ts
"""JetBrains IDE 插件检测工具。

检测各 JetBrains IDE（PyCharm、IntelliJ、WebStorm 等）中
是否安装了 claude-code-jetbrains-plugin 插件。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# 插件目录前缀（与 TS 版一致）
PLUGIN_PREFIX = "claude-code-jetbrains-plugin"

# IDE 名称 → 目录模式映射
_IDE_DIR_MAP: Dict[str, List[str]] = {
    "pycharm":       ["PyCharm"],
    "intellij":      ["IntelliJIdea", "IdeaIC"],
    "webstorm":      ["WebStorm"],
    "phpstorm":      ["PhpStorm"],
    "rubymine":      ["RubyMine"],
    "clion":         ["CLion"],
    "goland":        ["GoLand"],
    "rider":         ["Rider"],
    "datagrip":      ["DataGrip"],
    "appcode":       ["AppCode"],
    "dataspell":     ["DataSpell"],
    "aqua":          ["Aqua"],
    "gateway":       ["Gateway"],
    "fleet":         ["Fleet"],
    "androidstudio": ["AndroidStudio"],
}

# IdeType 别名（字符串）
IdeType = str


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass
class JetbrainsInfo:
    """JetBrains IDE 信息。"""
    ide_name: str
    version: Optional[str] = None
    plugin_version: Optional[str] = None
    plugin_dir: Optional[str] = None


# ---------------------------------------------------------------------------
# 路径构建
# ---------------------------------------------------------------------------
def _build_plugin_dir_paths(ide_name: str) -> List[Path]:
    """构建候选插件目录列表（对应 TS buildCommonPluginDirectoryPaths）。"""
    patterns = _IDE_DIR_MAP.get(ide_name.lower())
    if not patterns:
        return []

    home = Path.home()
    dirs: List[Path] = []
    platform = sys.platform

    if platform == "darwin":
        dirs.append(home / "Library" / "Application Support" / "JetBrains")
        dirs.append(home / "Library" / "Application Support")
        if ide_name.lower() == "androidstudio":
            dirs.append(home / "Library" / "Application Support" / "Google")

    elif platform == "win32":
        app_data = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        local_app_data = Path(
            os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local"
        )
        dirs.extend([
            app_data / "JetBrains",
            local_app_data / "JetBrains",
            app_data,
        ])
        if ide_name.lower() == "androidstudio":
            dirs.append(local_app_data / "Google")

    else:  # linux / other
        dirs.extend([
            home / ".config" / "JetBrains",
            home / ".local" / "share" / "JetBrains",
        ])
        for p in patterns:
            dirs.append(home / f".{p}")
        if ide_name.lower() == "androidstudio":
            dirs.append(home / ".config" / "Google")

    return dirs


# ---------------------------------------------------------------------------
# 目录检测
# ---------------------------------------------------------------------------
def _detect_plugin_dirs(ide_name: str) -> List[Path]:
    """返回所有实际存在的插件目录（去重）。"""
    patterns = _IDE_DIR_MAP.get(ide_name.lower())
    if not patterns:
        return []

    found: List[Path] = []
    is_linux = sys.platform.startswith("linux")

    for base_dir in _build_plugin_dir_paths(ide_name):
        if not base_dir.is_dir():
            continue
        try:
            entries = list(base_dir.iterdir())
        except OSError:
            continue
        for pattern in patterns:
            prefix = pattern  # 目录名以 pattern 开头即匹配
            for entry in entries:
                if not entry.name.startswith(prefix):
                    continue
                if not (entry.is_dir() or entry.is_symlink()):
                    continue
                if is_linux:
                    found.append(entry)
                else:
                    plugin_subdir = entry / "plugins"
                    if plugin_subdir.exists():
                        found.append(plugin_subdir)

    # 去重（保持顺序）
    seen: set = set()
    unique: List[Path] = []
    for p in found:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# 插件安装检测
# ---------------------------------------------------------------------------
def is_jetbrains_plugin_installed(ide_type: IdeType) -> bool:
    """检测指定 IDE 是否安装了 claude-code-jetbrains-plugin。"""
    for plugin_dir in _detect_plugin_dirs(ide_type):
        candidate = plugin_dir / PLUGIN_PREFIX
        if candidate.exists():
            return True
    return False


# 缓存
_plugin_cache: Dict[str, bool] = {}


def is_jetbrains_plugin_installed_cached(
    ide_type: IdeType, force_refresh: bool = False
) -> bool:
    """带内存缓存的插件检测（对应 TS isJetBrainsPluginInstalledCached）。"""
    if force_refresh:
        _plugin_cache.pop(ide_type, None)
    if ide_type not in _plugin_cache:
        _plugin_cache[ide_type] = is_jetbrains_plugin_installed(ide_type)
    return _plugin_cache[ide_type]


def is_jetbrains_plugin_installed_cached_sync(ide_type: IdeType) -> bool:
    """同步返回缓存结果；若缓存不存在则返回 False。"""
    return _plugin_cache.get(ide_type, False)


# ---------------------------------------------------------------------------
# detect_jetbrains — 便捷入口
# ---------------------------------------------------------------------------
def detect_jetbrains() -> Optional[JetbrainsInfo]:
    """检测当前环境中第一个安装了插件的 JetBrains IDE。

    Returns
    -------
    JetbrainsInfo
        若检测到已安装插件的 IDE，返回其信息。
    None
        若未检测到任何 IDE/插件。
    """
    for ide_name in _IDE_DIR_MAP:
        dirs = _detect_plugin_dirs(ide_name)
        for plugin_dir in dirs:
            candidate = plugin_dir / PLUGIN_PREFIX
            if candidate.exists():
                # 尝试从目录名解析版本号（形如 PyCharm2024.1）
                version = _extract_version_from_dir(plugin_dir)
                return JetbrainsInfo(
                    ide_name=ide_name,
                    version=version,
                    plugin_dir=str(candidate),
                )
    return None


def _extract_version_from_dir(plugin_dir: Path) -> Optional[str]:
    """从目录名中提取版本号，如 ``PyCharm2024.1.3`` → ``2024.1.3``。"""
    # plugin_dir 可能是 .../IntelliJIdea2024.1/plugins 或 .../IntelliJIdea2024.1
    parts = [plugin_dir.name, plugin_dir.parent.name]
    for part in parts:
        # 找到第一个数字字符的位置
        for i, ch in enumerate(part):
            if ch.isdigit():
                return part[i:]
    return None
