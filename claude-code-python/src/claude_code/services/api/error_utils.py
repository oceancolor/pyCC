"""API error utilities. Ported from services/api/errorUtils.ts"""
from __future__ import annotations
from typing import Optional, TypedDict

SSL_ERROR_CODES = {
    "UNABLE_TO_VERIFY_LEAF_SIGNATURE", "UNABLE_TO_GET_ISSUER_CERT",
    "UNABLE_TO_GET_ISSUER_CERT_LOCALLY", "CERT_SIGNATURE_FAILURE",
    "CERT_NOT_YET_VALID", "CERT_HAS_EXPIRED", "CERT_REVOKED",
    "CERT_REJECTED", "CERT_UNTRUSTED", "DEPTH_ZERO_SELF_SIGNED_CERT",
    "SELF_SIGNED_CERT_IN_CHAIN", "CERT_CHAIN_TOO_LONG",
    "PATH_LENGTH_EXCEEDED", "ERR_TLS_CERT_ALTNAME_INVALID",
    "HOSTNAME_MISMATCH", "ERR_TLS_HANDSHAKE_TIMEOUT",
    "ERR_SSL_WRONG_VERSION_NUMBER",
}


class ConnectionErrorDetails(TypedDict):
    code: str
    message: str
    is_ssl_error: bool


def extract_connection_error_details(error: Exception) -> Optional[ConnectionErrorDetails]:
    """Walk error cause chain to find root connection error."""
    current = error
    depth = 0
    while current and depth < 5:
        code = getattr(current, "code", None) or getattr(current, "errno", None)
        if code and isinstance(code, str):
            return {"code": code, "message": str(current), "is_ssl_error": code in SSL_ERROR_CODES}
        cause = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if cause and cause is not current:
            current = cause
            depth += 1
        else:
            break
    return None


def is_ssl_error(error: Exception) -> bool:
    details = extract_connection_error_details(error)
    return details is not None and details["is_ssl_error"]
