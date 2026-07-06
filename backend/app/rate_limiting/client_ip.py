"""Client IP resolution with explicit proxy trust. Pure (no FastAPI).

X-Forwarded-For is attacker-controlled unless the immediate peer is a
configured trusted proxy. Resolution walks the XFF chain from the right,
skipping trusted hops, and returns the first untrusted address — never the
blindly-taken leftmost entry.
"""

import ipaddress

_UNKNOWN = "unknown"


def parse_trusted_proxies(raw: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Comma-separated IPs/CIDRs -> networks; invalid entries are rejected loudly."""
    networks = []
    for entry in (part.strip() for part in raw.split(",")):
        if entry:
            networks.append(ipaddress.ip_network(entry, strict=False))
    return tuple(networks)


def _is_trusted(
    address: str, trusted: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in trusted)


def resolve_client_ip(
    peer_ip: str | None,
    forwarded_for: str | None,
    trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> str:
    """The address rate limiting should key on.

    - No trusted proxies configured, or the peer is not one of them: the
      socket peer address wins; XFF is ignored (it is forgeable).
    - Peer is trusted: walk XFF right-to-left, skip trusted hops, return the
      first untrusted address (the real client as seen by our edge).
    """
    if peer_ip is None:
        return _UNKNOWN
    if not trusted_proxies or not _is_trusted(peer_ip, trusted_proxies) or not forwarded_for:
        return peer_ip

    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop, trusted_proxies):
            return hop
    # Every hop was a trusted proxy: fall back to the leftmost entry.
    return hops[0] if hops else peer_ip
