"""Start the local web app and open it in your browser.

Usage:  python run.py
"""

from __future__ import annotations

import threading
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def _open_browser() -> None:
    time.sleep(1.5)
    try:
        webbrowser.open(URL)
    except Exception:
        pass


def main() -> None:
    try:
        import uvicorn
    except ModuleNotFoundError:
        raise SystemExit(
            "Dependencies are not installed yet.\n"
            "Run:  pip install -r requirements.txt  &&  playwright install chromium"
        )
    print(f"\n  Job Apply Agent is starting at {URL}\n  (Close this window to stop it.)\n")
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("jobagent.web:app", host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
