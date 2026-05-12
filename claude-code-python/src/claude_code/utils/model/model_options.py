# Ported from utils/model/modelOptions.ts
"""
Model option builders for the /model picker.

Each builder returns a ModelOption (value, label, description) that is shown
in the interactive model selection UI.  The list adapts to the active user
tier and API provider.

@[MODEL LAUNCH]: Search for this tag to find every place that needs updating
when a new Claude model is released.
"""
from __future__ import annotations

import os
from typing import List, Optional, TypedDict

# ---------------------------------------------------------------------------
# Dependency imports (all guarded so this module loads in partial envs)
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.model.model import (
        ModelSetting,
        get_canonical_name,
        get_claude_ai_user_default_model_description,
        get_default_sonnet_model,
        get_default_opus_model,
        get_default_haiku_model,
        get_default_main_loop_model_setting,
        get_marketing_name_for_model,
        get_user_specified_model_setting,
        is_opus_1m_merge_enabled,
        render_default_model_setting,
    )
except ImportError:
    ModelSetting = Optional[str]  # type: ignore[misc,assignment]

    def get_canonical_name(m: str) -> str: return m  # type: ignore[misc]
    def get_claude_ai_user_default_model_description(fast: bool = False) -> str: return "Default model"  # type: ignore[misc]
    def get_default_sonnet_model() -> str: return "claude-sonnet-4-6"  # type: ignore[misc]
    def get_default_opus_model() -> str: return "claude-opus-4-6"  # type: ignore[misc]
    def get_default_haiku_model() -> str: return "claude-haiku-4-5-20251001"  # type: ignore[misc]
    def get_default_main_loop_model_setting() -> str: return "sonnet"  # type: ignore[misc]
    def get_marketing_name_for_model(m: str) -> Optional[str]: return None  # type: ignore[misc]
    def get_user_specified_model_setting() -> Optional[str]: return None  # type: ignore[misc]
    def is_opus_1m_merge_enabled() -> bool: return False  # type: ignore[misc]
    def render_default_model_setting(s: str) -> str: return s  # type: ignore[misc]

try:
    from claude_code.utils.model.model_strings import get_model_strings
except ImportError:
    def get_model_strings() -> dict:  # type: ignore[misc]
        return {
            "opus46": "claude-opus-4-6",
            "opus41": "claude-opus-4-1-20250805",
            "sonnet46": "claude-sonnet-4-6",
            "sonnet45": "claude-sonnet-4-5-20250929",
            "sonnet40": "claude-sonnet-4-20250514",
            "haiku45": "claude-haiku-4-5-20251001",
            "haiku35": "claude-3-5-haiku-20241022",
        }

try:
    from claude_code.utils.model.providers import get_api_provider
except ImportError:
    def get_api_provider() -> str:  # type: ignore[misc]
        return "firstParty"

try:
    from claude_code.utils.auth import (
        is_claude_ai_subscriber,
        is_max_subscriber,
        is_team_premium_subscriber,
    )
except ImportError:
    def is_claude_ai_subscriber() -> bool: return False  # type: ignore[misc]
    def is_max_subscriber() -> bool: return False  # type: ignore[misc]
    def is_team_premium_subscriber() -> bool: return False  # type: ignore[misc]

try:
    from claude_code.utils.model.check1m_access import check_opus1m_access, check_sonnet1m_access
except ImportError:
    def check_opus1m_access() -> bool: return False  # type: ignore[misc]
    def check_sonnet1m_access() -> bool: return False  # type: ignore[misc]

try:
    from claude_code.utils.model_cost import (
        COST_TIER_3_15,
        COST_HAIKU_35,
        COST_HAIKU_45,
        format_model_pricing,
    )
    _HAS_MODEL_COST = True
except ImportError:
    _HAS_MODEL_COST = False
    COST_TIER_3_15 = None  # type: ignore[assignment]
    COST_HAIKU_35 = None  # type: ignore[assignment]
    COST_HAIKU_45 = None  # type: ignore[assignment]

    def format_model_pricing(costs: object) -> str:  # type: ignore[misc]
        return ""

try:
    from claude_code.utils.model.model_allowlist import is_model_allowed
except ImportError:
    def is_model_allowed(m: str) -> bool: return True  # type: ignore[misc]

try:
    from claude_code.utils.settings.settings import get_settings_deprecated  # type: ignore
    _HAS_SETTINGS = True
except ImportError:
    _HAS_SETTINGS = False

    def get_settings_deprecated() -> Optional[dict]: return None  # type: ignore[misc]

try:
    from claude_code.utils.config import get_global_config
except ImportError:
    def get_global_config() -> object:  # type: ignore[misc]
        class _Cfg:
            additionalModelOptionsCache: Optional[list] = None
        return _Cfg()

try:
    from claude_code.bootstrap.state import get_initial_main_loop_model
except ImportError:
    def get_initial_main_loop_model() -> Optional[str]: return None  # type: ignore[misc]

try:
    from claude_code.utils.context import has_1m_context
except ImportError:
    def has_1m_context(m: str) -> bool:  # type: ignore[misc]
        return "[1m]" in m.lower()

try:
    from claude_code.utils.model.ant_models import get_ant_models
except ImportError:
    def get_ant_models() -> list:  # type: ignore[misc]
        return []


# ---------------------------------------------------------------------------
# Type
# ---------------------------------------------------------------------------

class ModelOption(TypedDict, total=False):
    value: ModelSetting          # None → "Default (recommended)"
    label: str
    description: str
    descriptionForModel: str


# ---------------------------------------------------------------------------
# Pricing suffix helper
# ---------------------------------------------------------------------------

def _get_opus46_pricing_suffix(fast_mode: bool = False) -> str:
    """Return the pricing suffix string for Opus 4.6 (first-party only)."""
    if get_api_provider() != "firstParty":
        return ""
    if not _HAS_MODEL_COST:
        return ""
    try:
        from claude_code.utils.model_cost import get_opus46_cost_tier  # type: ignore
        pricing = format_model_pricing(get_opus46_cost_tier(fast_mode))
        lightning = " (⚡)" if fast_mode else ""
        return f" ·{lightning} {pricing}"
    except (ImportError, Exception):
        return ""


# ---------------------------------------------------------------------------
# Public option builders
# ---------------------------------------------------------------------------

def get_default_option_for_user(fast_mode: bool = False) -> ModelOption:
    """Return the 'Default (recommended)' model option for the current user tier."""
    if os.environ.get("USER_TYPE") == "ant":
        current_model = render_default_model_setting(get_default_main_loop_model_setting())
        return ModelOption(
            value=None,
            label="Default (recommended)",
            description=f"Use the default model for Ants (currently {current_model})",
            descriptionForModel=f"Default model (currently {current_model})",
        )

    if is_claude_ai_subscriber():
        return ModelOption(
            value=None,
            label="Default (recommended)",
            description=get_claude_ai_user_default_model_description(fast_mode),
        )

    # PAYG
    is_3p = get_api_provider() != "firstParty"
    current_model = render_default_model_setting(get_default_main_loop_model_setting())
    pricing_str = ""
    if not is_3p and _HAS_MODEL_COST and COST_TIER_3_15 is not None:
        pricing_str = f" · {format_model_pricing(COST_TIER_3_15)}"
    return ModelOption(
        value=None,
        label="Default (recommended)",
        description=f"Use the default model (currently {current_model}){'' if is_3p else pricing_str}",
    )


def _get_custom_sonnet_option() -> Optional[ModelOption]:
    is_3p = get_api_provider() != "firstParty"
    custom = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
    if is_3p and custom:
        is1m = has_1m_context(custom)
        name = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL_NAME") or custom
        desc = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL_DESCRIPTION") or f"Custom Sonnet model{' (1M context)' if is1m else ''}"
        desc_for_model = f"{os.environ.get('ANTHROPIC_DEFAULT_SONNET_MODEL_DESCRIPTION') or f'Custom Sonnet model{chr(32) + chr(40) + chr(49) + chr(77) + chr(32) + chr(99) + chr(111) + chr(110) + chr(116) + chr(101) + chr(120) + chr(116) + chr(41) if is1m else chr(0) * 0}'} ({custom})"
        # Cleaner:
        base_desc = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL_DESCRIPTION") or f"Custom Sonnet model{' with 1M context' if is1m else ''}"
        return ModelOption(
            value="sonnet",
            label=name,
            description=os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL_DESCRIPTION") or f"Custom Sonnet model{' (1M context)' if is1m else ''}",
            descriptionForModel=f"{base_desc} ({custom})",
        )
    return None


# @[MODEL LAUNCH]: Update or add model option functions below
def _get_sonnet46_option() -> ModelOption:
    is_3p = get_api_provider() != "firstParty"
    pricing = f" · {format_model_pricing(COST_TIER_3_15)}" if not is_3p and _HAS_MODEL_COST and COST_TIER_3_15 is not None else ""
    return ModelOption(
        value=get_model_strings().get("sonnet46", "claude-sonnet-4-6") if is_3p else "sonnet",
        label="Sonnet",
        description=f"Sonnet 4.6 · Best for everyday tasks{'' if is_3p else pricing}",
        descriptionForModel="Sonnet 4.6 - best for everyday tasks. Generally recommended for most coding tasks",
    )


def _get_custom_opus_option() -> Optional[ModelOption]:
    is_3p = get_api_provider() != "firstParty"
    custom = os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    if is_3p and custom:
        is1m = has_1m_context(custom)
        name = os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL_NAME") or custom
        base_desc = os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL_DESCRIPTION") or f"Custom Opus model{' with 1M context' if is1m else ''}"
        return ModelOption(
            value="opus",
            label=name,
            description=os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL_DESCRIPTION") or f"Custom Opus model{' (1M context)' if is1m else ''}",
            descriptionForModel=f"{base_desc} ({custom})",
        )
    return None


def _get_opus41_option() -> ModelOption:
    return ModelOption(
        value="opus",
        label="Opus 4.1",
        description="Opus 4.1 · Legacy",
        descriptionForModel="Opus 4.1 - legacy version",
    )


def _get_opus46_option(fast_mode: bool = False) -> ModelOption:
    is_3p = get_api_provider() != "firstParty"
    return ModelOption(
        value=get_model_strings().get("opus46", "claude-opus-4-6") if is_3p else "opus",
        label="Opus",
        description=f"Opus 4.6 · Most capable for complex work{_get_opus46_pricing_suffix(fast_mode)}",
        descriptionForModel="Opus 4.6 - most capable for complex work",
    )


def get_sonnet46_1m_option() -> ModelOption:
    is_3p = get_api_provider() != "firstParty"
    pricing = f" · {format_model_pricing(COST_TIER_3_15)}" if not is_3p and _HAS_MODEL_COST and COST_TIER_3_15 is not None else ""
    return ModelOption(
        value=(get_model_strings().get("sonnet46", "claude-sonnet-4-6") + "[1m]") if is_3p else "sonnet[1m]",
        label="Sonnet (1M context)",
        description=f"Sonnet 4.6 for long sessions{'' if is_3p else pricing}",
        descriptionForModel="Sonnet 4.6 with 1M context window - for long sessions with large codebases",
    )


def get_opus46_1m_option(fast_mode: bool = False) -> ModelOption:
    is_3p = get_api_provider() != "firstParty"
    return ModelOption(
        value=(get_model_strings().get("opus46", "claude-opus-4-6") + "[1m]") if is_3p else "opus[1m]",
        label="Opus (1M context)",
        description=f"Opus 4.6 for long sessions{_get_opus46_pricing_suffix(fast_mode)}",
        descriptionForModel="Opus 4.6 with 1M context window - for long sessions with large codebases",
    )


def _get_custom_haiku_option() -> Optional[ModelOption]:
    is_3p = get_api_provider() != "firstParty"
    custom = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
    if is_3p and custom:
        name = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME") or custom
        base_desc = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL_DESCRIPTION") or "Custom Haiku model"
        return ModelOption(
            value="haiku",
            label=name,
            description=base_desc,
            descriptionForModel=f"{base_desc} ({custom})",
        )
    return None


def _get_haiku45_option() -> ModelOption:
    is_3p = get_api_provider() != "firstParty"
    pricing = f" · {format_model_pricing(COST_HAIKU_45)}" if not is_3p and _HAS_MODEL_COST and COST_HAIKU_45 is not None else ""
    return ModelOption(
        value="haiku",
        label="Haiku",
        description=f"Haiku 4.5 · Fastest for quick answers{'' if is_3p else pricing}",
        descriptionForModel="Haiku 4.5 - fastest for quick answers. Lower cost but less capable than Sonnet 4.6.",
    )


def _get_haiku35_option() -> ModelOption:
    is_3p = get_api_provider() != "firstParty"
    pricing = f" · {format_model_pricing(COST_HAIKU_35)}" if not is_3p and _HAS_MODEL_COST and COST_HAIKU_35 is not None else ""
    return ModelOption(
        value="haiku",
        label="Haiku",
        description=f"Haiku 3.5 for simple tasks{'' if is_3p else pricing}",
        descriptionForModel="Haiku 3.5 - faster and lower cost, but less capable than Sonnet. Use for simple tasks.",
    )


def _get_haiku_option() -> ModelOption:
    """Return the correct Haiku option for the current provider's default Haiku model."""
    haiku_model = get_default_haiku_model()
    if haiku_model == get_model_strings().get("haiku45", "claude-haiku-4-5-20251001"):
        return _get_haiku45_option()
    return _get_haiku35_option()


def _get_max_opus_option(fast_mode: bool = False) -> ModelOption:
    return ModelOption(
        value="opus",
        label="Opus",
        description=f"Opus 4.6 · Most capable for complex work{_get_opus46_pricing_suffix(fast_mode) if fast_mode else ''}",
    )


def get_max_sonnet46_1m_option() -> ModelOption:
    is_3p = get_api_provider() != "firstParty"
    billing = " · Billed as extra usage" if is_claude_ai_subscriber() else ""
    pricing = f" · {format_model_pricing(COST_TIER_3_15)}" if not is_3p and _HAS_MODEL_COST and COST_TIER_3_15 is not None else ""
    return ModelOption(
        value="sonnet[1m]",
        label="Sonnet (1M context)",
        description=f"Sonnet 4.6 with 1M context{billing}{'' if is_3p else pricing}",
    )


def get_max_opus46_1m_option(fast_mode: bool = False) -> ModelOption:
    billing = " · Billed as extra usage" if is_claude_ai_subscriber() else ""
    return ModelOption(
        value="opus[1m]",
        label="Opus (1M context)",
        description=f"Opus 4.6 with 1M context{billing}{_get_opus46_pricing_suffix(fast_mode)}",
    )


def _get_merged_opus1m_option(fast_mode: bool = False) -> ModelOption:
    is_3p = get_api_provider() != "firstParty"
    pricing = _get_opus46_pricing_suffix(fast_mode) if not is_3p and fast_mode else ""
    return ModelOption(
        value=(get_model_strings().get("opus46", "claude-opus-4-6") + "[1m]") if is_3p else "opus[1m]",
        label="Opus (1M context)",
        description=f"Opus 4.6 with 1M context · Most capable for complex work{pricing}",
        descriptionForModel="Opus 4.6 with 1M context - most capable for complex work",
    )


_MAX_SONNET46_OPTION: ModelOption = ModelOption(
    value="sonnet",
    label="Sonnet",
    description="Sonnet 4.6 · Best for everyday tasks",
)

_MAX_HAIKU45_OPTION: ModelOption = ModelOption(
    value="haiku",
    label="Haiku",
    description="Haiku 4.5 · Fastest for quick answers",
)


def _get_opus_plan_option() -> ModelOption:
    return ModelOption(
        value="opusplan",
        label="Opus Plan Mode",
        description="Use Opus 4.6 in plan mode, Sonnet 4.6 otherwise",
    )


# ---------------------------------------------------------------------------
# Model family helpers (for upgrade hints)
# ---------------------------------------------------------------------------

def _get_model_family_info(
    model: str,
) -> Optional[dict]:
    """Return ``{alias, currentVersionName}`` if *model* belongs to a known family."""
    canonical = get_canonical_name(model)

    # Sonnet family
    if any(
        s in canonical
        for s in ("claude-sonnet-4-6", "claude-sonnet-4-5", "claude-sonnet-4-", "claude-3-7-sonnet", "claude-3-5-sonnet")
    ):
        name = get_marketing_name_for_model(get_default_sonnet_model())
        if name:
            return {"alias": "Sonnet", "currentVersionName": name}

    # Opus family
    if "claude-opus-4" in canonical:
        name = get_marketing_name_for_model(get_default_opus_model())
        if name:
            return {"alias": "Opus", "currentVersionName": name}

    # Haiku family
    if "claude-haiku" in canonical or "claude-3-5-haiku" in canonical:
        name = get_marketing_name_for_model(get_default_haiku_model())
        if name:
            return {"alias": "Haiku", "currentVersionName": name}

    return None


def _get_known_model_option(model: str) -> Optional[ModelOption]:
    """Return a ModelOption with human-readable label (and upgrade hint) for known models."""
    marketing_name = get_marketing_name_for_model(model)
    if not marketing_name:
        return None

    family_info = _get_model_family_info(model)
    if not family_info:
        return ModelOption(value=model, label=marketing_name, description=model)

    # Show upgrade hint when the alias now resolves to a newer version
    if marketing_name != family_info["currentVersionName"]:
        return ModelOption(
            value=model,
            label=marketing_name,
            description=f"Newer version available · select {family_info['alias']} for {family_info['currentVersionName']}",
        )

    return ModelOption(value=model, label=marketing_name, description=model)


# ---------------------------------------------------------------------------
# Core list builder
# ---------------------------------------------------------------------------

# @[MODEL LAUNCH]: Update the model picker lists below to include/reorder options.
def _get_model_options_base(fast_mode: bool = False) -> List[ModelOption]:
    if os.environ.get("USER_TYPE") == "ant":
        ant_model_options: List[ModelOption] = [
            ModelOption(
                value=m.get("alias"),
                label=m.get("label", ""),
                description=m.get("description") or f"[ANT-ONLY] {m.get('label', '')} ({m.get('model', '')})",
            )
            for m in get_ant_models()
        ]
        return [
            get_default_option_for_user(),
            *ant_model_options,
            _get_merged_opus1m_option(fast_mode),
            _get_sonnet46_option(),
            get_sonnet46_1m_option(),
            _get_haiku45_option(),
        ]

    if is_claude_ai_subscriber():
        if is_max_subscriber() or is_team_premium_subscriber():
            # Max / Team Premium: Opus is default
            opts: List[ModelOption] = [get_default_option_for_user(fast_mode)]
            if not is_opus_1m_merge_enabled() and check_opus1m_access():
                opts.append(get_max_opus46_1m_option(fast_mode))
            opts.append(_MAX_SONNET46_OPTION)
            if check_sonnet1m_access():
                opts.append(get_max_sonnet46_1m_option())
            opts.append(_MAX_HAIKU45_OPTION)
            return opts

        # Pro / Team Standard / Enterprise: Sonnet is default
        standard: List[ModelOption] = [get_default_option_for_user(fast_mode)]
        if check_sonnet1m_access():
            standard.append(get_max_sonnet46_1m_option())
        if is_opus_1m_merge_enabled():
            standard.append(_get_merged_opus1m_option(fast_mode))
        else:
            standard.append(_get_max_opus_option(fast_mode))
            if check_opus1m_access():
                standard.append(get_max_opus46_1m_option(fast_mode))
        standard.append(_MAX_HAIKU45_OPTION)
        return standard

    # PAYG 1P
    if get_api_provider() == "firstParty":
        payg1p: List[ModelOption] = [get_default_option_for_user(fast_mode)]
        if check_sonnet1m_access():
            payg1p.append(get_sonnet46_1m_option())
        if is_opus_1m_merge_enabled():
            payg1p.append(_get_merged_opus1m_option(fast_mode))
        else:
            payg1p.append(_get_opus46_option(fast_mode))
            if check_opus1m_access():
                payg1p.append(get_opus46_1m_option(fast_mode))
        payg1p.append(_get_haiku45_option())
        return payg1p

    # PAYG 3P
    payg3p: List[ModelOption] = [get_default_option_for_user(fast_mode)]

    custom_sonnet = _get_custom_sonnet_option()
    if custom_sonnet is not None:
        payg3p.append(custom_sonnet)
    else:
        payg3p.append(_get_sonnet46_option())
        if check_sonnet1m_access():
            payg3p.append(get_sonnet46_1m_option())

    custom_opus = _get_custom_opus_option()
    if custom_opus is not None:
        payg3p.append(custom_opus)
    else:
        payg3p.append(_get_opus41_option())
        payg3p.append(_get_opus46_option(fast_mode))
        if check_opus1m_access():
            payg3p.append(get_opus46_1m_option(fast_mode))

    custom_haiku = _get_custom_haiku_option()
    if custom_haiku is not None:
        payg3p.append(custom_haiku)
    else:
        payg3p.append(_get_haiku_option())

    return payg3p


# ---------------------------------------------------------------------------
# Allowlist filter
# ---------------------------------------------------------------------------

def _filter_model_options_by_allowlist(options: List[ModelOption]) -> List[ModelOption]:
    """Remove options not permitted by the enterprise availableModels allowlist.

    The Default option (value=None) is always preserved.
    """
    settings = get_settings_deprecated() or {} if _HAS_SETTINGS else {}
    if not settings.get("availableModels"):
        return options
    return [
        opt for opt in options
        if opt.get("value") is None or (opt.get("value") is not None and is_model_allowed(opt["value"]))
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_model_options(fast_mode: bool = False) -> List[ModelOption]:
    """Return the full list of selectable model options for the current session."""
    options = _get_model_options_base(fast_mode)

    # Custom model from ANTHROPIC_CUSTOM_MODEL_OPTION env var
    env_custom = os.environ.get("ANTHROPIC_CUSTOM_MODEL_OPTION")
    if env_custom and not any(o.get("value") == env_custom for o in options):
        options.append(ModelOption(
            value=env_custom,
            label=os.environ.get("ANTHROPIC_CUSTOM_MODEL_OPTION_NAME") or env_custom,
            description=os.environ.get("ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION") or f"Custom model ({env_custom})",
        ))

    # Additional model options cached during bootstrap
    try:
        additional = get_global_config().additionalModelOptionsCache  # type: ignore[union-attr]
        if additional:
            for opt in additional:
                if not any(o.get("value") == opt.get("value") for o in options):
                    options.append(opt)
    except Exception:
        pass

    # Ensure the currently active model (user-specified or initial) is in the list
    custom_model: ModelSetting = None
    current = get_user_specified_model_setting()
    initial = get_initial_main_loop_model()
    if current is not None and current != "" and current is not None:
        custom_model = current
    elif initial is not None:
        custom_model = initial

    if custom_model is None or any(o.get("value") == custom_model for o in options):
        return _filter_model_options_by_allowlist(options)
    elif custom_model == "opusplan":
        return _filter_model_options_by_allowlist([*options, _get_opus_plan_option()])
    elif custom_model == "opus" and get_api_provider() == "firstParty":
        return _filter_model_options_by_allowlist([*options, _get_max_opus_option(fast_mode)])
    elif custom_model == "opus[1m]" and get_api_provider() == "firstParty":
        return _filter_model_options_by_allowlist([*options, _get_merged_opus1m_option(fast_mode)])
    else:
        known = _get_known_model_option(custom_model)
        if known:
            options.append(known)
        else:
            options.append(ModelOption(
                value=custom_model,
                label=custom_model,
                description="Custom model",
            ))
        return _filter_model_options_by_allowlist(options)
