# Ported from utils/model/modelCapabilities.ts
"""
Model capability caching — reads a local JSON cache written by
refreshModelCapabilities() and exposes per-model max token limits.

The original TS uses Zod for schema validation; this port uses stdlib
json + manual validation instead.
"""
from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

# ---------------------------------------------------------------------------
# Dependency imports (guarded so the module still loads in partial envs)
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.env_utils import get_claude_config_home_dir
except ImportError:
    def get_claude_config_home_dir() -> str:  # type: ignore[misc]
        return os.path.expanduser("~/.claude")

try:
    from claude_code.utils.log import log_for_debugging
except ImportError:
    def log_for_debugging(msg: str, *args: object) -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.utils.privacy_level import is_essential_traffic_only
except ImportError:
    def is_essential_traffic_only() -> bool:  # type: ignore[misc]
        return False

try:
    from claude_code.utils.model.providers import get_api_provider, is_first_party_anthropic_base_url
except ImportError:
    def get_api_provider() -> str:  # type: ignore[misc]
        return "firstParty"

    def is_first_party_anthropic_base_url() -> bool:  # type: ignore[misc]
        return True

try:
    from claude_code.utils.auth import is_claude_ai_subscriber
except ImportError:
    def is_claude_ai_subscriber() -> bool:  # type: ignore[misc]
        return False

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ModelCapability(TypedDict, total=False):
    """Schema: keep only id, max_input_tokens, max_tokens (strip internal fields)."""
    id: str
    max_input_tokens: int
    max_tokens: int


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _get_cache_dir() -> str:
    return str(Path(get_claude_config_home_dir()) / "cache")


def _get_cache_path() -> str:
    return str(Path(_get_cache_dir()) / "model-capabilities.json")


def _is_model_capabilities_eligible() -> bool:
    """True only for internal Ant users on the first-party API endpoint."""
    if os.environ.get("USER_TYPE") != "ant":
        return False
    if get_api_provider() != "firstParty":
        return False
    if not is_first_party_anthropic_base_url():
        return False
    return True


def _parse_model_capability(entry: object) -> Optional[ModelCapability]:
    """Validate and strip an entry to the ModelCapability schema."""
    if not isinstance(entry, dict):
        return None
    model_id = entry.get("id")
    if not isinstance(model_id, str):
        return None
    result: ModelCapability = {"id": model_id}
    max_input = entry.get("max_input_tokens")
    if isinstance(max_input, (int, float)):
        result["max_input_tokens"] = int(max_input)
    max_out = entry.get("max_tokens")
    if isinstance(max_out, (int, float)):
        result["max_tokens"] = int(max_out)
    return result


def _sort_for_matching(models: List[ModelCapability]) -> List[ModelCapability]:
    """Longest-id-first so substring match prefers the most specific entry.

    Secondary key (alphabetical) keeps the order stable for equality checks.
    """
    return sorted(models, key=lambda m: (-len(m["id"]), m["id"]))


# ---------------------------------------------------------------------------
# Memoized cache loader
# Keyed on the cache-file path so tests that change CLAUDE_CONFIG_DIR get a
# fresh read (mirrors TS memoize(path => path)).
# ---------------------------------------------------------------------------

_cache_store: Dict[str, Optional[List[ModelCapability]]] = {}


def _load_cache(path: str) -> Optional[List[ModelCapability]]:
    """Read and validate the on-disk model-capabilities cache.

    Results are memoized in ``_cache_store`` to avoid repeated I/O — the TS
    original uses lodash ``memoize`` with the same semantics.
    """
    if path in _cache_store:
        return _cache_store[path]

    result: Optional[List[ModelCapability]] = None
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("models"), list):
            parsed: List[ModelCapability] = []
            for entry in data["models"]:
                cap = _parse_model_capability(entry)
                if cap is not None:
                    parsed.append(cap)
            result = parsed if parsed else None
    except Exception:
        result = None

    _cache_store[path] = result
    return result


def _invalidate_cache(path: str) -> None:
    """Remove *path* from the in-process cache (called after a successful write)."""
    _cache_store.pop(path, None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_model_capability(model: str) -> Optional[ModelCapability]:
    """Return the cached capability entry for *model*, or ``None``.

    Matching strategy (mirrors TS):
    1. Exact (case-insensitive) match on ``id``.
    2. Substring match — the cache is sorted longest-id-first so the most
       specific entry wins.
    """
    if not _is_model_capabilities_eligible():
        return None
    cached = _load_cache(_get_cache_path())
    if not cached:
        return None
    m = model.lower()
    # 1. Exact match
    for entry in cached:
        if entry["id"].lower() == m:
            return entry
    # 2. Substring match (longest-id-first ordering guarantees most-specific win)
    for entry in cached:
        if m.find(entry["id"].lower()) != -1:
            return entry
    return None


async def refresh_model_capabilities() -> None:
    """Fetch the models list from the Anthropic API and write it to the cache.

    Does nothing unless :func:`_is_model_capabilities_eligible` returns ``True``
    or essential-traffic-only mode is active.
    """
    if not _is_model_capabilities_eligible():
        return
    if is_essential_traffic_only():
        return

    try:
        from claude_code.services.api.client import get_anthropic_client  # type: ignore
    except ImportError:
        log_for_debugging("[modelCapabilities] Anthropic client not available, skipping refresh")
        return

    try:
        # Determine beta headers (claude.ai subscribers get the OAuth beta header)
        betas = None
        try:
            from claude_code.constants.oauth import OAUTH_BETA_HEADER  # type: ignore
            if is_claude_ai_subscriber():
                betas = [OAUTH_BETA_HEADER]
        except ImportError:
            pass

        anthropic = await get_anthropic_client(max_retries=1)
        parsed: List[ModelCapability] = []

        list_kwargs: Dict[str, object] = {}
        if betas is not None:
            list_kwargs["betas"] = betas

        async for entry in anthropic.models.list(**list_kwargs):
            # entry is a Pydantic/dataclass object — convert to dict first
            entry_dict = entry.model_dump() if hasattr(entry, "model_dump") else vars(entry)
            cap = _parse_model_capability(entry_dict)
            if cap is not None:
                parsed.append(cap)

        if not parsed:
            return

        path = _get_cache_path()
        models = _sort_for_matching(parsed)

        # Skip write if cache is identical
        current = _load_cache(path)
        if current is not None and _capabilities_equal(current, models):
            log_for_debugging("[modelCapabilities] cache unchanged, skipping write")
            return

        # Write atomically (mode 0o600 — owner read/write only)
        import asyncio

        cache_dir = Path(_get_cache_dir())
        await asyncio.to_thread(cache_dir.mkdir, parents=True, exist_ok=True)

        cache_data = {
            "models": list(models),
            "timestamp": int(time.time() * 1000),
        }
        cache_path = Path(path)
        tmp_path = cache_path.with_suffix(".tmp")

        def _write() -> None:
            tmp_path.write_text(
                json.dumps(cache_data, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.chmod(0o600)
            tmp_path.replace(cache_path)

        await asyncio.to_thread(_write)
        _invalidate_cache(path)
        log_for_debugging(f"[modelCapabilities] cached {len(models)} models")

    except Exception as exc:
        msg = str(exc) if exc else "unknown"
        log_for_debugging(f"[modelCapabilities] fetch failed: {msg}")


def _capabilities_equal(
    a: List[ModelCapability],
    b: List[ModelCapability],
) -> bool:
    """Deep-equality check mirroring lodash ``isEqual`` in the TS original."""
    if len(a) != len(b):
        return False
    return all(x == y for x, y in zip(a, b))
