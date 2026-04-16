# 原始 TS: utils/clipboard.ts
"""剪贴板读写（跨平台）"""
import subprocess
import sys
from typing import Optional


def copy_to_clipboard(text: str) -> bool:
    """将文本写入系统剪贴板。
    
    - macOS: pbcopy
    - Windows: clip
    - Linux: xclip（优先）或 xsel
    
    返回 True 表示成功，False 表示失败。
    """
    try:
        if sys.platform == "darwin":
            proc = subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                check=True,
            )
        elif sys.platform == "win32":
            proc = subprocess.run(
                ["clip"],
                input=text.encode("utf-16le"),
                check=True,
            )
        else:
            # Linux: 尝试 xclip，再 fallback 到 xsel
            try:
                proc = subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode("utf-8"),
                    check=True,
                )
            except FileNotFoundError:
                proc = subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=text.encode("utf-8"),
                    check=True,
                )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


def read_from_clipboard() -> Optional[str]:
    """从系统剪贴板读取文本。
    
    - macOS: pbpaste
    - Windows: PowerShell Get-Clipboard
    - Linux: xclip（优先）或 xsel
    
    返回文本字符串，失败返回 None。
    """
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                check=True,
            )
            return result.stdout.decode("utf-8")
        elif sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True,
                check=True,
            )
            return result.stdout.decode("utf-8").rstrip("\r\n")
        else:
            # Linux
            try:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-out"],
                    capture_output=True,
                    check=True,
                )
            except FileNotFoundError:
                result = subprocess.run(
                    ["xsel", "--clipboard", "--output"],
                    capture_output=True,
                    check=True,
                )
            return result.stdout.decode("utf-8")
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
