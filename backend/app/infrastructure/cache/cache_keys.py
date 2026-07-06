"""Redis key namespacing — every key in the instance goes through here.

Scheme: `app:{namespace}:{part}:{part}...` — the fixed `app:` prefix isolates
this application; the namespace isolates subsystems (rl = rate limiting,
future: cache, locks) so they can never collide.
"""

KEY_PREFIX = "app"
SEPARATOR = ":"

NAMESPACE_RATE_LIMIT = "rl"


def cache_key(namespace: str, *parts: str) -> str:
    """`app:{namespace}:{parts...}` — parts must not contain the separator."""
    cleaned = [part.replace(SEPARATOR, "_") for part in parts]
    return SEPARATOR.join([KEY_PREFIX, namespace, *cleaned])
