# Author: Arthi Chandra Sekar
"""
Thin wrapper around the GitHub REST API for Issues on a single repo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

GITHUB_API_BASE = "https://api.github.com"
ACCEPT_HEADER = "application/vnd.github+json"


class GitHubError(Exception):
    def __init__(self, status_code: int, error: str, message: str):
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


class NotFoundError(GitHubError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(404, "not_found", message)


class UnauthorizedError(GitHubError):
    def __init__(self, message: str = "GitHub token missing or invalid"):
        super().__init__(401, "unauthorized", message)


class ValidationError(GitHubError):
    def __init__(self, message: str = "Invalid request"):
        super().__init__(400, "validation_error", message)


class RateLimitedError(GitHubError):
    def __init__(self, retry_after: Optional[str] = None):
        message = "GitHub API rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(503, "rate_limited", message)
        self.retry_after = retry_after


@dataclass
class PageInfo:
    next: Optional[int] = None
    prev: Optional[int] = None
    first: Optional[int] = None
    last: Optional[int] = None


_LINK_ENTRY_RE = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')
_PAGE_PARAM_RE = re.compile(r"[?&]page=(\d+)")


def parse_link_header(link_header: Optional[str]) -> PageInfo:
    info = PageInfo()
    if not link_header:
        return info
    for url, rel in _LINK_ENTRY_RE.findall(link_header):
        page_match = _PAGE_PARAM_RE.search(url)
        if not page_match:
            continue
        page_num = int(page_match.group(1))
        if rel == "next":
            info.next = page_num
        elif rel == "prev":
            info.prev = page_num
        elif rel == "first":
            info.first = page_num
        elif rel == "last":
            info.last = page_num
    return info


def map_github_error(response: httpx.Response) -> GitHubError:
    status = response.status_code
    try:
        body = response.json()
        message = body.get("message", "Unknown GitHub error")
    except Exception:
        message = response.text or "Unknown GitHub error"

    if status == 401:
        return UnauthorizedError(message)
    if status == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        return RateLimitedError(response.headers.get("Retry-After"))
    if status == 404:
        return NotFoundError(message)
    if status == 422:
        return ValidationError(message)
    if status == 429:
        return RateLimitedError(response.headers.get("Retry-After"))
    return GitHubError(status, "github_error", message)


class GitHubClient:
    def __init__(self, token: str, owner: str, repo: str, base_url: str = GITHUB_API_BASE):
        self._owner = owner
        self._repo = repo
        self._base_url = base_url
        self._client = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": ACCEPT_HEADER,
            },
            timeout=10.0,
        )

    def close(self) -> None:
        self._client.close()

    def _repo_path(self, suffix: str = "") -> str:
        return f"/repos/{self._owner}/{self._repo}{suffix}"

    def _check_and_raise(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise map_github_error(response)

    def create_issue(self, title: str, body: Optional[str] = None,
                      labels: Optional[list[str]] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title}
        if body is not None:
            payload["body"] = body
        if labels is not None:
            payload["labels"] = labels

        response = self._client.post(self._repo_path("/issues"), json=payload)
        self._check_and_raise(response)
        return response.json()

    def list_issues(self, state: str = "open", labels: Optional[str] = None,
                     page: int = 1, per_page: int = 30,
                     if_none_match: Optional[str] = None
                     ) -> tuple[Optional[list[dict[str, Any]]], PageInfo, Optional[str], bool]:
        """
        Returns (issues_or_None, page_info, etag, not_modified).
        """
        params: dict[str, Any] = {"state": state, "page": page, "per_page": per_page}
        if labels:
            params["labels"] = labels

        headers = {}
        if if_none_match:
            headers["If-None-Match"] = if_none_match

        response = self._client.get(self._repo_path("/issues"), params=params, headers=headers)

        if response.status_code == 304:
            return None, PageInfo(), response.headers.get("ETag"), True

        self._check_and_raise(response)
        page_info = parse_link_header(response.headers.get("Link"))
        etag = response.headers.get("ETag")
        return response.json(), page_info, etag, False

    def get_issue(self, number: int, if_none_match: Optional[str] = None
                  ) -> tuple[Optional[dict[str, Any]], Optional[str], bool]:
        """
        Returns (issue_or_None, etag, not_modified). Mirrors list_issues'
        conditional-GET handling (payload, etag, not_modified ordering),
        minus PageInfo since a single issue has no pagination.
        """
        headers = {}
        if if_none_match:
            headers["If-None-Match"] = if_none_match

        response = self._client.get(self._repo_path(f"/issues/{number}"), headers=headers)

        if response.status_code == 304:
            return None, response.headers.get("ETag"), True

        self._check_and_raise(response)
        return response.json(), response.headers.get("ETag"), False

    def update_issue(self, number: int, title: Optional[str] = None,
                      body: Optional[str] = None, state: Optional[str] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state

        response = self._client.patch(self._repo_path(f"/issues/{number}"), json=payload)
        self._check_and_raise(response)
        return response.json()

    def create_comment(self, number: int, body: str) -> dict[str, Any]:
        response = self._client.post(
            self._repo_path(f"/issues/{number}/comments"), json={"body": body}
        )
        self._check_and_raise(response)
        return response.json()
