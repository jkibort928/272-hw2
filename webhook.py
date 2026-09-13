# Author: Jack Kibort
"""
GitHub webhook signature verification.

GitHub signs each delivery with HMAC-SHA256 over the raw request body,
sent as `X-Hub-Signature-256: sha256=<hex digest>`. We must compare using
a constant-time comparison to avoid timing attacks, and we must verify
against the *raw* bytes of the body (not a re-serialized/parsed version),
since re-serialization can change whitespace and break the signature.
"""
import hashlib
import hmac

SUPPORTED_EVENTS = {"issues", "issue_comment", "ping"}


def compute_signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    """
    Returns True iff signature_header is a valid HMAC-SHA256 signature of
    payload computed with secret. Never raises; a malformed header is
    just treated as invalid.
    """
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False

    expected = compute_signature(secret, payload)
    # hmac.compare_digest is constant-time and safe to use for this.
    return hmac.compare_digest(expected, signature_header)


def is_supported_event(event_name: str) -> bool:
    return event_name in SUPPORTED_EVENTS
