# 原始 TS: utils/userConfig.ts
"""用户级配置管理（~/.claude/settings.json）"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

_CONFIG_PATH = Path.home() / ".claude" / "settings.json"

_DEFAULTS: Dict[str, Any] = {
    "model": "claude-opus-4-5",
    "theme": "dark",
    "verbose": False,
    "autoCompact": True,
    "compactThreshold": 0.85,
    "maxTurns": 10,
    "showTokenUsage": True,
    "attribution": True,
    "checkForUpdates": True,
}


def load_user_config() -> Dict[str, Any]:
    config = dict(_DEFAULTS)
    if _CONFIG_PATH.exists():
        try:
            user = json.loads(_CONFIG_PATH.read_text())
            config.update(user)
        except (json.JSONDecodeError, OSError):
            pass
    # 环境变量覆盖
    if os.environ.get("ANTHROPIC_MODEL"):
        config["model"] = os.environ["ANTHROPIC_MODEL"]
    return config


def save_user_config(config: Dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(config, indent=2))


def get_config_value(key: str) -> Any:
    return load_user_config().get(key, _DEFAULTS.get(key))


def set_config_value(key: str, value: Any) -> None:
    config = load_user_config()
    config[key] = value
    save_user_config(config)
