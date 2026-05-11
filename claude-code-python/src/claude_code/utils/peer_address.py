"""Peer address parsing. Ported from utils/peerAddress.ts"""
from __future__ import annotations
from typing import Literal, TypedDict


class ParsedAddress(TypedDict):
    scheme: Literal["uds", "bridge", "other"]
    target: str


def parse_address(to: str) -> ParsedAddress:
    """Parse a URI-style address into ``scheme`` + ``target``.

    Schemes:
    - ``uds:`` — Unix Domain Socket path (also matched for bare ``/`` paths
      for backwards-compatibility with legacy senders).
    - ``bridge:`` — Bridge/relay target.
    - ``other`` — Everything else (teammate names, session IDs, …).

    Ported from utils/peerAddress.ts: parseAddress.
    """
    if to.startswith("uds:"):
        return {"scheme": "uds", "target": to[4:]}
    if to.startswith("bridge:"):
        return {"scheme": "bridge", "target": to[7:]}
    # Legacy: bare socket paths from old-code UDS senders
    if to.startswith("/"):
        return {"scheme": "uds", "target": to}
    return {"scheme": "other", "target": to}
