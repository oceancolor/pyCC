"""
IDE integration utilities.
Ported from utils/ide.ts (1494 lines).

Provides IDE detection, lockfile management, process detection,
and IDE-related helper functions.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

IdeKind = Literal["vscode", "jetbrains"]

IdeType = Literal[
    "cursor",
    "windsurf",
    "vscode",
    "pycharm",
    "intellij",
    "webstorm",
    "phpstorm",
    "rubymine",
    "clion",
    "goland",
    "rider",
    "datagrip",
    "appcode",
    "dataspell",
    "aqua",
    "gateway",
    "fleet",
    "androidstudio",
]


@dataclass
class IdeConfig:
    ide_kind: IdeKind
    display_name: str
    process_keywords_mac: List[str]
    process_keywords_windows: List[str]
    process_keywords_linux: List[str]


@dataclass
class LockfileJsonContent:
    workspace_folders: List[str] = field(default_factory=list)
    pid: Optional[int] = None
    ide_name: Optional[str] = None
    transport: Optional[str] = None  # 'ws' | 'sse'
    running_in_windows: bool = False
    auth_token: Optional[str] = None


@dataclass
class IdeLockfileInfo:
    workspace_folders: List[str]
    port: int
    pid: Optional[int] = None
    ide_name: Optional[str] = None
    use_web_socket: bool = False
    running_in_windows: bool = False
    auth_token: Optional[str] = None


@dataclass
class DetectedIDEInfo:
    name: str
    port: int
    workspace_folders: List[str]
    url: str
    is_valid: bool
    auth_token: Optional[str] = None
    ide_running_in_windows: Optional[bool] = None


@dataclass
class IDEExtensionInstallationStatus:
    installed: bool
    error: Optional[str]
    installed_version: Optional[str]
    ide_type: Optional[str]


# ---------------------------------------------------------------------------
# Supported IDE configurations
# ---------------------------------------------------------------------------

SUPPORTED_IDE_CONFIGS: Dict[str, IdeConfig] = {
    "cursor": IdeConfig(
        ide_kind="vscode",
        display_name="Cursor",
        process_keywords_mac=["Cursor Helper", "Cursor.app"],
        process_keywords_windows=["cursor.exe"],
        process_keywords_linux=["cursor"],
    ),
    "windsurf": IdeConfig(
        ide_kind="vscode",
        display_name="Windsurf",
        process_keywords_mac=["Windsurf Helper", "Windsurf.app"],
        process_keywords_windows=["windsurf.exe"],
        process_keywords_linux=["windsurf"],
    ),
    "vscode": IdeConfig(
        ide_kind="vscode",
        display_name="VS Code",
        process_keywords_mac=["Visual Studio Code", "Code Helper"],
        process_keywords_windows=["code.exe"],
        process_keywords_linux=["code"],
    ),
    "intellij": IdeConfig(
        ide_kind="jetbrains",
        display_name="IntelliJ IDEA",
        process_keywords_mac=["IntelliJ IDEA"],
        process_keywords_windows=["idea64.exe"],
        process_keywords_linux=["idea", "intellij"],
    ),
    "pycharm": IdeConfig(
        ide_kind="jetbrains",
        display_name="PyCharm",
        process_keywords_mac=["PyCharm"],
        process_keywords_windows=["pycharm64.exe"],
        process_keywords_linux=["pycharm"],
    ),
    "webstorm": IdeConfig(
        ide_kind="jetbrains",
        display_name="WebStorm",
        process_keywords_mac=["WebStorm"],
        process_keywords_windows=["webstorm64.exe"],
        process_keywords_linux=["webstorm"],
    ),
    "phpstorm": IdeConfig(
        ide_kind="jetbrains",
        display_name="PhpStorm",
        process_keywords_mac=["PhpStorm"],
        process_keywords_windows=["phpstorm64.exe"],
        process_keywords_linux=["phpstorm"],
    ),
    "rubymine": IdeConfig(
        ide_kind="jetbrains",
        display_name="RubyMine",
        process_keywords_mac=["RubyMine"],
        process_keywords_windows=["rubymine64.exe"],
        process_keywords_linux=["rubymine"],
    ),
    "clion": IdeConfig(
        ide_kind="jetbrains",
        display_name="CLion",
        process_keywords_mac=["CLion"],
        process_keywords_windows=["clion64.exe"],
        process_keywords_linux=["clion"],
    ),
    "goland": IdeConfig(
        ide_kind="jetbrains",
        display_name="GoLand",
        process_keywords_mac=["GoLand"],
        process_keywords_windows=["goland64.exe"],
        process_keywords_linux=["goland"],
    ),
    "rider": IdeConfig(
        ide_kind="jetbrains",
        display_name="Rider",
        process_keywords_mac=["Rider"],
        process_keywords_windows=["rider64.exe"],
        process_keywords_linux=["rider"],
    ),
    "datagrip": IdeConfig(
        ide_kind="jetbrains",
        display_name="DataGrip",
        process_keywords_mac=["DataGrip"],
        process_keywords_windows=["datagrip64.exe"],
        process_keywords_linux=["datagrip"],
    ),
    "appcode": IdeConfig(
        ide_kind="jetbrains",
        display_name="AppCode",
        process_keywords_mac=["AppCode"],
        process_keywords_windows=["appcode.exe"],
        process_keywords_linux=["appcode"],
    ),
    "dataspell": IdeConfig(
        ide_kind="jetbrains",
        display_name="DataSpell",
        process_keywords_mac=["DataSpell"],
        process_keywords_windows=["dataspell64.exe"],
        process_keywords_linux=["dataspell"],
    ),
    "aqua": IdeConfig(
        ide_kind="jetbrains",
        display_name="Aqua",
        process_keywords_mac=[],  # Do not auto-detect since aqua is too common
        process_keywords_windows=["aqua64.exe"],
        process_keywords_linux=[],
    ),
    "gateway": IdeConfig(
        ide_kind="jetbrains",
        display_name="Gateway",
        process_keywords_mac=[],  # Do not auto-detect since gateway is too common
        process_keywords_windows=["gateway64.exe"],
        process_keywords_linux=[],
    ),
    "fleet": IdeConfig(
        ide_kind="jetbrains",
        display_name="Fleet",
        process_keywords_mac=[],  # Do not auto-detect since fleet is too common
        process_keywords_windows=["fleet.exe"],
        process_keywords_linux=[],
    ),
    "androidstudio": IdeConfig(
        ide_kind="jetbrains",
        display_name="Android Studio",
        process_keywords_mac=["Android Studio"],
        process_keywords_windows=["studio64.exe"],
        process_keywords_linux=["android-studio"],
    ),
}

# ---------------------------------------------------------------------------
# Editor display names (for terminal/editor detection)
# ---------------------------------------------------------------------------

EDITOR_DISPLAY_NAMES: Dict[str, str] = {
    "code": "VS Code",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "antigravity": "Antigravity",
    "vi": "Vim",
    "vim": "Vim",
    "nano": "nano",
    "notepad": "Notepad",
    "start /wait notepad": "Notepad",
    "emacs": "Emacs",
    "subl": "Sublime Text",
    "atom": "Atom",
}

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def get_platform() -> str:
    """Return 'macos', 'windows', 'linux', or 'wsl'."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    # Check for WSL
    if os.path.exists("/proc/version"):
        try:
            with open("/proc/version") as f:
                content = f.read().lower()
                if "microsoft" in content or "wsl" in content:
                    return "wsl"
        except OSError:
            pass
    return "linux"


# ---------------------------------------------------------------------------
# Process utilities
# ---------------------------------------------------------------------------


def is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def get_ancestor_pids(pid: int, max_depth: int = 10) -> List[int]:
    """Walk up the process tree and return ancestor PIDs (synchronous)."""
    pids: List[int] = []
    current = pid
    for _ in range(max_depth):
        if not current or current <= 1:
            break
        try:
            result = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(current)],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode != 0:
                break
            ppid_str = result.stdout.strip()
            if not ppid_str:
                break
            ppid = int(ppid_str)
            if ppid <= 1:
                break
            pids.append(ppid)
            current = ppid
        except (subprocess.TimeoutExpired, ValueError, OSError):
            break
    return pids


# ---------------------------------------------------------------------------
# IDE type helpers
# ---------------------------------------------------------------------------


def is_vscode_ide(ide: Optional[str]) -> bool:
    """Return True if the IDE is a VS Code variant."""
    if not ide:
        return False
    config = SUPPORTED_IDE_CONFIGS.get(ide)
    return config is not None and config.ide_kind == "vscode"


def is_jetbrains_ide(ide: Optional[str]) -> bool:
    """Return True if the IDE is a JetBrains variant."""
    if not ide:
        return False
    config = SUPPORTED_IDE_CONFIGS.get(ide)
    return config is not None and config.ide_kind == "jetbrains"


def get_terminal_ide_type() -> Optional[str]:
    """Return the IDE type from the TERM_PROGRAM environment variable if supported."""
    terminal = os.environ.get("TERM_PROGRAM") or os.environ.get("TERMINAL_EMULATOR")
    if not terminal:
        return None
    terminal_lower = terminal.lower()
    for ide_type in SUPPORTED_IDE_CONFIGS:
        if ide_type in terminal_lower:
            return ide_type
    return None


def is_supported_terminal() -> bool:
    """Return True if we're running inside a supported IDE terminal."""
    if os.environ.get("FORCE_CODE_TERMINAL"):
        return True
    return get_terminal_ide_type() is not None


def to_ide_display_name(terminal: Optional[str]) -> str:
    """Convert a terminal/IDE identifier to a human-readable display name."""
    if not terminal:
        return "IDE"

    config = SUPPORTED_IDE_CONFIGS.get(terminal)
    if config:
        return config.display_name

    # Check editor command names (exact match first)
    editor_name = EDITOR_DISPLAY_NAMES.get(terminal.lower().strip())
    if editor_name:
        return editor_name

    # Extract command name from path/arguments
    command = terminal.split(" ")[0]
    command_name = os.path.basename(command).lower() if command else None
    if command_name:
        mapped = EDITOR_DISPLAY_NAMES.get(command_name)
        if mapped:
            return mapped
        # Fallback: capitalize the command basename
        return command_name.capitalize()

    return terminal.capitalize()


# ---------------------------------------------------------------------------
# Claude config home directory
# ---------------------------------------------------------------------------


def get_claude_config_home_dir() -> str:
    """Return the Claude configuration home directory path."""
    override = os.environ.get("CLAUDE_CONFIG_HOME_DIR") or os.environ.get(
        "CLAUDE_CONFIG_DIR"
    )
    if override:
        return override
    return str(Path.home() / ".claude")


# ---------------------------------------------------------------------------
# IDE lockfile paths
# ---------------------------------------------------------------------------


def get_ide_lockfiles_paths() -> List[str]:
    """
    Return the list of directories where IDE lockfiles may be found.
    Paths are not pre-checked for existence.
    """
    paths = [os.path.join(get_claude_config_home_dir(), "ide")]

    platform = get_platform()
    if platform != "wsl":
        return paths

    # WSL: also search Windows user directories
    windows_home = os.environ.get("USERPROFILE")
    if not windows_home:
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "$env:USERPROFILE",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                windows_home = result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass

    if windows_home:
        wsl_path = _windows_path_to_wsl(windows_home)
        paths.append(os.path.join(wsl_path, ".claude", "ide"))

    # Also search C:\Users\*
    try:
        users_dir = "/mnt/c/Users"
        for entry in os.scandir(users_dir):
            if not (entry.is_dir() or entry.is_symlink()):
                continue
            if entry.name in ("Public", "Default", "Default User", "All Users"):
                continue
            paths.append(os.path.join(users_dir, entry.name, ".claude", "ide"))
    except OSError:
        pass

    return paths


def _windows_path_to_wsl(windows_path: str) -> str:
    """Convert a Windows path like C:/Users/foo to /mnt/c/Users/foo."""
    # Replace backslashes
    path = windows_path.replace("\\", "/")
    # Convert drive letter: C:/... -> /mnt/c/...
    match = re.match(r"^([A-Za-z]):/?(.*)", path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2)
        return f"/mnt/{drive}/{rest}"
    return path


# ---------------------------------------------------------------------------
# Lockfile reading / sorting
# ---------------------------------------------------------------------------


def get_sorted_ide_lockfiles() -> List[str]:
    """
    Return all lockfile paths sorted by modification time (newest first).
    """
    lockfile_dirs = get_ide_lockfiles_paths()
    all_lockfiles: List[Tuple[str, float]] = []

    for dir_path in lockfile_dirs:
        try:
            for entry in os.scandir(dir_path):
                if entry.name.endswith(".lock"):
                    try:
                        mtime = entry.stat().st_mtime
                        all_lockfiles.append((entry.path, mtime))
                    except OSError:
                        pass
        except OSError:
            pass

    all_lockfiles.sort(key=lambda x: x[1], reverse=True)
    return [path for path, _ in all_lockfiles]


def read_ide_lockfile(path: str) -> Optional[IdeLockfileInfo]:
    """Parse a lockfile and return its info, or None on failure."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    workspace_folders: List[str] = []
    pid: Optional[int] = None
    ide_name: Optional[str] = None
    use_web_socket = False
    running_in_windows = False
    auth_token: Optional[str] = None

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            workspace_folders = parsed.get("workspaceFolders", [])
            raw_pid = parsed.get("pid")
            pid = int(raw_pid) if raw_pid is not None else None
            ide_name = parsed.get("ideName")
            use_web_socket = parsed.get("transport") == "ws"
            running_in_windows = parsed.get("runningInWindows", False) is True
            auth_token = parsed.get("authToken")
    except (json.JSONDecodeError, ValueError):
        # Older format: just a list of paths, one per line
        workspace_folders = [line.strip() for line in content.split("\n") if line.strip()]

    # Extract port from filename (e.g., 12345.lock -> 12345)
    filename = os.path.basename(path)
    if not filename:
        return None

    port_str = filename.replace(".lock", "")
    try:
        port = int(port_str)
    except ValueError:
        return None

    return IdeLockfileInfo(
        workspace_folders=workspace_folders,
        port=port,
        pid=pid,
        ide_name=ide_name,
        use_web_socket=use_web_socket,
        running_in_windows=running_in_windows,
        auth_token=auth_token,
    )


# ---------------------------------------------------------------------------
# Network / connection check
# ---------------------------------------------------------------------------


def check_ide_connection(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check if we can connect to host:port within the given timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as _:
            return True
    except (OSError, socket.timeout):
        return False


def detect_host_ip(is_ide_running_in_windows: bool, port: int) -> str:
    """
    Determine the host IP to use to connect to the IDE extension.
    On WSL with a Windows-hosted IDE, may need the WSL gateway IP.
    """
    override = os.environ.get("CLAUDE_CODE_IDE_HOST_OVERRIDE")
    if override:
        return override

    if get_platform() != "wsl" or not is_ide_running_in_windows:
        return "127.0.0.1"

    # WSL2: find gateway IP for the Windows host
    try:
        result = subprocess.run(
            "ip route show | grep -i default",
            shell=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout:
            match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                gateway_ip = match.group(1)
                if check_ide_connection(gateway_ip, port):
                    return gateway_ip
    except (subprocess.TimeoutExpired, OSError):
        pass

    return "127.0.0.1"


# ---------------------------------------------------------------------------
# Lockfile cleanup
# ---------------------------------------------------------------------------


def cleanup_stale_ide_lockfiles() -> None:
    """Remove lockfiles for dead processes or non-responding ports."""
    lockfiles = get_sorted_ide_lockfiles()
    for lockfile_path in lockfiles:
        info = read_ide_lockfile(lockfile_path)
        if info is None:
            try:
                os.unlink(lockfile_path)
            except OSError:
                pass
            continue

        host = detect_host_ip(info.running_in_windows, info.port)
        should_delete = False

        if info.pid is not None:
            if not is_process_running(info.pid):
                if get_platform() != "wsl":
                    should_delete = True
                else:
                    # PID may be unreliable in WSL — also check connection
                    if not check_ide_connection(host, info.port):
                        should_delete = True
        else:
            if not check_ide_connection(host, info.port):
                should_delete = True

        if should_delete:
            try:
                os.unlink(lockfile_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# IDE detection via lockfiles
# ---------------------------------------------------------------------------


def detect_ides(include_invalid: bool = False) -> List[DetectedIDEInfo]:
    """
    Detect running IDEs that have an active extension/plugin lockfile.

    :param include_invalid: If True, include IDEs whose workspace doesn't
                            match the current working directory.
    :returns: List of DetectedIDEInfo objects.
    """
    detected: List[DetectedIDEInfo] = []

    try:
        sse_port_str = os.environ.get("CLAUDE_CODE_SSE_PORT")
        env_port = int(sse_port_str) if sse_port_str else None

        # Normalize cwd to NFC for consistent path comparison
        try:
            import unicodedata
            cwd = unicodedata.normalize("NFC", os.getcwd())
        except Exception:
            cwd = os.getcwd()

        lockfiles = get_sorted_ide_lockfiles()

        skip_valid_check = bool(os.environ.get("CLAUDE_CODE_IDE_SKIP_VALID_CHECK"))
        platform = get_platform()
        needs_ancestry_check = platform != "wsl" and is_supported_terminal()

        for lockfile_path in lockfiles:
            info = read_ide_lockfile(lockfile_path)
            if info is None:
                continue

            is_valid = False
            if skip_valid_check:
                is_valid = True
            elif env_port is not None and info.port == env_port:
                is_valid = True
            else:
                is_valid = _check_workspace_match(info, cwd, platform)

            if not is_valid and not include_invalid:
                continue

            # PID ancestry check when running in a supported IDE terminal
            if needs_ancestry_check:
                port_matches_env = env_port is not None and info.port == env_port
                if not port_matches_env:
                    if info.pid is None or not is_process_running(info.pid):
                        continue
                    cur_ppid = os.getppid()
                    if cur_ppid != info.pid:
                        ancestors = set(get_ancestor_pids(cur_ppid))
                        if info.pid not in ancestors:
                            continue

            ide_name = info.ide_name or (
                to_ide_display_name(get_terminal_ide_type())
                if is_supported_terminal()
                else "IDE"
            )

            host = detect_host_ip(info.running_in_windows, info.port)
            if info.use_web_socket:
                url = f"ws://{host}:{info.port}"
            else:
                url = f"http://{host}:{info.port}/sse"

            detected.append(
                DetectedIDEInfo(
                    name=ide_name,
                    port=info.port,
                    workspace_folders=info.workspace_folders,
                    url=url,
                    is_valid=is_valid,
                    auth_token=info.auth_token,
                    ide_running_in_windows=info.running_in_windows,
                )
            )

        # When env_port is set, prefer the matching IDE
        if not include_invalid and env_port is not None:
            env_port_matches = [
                ide for ide in detected if ide.is_valid and ide.port == env_port
            ]
            if len(env_port_matches) == 1:
                return env_port_matches

    except Exception:
        pass

    return detected


def _check_workspace_match(
    info: IdeLockfileInfo, cwd: str, platform: str
) -> bool:
    """Return True if any of the lockfile's workspace folders contain cwd."""
    import unicodedata

    for ide_path in info.workspace_folders:
        if not ide_path:
            continue

        local_path = ide_path

        if (
            platform == "wsl"
            and info.running_in_windows
            and os.environ.get("WSL_DISTRO_NAME")
        ):
            # Check for WSL distro mismatch (simplified)
            distro = os.environ["WSL_DISTRO_NAME"]
            if f"\\\\wsl$\\{distro}" in ide_path or f"\\\\wsl.localhost\\{distro}" in ide_path:
                pass  # This distro matches
            elif re.search(r"\\\\wsl", ide_path, re.IGNORECASE):
                continue  # Different distro

            original = unicodedata.normalize(
                "NFC", os.path.realpath(local_path)
            )
            if cwd == original or cwd.startswith(original + os.sep):
                return True

            local_path = _windows_path_to_wsl(ide_path)

        try:
            resolved = unicodedata.normalize(
                "NFC", os.path.realpath(local_path)
            )
        except Exception:
            resolved = local_path

        if platform == "windows":
            # Case-insensitive drive letter comparison
            norm_cwd = re.sub(r"^[a-zA-Z]:", lambda m: m.group().upper(), cwd)
            norm_resolved = re.sub(
                r"^[a-zA-Z]:", lambda m: m.group().upper(), resolved
            )
            if norm_cwd == norm_resolved or norm_cwd.startswith(
                norm_resolved + os.sep
            ):
                return True
        else:
            if cwd == resolved or cwd.startswith(resolved + os.sep):
                return True

    return False


# ---------------------------------------------------------------------------
# Running IDE detection via process list
# ---------------------------------------------------------------------------

# Module-level cache (None = not yet populated)
_cached_running_ides: Optional[List[str]] = None


def detect_running_ides() -> List[str]:
    """
    Detect which IDEs are currently running via OS process list.
    Returns a list of IdeType strings. Updates the module-level cache.
    """
    global _cached_running_ides
    result = _detect_running_ides_impl()
    _cached_running_ides = result
    return result


def detect_running_ides_cached() -> List[str]:
    """Return cached IDE detection results, or run detection if cache is empty."""
    if _cached_running_ides is None:
        return detect_running_ides()
    return _cached_running_ides


def reset_detect_running_ides() -> None:
    """Reset the running IDE detection cache. Useful for testing."""
    global _cached_running_ides
    _cached_running_ides = None


def _detect_running_ides_impl() -> List[str]:
    """Internal: detect running IDEs by scanning the OS process list."""
    running: List[str] = []
    platform = get_platform()

    try:
        if platform == "macos":
            result = subprocess.run(
                "ps aux | grep -E "
                '"Visual Studio Code|Code Helper|Cursor Helper|Windsurf Helper|'
                "IntelliJ IDEA|PyCharm|WebStorm|PhpStorm|RubyMine|CLion|GoLand|"
                'Rider|DataGrip|AppCode|DataSpell|Aqua|Gateway|Fleet|Android Studio" '
                "| grep -v grep",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            stdout = result.stdout or ""
            for ide_type, config in SUPPORTED_IDE_CONFIGS.items():
                for keyword in config.process_keywords_mac:
                    if keyword in stdout:
                        running.append(ide_type)
                        break

        elif platform == "windows":
            result = subprocess.run(
                "tasklist | findstr /I "
                '"Code.exe Cursor.exe Windsurf.exe idea64.exe pycharm64.exe '
                "webstorm64.exe phpstorm64.exe rubymine64.exe clion64.exe "
                'goland64.exe rider64.exe datagrip64.exe appcode.exe dataspell64.exe '
                'aqua64.exe gateway64.exe fleet.exe studio64.exe"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            stdout_lower = (result.stdout or "").lower()
            for ide_type, config in SUPPORTED_IDE_CONFIGS.items():
                for keyword in config.process_keywords_windows:
                    if keyword.lower() in stdout_lower:
                        running.append(ide_type)
                        break

        else:  # linux or wsl
            result = subprocess.run(
                "ps aux | grep -E "
                '"code|cursor|windsurf|idea|pycharm|webstorm|phpstorm|rubymine|'
                'clion|goland|rider|datagrip|dataspell|aqua|gateway|fleet|android-studio" '
                "| grep -v grep",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            stdout_lower = (result.stdout or "").lower()
            for ide_type, config in SUPPORTED_IDE_CONFIGS.items():
                for keyword in config.process_keywords_linux:
                    if keyword in stdout_lower:
                        if ide_type != "vscode":
                            running.append(ide_type)
                            break
                        else:
                            # Avoid false positives: 'code' matches cursor/appcode
                            if "cursor" not in stdout_lower and "appcode" not in stdout_lower:
                                running.append(ide_type)
                                break

    except (subprocess.TimeoutExpired, OSError):
        pass

    return running


# ---------------------------------------------------------------------------
# VSCode command helpers
# ---------------------------------------------------------------------------


def get_vscode_ide_command(ide_type: str) -> Optional[str]:
    """Return the CLI command name for a VS Code variant."""
    ext = ".cmd" if get_platform() == "windows" else ""
    commands = {
        "vscode": "code" + ext,
        "cursor": "cursor" + ext,
        "windsurf": "windsurf" + ext,
    }
    return commands.get(ide_type)


def is_cursor_installed() -> bool:
    """Return True if the cursor CLI is available."""
    try:
        result = subprocess.run(
            ["cursor", "--version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_windsurf_installed() -> bool:
    """Return True if the windsurf CLI is available."""
    try:
        result = subprocess.run(
            ["windsurf", "--version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_vscode_installed() -> bool:
    """Return True if VS Code CLI is available and it's actually VS Code."""
    try:
        result = subprocess.run(
            ["code", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "Visual Studio Code" in (result.stdout or "")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Extension installation status
# ---------------------------------------------------------------------------


def is_ide_extension_installed(ide_type: str) -> bool:
    """
    Check if the Claude Code extension is installed in the given IDE.
    Returns False for JetBrains (requires separate plugin check).
    """
    if is_vscode_ide(ide_type):
        command = get_vscode_ide_command(ide_type)
        if command:
            try:
                env = dict(os.environ)
                if get_platform() == "linux":
                    env["DISPLAY"] = ""
                result = subprocess.run(
                    [command, "--list-extensions"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env=env,
                )
                extension_id = (
                    "anthropic.claude-code-internal"
                    if os.environ.get("USER_TYPE") == "ant"
                    else "anthropic.claude-code"
                )
                if result.stdout and extension_id in result.stdout:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass
    return False


# ---------------------------------------------------------------------------
# Find available IDE (single IDE detection for auto-connect)
# ---------------------------------------------------------------------------


def find_available_ide() -> Optional[DetectedIDEInfo]:
    """
    Clean up stale lockfiles, then look for exactly one valid IDE.
    Returns the IDE if exactly one is found, else None.
    Simple synchronous version (no polling loop).
    """
    cleanup_stale_ide_lockfiles()
    ides = detect_ides(include_invalid=False)
    if len(ides) == 1:
        return ides[0]
    return None


# ---------------------------------------------------------------------------
# IDE workspace root
# ---------------------------------------------------------------------------


def get_ide_workspace_root() -> Optional[str]:
    """
    Return the IDE workspace root folder that contains the current directory,
    or None if no matching IDE is found.
    """
    ides = detect_ides(include_invalid=False)
    cwd = os.getcwd()
    for ide in ides:
        if ide.is_valid and ide.workspace_folders:
            for folder in ide.workspace_folders:
                if folder and (cwd == folder or cwd.startswith(folder + os.sep)):
                    return folder
    return None


# ---------------------------------------------------------------------------
# IDE name helpers
# ---------------------------------------------------------------------------


def get_connected_ide_name(mcp_clients: list) -> Optional[str]:
    """
    Return the display name of the connected IDE from a list of MCP client dicts.
    Expects dicts with keys: type, name, config (where config has type/ideName).
    """
    for client in mcp_clients:
        if client.get("type") == "connected" and client.get("name") == "ide":
            return get_ide_client_name(client)
    return None


def get_ide_client_name(ide_client: Optional[dict]) -> Optional[str]:
    """Extract the IDE display name from a connected MCP client dict."""
    if ide_client is None:
        return None
    config = ide_client.get("config", {})
    if config.get("type") in ("sse-ide", "ws-ide"):
        return config.get("ideName")
    if is_supported_terminal():
        return to_ide_display_name(get_terminal_ide_type())
    return None


def has_access_to_ide_extension_diff_feature(mcp_clients: list) -> bool:
    """Return True if a connected IDE client is present."""
    return any(
        c.get("type") == "connected" and c.get("name") == "ide"
        for c in mcp_clients
    )


def get_connected_ide_client(mcp_clients: Optional[list]) -> Optional[dict]:
    """Return the first connected IDE client dict, or None."""
    if not mcp_clients:
        return None
    for client in mcp_clients:
        if client.get("type") == "connected" and client.get("name") == "ide":
            return client
    return None


# ---------------------------------------------------------------------------
# IDE type / path environment variables
# ---------------------------------------------------------------------------


def get_ide_type() -> Optional[str]:
    """
    Detect the current IDE type.
    Checks environment variables first, then falls back to terminal detection.
    """
    # TERM_PROGRAM is set by VS Code and derivatives
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program:
        term_lower = term_program.lower()
        for ide_type in SUPPORTED_IDE_CONFIGS:
            if ide_type in term_lower or term_lower in ide_type:
                return ide_type

    # JetBrains sets TERMINAL_EMULATOR
    terminal_emulator = os.environ.get("TERMINAL_EMULATOR", "")
    if "jetbrains" in terminal_emulator.lower():
        # Try to be more specific from the lockfiles
        ides = detect_ides(include_invalid=True)
        for ide in ides:
            ide_name_lower = (ide.name or "").lower()
            for ide_type, config in SUPPORTED_IDE_CONFIGS.items():
                if config.ide_kind == "jetbrains" and (
                    ide_type in ide_name_lower or config.display_name.lower() in ide_name_lower
                ):
                    return ide_type
        return "intellij"  # generic fallback for JetBrains

    return get_terminal_ide_type()


def get_ide_path_conversion() -> Optional[str]:
    """
    Return path conversion type needed for the current IDE environment.
    Returns 'windows-to-wsl' for WSL + Windows IDE, None otherwise.
    """
    platform = get_platform()
    if platform == "wsl":
        ides = detect_ides(include_invalid=True)
        for ide in ides:
            if ide.ide_running_in_windows:
                return "windows-to-wsl"
    return None


def launch_ide(path: str, ide_type: Optional[str] = None) -> bool:
    """
    Open the given path in the detected or specified IDE.
    Returns True if the launch command succeeded.
    """
    effective_ide = ide_type or get_ide_type()
    if effective_ide is None:
        return False

    if is_vscode_ide(effective_ide):
        command = get_vscode_ide_command(effective_ide)
        if command:
            try:
                result = subprocess.run(
                    [command, path],
                    capture_output=True,
                    timeout=10,
                )
                return result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                return False

    elif is_jetbrains_ide(effective_ide):
        # JetBrains IDEs: try common CLI launchers
        jetbrains_commands = {
            "intellij": ["idea"],
            "pycharm": ["pycharm"],
            "webstorm": ["webstorm"],
            "phpstorm": ["phpstorm"],
            "rubymine": ["rubymine"],
            "clion": ["clion"],
            "goland": ["goland"],
            "rider": ["rider"],
            "datagrip": ["datagrip"],
            "dataspell": ["dataspell"],
            "androidstudio": ["studio"],
        }
        commands = jetbrains_commands.get(effective_ide, [effective_ide])
        for cmd in commands:
            try:
                result = subprocess.run(
                    [cmd, path],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue

    return False
