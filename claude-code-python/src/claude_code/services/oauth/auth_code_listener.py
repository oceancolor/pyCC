"""OAuth auth code listener. Ported from services/oauth/auth-code-listener.ts"""
from __future__ import annotations
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse


class AuthCodeListener:
    """Temporary localhost HTTP server that captures OAuth authorization code redirects.

    When the user authorizes in the browser, the OAuth provider redirects to
    http://localhost:[port]/callback?code=AUTH_CODE&state=STATE
    This server captures that redirect and extracts the auth code.
    """

    def __init__(self, callback_path: str = "/callback") -> None:
        self._server: Optional[HTTPServer] = None
        self._port: int = 0
        self._callback_path = callback_path
        self._auth_code: Optional[str] = None
        self._expected_state: Optional[str] = None
        self._future: Optional[asyncio.Future] = None

    async def start(self, port: int = 0) -> int:
        """Start listening on an OS-assigned port. Returns the actual port."""
        loop = asyncio.get_event_loop()
        self._future = loop.create_future()

        listener = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence access logs
                pass

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != listener._callback_path:
                    self.send_response(404)
                    self.end_headers()
                    return

                params = parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                state = params.get("state", [None])[0]

                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body>Authorization complete. You may close this window.</body></html>")

                if listener._future and not listener._future.done():
                    if state == listener._expected_state and code:
                        listener._future.get_event_loop().call_soon_threadsafe(
                            listener._future.set_result, code
                        )
                    else:
                        listener._future.get_event_loop().call_soon_threadsafe(
                            listener._future.set_exception,
                            ValueError(f"Invalid state or missing code: state={state}"),
                        )

        self._server = HTTPServer(("localhost", port), Handler)
        self._port = self._server.server_address[1]

        # Run server in background thread
        import threading
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()

        return self._port

    def get_port(self) -> int:
        return self._port

    async def wait_for_authorization(
        self,
        state: str,
        on_ready: Optional[Callable] = None,
    ) -> str:
        """Block until the authorization code is received."""
        self._expected_state = state
        if on_ready:
            if asyncio.iscoroutinefunction(on_ready):
                await on_ready()
            else:
                on_ready()
        assert self._future is not None
        return await self._future

    def stop(self) -> None:
        """Stop the listener server."""
        if self._server:
            self._server.shutdown()
            self._server = None


async def start_auth_code_listener(port: int = 0) -> Optional[str]:
    """Start the auth code listener and return a URL for the callback."""
    listener = AuthCodeListener()
    actual_port = await listener.start(port)
    return f"http://localhost:{actual_port}/callback"
