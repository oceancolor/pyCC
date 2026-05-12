"""
in_process_transport.py - In-process MCP transport for directly embedded servers.

Port of TypeScript InProcessTransport.ts.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class InProcessTransport:
    """
    MCP transport that connects two in-process endpoints without network I/O.

    Used when an MCP server runs in the same Python process as the client
    (e.g., the computer-use MCP server).

    Creates a pair of linked transports (client-side and server-side) that
    exchange messages via asyncio queues.
    """

    def __init__(self):
        self._client_queue: asyncio.Queue = asyncio.Queue()
        self._server_queue: asyncio.Queue = asyncio.Queue()
        self._closed = False
        self._on_message: Optional[Callable[[Dict[str, Any]], None]] = None
        self._on_close: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[Exception], None]] = None
        self._linked: Optional['InProcessTransport'] = None
        self._reader_task: Optional[asyncio.Task] = None

    @classmethod
    def create_linked_pair(cls) -> tuple:
        """
        Create a linked pair of in-process transports.

        Returns:
            Tuple of (client_transport, server_transport).
        """
        client = cls()
        server = cls()
        client._linked = server
        server._linked = client
        return client, server

    def on_message(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Set the message handler."""
        self._on_message = handler

    def on_close(self, handler: Callable[[], None]) -> None:
        """Set the close handler."""
        self._on_close = handler

    def on_error(self, handler: Callable[[Exception], None]) -> None:
        """Set the error handler."""
        self._on_error = handler

    async def start(self) -> None:
        """Start receiving messages."""
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Background loop for reading messages from the queue."""
        while not self._closed:
            try:
                message = await asyncio.wait_for(
                    self._client_queue.get(),
                    timeout=1.0,
                )
                if self._on_message:
                    try:
                        self._on_message(message)
                    except Exception as e:
                        if self._on_error:
                            self._on_error(e)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._on_error:
                    self._on_error(e)

    async def send(self, message: Dict[str, Any]) -> None:
        """Send a message to the linked transport."""
        if self._closed:
            raise RuntimeError('Transport is closed')

        if self._linked:
            await self._linked._client_queue.put(message)

    async def close(self) -> None:
        """Close this transport."""
        if self._closed:
            return

        self._closed = True

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._on_close:
            self._on_close()

        if self._linked and not self._linked._closed:
            await self._linked.close()
