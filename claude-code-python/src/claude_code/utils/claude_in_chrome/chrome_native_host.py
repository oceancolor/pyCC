"""Chrome native messaging host. Ported from utils/claudeInChrome/chromeNativeHost.ts"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

VERSION = "1.0.0"
MAX_MESSAGE_SIZE = 1024 * 1024  # 1 MB

log = logging.getLogger(__name__)

_LOG_FILE: Optional[str] = (
    str(Path.home() / ".claude" / "debug" / "chrome-native-host.txt")
    if os.environ.get("USER_TYPE") == "ant"
    else None
)


def _log_to_file(message: str, *args: Any) -> None:
    """Append a log line to the debug log file (best-effort)."""
    if not _LOG_FILE:
        return
    try:
        timestamp = datetime.utcnow().isoformat()
        args_str = (" " + json.dumps(list(args))) if args else ""
        line = f"[{timestamp}] [Claude Chrome Native Host] {message}{args_str}\n"
        os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(f"[Claude Chrome Native Host] {message}", *args, file=sys.stderr)


def send_chrome_message(message: str) -> None:
    """Send a message to stdout using the Chrome native messaging protocol.

    The protocol prefixes each message with its 4-byte little-endian length.
    """
    msg_bytes = message.encode("utf-8")
    length_bytes = struct.pack("<I", len(msg_bytes))
    sys.stdout.buffer.write(length_bytes)
    sys.stdout.buffer.write(msg_bytes)
    sys.stdout.buffer.flush()


async def read_chrome_message() -> Optional[str]:
    """Read one message from stdin using the Chrome native messaging protocol.

    Returns None when stdin closes (Chrome disconnected).
    """
    loop = asyncio.get_event_loop()

    def _read_blocking() -> Optional[str]:
        raw = sys.stdin.buffer.read(4)
        if not raw or len(raw) < 4:
            return None
        length = struct.unpack("<I", raw)[0]
        if length > MAX_MESSAGE_SIZE:
            _log_to_file(f"Message too large: {length} bytes")
            return None
        data = sys.stdin.buffer.read(length)
        if len(data) < length:
            return None
        return data.decode("utf-8")

    return await loop.run_in_executor(None, _read_blocking)


class ChromeNativeHost:
    """Python implementation of the Chrome native messaging host."""

    def __init__(self) -> None:
        self._server: Optional[asyncio.AbstractServer] = None
        self._connected_clients: list = []

    async def start(self) -> None:
        """Start the local Unix-socket server that the extension connects to."""
        from .common import get_secure_socket_path, get_socket_dir

        socket_dir = get_socket_dir()
        os.makedirs(socket_dir, mode=0o700, exist_ok=True)

        session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
        socket_path = get_secure_socket_path(session_id)

        # Clean up stale socket
        try:
            os.unlink(socket_path)
        except FileNotFoundError:
            pass

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=socket_path
        )
        os.chmod(socket_path, 0o600)
        _log_to_file(f"Listening on {socket_path}")

    async def stop(self) -> None:
        """Stop the server and disconnect all clients."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        _log_to_file("Client connected")
        self._connected_clients.append(writer)
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                await self._dispatch(data.decode("utf-8", errors="replace"))
        finally:
            self._connected_clients.remove(writer)
            writer.close()
            _log_to_file("Client disconnected")

    async def _dispatch(self, payload: str) -> None:
        """Dispatch a message from the extension to the Claude session."""
        try:
            msg = json.loads(payload)
            _log_to_file("Received message", msg.get("type"))
        except json.JSONDecodeError:
            _log_to_file("Invalid JSON from client")

    async def handle_message(self, raw_message: str) -> None:
        """Handle an incoming Chrome native messaging message."""
        try:
            msg = json.loads(raw_message)
            msg_type = msg.get("type", "unknown")
            _log_to_file(f"Chrome message: {msg_type}")

            if msg_type == "ping":
                send_chrome_message(json.dumps({"type": "pong", "version": VERSION}))
        except json.JSONDecodeError:
            _log_to_file("Invalid JSON from Chrome")


async def run_chrome_native_host() -> None:
    """Entry point for the Chrome native messaging host process.

    Reads messages from Chrome via stdin and forwards them to the session socket.
    """
    _log_to_file("Initializing...")
    host = ChromeNativeHost()
    await host.start()

    while True:
        message = await read_chrome_message()
        if message is None:
            _log_to_file("Chrome disconnected (stdin closed)")
            break
        await host.handle_message(message)

    await host.stop()
    _log_to_file("Native host exiting")
