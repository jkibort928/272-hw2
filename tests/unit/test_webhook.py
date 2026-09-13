# Author: Jack Kibort
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.webhook import compute_signature, verify_signature, is_supported_event

SECRET = "test-secret"


def test_valid_signature_passes():
    body = b'{"action": "opened"}'
    sig = compute_signature(SECRET, body)
    assert verify_signature(SECRET, body, sig) is True


def test_tampered_body_fails():
    body = b'{"action": "opened"}'
    sig = compute_signature(SECRET, body)
    tampered_body = b'{"action": "closed"}'
    assert verify_signature(SECRET, tampered_body, sig) is False


def test_missing_signature_header_fails():
    body = b'{"action": "opened"}'
    assert verify_signature(SECRET, body, None) is False


def test_wrong_secret_fails():
    body = b'{"action": "opened"}'
    sig = compute_signature("wrong-secret", body)
    assert verify_signature(SECRET, body, sig) is False


def test_malformed_header_fails():
    body = b'{"action": "opened"}'
    assert verify_signature(SECRET, body, "not-a-real-signature") is False


def test_supported_events():
    assert is_supported_event("issues") is True
    assert is_supported_event("issue_comment") is True
    assert is_supported_event("ping") is True
    assert is_supported_event("star") is False
