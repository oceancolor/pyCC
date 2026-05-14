"""OAuth crypto utilities. Ported from services/oauth/crypto.ts"""
from __future__ import annotations
import base64
import hashlib
import os


def _base64_url_encode(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_code_verifier() -> str:
    """Generate a PKCE code verifier (32 random bytes, base64url-encoded)."""
    return _base64_url_encode(os.urandom(32))


def generate_code_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge (SHA-256 hash of verifier, base64url-encoded)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _base64_url_encode(digest)


def generate_state() -> str:
    """Generate a random OAuth state parameter (32 random bytes, base64url-encoded)."""
    return _base64_url_encode(os.urandom(32))
