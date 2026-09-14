# Author: Sabari Iyyapan Duraipandian
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import httpx
from src.github_client import (
    GitHubClient,
    parse_link_header,
    map_github_error,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
    RateLimitedError,
)


def test_parse_link_header_with_next_and_last():
    header = (
        '<https://api.github.com/repos/o/r/issues?page=2>; rel="next", '
        '<https://api.github.com/repos/o/r/issues?page=5>; rel="last"'
    )
    info = parse_link_header(header)
    assert info.next == 2
    assert info.last == 5
    assert info.prev is None


def test_parse_link_header_empty():
    info = parse_link_header(None)
    assert info.next is None
    assert info.prev is None
    assert info.first is None
    assert info.last is None


def test_parse_link_header_all_rels():
    header = (
        '<...?page=1>; rel="first", '
        '<...?page=2>; rel="prev", '
        '<...?page=4>; rel="next", '
        '<...?page=5>; rel="last"'
    )
    info = parse_link_header(header)
    assert info.first == 1
    assert info.prev == 2
    assert info.next == 4
    assert info.last == 5


def _make_response(status_code: int, json_body: dict, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_body,
        headers=headers or {},
        request=httpx.Request("GET", "https://api.github.com/repos/o/r/issues"),
    )


def test_map_404_to_not_found():
    resp = _make_response(404, {"message": "Not Found"})
    err = map_github_error(resp)
    assert isinstance(err, NotFoundError)
    assert err.status_code == 404


def test_map_401_to_unauthorized():
    resp = _make_response(401, {"message": "Bad credentials"})
    err = map_github_error(resp)
    assert isinstance(err, UnauthorizedError)


def test_map_422_to_validation_error():
    resp = _make_response(422, {"message": "Validation Failed"})
    err = map_github_error(resp)
    assert isinstance(err, ValidationError)


def test_map_403_rate_limited_to_rate_limited_error():
    resp = _make_response(
        403, {"message": "API rate limit exceeded"},
        headers={"X-RateLimit-Remaining": "0", "Retry-After": "60"},
    )
    err = map_github_error(resp)
    assert isinstance(err, RateLimitedError)
    assert err.retry_after == "60"


def test_map_429_to_rate_limited_error():
    resp = _make_response(429, {"message": "Too many requests"})
    err = map_github_error(resp)
    assert isinstance(err, RateLimitedError)


def _client_with_transport(handler) -> GitHubClient:
    client = GitHubClient(token="test-token", owner="o", repo="r")
    client._client = httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    return client


def test_get_issue_forwards_if_none_match_and_returns_etag():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(
            200, json={"number": 7, "title": "t", "state": "open", "labels": []},
            headers={"ETag": 'W/"abc"'},
        )

    client = _client_with_transport(handler)
    issue, etag, not_modified = client.get_issue(7, if_none_match='W/"old"')

    assert seen_headers.get("if-none-match") == 'W/"old"'
    assert issue["number"] == 7
    assert etag == 'W/"abc"'
    assert not_modified is False


def test_get_issue_maps_304_to_not_modified():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, headers={"ETag": 'W/"abc"'})

    client = _client_with_transport(handler)
    issue, etag, not_modified = client.get_issue(7, if_none_match='W/"abc"')

    assert issue is None
    assert etag == 'W/"abc"'
    assert not_modified is True


def test_get_issue_without_if_none_match_sends_no_header():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(
            200, json={"number": 1, "title": "t", "state": "open", "labels": []},
        )

    client = _client_with_transport(handler)
    client.get_issue(1)

    assert "if-none-match" not in seen_headers
