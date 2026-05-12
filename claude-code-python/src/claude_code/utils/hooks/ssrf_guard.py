"""
SSRF guard for HTTP hooks.

Blocks private, link-local, and other non-routable address ranges to prevent
project-configured HTTP hooks from reaching cloud metadata endpoints
(169.254.169.254) or internal infrastructure.

Loopback (127.0.0.0/8, ::1) is intentionally ALLOWED.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional


def is_blocked_address(address: str) -> bool:
    """Returns True if the address is in a range that HTTP hooks should not reach."""
    try:
        addr = ipaddress.ip_address(address)
    except ValueError:
        return False

    if isinstance(addr, ipaddress.IPv4Address):
        return _is_blocked_v4(addr)
    elif isinstance(addr, ipaddress.IPv6Address):
        return _is_blocked_v6(addr)
    return False


def _is_blocked_v4(addr: ipaddress.IPv4Address) -> bool:
    """Check if IPv4 address is in a blocked range."""
    # Loopback explicitly allowed
    if addr.is_loopback:
        return False

    octets = addr.packed
    a, b = octets[0], octets[1]

    # 0.0.0.0/8
    if a == 0:
        return True
    # 10.0.0.0/8
    if a == 10:
        return True
    # 169.254.0.0/16 — link-local (cloud metadata)
    if a == 169 and b == 254:
        return True
    # 172.16.0.0/12
    if a == 172 and 16 <= b <= 31:
        return True
    # 100.64.0.0/10 — CGNAT
    if a == 100 and 64 <= b <= 127:
        return True
    # 192.168.0.0/16
    if a == 192 and b == 168:
        return True

    return False


def _is_blocked_v6(addr: ipaddress.IPv6Address) -> bool:
    """Check if IPv6 address is in a blocked range."""
    # ::1 loopback explicitly allowed
    if addr.is_loopback:
        return False

    # Unspecified ::
    if addr == ipaddress.IPv6Address("::"):
        return True

    # IPv4-mapped IPv6 (::ffff:x.x.x.x)
    mapped = addr.ipv4_mapped
    if mapped is not None:
        return _is_blocked_v4(mapped)

    # fc00::/7 — unique local addresses
    if addr.is_private and not addr.is_loopback:
        return True

    # fe80::/10 — link-local
    if addr.is_link_local:
        return True

    return False


def ssrf_guarded_lookup(hostname: str) -> Optional[str]:
    """
    Resolve hostname and check if it resolves to a blocked address.
    Returns the resolved IP if safe, raises an error if blocked.
    """
    # Check if hostname is already an IP literal
    try:
        addr = ipaddress.ip_address(hostname)
        if is_blocked_address(str(addr)):
            raise ValueError(
                f"HTTP hook blocked: {hostname} is a private/link-local address. "
                f"Loopback (127.0.0.1, ::1) is allowed for local dev."
            )
        return hostname
    except ValueError as e:
        if "HTTP hook blocked" in str(e):
            raise
        # Not a valid IP literal, proceed with DNS lookup

    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ConnectionError(f"ENOTFOUND {hostname}: {e}") from e

    for res in results:
        address = res[4][0]
        if is_blocked_address(address):
            raise ValueError(
                f"HTTP hook blocked: {hostname} resolves to {address} "
                f"(private/link-local address). Loopback (127.0.0.1, ::1) is allowed for local dev."
            )

    if not results:
        raise ConnectionError(f"ENOTFOUND {hostname}")

    return results[0][4][0]
