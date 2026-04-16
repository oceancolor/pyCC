"""
mTLS (mutual TLS) certificate configuration loader.

Mirrors mtls.ts: reads cert/key/CA paths from environment variables and
returns a typed configuration dataclass.  No external dependencies required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


# ---------------------------------------------------------------------------
# Environment variable names (mirrors TS constants)
# ---------------------------------------------------------------------------

_ENV_CLIENT_CERT = "CLAUDE_CODE_CLIENT_CERT"
_ENV_CLIENT_KEY = "CLAUDE_CODE_CLIENT_KEY"
_ENV_CLIENT_KEY_PASSPHRASE = "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE"
_ENV_CA_CERT = "CLAUDE_CODE_CA_CERT"          # extra CA bundle (optional)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class MtlsConfig:
    """Paths and passphrase for mutual-TLS authentication.

    Attributes:
        cert_path:   Path to the PEM-encoded client certificate file.
        key_path:    Path to the PEM-encoded client private key file.
        ca_path:     Optional path to a PEM-encoded CA certificate bundle.
        passphrase:  Optional passphrase for an encrypted private key.
    """

    cert_path: str
    key_path: str
    ca_path: Optional[str] = None
    passphrase: Optional[str] = None

    def read_cert(self) -> str:
        """Return the PEM text of the client certificate."""
        return _read_file(self.cert_path)

    def read_key(self) -> str:
        """Return the PEM text of the client private key."""
        return _read_file(self.key_path)

    def read_ca(self) -> Optional[str]:
        """Return the PEM text of the CA bundle, or None if not set."""
        if self.ca_path is None:
            return None
        return _read_file(self.ca_path)

    def to_ssl_context_kwargs(self) -> dict:
        """Return keyword arguments suitable for :func:`ssl.SSLContext.load_cert_chain`
        and :func:`ssl.SSLContext.load_verify_locations`.

        Example::

            import ssl
            ctx = ssl.create_default_context()
            kwargs = config.to_ssl_context_kwargs()
            ctx.load_cert_chain(
                certfile=kwargs["certfile"],
                keyfile=kwargs["keyfile"],
                password=kwargs.get("password"),
            )
            if kwargs.get("cafile"):
                ctx.load_verify_locations(cafile=kwargs["cafile"])
        """
        result: dict = {
            "certfile": self.cert_path,
            "keyfile": self.key_path,
        }
        if self.passphrase:
            result["password"] = self.passphrase
        if self.ca_path:
            result["cafile"] = self.ca_path
        return result


# ---------------------------------------------------------------------------
# Factory / loader
# ---------------------------------------------------------------------------

def load_mtls_config() -> Optional[MtlsConfig]:
    """Load mTLS configuration from environment variables.

    Required variables:
    - ``CLAUDE_CODE_CLIENT_CERT`` — path to the client certificate.
    - ``CLAUDE_CODE_CLIENT_KEY``  — path to the client private key.

    Optional variables:
    - ``CLAUDE_CODE_CA_CERT``              — path to a CA bundle.
    - ``CLAUDE_CODE_CLIENT_KEY_PASSPHRASE`` — passphrase for the private key.

    Returns:
        A :class:`MtlsConfig` instance when both required variables are set,
        otherwise ``None``.
    """
    cert_path = os.environ.get(_ENV_CLIENT_CERT)
    key_path = os.environ.get(_ENV_CLIENT_KEY)

    if not cert_path or not key_path:
        return None

    return MtlsConfig(
        cert_path=cert_path,
        key_path=key_path,
        ca_path=os.environ.get(_ENV_CA_CERT),
        passphrase=os.environ.get(_ENV_CLIENT_KEY_PASSPHRASE),
    )


@lru_cache(maxsize=1)
def get_mtls_config_cached() -> Optional[MtlsConfig]:
    """Memoized version of :func:`load_mtls_config`.

    Cached for the lifetime of the process.  Call
    :func:`clear_mtls_cache` to force a reload (e.g. in tests).
    """
    return load_mtls_config()


def clear_mtls_cache() -> None:
    """Clear the memoization cache so the next call reloads from env."""
    get_mtls_config_cached.cache_clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()
