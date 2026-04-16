"""Session-scoped env vars. Ported from sessionEnvVars.ts"""
from __future__ import annotations
from typing import Dict
_session_env_vars: Dict[str, str] = {}

def get_session_env_vars() -> Dict[str, str]:
    return dict(_session_env_vars)

def set_session_env_var(name: str, value: str) -> None:
    _session_env_vars[name] = value

def delete_session_env_var(name: str) -> None:
    _session_env_vars.pop(name, None)

def clear_session_env_vars() -> None:
    _session_env_vars.clear()
