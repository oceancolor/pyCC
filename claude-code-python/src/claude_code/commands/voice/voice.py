"""
Ported from: commands/voice/voice.ts

/voice command — toggle voice-input mode (push-to-talk) on or off.

Performs pre-flight checks (auth, recording tools, microphone access) before
enabling.  All UI rendering from the React source is replaced by text messages.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

_LANG_HINT_MAX_SHOWS = 2


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _is_voice_mode_enabled() -> bool:
    try:
        from claude_code.voice.voice_mode_enabled import is_voice_mode_enabled  # type: ignore[import]
        return is_voice_mode_enabled()
    except ImportError:
        return False


def _is_anthropic_auth_enabled() -> bool:
    try:
        from claude_code.utils.auth import is_anthropic_auth_enabled  # type: ignore[import]
        return is_anthropic_auth_enabled()
    except ImportError:
        return False


def _get_initial_settings() -> dict:
    try:
        from claude_code.utils.settings.settings import get_initial_settings  # type: ignore[import]
        return get_initial_settings()
    except ImportError:
        return {}


def _update_settings_for_source(source: str, patch: dict) -> Dict[str, Any]:
    try:
        from claude_code.utils.settings.settings import update_settings_for_source  # type: ignore[import]
        return update_settings_for_source(source, patch)
    except ImportError:
        return {"error": None}


def _notify_settings_change(source: str) -> None:
    try:
        from claude_code.utils.settings.change_detector import settings_change_detector  # type: ignore[import]
        settings_change_detector.notify_change(source)
    except ImportError:
        pass


def _log_event(event: str, data: dict) -> None:
    try:
        from claude_code.services.analytics.index import log_event  # type: ignore[import]
        log_event(event, data)
    except (ImportError, Exception):
        pass


def _get_global_config() -> dict:
    try:
        from claude_code.utils.config import get_global_config  # type: ignore[import]
        return get_global_config()
    except ImportError:
        return {}


def _save_global_config(updater) -> None:
    try:
        from claude_code.utils.config import save_global_config  # type: ignore[import]
        save_global_config(updater)
    except ImportError:
        pass


def _get_shortcut_display(action: str, context_name: str, default_key: str) -> str:
    try:
        from claude_code.keybindings.shortcut_format import get_shortcut_display  # type: ignore[import]
        return get_shortcut_display(action, context_name, default_key)
    except ImportError:
        return default_key


def _normalize_language_for_stt(language: Optional[str]) -> Dict[str, Any]:
    try:
        from claude_code.hooks.use_voice import normalize_language_for_stt  # type: ignore[import]
        return normalize_language_for_stt(language)
    except ImportError:
        return {"code": language or "en-US", "fellBackFrom": None}


async def _is_voice_stream_available() -> bool:
    try:
        from claude_code.services.voice_stream_stt import is_voice_stream_available  # type: ignore[import]
        return is_voice_stream_available()
    except ImportError:
        return False


async def _check_recording_availability() -> Dict[str, Any]:
    try:
        from claude_code.services.voice import check_recording_availability  # type: ignore[import]
        return await check_recording_availability()
    except ImportError:
        return {"available": False, "reason": "Voice service not available."}


async def _check_voice_dependencies() -> Dict[str, Any]:
    try:
        from claude_code.services.voice import check_voice_dependencies  # type: ignore[import]
        return await check_voice_dependencies()
    except ImportError:
        return {"available": False, "installCommand": None}


async def _request_microphone_permission() -> bool:
    try:
        from claude_code.services.voice import request_microphone_permission  # type: ignore[import]
        return await request_microphone_permission()
    except ImportError:
        return False


def _mic_guidance() -> str:
    platform = sys.platform
    if platform == "win32":
        return "Settings \u2192 Privacy \u2192 Microphone"
    elif platform.startswith("linux"):
        return "your system's audio settings"
    else:
        return "System Settings \u2192 Privacy & Security \u2192 Microphone"


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Toggle voice mode on or off.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    # Kill-switch / auth gate
    if not _is_voice_mode_enabled():
        if not _is_anthropic_auth_enabled():
            return {
                "type": "text",
                "value": "Voice mode requires a Claude.ai account. Please run /login to sign in.",
            }
        return {"type": "text", "value": "Voice mode is not available."}

    current_settings = _get_initial_settings()
    is_currently_enabled: bool = current_settings.get("voiceEnabled") is True

    # Toggle OFF
    if is_currently_enabled:
        result = _update_settings_for_source("userSettings", {"voiceEnabled": False})
        if result.get("error"):
            return {
                "type": "text",
                "value": "Failed to update settings. Check your settings file for syntax errors.",
            }
        _notify_settings_change("userSettings")
        _log_event("tengu_voice_toggled", {"enabled": False})
        return {"type": "text", "value": "Voice mode disabled."}

    # Toggle ON — run pre-flight checks
    recording = await _check_recording_availability()
    if not recording.get("available"):
        return {
            "type": "text",
            "value": recording.get("reason") or "Voice mode is not available in this environment.",
        }

    if not await _is_voice_stream_available():
        return {
            "type": "text",
            "value": "Voice mode requires a Claude.ai account. Please run /login to sign in.",
        }

    deps = await _check_voice_dependencies()
    if not deps.get("available"):
        install_cmd = deps.get("installCommand")
        hint = (
            f"\nInstall audio recording tools? Run: {install_cmd}"
            if install_cmd
            else "\nInstall SoX manually for audio recording."
        )
        return {"type": "text", "value": f"No audio recording tool found.{hint}"}

    if not await _request_microphone_permission():
        guidance = _mic_guidance()
        return {
            "type": "text",
            "value": (
                f"Microphone access is denied. "
                f"To enable it, go to {guidance}, then run /voice again."
            ),
        }

    # All checks passed — enable
    result = _update_settings_for_source("userSettings", {"voiceEnabled": True})
    if result.get("error"):
        return {
            "type": "text",
            "value": "Failed to update settings. Check your settings file for syntax errors.",
        }
    _notify_settings_change("userSettings")
    _log_event("tengu_voice_toggled", {"enabled": True})

    key = _get_shortcut_display("voice:pushToTalk", "Chat", "Space")
    stt = _normalize_language_for_stt(current_settings.get("language"))
    cfg = _get_global_config()

    lang_code = stt.get("code", "en-US")
    fell_back_from = stt.get("fellBackFrom")
    lang_changed = cfg.get("voiceLangHintLastLanguage") != lang_code
    prior_count = 0 if lang_changed else (cfg.get("voiceLangHintShownCount") or 0)
    show_hint = not fell_back_from and prior_count < _LANG_HINT_MAX_SHOWS

    lang_note = ""
    if fell_back_from:
        lang_note = (
            f" Note: \"{fell_back_from}\" is not a supported dictation language; "
            f"using English. Change it via /config."
        )
    elif show_hint:
        lang_note = f" Dictation language: {lang_code} (/config to change)."

    if lang_changed or show_hint:
        def _update_lang_hint(prev: dict) -> dict:
            updated = dict(prev)
            updated["voiceLangHintShownCount"] = prior_count + (1 if show_hint else 0)
            updated["voiceLangHintLastLanguage"] = lang_code
            return updated
        _save_global_config(_update_lang_hint)

    return {
        "type": "text",
        "value": f"Voice mode enabled. Hold {key} to record.{lang_note}",
    }
