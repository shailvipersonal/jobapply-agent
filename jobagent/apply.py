"""Orchestrates a single job application end to end.

Flow for a given job URL:
  1. Open the page in the persistent browser (reusing any saved login).
  2. Click the "Apply" entry point if there is one.
  3. Opportunistically fill a login/sign-up form with saved credentials.
  4. Detect and fill the application form from the profile.
  5. Submit now (auto) or pause for your confirmation (review).
  6. Record the outcome in the local database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

from . import records
from .config import Credentials, Settings, flatten_profile
from .browser import open_page
from .form_filler import fill_form

# Confirm callback: given the action log, return True to submit.
ConfirmFn = Callable[[list[str]], bool]

_APPLY_TEXTS = [
    "Apply for this job", "Apply now", "Apply Now", "I'm interested",
    "Easy Apply", "Apply", "Start application",
]
_SUBMIT_TEXTS = [
    "Submit application", "Submit Application", "Submit", "Send application",
    "Send Application", "Finish", "Complete application",
]


@dataclass
class ApplyResult:
    url: str
    status: str
    company: str = ""
    title: str = ""
    message: str = ""
    log: list[str] = field(default_factory=list)


def _click_first(page: "Page", texts: list[str], timeout: int = 2500) -> bool:
    for t in texts:
        try:
            loc = page.get_by_role("button", name=t, exact=False)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=timeout)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            pass
        try:
            loc = page.get_by_role("link", name=t, exact=False)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=timeout)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            pass
    return False


def _maybe_login(page: "Page", email: str, password: str) -> bool:
    """Best-effort: if a login/sign-up form is visible, fill and submit it."""
    try:
        pwd = page.locator("input[type='password']:visible")
        if not pwd.count():
            return False
        email_field = page.locator(
            "input[type='email']:visible, input[name*='email' i]:visible"
        )
        if email_field.count():
            email_field.first.fill(email)
        pwd.first.fill(password)
        for t in ["Sign in", "Log in", "Login", "Continue", "Create account", "Sign up"]:
            loc = page.get_by_role("button", name=t, exact=False)
            if loc.count() and loc.first.is_visible():
                loc.first.click()
                page.wait_for_timeout(2500)
                return True
    except Exception:
        return False
    return False


def _detect_meta(page: "Page", url: str) -> tuple[str, str]:
    company = urlparse(url).hostname or ""
    title = ""
    try:
        title = (page.title() or "").strip()
        h1 = page.locator("h1")
        if h1.count():
            t = h1.first.inner_text().strip()
            if t:
                title = t
    except Exception:
        pass
    return company, title[:200]


def apply_to_job(
    context: "BrowserContext",
    url: str,
    settings: Settings,
    profile: dict,
    credentials: Credentials,
    submit_mode: str,
    confirm: ConfirmFn | None = None,
) -> ApplyResult:
    flat = flatten_profile(profile)
    email, password = credentials.for_url(url)

    page = open_page(context, url)
    company, title = _detect_meta(page, url)

    # Step into the application flow if there's an explicit Apply button.
    _click_first(page, _APPLY_TEXTS)
    # Some portals require sign-in before showing the form.
    if _maybe_login(page, email, password):
        page.wait_for_timeout(1000)
        _click_first(page, _APPLY_TEXTS)

    log = fill_form(page, settings, flat)

    meaningful = [l for l in log if not l.startswith("No fillable")]
    if not meaningful:
        result = ApplyResult(url, "failed", company, title,
                             "No form fields could be filled.", log)
        records.record(records.Application(url, company, title, "failed", result.message))
        return result

    # Decide whether to submit.
    do_submit = submit_mode == "auto"
    if submit_mode == "review" and confirm is not None:
        do_submit = confirm(log)

    if do_submit:
        clicked = _click_first(page, _SUBMIT_TEXTS, timeout=5000)
        page.wait_for_timeout(2500)
        status = "submitted" if clicked else "filled_pending_review"
        msg = "Submitted." if clicked else "Filled, but no submit button was found."
    else:
        status = "filled_pending_review"
        msg = "Form filled; left for your review (not submitted)."

    records.record(records.Application(url, company, title, status, msg))
    return ApplyResult(url, status, company, title, msg, log)


def submit_current(context: "BrowserContext") -> bool:
    """Click the submit button on whatever page is currently open.

    Used by the web UI's "Submit now" button after a review-mode fill.
    """
    page = context.pages[0] if context.pages else None
    if page is None:
        return False
    clicked = _click_first(page, _SUBMIT_TEXTS, timeout=5000)
    page.wait_for_timeout(2000)
    return clicked
