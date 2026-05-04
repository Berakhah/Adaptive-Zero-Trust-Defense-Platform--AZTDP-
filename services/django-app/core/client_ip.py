"""Resolve the real client IP under a trusted-proxy chain.

X-Client-Ip and X-Forwarded-For are honored only if the immediate connection
(REMOTE_ADDR) is inside an explicitly trusted CIDR. Otherwise REMOTE_ADDR wins.
This closes the spoofing surface where any HTTP client could set X-Client-Ip
to bypass IP/geo drift detection.
"""
from __future__ import annotations

import ipaddress
from typing import Iterable, List, Optional, Tuple


def parse_cidrs(raw: str) -> List[ipaddress._BaseNetwork]:
    nets: List[ipaddress._BaseNetwork] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            nets.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            continue
    return nets


def _is_trusted(ip: str, trusted: Iterable[ipaddress._BaseNetwork]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in trusted)


def resolve_client_ip(
    remote_addr: str,
    forwarded_for: Optional[str],
    x_client_ip: Optional[str],
    trusted_proxies: Iterable[ipaddress._BaseNetwork],
) -> Tuple[str, bool]:
    """Return (client_ip, was_forwarded). Falls back to remote_addr if untrusted."""
    if not remote_addr or not _is_trusted(remote_addr, trusted_proxies):
        return remote_addr or "", False

    if x_client_ip:
        candidate = x_client_ip.strip()
        if candidate:
            return candidate, True

    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first, True

    return remote_addr, False


def resolve_geo(
    x_geo: Optional[str],
    remote_addr: str,
    trusted_proxies: Iterable[ipaddress._BaseNetwork],
) -> str:
    """Geo header is only honored when REMOTE_ADDR is trusted; otherwise empty."""
    if not _is_trusted(remote_addr, trusted_proxies):
        return ""
    return (x_geo or "").strip()
