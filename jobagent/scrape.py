"""Fetch the visible text of a job posting so we can analyse it.

Runs inside the browser worker thread, reusing the live context (so it benefits
from any login session the user already has).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext


def get_job_text(context: "BrowserContext", url: str, timeout_ms: int = 45_000) -> tuple[str, str]:
    """Return (page_title, visible_text) for a job posting URL."""
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass
    title = ""
    try:
        title = (page.title() or "").strip()
    except Exception:
        pass
    try:
        text = page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        text = ""
    # Collapse excessive whitespace and cap length for the LLM.
    text = " ".join((text or "").split())
    return title, text[:12_000]
