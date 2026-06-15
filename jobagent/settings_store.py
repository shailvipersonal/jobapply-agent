"""Bridges the friendly web Setup form to the on-disk config files.

The web UI sends/receives one flat JSON object. This module reads it from (and
writes it to) ``config/profile.yaml``, ``config/credentials.yaml`` and ``.env``
so the rest of the app keeps using the same files as the CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import CONFIG_DIR, CREDENTIALS_PATH, PROFILE_PATH, ROOT

ENV_PATH = ROOT / ".env"

# Maps a flat form field -> dotted location inside profile.yaml.
_PROFILE_MAP = {
    "first_name": "personal.first_name",
    "last_name": "personal.last_name",
    "email": "personal.email",
    "phone": "personal.phone",
    "address_line1": "location.address_line1",
    "city": "location.city",
    "state": "location.state",
    "postal_code": "location.postal_code",
    "country": "location.country",
    "linkedin": "links.linkedin",
    "github": "links.github",
    "portfolio": "links.portfolio",
    "current_title": "experience.current_title",
    "current_company": "experience.current_company",
    "years_experience": "experience.years_experience",
    "desired_salary": "experience.desired_salary",
    "notice_period": "experience.notice_period",
    "authorized_to_work": "work_authorization.authorized_to_work",
    "require_sponsorship": "work_authorization.require_sponsorship",
    "willing_to_relocate": "work_authorization.willing_to_relocate",
    "remote_ok": "work_authorization.remote_ok",
    "highest_degree": "education.highest_degree",
    "field_of_study": "education.field_of_study",
    "school": "education.school",
    "graduation_year": "education.graduation_year",
    "how_did_you_hear": "answers.how_did_you_hear",
    "default_cover_note": "answers.default_cover_note",
    "resume_path": "documents.resume_path",
}


def _set_dotted(d: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value


def _get_dotted(d: dict, dotted: str) -> Any:
    cur: Any = d
    for k in dotted.split("."):
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(k, "")
    return cur if cur is not None else ""


def set_resume_path(path: str) -> None:
    """Update only documents.resume_path in profile.yaml (no other side effects)."""
    import yaml

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    profile: dict = {}
    if PROFILE_PATH.exists():
        profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}
    _set_dotted(profile, "documents.resume_path", str(path))
    PROFILE_PATH.write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def load_flat() -> dict[str, Any]:
    """Read all config into one flat dict for the Setup form (no password)."""
    import yaml

    profile: dict = {}
    if PROFILE_PATH.exists():
        profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}
    creds: dict = {}
    if CREDENTIALS_PATH.exists():
        creds = yaml.safe_load(CREDENTIALS_PATH.read_text(encoding="utf-8")) or {}
    env = _read_env()

    flat: dict[str, Any] = {k: _get_dotted(profile, dotted) for k, dotted in _PROFILE_MAP.items()}
    flat["account_email"] = (creds.get("default") or {}).get("email", "")
    flat["account_password_set"] = bool((creds.get("default") or {}).get("password"))
    flat["openai_api_key_set"] = bool(env.get("OPENAI_API_KEY"))
    flat["openai_model"] = env.get("OPENAI_MODEL", "gpt-4o-mini")
    flat["submit_mode"] = env.get("SUBMIT_MODE", "review")
    flat["headless"] = env.get("HEADLESS", "false")
    return flat


def save_flat(data: dict[str, Any]) -> None:
    """Persist the Setup form back to the config files."""
    import yaml

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # profile.yaml
    profile: dict = {}
    if PROFILE_PATH.exists():
        profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}
    for field, dotted in _PROFILE_MAP.items():
        if field in data and data[field] is not None:
            _set_dotted(profile, dotted, str(data[field]))
    # Derive full name.
    fn = _get_dotted(profile, "personal.first_name")
    ln = _get_dotted(profile, "personal.last_name")
    if fn or ln:
        _set_dotted(profile, "personal.full_name", f"{fn} {ln}".strip())
    PROFILE_PATH.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")

    # credentials.yaml -- only overwrite password if a new one was supplied.
    creds: dict = {}
    if CREDENTIALS_PATH.exists():
        creds = yaml.safe_load(CREDENTIALS_PATH.read_text(encoding="utf-8")) or {}
    creds.setdefault("default", {})
    if data.get("account_email"):
        creds["default"]["email"] = str(data["account_email"])
    if data.get("account_password"):
        creds["default"]["password"] = str(data["account_password"])
    creds.setdefault("overrides", {})
    CREDENTIALS_PATH.write_text(yaml.safe_dump(creds, sort_keys=False, allow_unicode=True), encoding="utf-8")

    # .env -- preserve existing key unless a new one is provided.
    env = _read_env()
    if data.get("openai_api_key"):
        env["OPENAI_API_KEY"] = str(data["openai_api_key"]).strip()
    env.setdefault("OPENAI_API_KEY", "")
    env["OPENAI_MODEL"] = str(data.get("openai_model") or env.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    env["SUBMIT_MODE"] = str(data.get("submit_mode") or env.get("SUBMIT_MODE") or "review").strip()
    env["HEADLESS"] = str(data.get("headless") or env.get("HEADLESS") or "false").strip()
    lines = [
        "# Auto-managed by the jobapply-agent Setup page.",
        *[f"{k}={v}" for k, v in env.items()],
    ]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
