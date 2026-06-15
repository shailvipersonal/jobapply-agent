"""Loads user configuration: the application profile and login credentials.

Everything personal lives in gitignored YAML files under ``config/`` plus a
``.env`` file. This module reads them once and exposes simple dataclasses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Project root = the folder that contains this package's parent.
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
BROWSER_PROFILE_DIR = ROOT / "browser_profile"

PROFILE_PATH = CONFIG_DIR / "profile.yaml"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.yaml"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass
class Settings:
    """Runtime settings sourced from environment variables / .env."""

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    submit_mode: str = "review"  # "review" or "auto"
    headless: bool = False

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


@dataclass
class Credentials:
    """Login credentials reused across job portals."""

    default_email: str
    default_password: str
    overrides: dict[str, dict[str, str]] = field(default_factory=dict)

    def for_url(self, url: str) -> tuple[str, str]:
        """Return (email, password) for a given job URL, honoring overrides."""
        host = (urlparse(url).hostname or "").lower()
        for domain, creds in self.overrides.items():
            if domain.lower() in host:
                return creds.get("email", self.default_email), creds.get(
                    "password", self.default_password
                )
        return self.default_email, self.default_password


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    if not path.exists():
        raise ConfigError(
            f"Missing config file: {path}\n"
            f"Run 'python -m jobagent init' or copy the matching .example file."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must be a YAML mapping.")
    return data


def load_settings() -> Settings:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ModuleNotFoundError:
        pass  # .env support is optional; env vars still work
    headless = os.getenv("HEADLESS", "false").strip().lower() in {"1", "true", "yes"}
    mode = os.getenv("SUBMIT_MODE", "review").strip().lower()
    if mode not in {"review", "auto"}:
        mode = "review"
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        submit_mode=mode,
        headless=headless,
    )


def load_profile() -> dict[str, Any]:
    """Load the application profile and return it as a nested dict."""
    return _load_yaml(PROFILE_PATH)


def load_credentials() -> Credentials:
    raw = _load_yaml(CREDENTIALS_PATH)
    default = raw.get("default", {})
    email = default.get("email")
    password = default.get("password")
    if not email or not password:
        raise ConfigError(
            "credentials.yaml must define default.email and default.password."
        )
    overrides = raw.get("overrides") or {}
    return Credentials(
        default_email=email, default_password=password, overrides=overrides
    )


def flatten_profile(profile: dict[str, Any]) -> dict[str, str]:
    """Flatten the nested profile into dotted keys -> string values.

    e.g. {"personal": {"email": "x"}} -> {"personal.email": "x"}.
    Used to give the form filler a flat lookup table of candidate values.
    """
    flat: dict[str, str] = {}

    def _walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                _walk(f"{prefix}.{k}" if prefix else k, v)
        elif value is None:
            return
        else:
            flat[prefix] = str(value).strip()

    _walk("", profile)
    return {k: v for k, v in flat.items() if v}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
