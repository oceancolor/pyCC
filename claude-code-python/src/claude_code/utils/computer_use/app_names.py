"""
app_names.py - Filter and sanitize installed-app data for computer use.

Port of TypeScript appNames.ts.
"""

import re
from typing import List, Optional, Set


# Path allowlist for user-facing apps
_PATH_ALLOWLIST: List[str] = [
    '/Applications/',
    '/System/Applications/',
]

# Name patterns that mark background services
_NAME_PATTERN_BLOCKLIST = [
    re.compile(r'Helper(?:$|\s\()'),
    re.compile(r'Agent(?:$|\s\()'),
    re.compile(r'Service(?:$|\s\()'),
    re.compile(r'Uninstaller(?:$|\s\()'),
    re.compile(r'Updater(?:$|\s\()'),
    re.compile(r'^\\.'),
]

# Always-keep bundle IDs
_ALWAYS_KEEP_BUNDLE_IDS: Set[str] = {
    # Browsers
    'com.apple.Safari',
    'com.google.Chrome',
    'com.microsoft.edgemac',
    'org.mozilla.firefox',
    'company.thebrowser.Browser',  # Arc
    # Communication
    'com.tinyspeck.slackmacgap',
    'us.zoom.xos',
    'com.microsoft.teams2',
    'com.microsoft.teams',
    'com.apple.MobileSMS',
    'com.apple.mail',
    # Productivity
    'com.microsoft.Word',
    'com.microsoft.Excel',
    'com.microsoft.Powerpoint',
    'com.microsoft.Outlook',
    'com.apple.iWork.Pages',
    'com.apple.iWork.Numbers',
    'com.apple.iWork.Keynote',
    'com.google.GoogleDocs',
    # Notes / PM
    'notion.id',
    'com.apple.Notes',
    'md.obsidian',
    'com.linear',
    'com.figma.Desktop',
    # Dev
    'com.microsoft.VSCode',
    'com.apple.Terminal',
    'com.googlecode.iterm2',
    'com.github.GitHubDesktop',
    # System essentials
    'com.apple.finder',
    'com.apple.iCal',
    'com.apple.systempreferences',
}

# Allowed characters in app names
_APP_NAME_ALLOWED = re.compile(r"^[\w .&'()+-]+$", re.UNICODE)
_APP_NAME_MAX_LEN = 40
_APP_NAME_MAX_COUNT = 50


def _is_user_facing_path(path: str, home_dir: Optional[str]) -> bool:
    """Check if a path is under a user-facing location."""
    if any(path.startswith(root) for root in _PATH_ALLOWLIST):
        return True
    if home_dir:
        user_apps = home_dir.rstrip('/') + '/Applications/'
        if path.startswith(user_apps):
            return True
    return False


def _is_noisy_name(name: str) -> bool:
    """Check if a name matches background service patterns."""
    return any(pattern.search(name) for pattern in _NAME_PATTERN_BLOCKLIST)


def _sanitize_core(raw: List[str], apply_char_filter: bool) -> List[str]:
    """Length cap + trim + dedupe + sort."""
    seen: Set[str] = set()
    result = []

    for name in raw:
        trimmed = name.strip()
        if not trimmed:
            continue
        if len(trimmed) > _APP_NAME_MAX_LEN:
            continue
        if apply_char_filter and not _APP_NAME_ALLOWED.match(trimmed):
            continue
        if trimmed in seen:
            continue
        seen.add(trimmed)
        result.append(trimmed)

    return sorted(result, key=lambda s: s.lower())


def _sanitize_app_names(raw: List[str]) -> List[str]:
    """Sanitize user-installable app names."""
    filtered = _sanitize_core(raw, True)
    if len(filtered) <= _APP_NAME_MAX_COUNT:
        return filtered
    return filtered[:_APP_NAME_MAX_COUNT] + [
        f"… and {len(filtered) - _APP_NAME_MAX_COUNT} more"
    ]


def _sanitize_trusted_names(raw: List[str]) -> List[str]:
    """Sanitize trusted (vendor) app names without char filter."""
    return _sanitize_core(raw, False)


def filter_apps_for_description(
    installed: List[dict],
    home_dir: Optional[str],
) -> List[str]:
    """
    Filter raw Spotlight results to user-facing apps, then sanitize.

    Args:
        installed: List of dicts with 'bundleId', 'displayName', 'path' keys
        home_dir: User's home directory path

    Returns:
        Sorted list of sanitized app display names
    """
    always_kept: List[str] = []
    rest: List[str] = []

    for app in installed:
        bundle_id = app.get('bundleId', '')
        display_name = app.get('displayName', '')
        path = app.get('path', '')

        if bundle_id in _ALWAYS_KEEP_BUNDLE_IDS:
            always_kept.append(display_name)
        elif _is_user_facing_path(path, home_dir) and not _is_noisy_name(display_name):
            rest.append(display_name)

    sanitized_always = _sanitize_trusted_names(always_kept)
    always_set = set(sanitized_always)

    return sanitized_always + [
        name for name in _sanitize_app_names(rest)
        if name not in always_set
    ]
