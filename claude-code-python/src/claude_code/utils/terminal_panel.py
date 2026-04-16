# 原始 TS: utils/terminalPanel.ts
"""终端面板状态管理。

对应 TypeScript terminalPanel.ts 的核心逻辑，去掉了
React/Ink 渲染依赖，保留 tmux 会话管理与状态模型。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# ---------------------------------------------------------------------------
# 状态数据类
# ---------------------------------------------------------------------------
TMUX_SESSION = "panel"


@dataclass
class TerminalPanelState:
    """终端面板当前状态快照。"""
    is_open: bool = False
    width: int = 0
    height: int = 0
    active_pane: Optional[str] = None
    has_tmux: Optional[bool] = None   # None = 未检测
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def get_terminal_panel_socket(session_id: str) -> str:
    """根据 session_id 生成唯一的 tmux socket 名称。

    对应 TS getTerminalPanelSocket()。
    """
    return f"claude-panel-{session_id[:8]}"


def _check_tmux() -> bool:
    """检测系统是否安装了 tmux。"""
    return shutil.which("tmux") is not None


def _run_tmux(*args: str, socket: str, **kwargs) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    """运行 tmux 命令（helper）。"""
    return subprocess.run(
        ["tmux", "-L", socket, *args],
        capture_output=True, text=True, **kwargs
    )


# ---------------------------------------------------------------------------
# TerminalPanelManager
# ---------------------------------------------------------------------------
class TerminalPanelManager:
    """管理终端面板生命周期（单例模式）。

    对应 TS TerminalPanel 类，去掉了 Ink/React 依赖。
    所有 tmux 操作均为同步调用（subprocess）。
    """

    def __init__(self, session_id: str = "default0") -> None:
        self._session_id = session_id
        self._socket = get_terminal_panel_socket(session_id)
        self._state = TerminalPanelState(session_id=session_id)
        self._cleanup_handlers: List[Callable[[], None]] = []
        self._cleanup_registered = False

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def open(self) -> bool:
        """打开终端面板（确保 tmux session 存在）。

        Returns True 表示成功打开或已打开，False 表示失败。
        """
        if self._state.is_open:
            return True
        if not self._ensure_tmux():
            return False
        if self._ensure_session():
            self._state.is_open = True
            return True
        return False

    def close(self) -> None:
        """关闭终端面板（杀掉 tmux server）。"""
        if self._state.is_open:
            try:
                subprocess.run(
                    ["tmux", "-L", self._socket, "kill-server"],
                    capture_output=True,
                )
            except FileNotFoundError:
                pass
            self._state.is_open = False

    def resize(self, width: int, height: int) -> None:
        """更新面板尺寸记录（stub：不直接控制终端尺寸）。"""
        self._state.width = width
        self._state.height = height

    def get_state(self) -> TerminalPanelState:
        """返回当前状态快照（副本）。"""
        return TerminalPanelState(
            is_open=self._state.is_open,
            width=self._state.width,
            height=self._state.height,
            active_pane=self._state.active_pane,
            has_tmux=self._state.has_tmux,
            session_id=self._state.session_id,
        )

    def toggle(self) -> bool:
        """切换面板开关状态。"""
        if self._state.is_open:
            self.close()
            return False
        return self.open()

    def attach(self) -> None:
        """attach 到 tmux session（阻塞，直到用户 detach）。"""
        if not self._state.is_open:
            raise RuntimeError("Panel is not open. Call open() first.")
        subprocess.run(
            ["tmux", "-L", self._socket, "attach-session", "-t", TMUX_SESSION],
            stdin=None, stdout=None, stderr=None,  # 继承 stdio
        )

    def register_cleanup(self, handler: Callable[[], None]) -> None:
        """注册面板关闭时的清理回调。"""
        self._cleanup_handlers.append(handler)

    def run_cleanup(self) -> None:
        """执行所有注册的清理回调。"""
        for h in self._cleanup_handlers:
            try:
                h()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _ensure_tmux(self) -> bool:
        if self._state.has_tmux is None:
            self._state.has_tmux = _check_tmux()
        return bool(self._state.has_tmux)

    def _has_session(self) -> bool:
        result = _run_tmux("has-session", "-t", TMUX_SESSION, socket=self._socket)
        return result.returncode == 0

    def _ensure_session(self) -> bool:
        if self._has_session():
            return True
        return self._create_session()

    def _create_session(self) -> bool:
        shell = os.environ.get("SHELL", "/bin/bash")
        cwd = os.getcwd()
        result = _run_tmux(
            "new-session", "-d", "-s", TMUX_SESSION, "-c", cwd, shell, "-l",
            socket=self._socket,
        )
        if result.returncode != 0:
            return False

        # 配置快捷键和状态栏（一次性批量）
        _run_tmux(
            "bind-key", "-n", "M-j", "detach-client", ";",
            "set-option", "-g", "status-style", "bg=default", ";",
            "set-option", "-g", "status-left", "", ";",
            "set-option", "-g", "status-right", " Alt+J to return to Claude ", ";",
            "set-option", "-g", "status-right-style", "fg=brightblack",
            socket=self._socket,
        )
        return True


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------
_instance: Optional[TerminalPanelManager] = None


def get_terminal_panel(session_id: str = "default0") -> TerminalPanelManager:
    """返回全局单例 TerminalPanelManager（对应 TS getTerminalPanel）。"""
    global _instance
    if _instance is None:
        _instance = TerminalPanelManager(session_id)
    return _instance
