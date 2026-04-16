"""ConfigTool — get/set Claude Code settings. Ported from ConfigTool/ConfigTool.ts"""
from __future__ import annotations
from typing import Any, Dict
from claude_code.tools.config_tool.constants import CONFIG_TOOL_NAME
from claude_code.tools.config_tool.supported_settings import is_supported, get_options_for_setting


class ConfigTool:
    name = CONFIG_TOOL_NAME
    description = "Get or set Claude Code configuration settings."
    is_read_only = False

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "setting": {"type": "string"},
                "value": {},
            },
            "required": ["setting"],
        }

    async def call(self, input: Dict[str, Any], context: Any = None) -> dict:
        from claude_code.utils.config import get_global_config, save_global_config
        setting = input.get("setting", "")
        value = input.get("value")
        config = get_global_config()

        if value is None:
            current = config.get(setting)
            return {"text": f"{setting} = {current!r}" if setting in config else f"Setting {setting!r} not configured."}

        if not is_supported(setting):
            return {"text": f"Setting {setting!r} is not supported."}

        opts = get_options_for_setting(setting)
        if opts and str(value) not in opts:
            return {"text": f"Invalid value {value!r} for {setting}. Options: {opts}"}

        old = config.get(setting)
        config[setting] = value
        save_global_config(config)
        return {"text": f"Set {setting} = {value!r} (was {old!r})"}
