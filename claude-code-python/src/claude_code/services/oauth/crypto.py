"""OAuth crypto utilities. Ported from services/oauth/crypto.ts"""
from __future__ import annotations
import base64, os, hashlib

def generate_code_verifier() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode()

def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
