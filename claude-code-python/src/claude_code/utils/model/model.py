"""Model selection utilities. Ported from utils/model/model.ts (623 lines)."""
from __future__ import annotations

import os
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Type aliases (mirrors TS exports)
# ---------------------------------------------------------------------------
ModelShortName = str
ModelName = str
ModelSetting = Optional[str]  # None means "use default"

# ---------------------------------------------------------------------------
# Internal dependency imports with try/except guards
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.model.aliases import is_model_alias, ModelAlias
except ImportError:
    ModelAlias = str  # type: ignore

    def is_model_alias(model: str) -> bool:  # type: ignore
        return model in ("sonnet", "opus", "haiku", "best", "opusplan", "sonnet[1m]", "opus[1m]")


try:
    from claude_code.utils.model.providers import get_api_provider
except ImportError:
    def get_api_provider() -> str:  # type: ignore
        if os.environ.get("CLAUDE_CODE_USE_BEDROCK", "").lower() in ("1", "true"):
            return "bedrock"
        if os.environ.get("CLAUDE_CODE_USE_VERTEX", "").lower() in ("1", "true"):
            return "vertex"
        if os.environ.get("CLAUDE_CODE_USE_FOUNDRY", "").lower() in ("1", "true"):
            return "foundry"
        if os.environ.get("HUNYUAN_API_KEY"):
            return "hunyuan"
        return "firstParty"


try:
    from claude_code.utils.model.model_strings import get_model_strings, resolve_overridden_model
except ImportError:
    def get_model_strings() -> dict:  # type: ignore
        return {
            "opus46": "claude-opus-4-6",
            "opus45": "claude-opus-4-5-20251101",
            "opus41": "claude-opus-4-1-20250805",
            "opus40": "claude-opus-4-20250514",
            "sonnet46": "claude-sonnet-4-6",
            "sonnet45": "claude-sonnet-4-5-20250929",
            "sonnet40": "claude-sonnet-4-20250514",
            "sonnet37": "claude-3-7-sonnet-20250219",
            "sonnet35": "claude-3-5-sonnet-20241022",
            "haiku45": "claude-haiku-4-5-20251001",
            "haiku35": "claude-3-5-haiku-20241022",
        }

    def resolve_overridden_model(model_id: str) -> str:  # type: ignore
        return model_id


try:
    from claude_code.utils.model.model_allowlist import is_model_allowed
except ImportError:
    def is_model_allowed(model: str) -> bool:  # type: ignore
        return True


try:
    from claude_code.utils.context import has_1m_context, is_1m_context_disabled, model_supports_1m
except ImportError:
    def has_1m_context(model: str) -> bool:  # type: ignore
        return "[1m]" in model.lower()

    def is_1m_context_disabled() -> bool:  # type: ignore
        return os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "").lower() in ("1", "true")

    def model_supports_1m(model: str) -> bool:  # type: ignore
        return "opus" in model or "sonnet" in model


try:
    from claude_code.utils.auth import (
        is_claude_ai_subscriber,
        is_max_subscriber,
        is_pro_subscriber,
        is_team_premium_subscriber,
        get_subscription_type,
    )
except ImportError:
    def is_claude_ai_subscriber() -> bool:  # type: ignore
        return False

    def is_max_subscriber() -> bool:  # type: ignore
        return False

    def is_pro_subscriber() -> bool:  # type: ignore
        return False

    def is_team_premium_subscriber() -> bool:  # type: ignore
        return False

    def get_subscription_type() -> Optional[str]:  # type: ignore
        return None


try:
    from claude_code.utils.model.ant_models import resolve_ant_model, get_ant_model_override_config  # type: ignore
    _HAS_ANT_MODELS = True
except ImportError:
    _HAS_ANT_MODELS = False

    def resolve_ant_model(model: str):  # type: ignore
        return None

    def get_ant_model_override_config():  # type: ignore
        return None


# ---------------------------------------------------------------------------
# Hunyuan constants
# ---------------------------------------------------------------------------
HUNYUAN_DEFAULT_MODEL = os.environ.get("HUNYUAN_DEFAULT_MODEL", "hunyuan-turbos-latest")
HUNYUAN_SMALL_MODEL = os.environ.get("HUNYUAN_SMALL_MODEL", "hunyuan-lite")

# ---------------------------------------------------------------------------
# Legacy Opus models that should be remapped on first-party API
# ---------------------------------------------------------------------------
_LEGACY_OPUS_FIRSTPARTY = [
    "claude-opus-4-20250514",
    "claude-opus-4-1-20250805",
    "claude-opus-4-0",
    "claude-opus-4-1",
]


def _is_env_truthy(val: Optional[str]) -> bool:
    return (val or "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_small_fast_model() -> ModelName:
    """Return the small/fast (Haiku-class) model to use."""
    if os.environ.get("HUNYUAN_API_KEY"):
        return os.environ.get("ANTHROPIC_SMALL_FAST_MODEL") or HUNYUAN_SMALL_MODEL
    return os.environ.get("ANTHROPIC_SMALL_FAST_MODEL") or get_default_haiku_model()


def is_non_custom_opus_model(model: ModelName) -> bool:
    """Return True if *model* is one of the known standard Opus variants."""
    ms = get_model_strings()
    return model in (
        ms.get("opus40", ""),
        ms.get("opus41", ""),
        ms.get("opus45", ""),
        ms.get("opus46", ""),
    )


def get_user_specified_model_setting() -> Optional[ModelSetting]:
    """Return the user-configured model (env / settings) or None.

    Priority:
    1. Session override (/model command)
    2. ANTHROPIC_MODEL env var
    3. Saved settings
    """
    specified: Optional[str] = None

    # 1. Session-level override
    try:
        from claude_code.bootstrap.state import get_main_loop_model_override  # type: ignore
        override = get_main_loop_model_override()
        if override is not None:
            specified = override
    except ImportError:
        pass

    if specified is None:
        # 2 & 3: env var or saved settings
        try:
            from claude_code.utils.settings.settings import get_settings_deprecated  # type: ignore
            settings = get_settings_deprecated() or {}
        except ImportError:
            settings = {}
        specified = os.environ.get("ANTHROPIC_MODEL") or settings.get("model") or None

    # Ignore if not in allowlist
    if specified and not is_model_allowed(specified):
        return None

    return specified


def get_main_loop_model() -> ModelName:
    """Return the resolved model name for the current session.

    Priority order (see :func:`get_user_specified_model_setting`):
    1. Session-level override
    2. --model flag / ANTHROPIC_MODEL env
    3. Saved settings
    4. Built-in default
    """
    model = get_user_specified_model_setting()
    if model is not None and model is not None and model != "":  # None means default
        return parse_user_specified_model(model)
    return get_default_main_loop_model()


def get_best_model() -> ModelName:
    """Return the most capable model available."""
    return get_default_opus_model()


def get_default_opus_model() -> ModelName:
    """Return the default Opus model string for the current provider."""
    override = os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    if override:
        return override
    ms = get_model_strings()
    return ms.get("opus46", "claude-opus-4-6")


def get_default_sonnet_model() -> ModelName:
    """Return the default Sonnet model string for the current provider."""
    override = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
    if override:
        return override
    if os.environ.get("HUNYUAN_API_KEY"):
        return HUNYUAN_DEFAULT_MODEL
    ms = get_model_strings()
    # 3P providers may not have 4.6 yet — default to 4.5
    if get_api_provider() != "firstParty":
        return ms.get("sonnet45", "claude-sonnet-4-5-20250929")
    return ms.get("sonnet46", "claude-sonnet-4-6")


def get_default_haiku_model() -> ModelName:
    """Return the default Haiku model string for the current provider."""
    override = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
    if override:
        return override
    ms = get_model_strings()
    return ms.get("haiku45", "claude-haiku-4-5-20251001")


def get_runtime_main_loop_model(
    *,
    permission_mode: str,
    main_loop_model: str,
    exceeds_200k_tokens: bool = False,
) -> ModelName:
    """Return the model to use for a given runtime context.

    Handles *opusplan* (uses Opus in plan mode) and *haiku* plan-mode upgrade
    (auto-upgrades to Sonnet).
    """
    user_setting = get_user_specified_model_setting()

    if (
        user_setting == "opusplan"
        and permission_mode == "plan"
        and not exceeds_200k_tokens
    ):
        return get_default_opus_model()

    if user_setting == "haiku" and permission_mode == "plan":
        return get_default_sonnet_model()

    return main_loop_model


def get_default_main_loop_model_setting() -> str:
    """Return the built-in default model setting (alias or name).

    - Ant users: use flag config, else Opus[1m]
    - Max / Team Premium: Opus (+ [1m] if enabled)
    - Everyone else: Sonnet
    """
    user_type = os.environ.get("USER_TYPE")
    if user_type == "ant":
        cfg = get_ant_model_override_config()
        if cfg and cfg.get("defaultModel"):
            return cfg["defaultModel"]
        return get_default_opus_model() + "[1m]"

    if is_max_subscriber():
        suffix = "[1m]" if is_opus_1m_merge_enabled() else ""
        return get_default_opus_model() + suffix

    if is_team_premium_subscriber():
        suffix = "[1m]" if is_opus_1m_merge_enabled() else ""
        return get_default_opus_model() + suffix

    return get_default_sonnet_model()


def get_default_main_loop_model() -> ModelName:
    """Synchronous resolution of the default model (bypasses user settings)."""
    return parse_user_specified_model(get_default_main_loop_model_setting())


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------

def first_party_name_to_canonical(name: ModelName) -> ModelShortName:
    """Strip date/provider suffixes from a first-party model ID.

    Input must already be a 1P-format ID.  Does not touch settings.
    """
    name = name.lower()
    # Order matters: check more specific versions first
    if "claude-opus-4-6" in name:
        return "claude-opus-4-6"
    if "claude-opus-4-5" in name:
        return "claude-opus-4-5"
    if "claude-opus-4-1" in name:
        return "claude-opus-4-1"
    if "claude-opus-4" in name:
        return "claude-opus-4"
    if "claude-sonnet-4-6" in name:
        return "claude-sonnet-4-6"
    if "claude-sonnet-4-5" in name:
        return "claude-sonnet-4-5"
    if "claude-sonnet-4" in name:
        return "claude-sonnet-4"
    if "claude-haiku-4-5" in name:
        return "claude-haiku-4-5"
    if "claude-3-7-sonnet" in name:
        return "claude-3-7-sonnet"
    if "claude-3-5-sonnet" in name:
        return "claude-3-5-sonnet"
    if "claude-3-5-haiku" in name:
        return "claude-3-5-haiku"
    if "claude-3-opus" in name:
        return "claude-3-opus"
    if "claude-3-sonnet" in name:
        return "claude-3-sonnet"
    if "claude-3-haiku" in name:
        return "claude-3-haiku"
    match = re.search(r"(claude-(\d+-\d+-)?\w+)", name)
    if match and match.group(1):
        return match.group(1)
    return name


def get_canonical_name(full_model_name: ModelName) -> ModelShortName:
    """Map a full model string to its unified canonical short name.

    Works across 1P and 3P providers, e.g.
    ``'claude-3-5-haiku-20241022'`` and
    ``'us.anthropic.claude-3-5-haiku-20241022-v1:0'`` both → ``'claude-3-5-haiku'``.
    """
    return first_party_name_to_canonical(resolve_overridden_model(full_model_name))


def _mask_model_codename(base_name: str) -> str:
    """Mask the first dash-separated segment of an internal codename."""
    parts = base_name.split("-")
    if not parts:
        return base_name
    codename = parts[0]
    masked = codename[:3] + "*" * max(0, len(codename) - 3)
    return "-".join([masked] + parts[1:])


def render_model_name(model: ModelName) -> str:
    """Return a human-readable display name for *model*."""
    public = get_public_model_display_name(model)
    if public:
        return public
    user_type = os.environ.get("USER_TYPE")
    if user_type == "ant":
        resolved = parse_user_specified_model(model)
        ant_model = resolve_ant_model(model)
        if ant_model:
            base_name = ant_model.get("model", model).replace("[1m]", "").replace("[1M]", "")
            masked = _mask_model_codename(base_name)
            suffix = "[1m]" if has_1m_context(resolved) else ""
            return masked + suffix
        if resolved != model:
            return f"{model} ({resolved})"
        return resolved
    return model


def get_public_model_name(model: ModelName) -> str:
    """Return "Claude {ModelName}" for public models, else "Claude ({model})"."""
    public = get_public_model_display_name(model)
    if public:
        return f"Claude {public}"
    return f"Claude ({model})"


def get_public_model_display_name(model: ModelName) -> Optional[str]:
    """Return a human-readable display name for known public models, or None."""
    ms = get_model_strings()
    mapping = {
        ms.get("opus46", ""): "Opus 4.6",
        ms.get("opus46", "") + "[1m]": "Opus 4.6 (1M context)",
        ms.get("opus45", ""): "Opus 4.5",
        ms.get("opus41", ""): "Opus 4.1",
        ms.get("opus40", ""): "Opus 4",
        ms.get("sonnet46", "") + "[1m]": "Sonnet 4.6 (1M context)",
        ms.get("sonnet46", ""): "Sonnet 4.6",
        ms.get("sonnet45", "") + "[1m]": "Sonnet 4.5 (1M context)",
        ms.get("sonnet45", ""): "Sonnet 4.5",
        ms.get("sonnet40", ""): "Sonnet 4",
        ms.get("sonnet40", "") + "[1m]": "Sonnet 4 (1M context)",
        ms.get("sonnet37", ""): "Sonnet 3.7",
        ms.get("sonnet35", ""): "Sonnet 3.5",
        ms.get("haiku45", ""): "Haiku 4.5",
        ms.get("haiku35", ""): "Haiku 3.5",
    }
    return mapping.get(model)


# ---------------------------------------------------------------------------
# Model parsing
# ---------------------------------------------------------------------------

def parse_user_specified_model(model_input: str) -> ModelName:
    """Resolve a user-supplied model string (alias or full name) to a concrete ID.

    Supports:
    - Family aliases: ``sonnet``, ``opus``, ``haiku``, ``best``, ``opusplan``
    - ``[1m]`` suffix on any alias to request 1M context
    - Legacy Opus 4.0/4.1 remap on first-party API
    - Ant-only codename resolution
    """
    trimmed = model_input.strip()
    normalized = trimmed.lower()

    _has_1m = has_1m_context(normalized)
    model_base = normalized.replace("[1m]", "").strip() if _has_1m else normalized
    suffix = "[1m]" if _has_1m else ""

    if is_model_alias(model_base):
        if model_base == "opusplan":
            return get_default_sonnet_model() + suffix  # Sonnet is default; Opus in plan mode
        if model_base == "sonnet":
            return get_default_sonnet_model() + suffix
        if model_base == "haiku":
            return get_default_haiku_model() + suffix
        if model_base == "opus":
            return get_default_opus_model() + suffix
        if model_base == "best":
            return get_best_model()

    # Legacy Opus 4.0/4.1 remap on first-party API
    if (
        get_api_provider() == "firstParty"
        and _is_legacy_opus_first_party(model_base)
        and is_legacy_model_remap_enabled()
    ):
        return get_default_opus_model() + suffix

    # Ant-only codename resolution
    if os.environ.get("USER_TYPE") == "ant":
        ant_model = resolve_ant_model(model_base)
        if ant_model:
            return ant_model.get("model", model_base) + suffix

    # Preserve original case for custom model names
    if _has_1m:
        base = re.sub(r"\[1m\]$", "", trimmed, flags=re.IGNORECASE).strip()
        return base + "[1m]"
    return trimmed


def resolve_skill_model_override(skill_model: str, current_model: str) -> str:
    """Resolve a skill's ``model:`` frontmatter against the current session model.

    Carries the ``[1m]`` suffix over when the target family supports it, so a
    skill with ``model: opus`` on a 1M session doesn't silently downgrade context.
    """
    if has_1m_context(skill_model) or not has_1m_context(current_model):
        return skill_model
    # Check if the resolved target model family supports 1M
    if model_supports_1m(parse_user_specified_model(skill_model)):
        return skill_model + "[1m]"
    return skill_model


def is_legacy_model_remap_enabled() -> bool:
    """Return False if the legacy Opus remap is explicitly disabled."""
    return not _is_env_truthy(os.environ.get("CLAUDE_CODE_DISABLE_LEGACY_MODEL_REMAP"))


def _is_legacy_opus_first_party(model: str) -> bool:
    return model in _LEGACY_OPUS_FIRSTPARTY


# ---------------------------------------------------------------------------
# Display / pricing helpers
# ---------------------------------------------------------------------------

def is_opus_1m_merge_enabled() -> bool:
    """Return True when Opus 1M context merging is active."""
    if is_1m_context_disabled() or is_pro_subscriber() or get_api_provider() != "firstParty":
        return False
    # Fail closed when subscriber type is unknown
    if is_claude_ai_subscriber() and get_subscription_type() is None:
        return False
    return True


def get_claude_ai_user_default_model_description(fast_mode: bool = False) -> str:
    """Return the user-facing description of the default model for claude.ai users."""
    if is_max_subscriber() or is_team_premium_subscriber():
        if is_opus_1m_merge_enabled():
            suffix = _get_opus46_pricing_suffix(fast_mode) if fast_mode else ""
            return f"Opus 4.6 with 1M context · Most capable for complex work{suffix}"
        suffix = _get_opus46_pricing_suffix(fast_mode) if fast_mode else ""
        return f"Opus 4.6 · Most capable for complex work{suffix}"
    return "Sonnet 4.6 · Best for everyday tasks"


def render_default_model_setting(setting: str) -> str:
    """Return display string for the default model setting."""
    if setting == "opusplan":
        return "Opus 4.6 in plan mode, else Sonnet 4.6"
    return render_model_name(parse_user_specified_model(setting))


def render_model_setting(setting: str) -> str:
    """Return display string for a model setting (alias-aware)."""
    if setting == "opusplan":
        return "Opus Plan"
    if is_model_alias(setting):
        return setting.capitalize()
    return render_model_name(setting)


def _get_opus46_pricing_suffix(fast_mode: bool) -> str:
    if get_api_provider() != "firstParty":
        return ""
    try:
        from claude_code.utils.model_cost import format_model_pricing, get_opus46_cost_tier  # type: ignore
        pricing = format_model_pricing(get_opus46_cost_tier(fast_mode))
        lightning = " (⚡)" if fast_mode else ""
        return f" ·{lightning} {pricing}"
    except ImportError:
        return ""


def model_display_string(model: ModelSetting) -> str:
    """Return a display string for a model setting (including None = default)."""
    if model is None:
        user_type = os.environ.get("USER_TYPE")
        if user_type == "ant":
            return f"Default for Ants ({render_default_model_setting(get_default_main_loop_model_setting())})"
        if is_claude_ai_subscriber():
            return f"Default ({get_claude_ai_user_default_model_description()})"
        return f"Default ({get_default_main_loop_model()})"
    resolved = parse_user_specified_model(model)
    return model if model == resolved else f"{model} ({resolved})"


def get_marketing_name_for_model(model_id: str) -> Optional[str]:
    """Return a marketing display name (e.g. 'Sonnet 4.6') or None for unknown models."""
    if get_api_provider() == "foundry":
        # Foundry deployment IDs are user-defined
        return None

    has_1m = "[1m]" in model_id.lower()
    canonical = get_canonical_name(model_id)

    if "claude-opus-4-6" in canonical:
        return "Opus 4.6 (with 1M context)" if has_1m else "Opus 4.6"
    if "claude-opus-4-5" in canonical:
        return "Opus 4.5"
    if "claude-opus-4-1" in canonical:
        return "Opus 4.1"
    if "claude-opus-4" in canonical:
        return "Opus 4"
    if "claude-sonnet-4-6" in canonical:
        return "Sonnet 4.6 (with 1M context)" if has_1m else "Sonnet 4.6"
    if "claude-sonnet-4-5" in canonical:
        return "Sonnet 4.5 (with 1M context)" if has_1m else "Sonnet 4.5"
    if "claude-sonnet-4" in canonical:
        return "Sonnet 4 (with 1M context)" if has_1m else "Sonnet 4"
    if "claude-3-7-sonnet" in canonical:
        return "Claude 3.7 Sonnet"
    if "claude-3-5-sonnet" in canonical:
        return "Claude 3.5 Sonnet"
    if "claude-haiku-4-5" in canonical:
        return "Haiku 4.5"
    if "claude-3-5-haiku" in canonical:
        return "Claude 3.5 Haiku"

    return None


def normalize_model_string_for_api(model: str) -> str:
    """Strip [1m] / [2m] suffixes before sending to the API."""
    return re.sub(r"\[(1|2)m\]", "", model, flags=re.IGNORECASE)
