"""
Tool validation config - configuration for validating tool-specific settings.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple


class ToolValidationConfig:
    """Configuration for validating a specific tool's settings."""

    def __init__(
        self,
        tool_name: str,
        validate: Callable[[Any], List[str]],
        description: str = "",
    ) -> None:
        self.tool_name = tool_name
        self.validate = validate
        self.description = description


def no_validation(_input: Any) -> List[str]:
    """Validation function that always passes."""
    return []


# Registry of tool validation configs
_tool_validation_configs: Dict[str, ToolValidationConfig] = {}


def register_tool_validation_config(config: ToolValidationConfig) -> None:
    """Register a tool validation configuration."""
    _tool_validation_configs[config.tool_name] = config


def get_tool_validation_config(tool_name: str) -> Optional[ToolValidationConfig]:
    """Get the validation config for a tool."""
    return _tool_validation_configs.get(tool_name)


def validate_tool_settings(
    tool_name: str,
    settings: Any,
) -> List[str]:
    """Validate settings for a specific tool. Returns list of error messages."""
    config = get_tool_validation_config(tool_name)
    if config is None:
        return []
    return config.validate(settings)
