"""Local web app: a personal job-application dashboard.

Run with:  python run.py   (or: python -m uvicorn jobagent.web:app)

Serves a friendly UI to: save your details once, upload a resume, score it
against a job description (and AI-rewrite it), then auto-apply by pasting a link
-- all driven by the browser-automation engine in this package.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from . import records, resume as resume_mod, scrape, settings_store
from .apply import apply_to_job, submit_current
from .browser_worker import BrowserWorker
from .config import DATA_DIR, ROOT, load_credentials, load_profile, load_settings

WEBUI_DIR = ROOT / "webui"
UPLOAD_DIR = DATA_DIR / "uploads"
IMPROVED_RESUME = DATA_DIR / "improved_resume.docx"
IMPROVED_RESUME_MD = DATA_DIR / "improved_resume.md"


@dataclass
class AppState:
    worker: BrowserWorker | None = None
    resume_text: str = ""
    resume_name: str = ""
    jd_text: str = ""
    jd_title: str = ""
    last_apply_url: str = ""
    last_apply_meta: tuple[str, str] = field(default_factory=lambda: ("", ""))


state = AppState()
app = FastAPI(title="Personal Job Apply Agent")


def get_worker() -> BrowserWorker:
    if state.worker is None:
        s = load_settings()
        state.worker = BrowserWorker(headless=s.headless)
        state.worker.start()
    return state.worker


@app.on_event("shutdown")
def _shutdown() -> None:
    if state.worker is not None:
        state.worker.stop()


# ----------------------------------------------------------------------------- UI
@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (WEBUI_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


# ------------------------------------------------------------------------- status
@app.get("/api/status")
def status() -> dict[str, Any]:
    s = load_settings()
    flat = settings_store.load_flat()
    profile_ready = bool(flat.get("email") and flat.get("first_name"))
    return {
        "profile_ready": profile_ready,
        "resume_uploaded": bool(state.resume_text),
        "resume_name": state.resume_name,
        "llm_enabled": s.llm_enabled,
        "submit_mode": s.submit_mode,
    }


# ----------------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return settings_store.load_flat()


@app.post("/api/settings")
def post_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings_store.save_flat(payload)
    return {"ok": True, "message": "Settings saved."}


# ------------------------------------------------------------------------- resume
@app.post("/api/resume")
def upload_resume(file: UploadFile = File(...)) -> dict[str, Any]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "resume").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md"}:
        raise HTTPException(400, "Please upload a PDF, DOCX, TXT, or MD file.")
    dest = UPLOAD_DIR / f"resume{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        text = resume_mod.extract_text(dest)
    except Exception as exc:
        raise HTTPException(400, f"Could not read resume: {exc}")
    if not text.strip():
        raise HTTPException(400, "No text could be extracted from that file.")
    state.resume_text = text
    state.resume_name = file.filename or dest.name
    settings_store.set_resume_path(str(dest.resolve()))
    return {"ok": True, "name": state.resume_name, "characters": len(text)}


# ------------------------------------------------------------------------ analyze
@app.post("/api/analyze")
def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    if not state.resume_text:
        raise HTTPException(400, "Upload your resume first (Resume tab).")
    job_url = (payload.get("job_url") or "").strip()
    jd_text = (payload.get("jd_text") or "").strip()
    if job_url and not jd_text:
        worker = get_worker()
        title, jd_text = worker.submit(lambda ctx: scrape.get_job_text(ctx, job_url))
        state.jd_title = title
    if not jd_text:
        raise HTTPException(400, "Provide a job link or paste the job description.")
    state.jd_text = jd_text
    s = load_settings()
    report = resume_mod.analyze(state.resume_text, jd_text, s)
    report["job_title"] = state.jd_title
    report["can_rewrite"] = s.llm_enabled
    return report


# ------------------------------------------------------------------------ improve
@app.post("/api/improve")
def improve() -> dict[str, Any]:
    if not state.resume_text or not state.jd_text:
        raise HTTPException(400, "Run an analysis first so I know the target job.")
    s = load_settings()
    try:
        markdown = resume_mod.rewrite(state.resume_text, state.jd_text, s)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    IMPROVED_RESUME_MD.parent.mkdir(parents=True, exist_ok=True)
    IMPROVED_RESUME_MD.write_text(markdown, encoding="utf-8")
    try:
        resume_mod.save_docx(markdown, IMPROVED_RESUME)
        has_docx = True
    except Exception:
        has_docx = False
    return {"ok": True, "markdown": markdown, "docx": has_docx}


@app.get("/api/download/improved")
def download_improved():
    if IMPROVED_RESUME.exists():
        return FileResponse(
            IMPROVED_RESUME,
            filename="improved_resume.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if IMPROVED_RESUME_MD.exists():
        return FileResponse(IMPROVED_RESUME_MD, filename="improved_resume.md")
    raise HTTPException(404, "No improved resume generated yet.")


# -------------------------------------------------------------------------- apply
@app.post("/api/apply")
def apply(payload: dict[str, Any]) -> dict[str, Any]:
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "Paste a job link to apply to.")
    auto = bool(payload.get("auto"))
    try:
        s = load_settings()
        profile = load_profile()
        creds = load_credentials()
    except Exception as exc:
        raise HTTPException(400, f"Finish Setup first: {exc}")
    mode = "auto" if auto else "review"
    worker = get_worker()
    result = worker.submit(
        lambda ctx: apply_to_job(ctx, url, s, profile, creds, mode, confirm=None),
        timeout=300,
    )
    state.last_apply_url = result.url
    state.last_apply_meta = (result.company, result.title)
    return {
        "ok": True,
        "status": result.status,
        "message": result.message,
        "title": result.title,
        "company": result.company,
        "log": result.log,
        "submitted": result.status == "submitted",
    }


@app.post("/api/submit")
def submit() -> dict[str, Any]:
    if not state.last_apply_url:
        raise HTTPException(400, "Fill an application first.")
    worker = get_worker()
    clicked = worker.submit(lambda ctx: submit_current(ctx))
    company, title = state.last_apply_meta
    status = "submitted" if clicked else "filled_pending_review"
    msg = "Submitted from review." if clicked else "Could not find a submit button."
    records.record(records.Application(state.last_apply_url, company, title, status, msg))
    return {"ok": clicked, "status": status, "message": msg}


# ------------------------------------------------------------------------ history
@app.get("/api/history")
def history(limit: int = 200) -> dict[str, Any]:
    apps = records.list_all(limit=limit)
    return {
        "applications": [
            {
                "id": a.id,
                "applied_at": a.applied_at,
                "company": a.company,
                "title": a.title,
                "status": a.status,
                "url": a.url,
                "notes": a.notes,
            }
            for a in apps
        ]
    }


@app.get("/api/history.csv")
def history_csv():
    out = DATA_DIR / "applications.csv"
    records.export_csv(out)
    return FileResponse(out, filename="applications.csv", media_type="text/csv")
