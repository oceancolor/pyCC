# 原始 TS: utils/doctorContextWarnings.ts / utils/doctorDiagnostic.ts
"""诊断警告（doctor 命令扩展）"""
from __future__ import annotations
import os
import sys
from typing import List


def check_context_warnings() -> List[str]:
    """返回当前环境的上下文警告列表"""
    warnings = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        warnings.append("❌ ANTHROPIC_API_KEY 未设置")
    if sys.version_info < (3, 9):
        warnings.append(f"⚠️ Python 版本过低：{sys.version}（推荐 3.9+）")
    try:
        import anthropic  # noqa
    except ImportError:
        warnings.append("❌ anthropic 包未安装，运行 pip install anthropic")
    try:
        import prompt_toolkit  # noqa
    except ImportError:
        warnings.append("⚠️ prompt_toolkit 未安装，交互模式不可用（pip install prompt_toolkit）")
    try:
        import rich  # noqa
    except ImportError:
        warnings.append("⚠️ rich 未安装，输出高亮不可用（pip install rich）")
    return warnings


def run_diagnostics() -> dict:
    warnings = check_context_warnings()
    return {
        "warnings": warnings,
        "ok": len(warnings) == 0,
        "python_version": sys.version,
        "api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }
