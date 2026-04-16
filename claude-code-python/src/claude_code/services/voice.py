"""Voice recording service stub. Ported from services/voice.ts (native audio → stub)"""
from __future__ import annotations
import asyncio
import os
import sys
from typing import AsyncIterator, Optional


RECORDING_SAMPLE_RATE = 16000
RECORDING_CHANNELS = 1


def is_voice_available() -> bool:
    """Check if voice recording is available on this platform."""
    if sys.platform not in ('darwin', 'linux', 'win32'):
        return False
    # Check for SoX on Linux
    if sys.platform == 'linux':
        import shutil
        return shutil.which('rec') is not None or shutil.which('arecord') is not None
    return False


async def start_recording() -> "AudioRecorder":
    """Start a voice recording session."""
    return AudioRecorder()


class AudioRecorder:
    def __init__(self) -> None:
        self._proc: Optional[asyncio.subprocess.Process] = None

    async def start(self) -> None:
        if not is_voice_available():
            raise RuntimeError("Voice recording not available on this platform")
        # Stub: would start native audio capture

    async def stop(self) -> Optional[bytes]:
        """Stop recording and return raw audio bytes."""
        return None

    def is_recording(self) -> bool:
        return self._proc is not None and self._proc.returncode is None
