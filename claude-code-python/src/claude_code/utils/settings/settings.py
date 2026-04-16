"""
Settings system for Claude Code.
Python port of utils/settings/settings.ts

Provides multi-source settings loading, merging, and updating.
Sources in priority order (lowest to highest):
  plugin < userSettings < projectSettings < localSettings < flagSettings < policySettings

No third-party dependencies — pure standard library.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

SettingsJson = Dict[str, Any]

SettingSource = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
]

EditableSettingSource = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
]

ValidationError = Dict[str, Any]  # {file, path, message}

SettingsWithErrors = Dict[str, Any]  # {settings: SettingsJson, errors: List[ValidationError]}


# ---------------------------------------------------------------------------
# Helpers imported from sibling modules (with stubs for missing ones)
# ---------------------------------------------------------------------------

def _get_claude_config_home_dir() -> str:
    """Return the Claude config home directory."""
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir
        return get_claude_config_home_dir()
    except ImportError:
        base = os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
        return base


def _get_original_cwd() -> str:
    """Return the original working directory."""
    return os.environ.get("CLAUDE_ORIGINAL_CWD", os.getcwd())


def _is_env_truthy(value: Optional[str]) -> bool:
    if not value:
        return False
    return value.lower().strip() in ("1", "true", "yes", "on")


def _is_enoent(error: Exception) -> bool:
    return isinstance(error, (FileNotFoundError, NotADirectoryError))


def _get_errno_code(error: Exception) -> Optional[str]:
    if isinstance(error, FileNotFoundError):
        return "ENOENT"
    if isinstance(error, NotADirectoryError):
        return "ENOTDIR"
    if isinstance(error, PermissionError):
        return "EACCES"
    return None


def _safe_parse_json(content: str) -> Optional[Any]:
    """Parse JSON, returning None on error."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _read_file_sync(path: str) -> Optional[str]:
    """Read a file synchronously, returning None if not found."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return None


def _get_managed_file_path() -> str:
    """Return the path to the managed settings directory."""
    # Typically /etc/claude or a platform-specific directory
    return os.environ.get("CLAUDE_MANAGED_SETTINGS_DIR",
                          "/etc/claude" if os.name != "nt" else "C:\\ProgramData\\Claude")


def _get_managed_settings_drop_in_dir() -> str:
    """Return the drop-in directory for managed settings fragments."""
    return os.path.join(_get_managed_file_path(), "managed-settings.d")


def _get_managed_settings_file_path() -> str:
    return os.path.join(_get_managed_file_path(), "managed-settings.json")


def _get_flag_settings_path() -> Optional[str]:
    """Return the path set via --settings flag (from env or state)."""
    return os.environ.get("CLAUDE_FLAG_SETTINGS_PATH")


def _get_flag_settings_inline() -> Optional[SettingsJson]:
    """Return inline settings from the SDK (set via env or state)."""
    raw = os.environ.get("CLAUDE_FLAG_SETTINGS_INLINE")
    if not raw:
        return None
    parsed = _safe_parse_json(raw)
    if isinstance(parsed, dict):
        return parsed
    return None


def _get_use_cowork_plugins() -> bool:
    return _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_COWORK_PLUGINS"))


def _safe_resolve_path(path: str) -> str:
    """Resolve symlinks and canonicalize path, returning original on error."""
    try:
        return str(Path(path).resolve())
    except OSError:
        return path


# ---------------------------------------------------------------------------
# Settings validation (stub — just ensures it's a dict)
# ---------------------------------------------------------------------------

def _validate_settings_schema(data: Any) -> Tuple[bool, Optional[SettingsJson], List[ValidationError]]:
    """
    Validate data against the settings schema.
    Returns (success, parsed_data, errors).
    Stub: accepts any dict as valid.
    """
    if not isinstance(data, dict):
        return False, None, [{"file": "", "path": "", "message": "Settings must be a JSON object"}]
    return True, data, []


def _filter_invalid_permission_rules(data: Any, path: str) -> List[ValidationError]:
    """Filter out invalid permission rules (stub)."""
    return []


def _format_zod_error(error: Any, path: str) -> List[ValidationError]:
    """Format a validation error (stub)."""
    return [{"file": path, "path": "", "message": str(error)}]


# ---------------------------------------------------------------------------
# Internal write tracking (stub)
# ---------------------------------------------------------------------------

def _mark_internal_write(path: str) -> None:
    """Mark a file write as internal (to suppress change detection)."""
    try:
        from claude_code.utils.settings.internal_writes import mark_internal_write
        mark_internal_write(path)
    except (ImportError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# MDM / platform settings (stubs — no platform MDM in Python port)
# ---------------------------------------------------------------------------

def _get_mdm_settings() -> Dict[str, Any]:
    return {"settings": {}, "errors": []}


def _get_hkcu_settings() -> Dict[str, Any]:
    return {"settings": {}, "errors": []}


def _get_remote_managed_settings_sync_from_cache() -> Optional[SettingsJson]:
    return None


# ---------------------------------------------------------------------------
# Plugin settings (stub)
# ---------------------------------------------------------------------------

def _get_plugin_settings_base() -> Optional[SettingsJson]:
    try:
        from claude_code.utils.settings.settings_cache import get_plugin_settings_base
        return get_plugin_settings_base()
    except (ImportError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_parsed_file_cache: Dict[str, Dict[str, Any]] = {}
_source_settings_cache: Dict[str, Optional[SettingsJson]] = {}
_session_settings_cache: Optional[SettingsWithErrors] = None


def _get_cached_parsed_file(path: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        return _parsed_file_cache.get(path)


def _set_cached_parsed_file(path: str, result: Dict[str, Any]) -> None:
    with _cache_lock:
        _parsed_file_cache[path] = result


def _get_cached_settings_for_source(source: SettingSource) -> Optional[SettingsJson]:
    with _cache_lock:
        sentinel = object()
        val = _source_settings_cache.get(source, sentinel)
        if val is sentinel:
            return None  # Not in cache — but we can't distinguish "None" from "missing"
        return val  # type: ignore[return-value]


def _has_cached_settings_for_source(source: SettingSource) -> bool:
    with _cache_lock:
        return source in _source_settings_cache


def _set_cached_settings_for_source(source: SettingSource, result: Optional[SettingsJson]) -> None:
    with _cache_lock:
        _source_settings_cache[source] = result


def _get_session_settings_cache() -> Optional[SettingsWithErrors]:
    with _cache_lock:
        return _session_settings_cache


def _set_session_settings_cache(result: SettingsWithErrors) -> None:
    global _session_settings_cache
    with _cache_lock:
        _session_settings_cache = result


def reset_settings_cache() -> None:
    """Invalidate all settings caches."""
    global _session_settings_cache
    with _cache_lock:
        _parsed_file_cache.clear()
        _source_settings_cache.clear()
        _session_settings_cache = None
    # Also reset any external cache module
    try:
        from claude_code.utils.settings.settings_cache import resetSettingsCache
        resetSettingsCache()
    except (ImportError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# Enabled setting sources
# ---------------------------------------------------------------------------

def _get_enabled_setting_sources() -> List[SettingSource]:
    """Return all setting sources in priority order (lowest first)."""
    sources: List[SettingSource] = [
        "userSettings",
        "projectSettings",
        "localSettings",
    ]
    flag_path = _get_flag_settings_path()
    flag_inline = _get_flag_settings_inline()
    if flag_path or flag_inline:
        sources.append("flagSettings")
    sources.append("policySettings")
    return sources

# Internal alias used inside _load_settings_from_disk to avoid name shadowing
__get_enabled_setting_sources = _get_enabled_setting_sources


# ---------------------------------------------------------------------------
# Managed file settings
# ---------------------------------------------------------------------------

def load_managed_file_settings() -> Dict[str, Any]:
    """
    Load file-based managed settings: managed-settings.json + managed-settings.d/*.json.

    managed-settings.json is merged first (lowest precedence / base), then drop-in
    files are sorted alphabetically and merged on top. Returns:
      {"settings": SettingsJson|None, "errors": List[ValidationError]}
    """
    errors: List[ValidationError] = []
    merged: SettingsJson = {}
    found = False

    # Base managed-settings.json
    base_result = parse_settings_file(_get_managed_settings_file_path())
    errors.extend(base_result["errors"])
    if base_result["settings"] and len(base_result["settings"]) > 0:
        merged = _merge_settings(merged, base_result["settings"])
        found = True

    # Drop-in directory
    drop_in_dir = _get_managed_settings_drop_in_dir()
    try:
        entries = sorted(
            e.name for e in os.scandir(drop_in_dir)
            if (e.is_file(follow_symlinks=True) or e.is_symlink())
            and e.name.endswith(".json")
            and not e.name.startswith(".")
        )
        for name in entries:
            file_result = parse_settings_file(os.path.join(drop_in_dir, name))
            errors.extend(file_result["errors"])
            if file_result["settings"] and len(file_result["settings"]) > 0:
                merged = _merge_settings(merged, file_result["settings"])
                found = True
    except (FileNotFoundError, NotADirectoryError):
        pass
    except OSError as e:
        code = _get_errno_code(e)
        if code not in ("ENOENT", "ENOTDIR"):
            pass  # log in full impl

    return {"settings": merged if found else None, "errors": errors}


def get_managed_file_settings_presence() -> Dict[str, bool]:
    """
    Check which file-based managed settings sources are present.
    Returns {"hasBase": bool, "hasDropIns": bool}
    """
    base_result = parse_settings_file(_get_managed_settings_file_path())
    has_base = bool(base_result["settings"] and len(base_result["settings"]) > 0)

    has_drop_ins = False
    drop_in_dir = _get_managed_settings_drop_in_dir()
    try:
        has_drop_ins = any(
            (e.is_file(follow_symlinks=True) or e.is_symlink())
            and e.name.endswith(".json")
            and not e.name.startswith(".")
            for e in os.scandir(drop_in_dir)
        )
    except OSError:
        pass

    return {"hasBase": has_base, "hasDropIns": has_drop_ins}


# ---------------------------------------------------------------------------
# Parse settings file
# ---------------------------------------------------------------------------

def parse_settings_file(path: str) -> Dict[str, Any]:
    """
    Parse a settings JSON file into a structured format.
    Uses per-path caching. Returns {"settings": SettingsJson|None, "errors": List[ValidationError]}
    """
    cached = _get_cached_parsed_file(path)
    if cached is not None:
        # Clone to prevent mutation of cached entry
        return {
            "settings": dict(cached["settings"]) if cached["settings"] else None,
            "errors": cached["errors"],
        }

    result = _parse_settings_file_uncached(path)
    _set_cached_parsed_file(path, result)
    return {
        "settings": dict(result["settings"]) if result["settings"] else None,
        "errors": result["errors"],
    }


def _parse_settings_file_uncached(path: str) -> Dict[str, Any]:
    """Parse a settings file without caching."""
    try:
        resolved_path = _safe_resolve_path(path)
        content = _read_file_sync(resolved_path)

        if content is None:
            return {"settings": None, "errors": []}

        if content.strip() == "":
            return {"settings": {}, "errors": []}

        data = _safe_parse_json(content)
        if data is None:
            return {"settings": None, "errors": [{"file": path, "path": "", "message": "Invalid JSON"}]}

        # Filter invalid permission rules
        rule_warnings = _filter_invalid_permission_rules(data, path)

        success, parsed, schema_errors = _validate_settings_schema(data)
        if not success:
            return {"settings": None, "errors": rule_warnings + schema_errors}

        return {"settings": parsed, "errors": rule_warnings}

    except (FileNotFoundError, NotADirectoryError):
        return {"settings": None, "errors": []}
    except OSError:
        return {"settings": None, "errors": []}


# ---------------------------------------------------------------------------
# Root path / file path helpers
# ---------------------------------------------------------------------------

def get_settings_root_path_for_source(source: SettingSource) -> str:
    """Return the absolute root path associated with the given settings source."""
    if source == "userSettings":
        return str(Path(_get_claude_config_home_dir()).resolve())
    elif source in ("policySettings", "projectSettings", "localSettings"):
        return str(Path(_get_original_cwd()).resolve())
    elif source == "flagSettings":
        flag_path = _get_flag_settings_path()
        if flag_path:
            return str(Path(flag_path).resolve().parent)
        return str(Path(_get_original_cwd()).resolve())
    # Default
    return str(Path(_get_original_cwd()).resolve())


def _get_user_settings_file_path() -> str:
    """Return the user settings filename (cowork vs standard)."""
    if _get_use_cowork_plugins() or _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_COWORK_PLUGINS")):
        return "cowork_settings.json"
    return "settings.json"


def _get_relative_settings_file_path_for_source(
    source: Literal["projectSettings", "localSettings"]
) -> str:
    if source == "projectSettings":
        return os.path.join(".claude", "settings.json")
    elif source == "localSettings":
        return os.path.join(".claude", "settings.local.json")
    raise ValueError(f"Unknown source: {source}")


def get_settings_file_path_for_source(source: SettingSource) -> Optional[str]:
    """Return the absolute file path for the given settings source."""
    if source == "userSettings":
        root = get_settings_root_path_for_source(source)
        return os.path.join(root, _get_user_settings_file_path())
    elif source in ("projectSettings", "localSettings"):
        root = get_settings_root_path_for_source(source)
        rel = _get_relative_settings_file_path_for_source(source)  # type: ignore[arg-type]
        return os.path.join(root, rel)
    elif source == "policySettings":
        return _get_managed_settings_file_path()
    elif source == "flagSettings":
        return _get_flag_settings_path()
    return None


# ---------------------------------------------------------------------------
# Per-source settings
# ---------------------------------------------------------------------------

def get_settings_for_source(source: SettingSource) -> Optional[SettingsJson]:
    """Get settings for the given source, using per-source cache."""
    if _has_cached_settings_for_source(source):
        return _get_cached_settings_for_source(source)
    result = _get_settings_for_source_uncached(source)
    _set_cached_settings_for_source(source, result)
    return result


def _get_settings_for_source_uncached(source: SettingSource) -> Optional[SettingsJson]:
    """Get settings for the given source without cache."""
    if source == "policySettings":
        # First source wins: remote > HKLM/plist > file > HKCU
        remote = _get_remote_managed_settings_sync_from_cache()
        if remote and len(remote) > 0:
            return remote

        mdm_result = _get_mdm_settings()
        if len(mdm_result["settings"]) > 0:
            return mdm_result["settings"]

        file_result = load_managed_file_settings()
        if file_result["settings"]:
            return file_result["settings"]

        hkcu = _get_hkcu_settings()
        if len(hkcu["settings"]) > 0:
            return hkcu["settings"]

        return None

    file_path = get_settings_file_path_for_source(source)
    file_settings: Optional[SettingsJson] = None
    if file_path:
        file_result = parse_settings_file(file_path)
        file_settings = file_result["settings"]

    # For flagSettings, also merge inline settings
    if source == "flagSettings":
        inline = _get_flag_settings_inline()
        if inline:
            success, parsed_inline, _ = _validate_settings_schema(inline)
            if success and parsed_inline:
                return _merge_settings(file_settings or {}, parsed_inline)

    return file_settings


# ---------------------------------------------------------------------------
# Update settings for source
# ---------------------------------------------------------------------------

def update_settings_for_source(
    source: EditableSettingSource,
    settings: SettingsJson,
) -> Dict[str, Any]:
    """
    Merge `settings` into existing settings for `source` and persist to disk.
    Returns {"error": None} on success, {"error": Exception} on failure.
    """
    file_path = get_settings_file_path_for_source(source)
    if not file_path:
        return {"error": None}

    try:
        # Create directory if needed
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        # Get existing settings (bypass cache to avoid stale merges)
        existing: Optional[SettingsJson] = _get_settings_for_source_uncached(source)

        if existing is None:
            # Check if file has JSON syntax error
            content = _read_file_sync(file_path)
            if content is not None:
                raw = _safe_parse_json(content)
                if raw is None:
                    return {"error": Exception(f"Invalid JSON syntax in settings file at {file_path}")}
                if isinstance(raw, dict):
                    existing = raw

        # Merge with deletion support (None values delete keys)
        updated = _merge_settings_with_deletion(existing or {}, settings)

        # Mark internal write
        _mark_internal_write(file_path)

        # Write to disk
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=False)
            f.write("\n")

        # Invalidate cache
        reset_settings_cache()

        # Add localSettings to gitignore
        if source == "localSettings":
            _maybe_add_to_gitignore(source)

    except Exception as e:
        return {"error": e}

    return {"error": None}


def _maybe_add_to_gitignore(source: Literal["localSettings"]) -> None:
    """Add localSettings file to .gitignore (best-effort)."""
    try:
        rel_path = _get_relative_settings_file_path_for_source(source)
        gitignore_path = os.path.join(_get_original_cwd(), ".gitignore")
        if not os.path.exists(gitignore_path):
            return
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        if rel_path not in content:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write(f"\n{rel_path}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Merge utilities
# ---------------------------------------------------------------------------

def _merge_settings(base: SettingsJson, override: SettingsJson) -> SettingsJson:
    """
    Deep-merge override into base.
    Arrays are concatenated and deduplicated (settingsMergeCustomizer).
    """
    result = dict(base)
    for key, src_val in override.items():
        if src_val is None:
            result.pop(key, None)
            continue
        if isinstance(src_val, list) and isinstance(result.get(key), list):
            # Concatenate and deduplicate (preserving order)
            seen = []
            combined = list(result[key]) + list(src_val)
            deduped: list = []
            seen_set: set = set()
            for item in combined:
                item_key = json.dumps(item, sort_keys=True) if isinstance(item, dict) else item
                if item_key not in seen_set:
                    seen_set.add(item_key)
                    deduped.append(item)
            result[key] = deduped
        elif isinstance(src_val, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_settings(result[key], src_val)
        else:
            result[key] = src_val
    return result


def _merge_settings_with_deletion(base: SettingsJson, override: SettingsJson) -> SettingsJson:
    """
    Merge override into base, treating None values as deletions.
    Arrays are replaced (not merged) when provided.
    """
    result = dict(base)
    for key, src_val in override.items():
        if src_val is None:
            result.pop(key, None)
        elif isinstance(src_val, list):
            # For arrays in update calls: replace entirely
            result[key] = src_val
        elif isinstance(src_val, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_settings_with_deletion(result[key], src_val)
        else:
            result[key] = src_val
    return result


def settings_merge_customizer(obj_value: Any, src_value: Any) -> Any:
    """
    Custom merge function: arrays are concatenated and deduplicated.
    Returns None to use default lodash-style merge for other types.
    Exported for testing.
    """
    if isinstance(obj_value, list) and isinstance(src_value, list):
        seen_set: set = set()
        deduped: list = []
        for item in obj_value + src_value:
            item_key = json.dumps(item, sort_keys=True) if isinstance(item, dict) else item
            if item_key not in seen_set:
                seen_set.add(item_key)
                deduped.append(item)
        return deduped
    return None  # Use default merge


# ---------------------------------------------------------------------------
# Initial settings / merged settings
# ---------------------------------------------------------------------------

_is_loading_settings = False


def _load_settings_from_disk() -> SettingsWithErrors:
    """Load and merge settings from all sources. Core implementation."""
    global _is_loading_settings
    if _is_loading_settings:
        return {"settings": {}, "errors": []}

    _is_loading_settings = True
    try:
        plugin_settings = _get_plugin_settings_base()
        merged: SettingsJson = {}
        if plugin_settings:
            merged = _merge_settings(merged, plugin_settings)

        all_errors: List[ValidationError] = []
        seen_errors: set = set()
        seen_files: set = set()

        for source in __get_enabled_setting_sources():
            if source == "policySettings":
                policy_settings: Optional[SettingsJson] = None
                policy_errors: List[ValidationError] = []

                # 1. Remote (highest priority)
                remote = _get_remote_managed_settings_sync_from_cache()
                if remote and len(remote) > 0:
                    success, parsed, errs = _validate_settings_schema(remote)
                    if success and parsed:
                        policy_settings = parsed
                    else:
                        policy_errors.extend(_format_zod_error(errs, "remote managed settings"))

                # 2. MDM
                if not policy_settings:
                    mdm = _get_mdm_settings()
                    if len(mdm["settings"]) > 0:
                        policy_settings = mdm["settings"]
                    policy_errors.extend(mdm.get("errors", []))

                # 3. File-based managed settings
                if not policy_settings:
                    file_managed = load_managed_file_settings()
                    if file_managed["settings"]:
                        policy_settings = file_managed["settings"]
                    policy_errors.extend(file_managed["errors"])

                # 4. HKCU
                if not policy_settings:
                    hkcu = _get_hkcu_settings()
                    if len(hkcu["settings"]) > 0:
                        policy_settings = hkcu["settings"]
                    policy_errors.extend(hkcu.get("errors", []))

                if policy_settings:
                    merged = _merge_settings(merged, policy_settings)

                for err in policy_errors:
                    err_key = f"{err.get('file')}:{err.get('path')}:{err.get('message')}"
                    if err_key not in seen_errors:
                        seen_errors.add(err_key)
                        all_errors.append(err)
                continue

            # Non-policy sources
            file_path = get_settings_file_path_for_source(source)
            if file_path:
                resolved = _safe_resolve_path(file_path)
                if resolved not in seen_files:
                    seen_files.add(resolved)
                    result = parse_settings_file(file_path)

                    for err in result["errors"]:
                        err_key = f"{err.get('file')}:{err.get('path')}:{err.get('message')}"
                        if err_key not in seen_errors:
                            seen_errors.add(err_key)
                            all_errors.append(err)

                    if result["settings"]:
                        merged = _merge_settings(merged, result["settings"])

            # flagSettings: also merge inline
            if source == "flagSettings":
                inline = _get_flag_settings_inline()
                if inline:
                    success, parsed, _ = _validate_settings_schema(inline)
                    if success and parsed:
                        merged = _merge_settings(merged, parsed)

        return {"settings": merged, "errors": all_errors}

    finally:
        _is_loading_settings = False


def get_settings_with_errors() -> SettingsWithErrors:
    """Get merged settings and validation errors, using session cache."""
    cached = _get_session_settings_cache()
    if cached is not None:
        return cached
    result = _load_settings_from_disk()
    _set_session_settings_cache(result)
    return result


def get_initial_settings() -> SettingsJson:
    """
    Get merged settings from all sources.
    Returns at least an empty dict.
    Uses session-level caching.
    """
    result = get_settings_with_errors()
    return result.get("settings") or {}


# Backward compat alias
get_settings_deprecated = get_initial_settings


# ---------------------------------------------------------------------------
# Settings with sources
# ---------------------------------------------------------------------------

class SettingsWithSources:
    def __init__(self, effective: SettingsJson, sources: List[Dict[str, Any]]):
        self.effective = effective
        self.sources = sources  # [{"source": str, "settings": SettingsJson}]


def get_settings_with_sources() -> SettingsWithSources:
    """
    Get effective merged settings alongside raw per-source settings.
    Always reads fresh from disk.
    """
    reset_settings_cache()
    sources = []
    for source in _get_enabled_setting_sources():
        settings = get_settings_for_source(source)
        if settings and len(settings) > 0:
            sources.append({"source": source, "settings": settings})
    return SettingsWithSources(effective=get_initial_settings(), sources=sources)


# ---------------------------------------------------------------------------
# Auto mode
# ---------------------------------------------------------------------------

def has_auto_mode_opt_in() -> bool:
    """
    Return True if any trusted settings source has opted into auto mode.
    projectSettings is excluded (RCE risk).
    """
    # Check for TRANSCRIPT_CLASSIFIER feature flag
    has_feature = _is_env_truthy(os.environ.get("CLAUDE_FEATURE_TRANSCRIPT_CLASSIFIER"))
    if not has_feature:
        return False

    for source in ("userSettings", "localSettings", "flagSettings", "policySettings"):
        settings = get_settings_for_source(source)  # type: ignore[arg-type]
        if settings and settings.get("skipAutoPermissionPrompt"):
            return True

    return False


def get_auto_mode_config() -> Optional[Dict[str, Any]]:
    """
    Get merged autoMode config from trusted settings sources.
    Only available when TRANSCRIPT_CLASSIFIER feature is active.
    projectSettings intentionally excluded.
    """
    has_feature = _is_env_truthy(os.environ.get("CLAUDE_FEATURE_TRANSCRIPT_CLASSIFIER"))
    if not has_feature:
        return None

    allow: List[str] = []
    soft_deny: List[str] = []
    environment: List[str] = []

    for source in ("userSettings", "localSettings", "flagSettings", "policySettings"):
        settings = get_settings_for_source(source)  # type: ignore[arg-type]
        if not settings:
            continue
        auto_mode = settings.get("autoMode")
        if not isinstance(auto_mode, dict):
            continue

        if isinstance(auto_mode.get("allow"), list):
            allow.extend(auto_mode["allow"])
        if isinstance(auto_mode.get("soft_deny"), list):
            soft_deny.extend(auto_mode["soft_deny"])
        if isinstance(auto_mode.get("deny"), list) and os.environ.get("USER_TYPE") == "ant":
            soft_deny.extend(auto_mode["deny"])
        if isinstance(auto_mode.get("environment"), list):
            environment.extend(auto_mode["environment"])

    if allow or soft_deny or environment:
        result: Dict[str, Any] = {}
        if allow:
            result["allow"] = allow
        if soft_deny:
            result["soft_deny"] = soft_deny
        if environment:
            result["environment"] = environment
        return result

    return None


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def has_skip_dangerous_mode_permission_prompt() -> bool:
    """Return True if any trusted source has accepted bypass permissions mode."""
    for source in ("userSettings", "localSettings", "flagSettings", "policySettings"):
        settings = get_settings_for_source(source)  # type: ignore[arg-type]
        if settings and settings.get("skipDangerousModePermissionPrompt"):
            return True
    return False


def get_managed_settings_keys_for_logging(settings: SettingsJson) -> List[str]:
    """Return sorted list of keys from managed settings for logging."""
    keys_to_expand = {"permissions", "sandbox", "hooks"}
    all_keys: List[str] = []

    for key, value in settings.items():
        if key in keys_to_expand and isinstance(value, dict):
            for nested_key in value:
                all_keys.append(f"{key}.{nested_key}")
        else:
            all_keys.append(key)

    return sorted(all_keys)


def raw_settings_contains_key(key: str) -> bool:
    """Check if any raw settings file contains a specific key."""
    for source in _get_enabled_setting_sources():
        if source == "policySettings":
            continue
        file_path = get_settings_file_path_for_source(source)
        if not file_path:
            continue
        try:
            resolved = _safe_resolve_path(file_path)
            content = _read_file_sync(resolved)
            if not content or not content.strip():
                continue
            raw = _safe_parse_json(content)
            if isinstance(raw, dict) and key in raw:
                return True
        except OSError:
            pass
    return False
