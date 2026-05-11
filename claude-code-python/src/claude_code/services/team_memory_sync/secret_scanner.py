"""
team_memory_sync/secret_scanner.py — Client-side secret scanner for team memory.
Ported from services/teamMemorySync/secretScanner.ts (324 lines).

Scans content for credentials before upload so secrets never leave the user's
machine. Uses a curated subset of high-confidence rules from gitleaks
(https://github.com/gitleaks/gitleaks, MIT license) — only rules with
distinctive prefixes that have near-zero false-positive rates are included.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class SecretMatch:
    """
    Gitleaks rule ID that matched (e.g., "github-pat", "aws-access-token").
    label: Human-readable label derived from the rule ID.
    The actual matched text is intentionally NOT returned.
    """
    rule_id: str
    label: str


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

# Anthropic API key prefix, assembled at runtime so the literal byte
# sequence isn't present in the bundle (excluded-strings check).
_ANT_KEY_PFX = "-".join(["sk", "ant", "api"])

_SECRET_RULES: List[dict] = [
    # — Cloud providers —
    {
        "id": "aws-access-token",
        "source": r"\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b",
    },
    {
        "id": "gcp-api-key",
        "source": r"\b(AIza[\w-]{35})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "azure-ad-client-secret",
        "source": r"(?:^|[\\'\"\x60\s>=:(,)])([a-zA-Z0-9_~.]{3}\dQ~[a-zA-Z0-9_~.-]{31,34})(?:$|[\\'\"\x60\s<),])",
    },
    {
        "id": "digitalocean-pat",
        "source": r"\b(dop_v1_[a-f0-9]{64})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "digitalocean-access-token",
        "source": r"\b(doo_v1_[a-f0-9]{64})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },

    # — AI APIs —
    {
        "id": "anthropic-api-key",
        "source": r"\b(" + _ANT_KEY_PFX + r"03-[a-zA-Z0-9_\-]{93}AA)(?:[\x60'\"\s;]|\\[nr]|$)",
    },
    {
        "id": "anthropic-admin-api-key",
        "source": r"\b(sk-ant-admin01-[a-zA-Z0-9_\-]{93}AA)(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "openai-api-key",
        "source": (
            r"\b(sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})"
            r"T3BlbkFJ(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})\b"
            r"|sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20})"
            r"(?:[\x60'\"\\s;]|\\[nr]|$)"
        ),
    },
    {
        "id": "huggingface-access-token",
        "source": r"\b(hf_[a-zA-Z]{34})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },

    # — Version control —
    {
        "id": "github-pat",
        "source": r"ghp_[0-9a-zA-Z]{36}",
    },
    {
        "id": "github-fine-grained-pat",
        "source": r"github_pat_\w{82}",
    },
    {
        "id": "github-app-token",
        "source": r"(?:ghu|ghs)_[0-9a-zA-Z]{36}",
    },
    {
        "id": "github-oauth",
        "source": r"gho_[0-9a-zA-Z]{36}",
    },
    {
        "id": "github-refresh-token",
        "source": r"ghr_[0-9a-zA-Z]{36}",
    },
    {
        "id": "gitlab-pat",
        "source": r"glpat-[\w-]{20}",
    },
    {
        "id": "gitlab-deploy-token",
        "source": r"gldt-[0-9a-zA-Z_\-]{20}",
    },

    # — Communication —
    {
        "id": "slack-bot-token",
        "source": r"xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*",
    },
    {
        "id": "slack-user-token",
        "source": r"xox[pe](?:-[0-9]{10,13}){3}-[a-zA-Z0-9-]{28,34}",
    },
    {
        "id": "slack-app-token",
        "source": r"xapp-\d-[A-Z0-9]+-\d+-[a-z0-9]+",
        "flags": re.IGNORECASE,
    },
    {
        "id": "twilio-api-key",
        "source": r"SK[0-9a-fA-F]{32}",
    },
    {
        "id": "sendgrid-api-token",
        "source": r"\b(SG\.[a-zA-Z0-9=_\-.]{66})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },

    # — Dev tooling —
    {
        "id": "npm-access-token",
        "source": r"\b(npm_[a-zA-Z0-9]{36})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "pypi-upload-token",
        "source": r"pypi-AgEIcHlwaS5vcmc[\w-]{50,1000}",
    },
    {
        "id": "databricks-api-token",
        "source": r"\b(dapi[a-f0-9]{32}(?:-\d)?)(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "hashicorp-tf-api-token",
        "source": r"[a-zA-Z0-9]{14}\.atlasv1\.[a-zA-Z0-9\-_=]{60,70}",
    },
    {
        "id": "pulumi-api-token",
        "source": r"\b(pul-[a-f0-9]{40})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "postman-api-token",
        "source": r"\b(PMAK-[a-fA-F0-9]{24}-[a-fA-F0-9]{34})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },

    # — Observability —
    {
        "id": "grafana-api-key",
        "source": r"\b(eyJrIjoi[A-Za-z0-9+/]{70,400}={0,3})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "grafana-cloud-api-token",
        "source": r"\b(glc_[A-Za-z0-9+/]{32,400}={0,3})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "grafana-service-account-token",
        "source": r"\b(glsa_[A-Za-z0-9]{32}_[A-Fa-f0-9]{8})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "sentry-user-token",
        "source": r"\b(sntryu_[a-f0-9]{64})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "sentry-org-token",
        "source": (
            r"\bsntrys_eyJpYXQiO[a-zA-Z0-9+/]{10,200}"
            r"(?:LCJyZWdpb25fdXJs|InJlZ2lvbl91cmwi|cmVnaW9uX3VybCI6)"
            r"[a-zA-Z0-9+/]{10,200}={0,2}_[a-zA-Z0-9+/]{43}"
        ),
    },

    # — Payment / commerce —
    {
        "id": "stripe-access-token",
        "source": r"\b((?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99})(?:[\x60'\"\\s;]|\\[nr]|$)",
    },
    {
        "id": "shopify-access-token",
        "source": r"shpat_[a-fA-F0-9]{32}",
    },
    {
        "id": "shopify-shared-secret",
        "source": r"shpss_[a-fA-F0-9]{32}",
    },

    # — Crypto —
    {
        "id": "private-key",
        "source": (
            r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----[\s\S-]{64,}?"
            r"-----END[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----"
        ),
        "flags": re.IGNORECASE,
    },
]

# Lazily compiled pattern cache
_compiled_rules: Optional[List[dict]] = None


def _get_compiled_rules() -> List[dict]:
    """Compile rules lazily on first call."""
    global _compiled_rules
    if _compiled_rules is None:
        _compiled_rules = []
        for rule in _SECRET_RULES:
            flags = rule.get("flags", 0)
            if isinstance(flags, str):
                flags = re.IGNORECASE if "i" in flags else 0
            _compiled_rules.append({
                "id": rule["id"],
                "re": re.compile(rule["source"], flags | re.DOTALL),
            })
    return _compiled_rules


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

_SPECIAL_CASE: dict = {
    "aws": "AWS",
    "gcp": "GCP",
    "api": "API",
    "pat": "PAT",
    "ad": "AD",
    "tf": "TF",
    "oauth": "OAuth",
    "npm": "NPM",
    "pypi": "PyPI",
    "jwt": "JWT",
    "github": "GitHub",
    "gitlab": "GitLab",
    "openai": "OpenAI",
    "digitalocean": "DigitalOcean",
    "huggingface": "HuggingFace",
    "hashicorp": "HashiCorp",
    "sendgrid": "SendGrid",
}


def _rule_id_to_label(rule_id: str) -> str:
    """
    Convert a gitleaks rule ID (kebab-case) to a human-readable label.
    e.g., "github-pat" → "GitHub PAT", "aws-access-token" → "AWS Access Token"
    """
    return " ".join(
        _SPECIAL_CASE.get(part, part.capitalize())
        for part in rule_id.split("-")
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_for_secrets(content: str) -> List[SecretMatch]:
    """
    Scan a string for potential secrets.

    Returns one match per rule that fired (deduplicated by rule ID). The
    actual matched text is intentionally NOT returned — we never log or
    display secret values.
    """
    matches: List[SecretMatch] = []
    seen: set = set()

    for rule in _get_compiled_rules():
        rule_id = rule["id"]
        if rule_id in seen:
            continue
        if rule["re"].search(content):
            seen.add(rule_id)
            matches.append(SecretMatch(
                rule_id=rule_id,
                label=_rule_id_to_label(rule_id),
            ))

    return matches


def get_secret_label(rule_id: str) -> str:
    """
    Get a human-readable label for a gitleaks rule ID.
    Falls back to kebab-to-Title conversion for unknown IDs.
    """
    return _rule_id_to_label(rule_id)


# Lazily compiled redaction patterns (with global flag equivalent in Python)
_redact_rules: Optional[List[re.Pattern]] = None


def redact_secrets(content: str) -> str:
    """
    Redact any matched secrets in-place with [REDACTED].
    Unlike scan_for_secrets, this returns the content with spans replaced
    so the surrounding text can still be written to disk safely.
    """
    global _redact_rules
    if _redact_rules is None:
        _redact_rules = []
        for rule in _SECRET_RULES:
            flags = rule.get("flags", 0)
            if isinstance(flags, str):
                flags = re.IGNORECASE if "i" in flags else 0
            # Add DOTALL to match newlines in private-key patterns
            _redact_rules.append(re.compile(rule["source"], flags | re.DOTALL))

    for pattern in _redact_rules:
        def _replace_group(m: re.Match) -> str:
            groups = m.groups()
            if groups and isinstance(groups[0], str):
                # Replace only the captured group, not boundary chars
                full = m.group(0)
                captured = groups[0]
                idx = full.find(captured)
                if idx >= 0:
                    return full[:idx] + "[REDACTED]" + full[idx + len(captured):]
            return "[REDACTED]"

        content = pattern.sub(_replace_group, content)

    return content
