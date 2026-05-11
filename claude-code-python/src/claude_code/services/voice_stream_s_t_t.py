"""
Voice stream speech-to-text client for push-to-talk.

Port of services/voiceStreamSTT.ts (544 lines)

Connects to Anthropic's voice_stream WebSocket endpoint using OAuth credentials.
Designed for hold-to-talk: hold the keybinding to record, release to stop and submit.

The wire protocol uses JSON control messages (KeepAlive, CloseStream) and
binary audio frames. The server responds with TranscriptText and
TranscriptEndpoint JSON messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VOICE_STREAM_PATH = "/api/ws/speech_to_text/voice_stream"
_KEEPALIVE_INTERVAL_MS = 8_000
_KEEPALIVE_MSG = '{"type":"KeepAlive"}'
_CLOSE_STREAM_MSG = '{"type":"CloseStream"}'

# finalize() resolution timers.
# `no_data` fires when no TranscriptText arrives post-CloseStream.
# `safety` is the last-resort cap if the WS hangs.
FINALIZE_TIMEOUTS_MS: dict[str, int] = {
    "safety": 5_000,
    "no_data": 1_500,
}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

FinalizeSource = Literal[
    "post_closestream_endpoint",
    "no_data_timeout",
    "safety_timeout",
    "ws_close",
    "ws_already_closed",
]


@dataclass
class VoiceStreamCallbacks:
    """Callbacks for voice stream events."""

    on_transcript: Callable[[str, bool], None]
    """Called with (text, is_final) for each transcript chunk."""

    on_error: Callable[[str, Optional[dict]], None]
    """Called with (error_message, opts) on error. opts may have {'fatal': bool}."""

    on_close: Callable[[], None]
    """Called when the connection is closed."""

    on_ready: Callable[["VoiceStreamConnection"], None]
    """Called with the connection object when the WebSocket is open."""


class VoiceStreamConnection:
    """
    Represents an active voice stream WebSocket connection.
    Provides send(), finalize(), close(), and is_connected() methods.
    """

    def __init__(
        self,
        ws: "websockets.WebSocketClientProtocol",  # type: ignore[name-defined]
        callbacks: VoiceStreamCallbacks,
        is_nova3: bool = False,
    ) -> None:
        self._ws = ws
        self._callbacks = callbacks
        self._is_nova3 = is_nova3
        self._finalized = False
        self._finalizing = False
        self._connected = True
        self._keepalive_task: Optional[asyncio.Task] = None
        self._finalize_future: Optional[asyncio.Future[FinalizeSource]] = None
        self._cancel_no_data_timer: Optional[Callable] = None
        self._last_transcript_text: str = ""

    def send(self, audio_chunk: bytes) -> None:
        """Send an audio chunk to the WebSocket."""
        if self._ws is None:
            return
        if self._finalized:
            logger.debug(
                "[voice_stream] Dropping audio chunk after CloseStream: %d bytes",
                len(audio_chunk),
            )
            return
        logger.debug(
            "[voice_stream] Sending audio chunk: %d bytes", len(audio_chunk)
        )
        asyncio.ensure_future(self._ws.send(bytes(audio_chunk)))

    async def finalize(self) -> FinalizeSource:
        """
        Signal end of recording. Sends CloseStream and waits for final transcript.
        Returns a FinalizeSource indicating how the finalization resolved.
        """
        if self._finalizing or self._finalized:
            return "ws_already_closed"

        self._finalizing = True
        self._finalize_future = asyncio.get_event_loop().create_future()

        async def _do_close_stream() -> None:
            # Defer CloseStream by one event loop iteration so any pending audio
            # callbacks are flushed first.
            await asyncio.sleep(0)
            self._finalized = True
            try:
                if self._ws and not self._ws.closed:
                    logger.debug("[voice_stream] Sending CloseStream (finalize)")
                    await self._ws.send(_CLOSE_STREAM_MSG)
            except Exception:
                pass

        asyncio.ensure_future(_do_close_stream())

        # Set up timers
        loop = asyncio.get_event_loop()

        safety_handle = loop.call_later(
            FINALIZE_TIMEOUTS_MS["safety"] / 1000.0,
            lambda: self._resolve_finalize("safety_timeout"),
        )
        no_data_handle = loop.call_later(
            FINALIZE_TIMEOUTS_MS["no_data"] / 1000.0,
            lambda: self._resolve_finalize("no_data_timeout"),
        )

        def cancel_no_data() -> None:
            no_data_handle.cancel()
            self._cancel_no_data_timer = None

        self._cancel_no_data_timer = cancel_no_data

        try:
            result = await self._finalize_future
        finally:
            safety_handle.cancel()

        return result

    def _resolve_finalize(self, source: FinalizeSource) -> None:
        """Resolve the finalize future with the given source."""
        if self._finalize_future and not self._finalize_future.done():
            # Promote any unreported interim transcript
            if self._last_transcript_text:
                logger.debug(
                    "[voice_stream] Promoting unreported interim before %s resolve",
                    source,
                )
                text = self._last_transcript_text
                self._last_transcript_text = ""
                self._callbacks.on_transcript(text, True)
            logger.debug("[voice_stream] Finalize resolved via %s", source)
            self._finalize_future.set_result(source)

    def close(self) -> None:
        """Close the WebSocket connection."""
        self._finalized = True
        self._connected = False
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        asyncio.ensure_future(self._do_close())

    async def _do_close(self) -> None:
        try:
            if self._ws and not self._ws.closed:
                await self._ws.close()
        except Exception:
            pass

    def is_connected(self) -> bool:
        """Returns True if the WebSocket is connected and open."""
        return self._connected and (self._ws is not None and not self._ws.closed)

    def handle_message(self, raw: str) -> None:
        """Process an incoming WebSocket message."""
        logger.debug(
            "[voice_stream] Message received (%d chars): %s",
            len(raw),
            raw[:200],
        )
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type")

        if msg_type == "TranscriptText":
            transcript = msg.get("data", "")
            logger.debug('[voice_stream] TranscriptText: "%s"', transcript)

            # Data arrived after CloseStream → disarm no-data timer
            if self._finalized and self._cancel_no_data_timer:
                self._cancel_no_data_timer()

            if transcript:
                # Detect new speech segment (non-cumulative for non-Nova3)
                if not self._is_nova3 and self._last_transcript_text:
                    prev = self._last_transcript_text.lstrip()
                    nxt = transcript.lstrip()
                    if (
                        prev
                        and nxt
                        and not nxt.startswith(prev)
                        and not prev.startswith(nxt)
                    ):
                        logger.debug(
                            '[voice_stream] Auto-finalizing previous segment: "%s"',
                            self._last_transcript_text,
                        )
                        self._callbacks.on_transcript(self._last_transcript_text, True)

                self._last_transcript_text = transcript
                self._callbacks.on_transcript(transcript, False)

        elif msg_type == "TranscriptEndpoint":
            logger.debug(
                '[voice_stream] TranscriptEndpoint, lastTranscriptText="%s"',
                self._last_transcript_text,
            )
            final_text = self._last_transcript_text
            self._last_transcript_text = ""
            if final_text:
                self._callbacks.on_transcript(final_text, True)
            if self._finalized:
                self._resolve_finalize("post_closestream_endpoint")

        elif msg_type == "TranscriptError":
            desc = msg.get("description") or msg.get("error_code") or "unknown transcription error"
            logger.debug("[voice_stream] TranscriptError: %s", desc)
            if not self._finalizing:
                self._callbacks.on_error(desc, None)

        elif msg_type == "error":
            error_detail = msg.get("message") or json.dumps(msg)
            logger.debug("[voice_stream] Server error: %s", error_detail)
            if not self._finalizing:
                self._callbacks.on_error(error_detail, None)

    def handle_close(self, code: int, reason: str) -> None:
        """Handle WebSocket close event."""
        logger.debug(
            '[voice_stream] WebSocket closed: code=%d reason="%s"', code, reason
        )
        self._connected = False
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

        # Promote unreported interim transcript
        if self._last_transcript_text:
            logger.debug(
                "[voice_stream] Promoting unreported interim transcript to final on close"
            )
            text = self._last_transcript_text
            self._last_transcript_text = ""
            self._callbacks.on_transcript(text, True)

        self._resolve_finalize("ws_close")

        if not self._finalizing and code not in (1000, 1005):
            self._callbacks.on_error(
                f"Connection closed: code {code}" + (f" — {reason}" if reason else ""),
                None,
            )
        self._callbacks.on_close()

    def handle_error(self, error: Exception) -> None:
        """Handle WebSocket error event."""
        logger.debug("[voice_stream] WebSocket error: %s", error)
        if not self._finalizing:
            self._callbacks.on_error(
                f"Voice stream connection error: {error}", None
            )


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------


def is_voice_stream_available() -> bool:
    """
    Checks if voice streaming is available.
    Requires valid Anthropic OAuth tokens.
    """
    try:
        from ..utils.auth import (  # type: ignore[import]
            get_claude_ai_oauth_tokens,
            is_anthropic_auth_enabled,
        )

        if not is_anthropic_auth_enabled():
            return False
        tokens = get_claude_ai_oauth_tokens()
        return tokens is not None and getattr(tokens, "access_token", None) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


async def connect_voice_stream(
    callbacks: VoiceStreamCallbacks,
    options: Optional[dict] = None,
) -> Optional[VoiceStreamConnection]:
    """
    Establishes a WebSocket connection to the Anthropic voice stream endpoint.

    :param callbacks: Event callbacks for transcript, error, close, and ready events.
    :param options: Optional dict with 'language' (str) and 'keyterms' (list[str]).
    :returns: VoiceStreamConnection if connection succeeded, None otherwise.
    """
    try:
        import websockets  # type: ignore[import]
    except ImportError:
        logger.warning(
            "[voice_stream] 'websockets' package not installed. "
            "Install with: pip install websockets"
        )
        callbacks.on_error(
            "websockets package not installed. Run: pip install websockets",
            {"fatal": True},
        )
        return None

    # Refresh OAuth token
    try:
        from ..utils.auth import (  # type: ignore[import]
            check_and_refresh_oauth_token_if_needed,
            get_claude_ai_oauth_tokens,
        )

        await check_and_refresh_oauth_token_if_needed()
        tokens = get_claude_ai_oauth_tokens()
        access_token = getattr(tokens, "access_token", None) if tokens else None
    except Exception:
        access_token = None

    if not access_token:
        logger.debug("[voice_stream] No OAuth token available")
        return None

    # Build WebSocket URL
    ws_base_url = os.environ.get("VOICE_STREAM_BASE_URL")
    if not ws_base_url:
        try:
            from ..constants.oauth import get_oauth_config  # type: ignore[import]

            base_api_url = get_oauth_config().BASE_API_URL
        except Exception:
            base_api_url = "https://api.anthropic.com"
        ws_base_url = base_api_url.replace("https://", "wss://").replace(
            "http://", "ws://"
        )

    lang = (options or {}).get("language", "en")
    keyterms = (options or {}).get("keyterms", [])

    params = {
        "encoding": "linear16",
        "sample_rate": "16000",
        "channels": "1",
        "endpointing_ms": "300",
        "utterance_end_ms": "1000",
        "language": lang,
    }

    # Check Nova 3 feature flag
    is_nova3 = False
    try:
        from .analytics.growthbook import (  # type: ignore[import]
            get_feature_value_cached_may_be_stale,
        )

        is_nova3 = bool(get_feature_value_cached_may_be_stale("tengu_cobalt_frost", False))
        if is_nova3:
            params["use_conversation_engine"] = "true"
            params["stt_provider"] = "deepgram-nova3"
            logger.debug("[voice_stream] Nova 3 gate enabled (tengu_cobalt_frost)")
    except Exception:
        pass

    # Build query string
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    for term in keyterms:
        qs += f"&keyterms={term}"

    url = f"{ws_base_url}{_VOICE_STREAM_PATH}?{qs}"
    logger.debug("[voice_stream] Connecting to %s", url)

    # Build headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "x-app": "cli",
    }

    try:
        ws = await websockets.connect(url, extra_headers=headers)
    except Exception as e:
        logger.debug("[voice_stream] Connection failed: %s", e)
        callbacks.on_error(f"Voice stream connection error: {e}", None)
        return None

    conn = VoiceStreamConnection(ws, callbacks, is_nova3=is_nova3)

    # Send initial KeepAlive
    await ws.send(_KEEPALIVE_MSG)
    logger.debug("[voice_stream] Sending initial KeepAlive")

    # Start keepalive loop
    async def _keepalive_loop() -> None:
        while conn.is_connected():
            await asyncio.sleep(_KEEPALIVE_INTERVAL_MS / 1000.0)
            if conn.is_connected():
                try:
                    await ws.send(_KEEPALIVE_MSG)
                    logger.debug("[voice_stream] Sending periodic KeepAlive")
                except Exception:
                    break

    conn._keepalive_task = asyncio.ensure_future(_keepalive_loop())

    # Start receive loop
    async def _receive_loop() -> None:
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    conn.handle_message(raw.decode("utf-8", errors="replace"))
                else:
                    conn.handle_message(str(raw))
        except Exception as e:
            conn.handle_error(e)
        finally:
            conn.handle_close(getattr(ws, "close_code", 1006) or 1006, "")

    asyncio.ensure_future(_receive_loop())

    # Notify caller that connection is ready
    callbacks.on_ready(conn)

    return conn
