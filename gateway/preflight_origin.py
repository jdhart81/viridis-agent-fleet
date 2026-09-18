"""Select one fixed, owned origin; this marker never grants authority."""

SECURITY_BASE = "https://mcp.viridis-security.com"
ORIGIN_HEADER = "x-viridis-security-origin"


def service_origin(agent, fallback):
    """Canonical Security discovery; preserve isolated test/rehearsal origins."""
    if agent in {"maxwell-defense", "security-preflight"} and fallback.rstrip("/") == "https://mcp.viridisconservation.com":
        return SECURITY_BASE
    return fallback.rstrip("/")


def request_origin(request, fallback, agent="security-preflight"):
    """Keep legacy quotes intact and bind Security-front-door quotes exactly.

    Any caller can select this public alias. It changes only the advertised
    address, never identity, prices, entitlements, signatures, or permissions.
    Arbitrary Host and Forwarded headers are deliberately ignored.
    """
    if (agent in {"security-preflight", "maxwell-defense"}
            and request.headers.get(ORIGIN_HEADER) == SECURITY_BASE):
        return SECURITY_BASE
    return fallback.rstrip("/")
