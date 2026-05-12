"""
Internal writes - settings fields that should not be written to editable sources.
"""

from __future__ import annotations

from typing import Set

# These fields are managed internally and should not be editable by users
# (they're set by the app and tracked separately).
INTERNAL_WRITE_FIELDS: Set[str] = {
    "lastOnboardingVersion",
    "numStartups",
    "hasCompletedProjectOnboarding",
    "hasCompletedOnboarding",
    "installationId",
    "firstOnboardingDate",
    "lastReleaseNotesDismissalDate",
    "primaryApiKey",
    "oauthAccount",
}


def is_internal_write_field(key: str) -> bool:
    """Check if a settings key is an internal write field."""
    return key in INTERNAL_WRITE_FIELDS


def filter_internal_fields(settings: dict) -> dict:
    """Remove internal write fields from a settings dict."""
    return {k: v for k, v in settings.items() if k not in INTERNAL_WRITE_FIELDS}
