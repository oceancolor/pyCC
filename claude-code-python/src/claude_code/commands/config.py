# 原始 TS: commands/config/
"""配置管理命令：读取/设置/列出配置项"""
import json
import os
from pathlib import Path
from typing import Any, Optional


CONFIG_PATH = Path.home() / ".claude" / "config.json"

# 已知配置键及其默认值与描述
_KNOWN_KEYS: dict = {
    "model":            ("claude-3-5-sonnet-20241022", "Default model to use"),
    "max_tokens":       (8192,                          "Max tokens per response"),
    "temperature":      (1.0,                           "Sampling temperature (0-1)"),
    "stream":           (True,                          "Enable streaming responses"),
    "auto_save":        (True,                          "Auto-save conversation history"),
    "history_dir":      ("~/.claude/history",           "Directory for conversation history"),
    "theme":            ("dark",                        "Terminal color theme (dark/light)"),
    "verbose":          (False,                         "Enable verbose/debug output"),
}


def _load_raw() -> dict:
    """从磁盘加载配置文件，文件不存在时返回空字典"""
    if not CONFIG_PATH.exists():
        return {}
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        return json.loads(text) if text.strip() else {}
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(f"Failed to read config at {CONFIG_PATH}: {e}") from e


def _save_raw(data: dict) -> None:
    """将配置字典写回磁盘"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        raise RuntimeError(f"Failed to write config to {CONFIG_PATH}: {e}") from e


def get_config(key: str) -> Optional[Any]:
    """
    读取指定配置键的值。

    优先级：配置文件 > 环境变量 > 内置默认值

    Returns:
        配置值，若键不存在则返回 None。
    """
    # 1. 配置文件
    data = _load_raw()
    if key in data:
        return data[key]

    # 2. 环境变量（CLAUDE_<KEY> 大写）
    env_key = f"CLAUDE_{key.upper()}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val

    # 3. 内置默认
    if key in _KNOWN_KEYS:
        return _KNOWN_KEYS[key][0]

    return None


def set_config(key: str, value: Any) -> None:
    """
    设置配置键的值并持久化到磁盘。

    Args:
        key:   配置键名
        value: 任意 JSON 可序列化的值
    """
    data = _load_raw()
    data[key] = value
    _save_raw(data)


def list_config() -> dict:
    """
    列出所有有效配置（文件中的值 + 未覆盖的已知默认值）。

    Returns:
        完整的配置字典。
    """
    result = {k: v for k, (v, _) in _KNOWN_KEYS.items()}  # 先填默认
    result.update(_load_raw())                              # 文件值覆盖默认
    return result


def config_command(action: str, key: str = None, value: str = None):
    """
    配置命令入口。

    Args:
        action: "get" | "set" | "list" | "reset"
        key:    配置键名（get/set 必填，list/reset 可选）
        value:  配置值字符串（set 时必填）

    Returns:
        - list  → dict（完整配置）
        - get   → Any（单个值）
        - set   → None（成功静默）
        - reset → None（成功静默）

    Raises:
        ValueError: 参数无效
        RuntimeError: 文件读写失败
    """
    action = action.strip().lower()

    if action == "list":
        cfg = list_config()
        print(f"Config file: {CONFIG_PATH}")
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return cfg

    if action == "get":
        if not key:
            raise ValueError("'get' requires a key argument.")
        val = get_config(key)
        if val is None:
            print(f"Key '{key}' is not set.")
        else:
            print(f"{key} = {json.dumps(val)}")
        return val

    if action == "set":
        if not key:
            raise ValueError("'set' requires a key argument.")
        if value is None:
            raise ValueError("'set' requires a value argument.")

        # 尝试将字符串 value 解析为 JSON（支持 bool、int、float、list 等）
        try:
            parsed: Any = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed = value  # 保留原始字符串

        set_config(key, parsed)
        print(f"Set {key} = {json.dumps(parsed)}")
        return None

    if action == "reset":
        if key:
            # 只重置指定键
            data = _load_raw()
            if key in data:
                del data[key]
                _save_raw(data)
                print(f"Reset '{key}' to default.")
            else:
                print(f"Key '{key}' was not set; nothing to reset.")
        else:
            # 重置全部：清空配置文件
            _save_raw({})
            print("All config keys reset to defaults.")
        return None

    raise ValueError(
        f"Unknown action '{action}'. Valid actions: get, set, list, reset."
    )
