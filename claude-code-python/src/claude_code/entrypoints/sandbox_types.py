"""
Sandbox types for the Claude Code Agent SDK.

This file is the single source of truth for sandbox configuration types.
Both the SDK and the settings validation import from here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ============================================================================
# Schema dicts (mirrors Zod schemas as metadata/descriptions)
# ============================================================================

SandboxNetworkConfigSchema: Dict[str, Any] = {
    "type": "object",
    "optional": True,
    "properties": {
        "allowedDomains": {"type": "array", "items": {"type": "string"}, "optional": True},
        "allowManagedDomainsOnly": {
            "type": "boolean",
            "optional": True,
            "description": (
                "When true (and set in managed settings), only allowedDomains and "
                "WebFetch(domain:...) allow rules from managed settings are respected. "
                "User, project, local, and flag settings domains are ignored. "
                "Denied domains are still respected from all sources."
            ),
        },
        "allowUnixSockets": {
            "type": "array",
            "items": {"type": "string"},
            "optional": True,
            "description": "macOS only: Unix socket paths to allow. Ignored on Linux (seccomp cannot filter by path).",
        },
        "allowAllUnixSockets": {
            "type": "boolean",
            "optional": True,
            "description": "If true, allow all Unix sockets (disables blocking on both platforms).",
        },
        "allowLocalBinding": {"type": "boolean", "optional": True},
        "httpProxyPort": {"type": "number", "optional": True},
        "socksProxyPort": {"type": "number", "optional": True},
    },
}

SandboxFilesystemConfigSchema: Dict[str, Any] = {
    "type": "object",
    "optional": True,
    "properties": {
        "allowWrite": {
            "type": "array",
            "items": {"type": "string"},
            "optional": True,
            "description": (
                "Additional paths to allow writing within the sandbox. "
                "Merged with paths from Edit(...) allow permission rules."
            ),
        },
        "denyWrite": {
            "type": "array",
            "items": {"type": "string"},
            "optional": True,
            "description": (
                "Additional paths to deny writing within the sandbox. "
                "Merged with paths from Edit(...) deny permission rules."
            ),
        },
        "denyRead": {
            "type": "array",
            "items": {"type": "string"},
            "optional": True,
            "description": (
                "Additional paths to deny reading within the sandbox. "
                "Merged with paths from Read(...) deny permission rules."
            ),
        },
        "allowRead": {
            "type": "array",
            "items": {"type": "string"},
            "optional": True,
            "description": (
                "Paths to re-allow reading within denyRead regions. "
                "Takes precedence over denyRead for matching paths."
            ),
        },
        "allowManagedReadPathsOnly": {
            "type": "boolean",
            "optional": True,
            "description": "When true (set in managed settings), only allowRead paths from policySettings are used.",
        },
    },
}

SandboxSettingsSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean", "optional": True},
        "failIfUnavailable": {
            "type": "boolean",
            "optional": True,
            "description": (
                "Exit with an error at startup if sandbox.enabled is true but the sandbox cannot start "
                "(missing dependencies, unsupported platform, or platform not in enabledPlatforms). "
                "When false (default), a warning is shown and commands run unsandboxed. "
                "Intended for managed-settings deployments that require sandboxing as a hard gate."
            ),
        },
        "autoAllowBashIfSandboxed": {"type": "boolean", "optional": True},
        "allowUnsandboxedCommands": {
            "type": "boolean",
            "optional": True,
            "description": (
                "Allow commands to run outside the sandbox via the dangerouslyDisableSandbox parameter. "
                "When false, the dangerouslyDisableSandbox parameter is completely ignored and all commands must run sandboxed. "
                "Default: true."
            ),
        },
        "network": SandboxNetworkConfigSchema,
        "filesystem": SandboxFilesystemConfigSchema,
        "ignoreViolations": {"type": "record", "key": "string", "value": {"type": "array", "items": {"type": "string"}}, "optional": True},
        "enableWeakerNestedSandbox": {"type": "boolean", "optional": True},
        "enableWeakerNetworkIsolation": {
            "type": "boolean",
            "optional": True,
            "description": (
                "macOS only: Allow access to com.apple.trustd.agent in the sandbox. "
                "Needed for Go-based CLI tools (gh, gcloud, terraform, etc.) to verify TLS certificates "
                "when using httpProxyPort with a MITM proxy and custom CA. "
                "**Reduces security** — opens a potential data exfiltration vector through the trustd service. Default: false"
            ),
        },
        "excludedCommands": {"type": "array", "items": {"type": "string"}, "optional": True},
        "ripgrep": {
            "type": "object",
            "optional": True,
            "description": "Custom ripgrep configuration for bundled ripgrep support",
            "properties": {
                "command": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}, "optional": True},
            },
        },
    },
    "additionalProperties": True,  # passthrough
}


# ============================================================================
# TypedDict / type aliases (inferred from schemas)
# ============================================================================

from typing import TypedDict


class SandboxNetworkConfig(TypedDict, total=False):
    allowedDomains: List[str]
    allowManagedDomainsOnly: bool
    allowUnixSockets: List[str]
    allowAllUnixSockets: bool
    allowLocalBinding: bool
    httpProxyPort: int
    socksProxyPort: int


class SandboxFilesystemConfig(TypedDict, total=False):
    allowWrite: List[str]
    denyWrite: List[str]
    denyRead: List[str]
    allowRead: List[str]
    allowManagedReadPathsOnly: bool


class _RipgrepConfig(TypedDict, total=False):
    command: str
    args: List[str]


class SandboxSettings(TypedDict, total=False):
    enabled: bool
    failIfUnavailable: bool
    autoAllowBashIfSandboxed: bool
    allowUnsandboxedCommands: bool
    network: Optional[SandboxNetworkConfig]
    filesystem: Optional[SandboxFilesystemConfig]
    ignoreViolations: Dict[str, List[str]]
    enableWeakerNestedSandbox: bool
    enableWeakerNetworkIsolation: bool
    excludedCommands: List[str]
    ripgrep: Optional[_RipgrepConfig]


# SandboxIgnoreViolations is the non-None type of SandboxSettings['ignoreViolations']
SandboxIgnoreViolations = Dict[str, List[str]]
