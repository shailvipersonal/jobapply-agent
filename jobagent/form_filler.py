"""Detects form fields on a page and fills them from the user's profile.

Two layers of intelligence:
  1. Heuristic keyword matching (always available, no API key needed).
  2. Optional LLM mapping (jobagent.llm) which overrides heuristics when it is
     confident -- handy for unusually worded forms.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

from .config import Settings
from . import llm

# JS that tags every fillable field with a stable index and returns metadata.
_EXTRACT_JS = r"""
() => {
  const out = [];
  let idx = 0;
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const labelFor = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l && l.innerText.trim()) return l.innerText.trim();
    }
    const wrap = el.closest('label');
    if (wrap && wrap.innerText.trim()) return wrap.innerText.trim();
    if (el.placeholder) return el.placeholder;
    // Look at preceding sibling text / parent heading.
    let p = el.parentElement;
    for (let i = 0; i < 3 && p; i++) {
      const t = Array.from(p.childNodes)
        .filter(n => n.nodeType === 3)
        .map(n => n.textContent.trim())
        .filter(Boolean)
        .join(' ');
      if (t) return t;
      p = p.parentElement;
    }
    return el.name || '';
  };
  const tag = (el, type, options) => {
    el.setAttribute('data-jobagent-idx', String(idx));
    out.push({
      index: idx,
      type: type,
      label: (labelFor(el) || '').replace(/\s+/g, ' ').trim().slice(0, 200),
      name: el.name || '',
      options: options || [],
    });
    idx++;
  };

  document.querySelectorAll('input, textarea, select').forEach((el) => {
    if (!isVisible(el)) return;
    const t = (el.type || el.tagName).toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(t)) return;
    if (el.disabled || el.readOnly) return;
    if (el.tagName.toLowerCase() === 'select') {
      const opts = Array.from(el.options).map(o => o.text.trim()).filter(Boolean);
      tag(el, 'select', opts);
    } else if (t === 'radio' || t === 'checkbox') {
      tag(el, t, [el.value || labelFor(el)]);
    } else if (t === 'file') {
      tag(el, 'file', []);
    } else {
      tag(el, 'text', []);
    }
  });
  return out;
}
"""

# keyword -> dotted profile key. First match wins (order matters: specific first).
_HEURISTICS: list[tuple[tuple[str, ...], str]] = [
    (("first name", "given name", "firstname"), "personal.first_name"),
    (("last name", "surname", "family name", "lastname"), "personal.last_name"),
    (("full name", "your name", "legal name", "name"), "personal.full_name"),
    (("email",), "personal.email"),
    (("phone", "mobile", "telephone", "cell"), "personal.phone"),
    (("linkedin",), "links.linkedin"),
    (("github",), "links.github"),
    (("portfolio", "personal website", "website", "url"), "links.portfolio"),
    (("address",), "location.address_line1"),
    (("city",), "location.city"),
    (("state", "province", "region"), "location.state"),
    (("zip", "postal", "post code"), "location.postal_code"),
    (("country",), "location.country"),
    (("desired salary", "salary", "compensation", "expected pay"), "experience.desired_salary"),
    (("current company", "current employer", "employer", "company"), "experience.current_company"),
    (("current title", "current role", "job title", "position", "title"), "experience.current_title"),
    (("years of experience", "years experience", "experience"), "experience.years_experience"),
    (("notice period", "notice"), "experience.notice_period"),
    (("start date", "available", "availability"), "experience.earliest_start_date"),
    (("school", "university", "college", "institution"), "education.school"),
    (("degree", "qualification"), "education.highest_degree"),
    (("field of study", "major", "discipline"), "education.field_of_study"),
    (("graduation", "grad year"), "education.graduation_year"),
    (("authorized", "authorization", "legally", "eligible to work", "right to work"),
     "work_authorization.authorized_to_work"),
    (("sponsor", "visa"), "work_authorization.require_sponsorship"),
    (("relocate",), "work_authorization.willing_to_relocate"),
    (("remote",), "work_authorization.remote_ok"),
    (("how did you hear", "referral source", "source"), "answers.how_did_you_hear"),
    (("cover letter", "why", "message", "additional information", "anything else", "notes"),
     "answers.default_cover_note"),
    (("gender",), "demographics.gender"),
    (("race", "ethnicity"), "demographics.race_ethnicity"),
    (("veteran",), "demographics.veteran_status"),
    (("disability",), "demographics.disability_status"),
]


def extract_fields(page: "Page") -> list[dict[str, Any]]:
    return page.evaluate(_EXTRACT_JS)


def _heuristic_value(field: dict[str, Any], flat: dict[str, str]) -> str | None:
    text = f"{field.get('label', '')} {field.get('name', '')}".lower()
    if field.get("type") == "file":
        if "cover" in text and flat.get("documents.cover_letter_path"):
            return flat["documents.cover_letter_path"]
        return flat.get("documents.resume_path")
    for keywords, key in _HEURISTICS:
        if any(k in text for k in keywords) and flat.get(key):
            return flat[key]
    return None


def _pick_option(value: str, options: list[str]) -> str | None:
    """Match a desired value to one of the available options."""
    if not options:
        return value
    v = value.strip().lower()
    for o in options:
        if o.strip().lower() == v:
            return o
    for o in options:
        if v and (v in o.lower() or o.lower() in v):
            return o
    # Common yes/no normalisation.
    if v in {"yes", "no"}:
        for o in options:
            if o.strip().lower().startswith(v):
                return o
    return None


def fill_form(
    page: "Page",
    settings: Settings,
    profile_flat: dict[str, str],
) -> list[str]:
    """Fill all detected fields. Returns a human-readable log of actions."""
    fields = extract_fields(page)
    log: list[str] = []
    if not fields:
        return ["No fillable fields detected on this page."]

    llm_map = llm.map_fields(settings, profile_flat, fields)

    for field in fields:
        idx = field["index"]
        ftype = field.get("type", "text")
        label = field.get("label", "") or field.get("name", "") or f"field {idx}"
        value = llm_map.get(idx) or _heuristic_value(field, profile_flat)
        if not value:
            continue

        locator = page.locator(f"[data-jobagent-idx='{idx}']")
        try:
            if ftype == "select":
                chosen = _pick_option(value, field.get("options", []))
                if chosen:
                    locator.select_option(label=chosen)
                    log.append(f"select  | {label!r} -> {chosen!r}")
            elif ftype == "radio":
                opt = (field.get("options") or [""])[0]
                if _pick_option(value, [opt]) or value.lower() in opt.lower():
                    locator.check()
                    log.append(f"radio   | {label!r} -> checked")
            elif ftype == "checkbox":
                if value.strip().lower() in {"yes", "true", "1", "on"}:
                    locator.check()
                    log.append(f"check   | {label!r} -> checked")
            elif ftype == "file":
                locator.set_input_files(value)
                log.append(f"upload  | {label!r} -> {value}")
            else:
                locator.fill(value)
                log.append(f"text    | {label!r} -> {value!r}")
        except Exception as exc:  # one bad field shouldn't abort the whole form
            log.append(f"skip    | {label!r} ({type(exc).__name__})")

    return log
