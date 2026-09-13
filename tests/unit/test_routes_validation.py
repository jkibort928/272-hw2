# Author: Jack Kibort
"""
Route validation tests. These don't hit real GitHub — they only check that
bad input is rejected with 400 before we'd ever call out to the GitHub
client, and use unittest.mock to stub the client for the happy path.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_OWNER", "test-owner")
os.environ.setdefault("GITHUB_REPO", "test-repo")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("PORT", "8000")

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_create_issue_missing_title_returns_400():
    response = client.post("/issues", json={"body": "no title here"})
    assert response.status_code in (400, 422)


def test_update_issue_invalid_state_returns_400():
    with patch("src.main.github_client.update_issue") as mock_update:
        response = client.patch("/issues/1", json={"state": "not-a-real-state"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "validation_error"


def test_list_issues_invalid_state_returns_400():
    response = client.get("/issues", params={"state": "bogus"})
    assert response.status_code == 400


def test_list_issues_per_page_too_large_returns_400():
    response = client.get("/issues", params={"per_page": 500})
    assert response.status_code == 400


def test_healthz_returns_ok():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_invalid_signature_returns_401():
    response = client.post(
        "/webhook",
        json={"action": "opened"},
        headers={
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "test-delivery-1",
        },
    )
    assert response.status_code == 401


def test_webhook_unsupported_event_returns_400():
    import hmac
    import hashlib

    body = b'{"action": "opened"}'
    secret = os.environ["WEBHOOK_SECRET"]
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "star",
            "X-GitHub-Delivery": "test-delivery-2",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400
