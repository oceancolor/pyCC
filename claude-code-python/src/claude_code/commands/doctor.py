# 原始 TS: commands/doctor/
"""环境检查命令：检查 python 版本、API key、网络、依赖包"""
import sys
import os
import subprocess
import importlib
from dataclasses import dataclass
from typing import List


@dataclass
class CheckResult:
    name: str
    status: bool
    message: str


def check_python_version() -> CheckResult:
    """检查 Python 版本是否满足最低要求（3.8+）"""
    major, minor = sys.version_info.major, sys.version_info.minor
    version_str = f"{major}.{minor}.{sys.version_info.micro}"
    if major < 3 or (major == 3 and minor < 8):
        return CheckResult(
            name="Python Version",
            status=False,
            message=f"Python {version_str} is too old. Requires Python 3.8+.",
        )
    return CheckResult(
        name="Python Version",
        status=True,
        message=f"Python {version_str} ✓",
    )


def check_api_key() -> CheckResult:
    """检查 ANTHROPIC_API_KEY 是否已配置"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return CheckResult(
            name="API Key",
            status=False,
            message="ANTHROPIC_API_KEY is not set. Export it in your shell or .env file.",
        )
    if not api_key.startswith("sk-"):
        return CheckResult(
            name="API Key",
            status=False,
            message="ANTHROPIC_API_KEY looks invalid (should start with 'sk-').",
        )
    masked = api_key[:8] + "..." + api_key[-4:]
    return CheckResult(
        name="API Key",
        status=True,
        message=f"ANTHROPIC_API_KEY found ({masked}) ✓",
    )


def check_network() -> CheckResult:
    """检查网络连通性（尝试访问 Anthropic API 端点）"""
    import urllib.request
    import urllib.error

    test_url = "https://api.anthropic.com"
    try:
        req = urllib.request.Request(test_url, method="HEAD")
        req.add_header("User-Agent", "claude-code-python/doctor")
        with urllib.request.urlopen(req, timeout=5):
            pass
        return CheckResult(
            name="Network",
            status=True,
            message=f"Reached {test_url} ✓",
        )
    except urllib.error.HTTPError as e:
        # HTTP error still means we reached the server
        if e.code < 500:
            return CheckResult(
                name="Network",
                status=True,
                message=f"Reached {test_url} (HTTP {e.code}) ✓",
            )
        return CheckResult(
            name="Network",
            status=False,
            message=f"Server error reaching {test_url}: HTTP {e.code}",
        )
    except Exception as e:
        return CheckResult(
            name="Network",
            status=False,
            message=f"Cannot reach {test_url}: {e}",
        )


def check_dependencies() -> CheckResult:
    """检查核心依赖包是否已安装"""
    required = ["anthropic", "rich", "prompt_toolkit"]
    missing = []
    for pkg in required:
        spec = importlib.util.find_spec(pkg)
        if spec is None:
            missing.append(pkg)

    if missing:
        return CheckResult(
            name="Dependencies",
            status=False,
            message=f"Missing packages: {', '.join(missing)}. Run: pip install {' '.join(missing)}",
        )
    return CheckResult(
        name="Dependencies",
        status=True,
        message=f"All required packages installed ({', '.join(required)}) ✓",
    )


def doctor_command() -> List[CheckResult]:
    """运行所有环境检查，返回检查结果列表"""
    checks = [
        check_python_version(),
        check_api_key(),
        check_network(),
        check_dependencies(),
    ]

    # 打印结果摘要
    print("Claude Code - Environment Doctor")
    print("=" * 40)
    all_ok = True
    for result in checks:
        icon = "✅" if result.status else "❌"
        print(f"{icon}  {result.name}: {result.message}")
        if not result.status:
            all_ok = False
    print("=" * 40)
    if all_ok:
        print("All checks passed. You're good to go!")
    else:
        print("Some checks failed. Please fix the issues above.")

    return checks
