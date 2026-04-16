# 原始 TS: utils/mcpWebSocketTransport.ts
"""MCP WebSocket 传输层。

提供 WebSocketTransport 类，实现 MCP Transport 协议：
start / close / send，以及 onmessage / onclose / onerror 回调。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# WebSocket readyState 常量
WS_CONNECTING = 0
WS_OPEN = 1
WS_CLOSING = 2
WS_CLOSED = 3

# ---------------------------------------------------------------------------
# 尝试导入 websockets；若不可用则提供最小 stub
# ---------------------------------------------------------------------------
try:
    import websockets  # type: ignore
    import websockets.exceptions  # type: ignore
    _HAS_WEBSOCKETS = True
except ImportError:  # pragma: no cover
    _HAS_WEBSOCKETS = False
    websockets = None  # type: ignore


# ---------------------------------------------------------------------------
# JSON-RPC 消息类型（简化版）
# ---------------------------------------------------------------------------
JSONRPCMessage = Dict[str, Any]


def _parse_jsonrpc(raw: str) -> JSONRPCMessage:
    """解析并基本校验 JSON-RPC 消息。"""
    msg = json.loads(raw)
    if not isinstance(msg, dict):
        raise ValueError(f"Expected JSON object, got {type(msg)}")
    if "jsonrpc" not in msg:
        raise ValueError("Missing 'jsonrpc' field")
    return msg


# ---------------------------------------------------------------------------
# WebSocket 适配器抽象（兼容不同后端）
# ---------------------------------------------------------------------------
class _WsAdapter:
    """对底层 websockets 连接的轻量封装。"""

    def __init__(self, ws: Any) -> None:
        self._ws = ws

    @property
    def open(self) -> bool:
        if hasattr(self._ws, "open"):
            return bool(self._ws.open)
        state = getattr(self._ws, "state", None)
        if state is not None:
            # websockets >= 10 uses State enum
            return str(state).endswith("OPEN")
        return False

    async def send(self, data: str) -> None:
        await self._ws.send(data)

    async def close(self) -> None:
        await self._ws.close()

    def __aiter__(self):  # type: ignore[return]
        return self._ws.__aiter__()


# ---------------------------------------------------------------------------
# WebSocketTransport
# ---------------------------------------------------------------------------
class WebSocketTransport:
    """MCP WebSocket 传输实现。

    与 TypeScript 版 WebSocketTransport 功能对等：
    - start()  — 等待连接就绪
    - send()   — 发送 JSON-RPC 消息
    - close()  — 关闭连接
    - 回调：onmessage / onclose / onerror
    """

    def __init__(self, ws: Any) -> None:
        """
        Parameters
        ----------
        ws:
            已建立（或正在建立）的 WebSocket 连接对象。
            接受 websockets 库的 WebSocketClientProtocol，
            或任何实现了 send / close / __aiter__ 的对象。
        """
        self._ws = _WsAdapter(ws)
        self._started = False
        self._recv_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

        # 公开回调（与 TS 版对齐）
        self.onmessage: Optional[Callable[[JSONRPCMessage], None]] = None
        self.onclose: Optional[Callable[[], None]] = None
        self.onerror: Optional[Callable[[Exception], None]] = None

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动传输层，开始接收消息。每个实例只能调用一次。"""
        if self._started:
            raise RuntimeError("start() can only be called once per transport.")
        if not self._ws.open:
            raise RuntimeError("WebSocket is not open. Cannot start transport.")
        self._started = True
        self._recv_task = asyncio.ensure_future(self._recv_loop())

    async def close(self) -> None:
        """关闭 WebSocket 连接并停止接收循环。"""
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        try:
            await self._ws.close()
        except Exception:
            pass
        self._fire_close()

    async def send(self, message: JSONRPCMessage) -> None:
        """序列化并发送 JSON-RPC 消息。"""
        if not self._ws.open:
            logger.error("mcp_websocket_send_not_opened")
            raise RuntimeError("WebSocket is not open. Cannot send message.")
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        try:
            await self._ws.send(raw)
        except Exception as exc:
            self._fire_error(exc)
            raise

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    msg = _parse_jsonrpc(raw)
                    if self.onmessage:
                        self.onmessage(msg)
                except Exception as exc:
                    logger.error("mcp_websocket_message_fail: %s", exc)
                    self._fire_error(exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("mcp_websocket_recv_error: %s", exc)
            self._fire_error(exc)
        finally:
            self._fire_close()

    def _fire_error(self, exc: Exception) -> None:
        if self.onerror:
            try:
                self.onerror(exc)
            except Exception:
                pass

    def _fire_close(self) -> None:
        if self.onclose:
            try:
                self.onclose()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 工厂函数（需要 websockets 库）
# ---------------------------------------------------------------------------
async def connect_websocket_transport(uri: str) -> "WebSocketTransport":
    """连接到指定 URI 并返回已启动的 WebSocketTransport。

    需要安装 `websockets` 包。

    Parameters
    ----------
    uri:
        WebSocket 服务端地址，如 ``ws://localhost:8080``。
    """
    if not _HAS_WEBSOCKETS:
        raise ImportError(
            "websockets package is required. Install with: pip install websockets"
        )
    ws = await websockets.connect(uri)  # type: ignore[union-attr]
    transport = WebSocketTransport(ws)
    await transport.start()
    return transport
