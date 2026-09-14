# # Samhitha Banda

# GitHub Issues Gateway Service

This is a small service that sits in front of the GitHub REST API and
exposes a simpler set of endpoints for managing Issues on one repo. It
also listens for GitHub webhooks (issues + issue comments), validates
them, and stores a log of what came in so you can debug things later.

Built for CMPE 272 HW#2.

## Running it

### With Docker (probably the easiest way)

First, copy `.env.example` to `.env` and fill in your own values — see
the table below for what each one means.

```bash
docker build -t github-issues-gateway .
docker run --rm -p 8000:8000 --env-file .env github-issues-gateway
```

Check that it's actually up:
```bash
curl http://localhost:8000/healthz
```
You should get back `{"status": "ok"}`.

### Without Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then set the env vars (either export them or use a `.env` loader of your
choice):
```bash
export GITHUB_TOKEN=your_pat_here
export GITHUB_OWNER=your_username
export GITHUB_REPO=your_test_repo
export WEBHOOK_SECRET=whatever_secret_you_picked
export PORT=8000
```

And run:
```bash
uvicorn src.main:app --reload --port 8000
```

## Environment variables

| Variable | Required? | What it's for |
|---|---|---|
| `GITHUB_TOKEN` | yes | Fine-grained PAT scoped to Issues read/write on just the one test repo — nothing else |
| `GITHUB_OWNER` | yes | your github username / org |
| `GITHUB_REPO` | yes | the repo the service manages issues for |
| `WEBHOOK_SECRET` | yes | shared secret for verifying incoming webhook signatures |
| `PORT` | no, defaults to 8000 | port the app listens on |

The token only has Issues permission on one repo — didn't want to give it
more access than it actually needs in case it ever leaked. `.env` never
gets committed (it's in `.gitignore`), only `.env.example` with the
placeholder names is checked in.

## Trying out the API

Everything below assumes it's running on `http://localhost:8000`.

Create an issue:
```bash
curl -X POST http://localhost:8000/issues \
  -H "Content-Type: application/json" \
  -d '{"title": "Bug: login fails on Safari", "body": "steps to repro...", "labels": ["bug"]}'
```

List issues:
```bash
curl "http://localhost:8000/issues?state=open&per_page=20"
```

Get one issue:
```bash
curl http://localhost:8000/issues/42
```

Close / reopen:
```bash
curl -X PATCH http://localhost:8000/issues/42 -H "Content-Type: application/json" -d '{"state": "closed"}'
curl -X PATCH http://localhost:8000/issues/42 -H "Content-Type: application/json" -d '{"state": "open"}'
```

Add a comment:
```bash
curl -X POST http://localhost:8000/issues/42/comments \
  -H "Content-Type: application/json" \
  -d '{"body": "thanks, looking into it"}'
```

See recent webhook deliveries the service has recorded:
```bash
curl http://localhost:8000/events
```

## Setting up webhooks

Since GitHub needs a public URL to send webhooks to, you'll need a
tunnel. I used ngrok, but cloudflared works the same way:

```bash
ngrok http 8000
```

That gives you a URL like `https://xxxx.ngrok.io`. Then:

1. Go to your test repo → Settings → Webhooks → Add webhook
2. Payload URL: `https://xxxx.ngrok.io/webhook`
3. Content type: `application/json`
4. Secret: same value as your `WEBHOOK_SECRET`
5. Under "which events", pick individual events and check **Issues** and
   **Issue comments**
6. Save

Then just create/comment on an issue in the repo and check `/events` —
you should see it show up.

If you need to resend a delivery for testing, GitHub lets you do that
from the webhook's "Recent Deliveries" tab — click a delivery, hit
Redeliver. This is safe to do multiple times since deliveries are
deduped by the `X-GitHub-Delivery` id, so redelivering the same event
won't create a second entry.

One thing worth mentioning — rotate the webhook secret after you're done
testing/demoing if you shared the tunnel URL with anyone, since it's a
public URL while the tunnel's running.

## Tests

```bash
pip install -r requirements.txt
pytest tests/unit -v
```

with coverage:
```bash
pytest tests/unit --cov=src --cov-report=term-missing
```

Integration tests live in `tests/integration` and actually hit the real
GitHub API against your test repo, so you'll need a valid token set up
before running those.

## Layout

```
src/
  main.py           - the FastAPI routes
  github_client.py  - wraps calls to GitHub (pagination, error mapping, etc)
  webhook.py        - HMAC signature checking
  store.py          - sqlite store for webhook events
  config.py         - reads env vars
tests/
  unit/
  integration/
openapi.yaml
design-note.docx
requirements.txt
dockerfile
docker-compose.yaml   (optional, not required for grading)
```
