"""Voice stream STT service stub. Ported from services/voiceStreamSTT.ts"""
from __future__ import annotations
from typing import AsyncIterator, Optional


async def transcribe_audio(audio_bytes: bytes,
                           keyterms: Optional[list] = None,
                           language: str = "en") -> Optional[str]:
    """Transcribe audio bytes via STT service. Stub: returns None."""
    return None


async def stream_transcription(audio_stream) -> AsyncIterator[str]:
    """Stream real-time transcription. Stub."""
    return
    yield  # make it a generator
