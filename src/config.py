# Author: Jack Kibort and Arthi Chandra Sekar
"""
Central place for reading required configuration from environment
variables. Fails fast and loudly if something required is missing, rather
than letting a None token silently reach the GitHub client.
"""
import os


class MissingConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingConfigError(f"Required environment variable {name} is not set")
    return value


class Settings:
    """Loaded once at process startup."""

    def __init__(self) -> None:
        self.github_token: str = _require("GITHUB_TOKEN")
        self.github_owner: str = _require("GITHUB_OWNER")
        self.github_repo: str = _require("GITHUB_REPO")
        self.webhook_secret: str = _require("WEBHOOK_SECRET")
        self.port: int = int(os.environ.get("PORT", "8000"))


def get_settings() -> Settings:
    return Settings()
