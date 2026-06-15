"""A single background thread that owns the Playwright browser.

Playwright's sync API must be driven from one thread. The web server, however,
handles each request on a different thread. This worker bridges the two: it runs
Playwright in its own thread and serializes browser actions submitted from the
web app, while keeping a *single persistent browser window open* for the whole
session -- so you can watch the agent work and review forms before submitting.
"""

from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from typing import Any, Callable

from .config import BROWSER_PROFILE_DIR

# A task is a function that receives the live BrowserContext and returns anything.
Task = Callable[[Any], Any]


class BrowserWorker:
    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self._tasks: "queue.Queue[tuple[Task | None, Future]]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="browser-worker", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=90)
        if self._startup_error is not None:
            raise self._startup_error

    def _run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            self._startup_error = RuntimeError(
                "Playwright is not installed. Run: pip install -r requirements.txt "
                "&& playwright install chromium"
            )
            self._ready.set()
            return

        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(BROWSER_PROFILE_DIR),
                    headless=self.headless,
                    viewport={"width": 1366, "height": 900},
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                )
                self._ready.set()
                while True:
                    fn, fut = self._tasks.get()
                    if fn is None:  # shutdown sentinel
                        if not fut.done():
                            fut.set_result(None)
                        break
                    try:
                        fut.set_result(fn(context))
                    except BaseException as exc:  # noqa: BLE001 - report back to caller
                        fut.set_exception(exc)
                try:
                    context.close()
                except Exception:
                    pass
        except BaseException as exc:  # launch failure
            self._startup_error = exc
            self._ready.set()

    def submit(self, fn: Task, timeout: float = 240) -> Any:
        """Run ``fn(context)`` on the browser thread and return its result."""
        if self._thread is None:
            self.start()
        fut: Future = Future()
        self._tasks.put((fn, fut))
        return fut.result(timeout=timeout)

    def stop(self) -> None:
        if self._thread is None:
            return
        fut: Future = Future()
        self._tasks.put((None, fut))
        try:
            fut.result(timeout=15)
        except Exception:
            pass
        self._thread = None
        self._ready.clear()
