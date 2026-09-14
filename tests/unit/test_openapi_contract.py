# Author: Sabari Iyyapan Duraipandian
"""
Guards against openapi.yaml drifting away from the routes actually
implemented in src.main - e.g. if a future edit adds/renames a route (or
adds ETag support the way test_etag.py's routes do) without updating the
spec, this fails instead of the mismatch going unnoticed.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_OWNER", "test-owner")
os.environ.setdefault("GITHUB_REPO", "test-repo")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("PORT", "8000")

import pytest
import yaml

from src.main import app

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi.yaml"

# Routes FastAPI adds automatically that are not part of our documented API.
FASTAPI_BUILTIN_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def test_spec_is_openapi_31(spec):
    assert spec["openapi"].startswith("3.1")


def test_every_documented_path_is_implemented(spec):
    implemented = {r.path for r in app.routes if hasattr(r, "path")}
    for documented_path in spec["paths"]:
        assert documented_path in implemented, (
            f"{documented_path} is documented in openapi.yaml but not implemented in src.main"
        )


def test_every_implemented_route_is_documented(spec):
    documented = set(spec["paths"])
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None or path in FASTAPI_BUILTIN_ROUTES:
            continue
        assert path in documented, (
            f"{path} is implemented in src.main but not documented in openapi.yaml"
        )
