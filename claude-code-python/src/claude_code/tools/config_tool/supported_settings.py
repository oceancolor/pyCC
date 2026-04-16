"""Supported settings for ConfigTool. Ported from ConfigTool/supportedSettings.ts"""
SUPPORTED_SETTINGS = {
    "theme": {"options": ["dark", "light"], "type": "string"},
    "model": {"type": "string"},
    "permissions.defaultMode": {"options": ["default", "acceptEdits", "plan", "auto"], "type": "string"},
    "verbose": {"type": "boolean"},
    "maxTokens": {"type": "integer"},
}

def is_supported(key: str) -> bool:
    return key in SUPPORTED_SETTINGS

def get_options_for_setting(key: str):
    return SUPPORTED_SETTINGS.get(key, {}).get("options")

def get_config(key: str, global_config: dict):
    return global_config.get(key)

def get_path(key: str) -> str:
    return key
