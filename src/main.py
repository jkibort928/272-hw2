# Author: Jack Kibort and Arthi Chandra Sekar
"""
FastAPI app implementing the routes described in openapi.yaml.
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .config import get_settings
from .github_client import GitHubClient, GitHubError
from .store import EventStore
from .webhook import is_supported_event, verify_signature

app = FastAPI(title="GitHub Issues Gateway Service")

settings = get_settings()
github_client = GitHubClient(
    token=settings.github_token,
    owner=settings.github_owner,
    repo=settings.github_repo,
)
event_store = EventStore()


class IssueCreate(BaseModel):
    title: str = Field(min_length=1)
    body: Optional[str] = None
    labels: Optional[list[str]] = None


class IssueUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    state: Optional[str] = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


def error_body(error: str, message: str) -> dict:
    return {"error": error, "message": message}


def github_error_to_http(exc: GitHubError) -> HTTPException:
    return HTTPException(status_code=exc.status_code,
                          detail=error_body(exc.error, exc.message))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/issues", status_code=201)
def create_issue(payload: IssueCreate, response: Response):
    try:
        issue = github_client.create_issue(
            title=payload.title, body=payload.body, labels=payload.labels
        )
    except GitHubError as exc:
        raise github_error_to_http(exc)

    response.headers["Location"] = f"/issues/{issue['number']}"
    return _serialize_issue(issue)


@app.get("/issues")
def list_issues(response: Response, state: str = "open",
                 labels: Optional[str] = None, page: int = 1, per_page: int = 30,
                 if_none_match: Optional[str] = Header(default=None, alias="If-None-Match")):
    if state not in ("open", "closed", "all"):
        raise HTTPException(400, detail=error_body(
            "validation_error", "state must be one of open, closed, all"))
    if per_page > 100:
        raise HTTPException(400, detail=error_body(
            "validation_error", "per_page must be <= 100"))

    try:
        issues, page_info, etag, not_modified = github_client.list_issues(
            state=state, labels=labels, page=page, per_page=per_page,
            if_none_match=if_none_match,
        )
    except GitHubError as exc:
        raise github_error_to_http(exc)

    if etag:
        response.headers["ETag"] = etag

    if not_modified:
        return Response(status_code=304, headers=dict(response.headers))

    link_parts = []
    if page_info.next:
        link_parts.append(f'<{page_info.next}>; rel="next"')
    if page_info.prev:
        link_parts.append(f'<{page_info.prev}>; rel="prev"')
    if page_info.last:
        link_parts.append(f'<{page_info.last}>; rel="last"')
    if link_parts:
        response.headers["Link"] = ", ".join(link_parts)

    return [_serialize_issue(i) for i in issues]


@app.get("/issues/{number}")
def get_issue(number: int):
    try:
        issue = github_client.get_issue(number)
    except GitHubError as exc:
        raise github_error_to_http(exc)
    return _serialize_issue(issue)


@app.patch("/issues/{number}")
def update_issue(number: int, payload: IssueUpdate):
    if payload.state is not None and payload.state not in ("open", "closed"):
        raise HTTPException(400, detail=error_body(
            "validation_error", "state must be 'open' or 'closed'"))

    try:
        issue = github_client.update_issue(
            number, title=payload.title, body=payload.body, state=payload.state
        )
    except GitHubError as exc:
        raise github_error_to_http(exc)
    return _serialize_issue(issue)


@app.post("/issues/{number}/comments", status_code=201)
def create_comment(number: int, payload: CommentCreate):
    try:
        comment = github_client.create_comment(number, payload.body)
    except GitHubError as exc:
        raise github_error_to_http(exc)

    return {
        "id": comment["id"],
        "body": comment["body"],
        "user": comment.get("user", {}).get("login"),
        "created_at": comment["created_at"],
        "html_url": comment["html_url"],
    }


@app.post("/webhook", status_code=204)
async def receive_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(default=None, alias="X-GitHub-Delivery"),
):
    raw_body = await request.body()

    if not verify_signature(settings.webhook_secret, raw_body, x_hub_signature_256):
        raise HTTPException(401, detail=error_body(
            "invalid_signature", "Signature verification failed"))

    if not x_github_event or not is_supported_event(x_github_event):
        raise HTTPException(400, detail=error_body(
            "unsupported_event", f"Event type '{x_github_event}' is not handled"))

    if x_github_event == "ping":
        return Response(status_code=204)

    payload = await request.json()
    action = payload.get("action")
    issue_number = (payload.get("issue") or {}).get("number")
    delivery_id = x_github_delivery or "unknown"

    if not event_store.already_processed(delivery_id, action):
        event_store.record(delivery_id, x_github_event, action, issue_number)

    return Response(status_code=204)


@app.get("/events")
def list_events(limit: int = 20):
    records = event_store.recent(limit)
    return [
        {
            "id": r.id,
            "event": r.event,
            "action": r.action,
            "issue_number": r.issue_number,
            "timestamp": r.timestamp,
        }
        for r in records
    ]


def _serialize_issue(issue: dict) -> dict:
    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue.get("body"),
        "state": issue["state"],
        "labels": [
            label["name"] if isinstance(label, dict) else label
            for label in issue.get("labels", [])
        ],
        "html_url": issue.get("html_url"),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
    }
