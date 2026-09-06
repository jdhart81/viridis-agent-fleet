"""Select one fixed, owned origin; this marker never grants authority."""

SECURITY_BASE = "https://mcp.viridis-security.com"
ORIGIN_HEADER = "x-viridis-security-origin"


def request_origin(request, fallback, agent="security-preflight"):
    """Keep legacy quotes intact and bind Security-front-door quotes exactly.

    Any caller can select this public alias. It changes only the advertised
    address, never identity, prices, entitlements, signatures, or permissions.
    Arbitrary Host and Forwarded headers are deliberately ignored.
    """
    if (agent == "security-preflight"
            and request.headers.get(ORIGIN_HEADER) == SECURITY_BASE):
        return SECURITY_BASE
    return fallback.rstrip("/")
