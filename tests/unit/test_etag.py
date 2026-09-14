# Author: Sabari Iyyapan Duraipandian
"""
Conditional GET / ETag tests for GET /issues/{number}. These mock the
GitHub client directly, so no network call happens - they only check that
main.py wires the client's (issue, etag, not_modified) tuple into the right
HTTP response shape.
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


def test_get_issue_returns_etag_header():
    fake_issue = {
        "number": 7,
        "title": "t",
        "body": None,
        "state": "open",
        "labels": [],
        "html_url": "https://github.com/o/r/issues/7",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    with patch("src.main.github_client.get_issue",
               return_value=(fake_issue, 'W/"abc123"', False)) as mock_get:
        response = client.get("/issues/7")

    assert response.status_code == 200
    assert response.headers["ETag"] == 'W/"abc123"'
    assert response.json()["number"] == 7
    mock_get.assert_called_once_with(7, if_none_match=None)


def test_get_issue_forwards_if_none_match_header():
    fake_issue = {"number": 7, "title": "t", "state": "open", "labels": []}
    with patch("src.main.github_client.get_issue",
               return_value=(fake_issue, 'W/"abc123"', False)) as mock_get:
        client.get("/issues/7", headers={"If-None-Match": 'W/"abc123"'})

    mock_get.assert_called_once_with(7, if_none_match='W/"abc123"')


def test_get_issue_conditional_returns_304_with_empty_body():
    with patch("src.main.github_client.get_issue",
               return_value=(None, 'W/"abc123"', True)):
        response = client.get("/issues/7", headers={"If-None-Match": 'W/"abc123"'})

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["ETag"] == 'W/"abc123"'
