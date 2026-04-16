# 原始 TS: utils/envDynamic.ts
"""动态环境检测（运行时环境信息）"""
from __future__ import annotations
import os
import platform
import sys
from typing import Dict


def get_runtime_env() -> Dict[str, str]:
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "arch": platform.machine(),
        "python": sys.version.split()[0],
        "shell": os.environ.get("SHELL", "unknown"),
        "term": os.environ.get("TERM", "unknown"),
        "lang": os.environ.get("LANG", "unknown"),
        "home": os.path.expanduser("~"),
        "cwd": os.getcwd(),
        "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
    }


def is_wsl() -> bool:
    return "microsoft" in platform.release().lower() or "WSL" in os.environ.get("WSLENV", "WSL_DISTRO_NAME" in os.environ and "1" or "")


def is_macos() -> bool:
    return platform.system() == "Darwin"


def is_linux() -> bool:
    return platform.system() == "Linux"


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_ci() -> bool:
    return any(os.environ.get(v) for v in ("CI", "GITHUB_ACTIONS", "JENKINS_URL", "GITLAB_CI", "CIRCLECI"))
