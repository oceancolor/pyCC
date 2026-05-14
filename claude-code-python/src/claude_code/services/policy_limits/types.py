"""Policy limits types. Ported from services/policyLimits/types.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PolicyRestriction:
    """Per-feature policy restriction."""
    allowed: bool = True


# Dict mapping feature name -> restriction
PolicyRestrictions = Dict[str, PolicyRestriction]


@dataclass
class PolicyLimitsResponse:
    """Response from the policy limits API."""
    restrictions: PolicyRestrictions = field(default_factory=dict)


@dataclass
class PolicyLimitsFetchResult:
    """Result of fetching policy limits from the API."""
    success: bool = False
    restrictions: Optional[PolicyRestrictions] = None  # None = 304 Not Modified
    etag: Optional[str] = None
    error: Optional[str] = None
    skip_retry: bool = False  # True = don't retry (e.g. auth errors)
