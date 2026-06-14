"""Failure classification helpers without live-run dependencies."""

from .result import EvalResult


def is_infra_error(result: EvalResult) -> bool:
    """Return true for transient provider/network errors worth rerunning."""
    if not result.error:
        return False

    error = result.error.lower()
    transient_markers = [
        "remote host terminated",
        "handshake",
        "tls",
        "i/o error",
        "timeout",
        "timed out",
        "429",
        "too many requests",
        "connection reset",
        "connection refused",
        "connection aborted",
        "temporarily unavailable",
        "produced empty code stream",
        "returned empty code stream",
        "empty response from java service",
    ]
    return any(marker in error for marker in transient_markers)
