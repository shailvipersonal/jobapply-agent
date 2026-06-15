"""Thin wrapper around Playwright using a *persistent* browser profile.

Using a persistent context (a real on-disk user-data dir) is what lets the agent
"create an account once and reuse it": cookies, logins and sessions survive
between runs, exactly like a normal browser. The first time you apply on a site
you may need to create/confirm the account; after that you stay logged in.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

from .config import BROWSER_PROFILE_DIR

if TYPE_CHECKING:  # imported lazily at runtime so the rest of the CLI works without it
    from playwright.sync_api import BrowserContext, Page


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "Playwright is not installed. Run:\n"
            "    pip install -r requirements.txt\n"
            "    playwright install chromium"
        ) from exc


@contextmanager
def browser_session(headless: bool = False) -> "Iterator[BrowserContext]":
    """Yield a persistent browser context, cleaning up on exit."""
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    sync_playwright = _require_playwright()
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=headless,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        # Reduce obvious automation fingerprints.
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        try:
            yield context
        finally:
            context.close()


def open_page(context: "BrowserContext", url: str, timeout_ms: int = 45_000) -> "Page":
    """Open (or reuse) a page and navigate to the URL."""
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass  # networkidle is best-effort; many job pages keep connections open
    return page
