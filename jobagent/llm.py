"""Optional LLM-assisted field mapping.

Given the list of fields extracted from a job application form and the user's
flattened profile, ask an LLM to decide the best value for each field. This is
what lets the agent adapt to arbitrary, oddly-worded forms it has never seen.

If no OPENAI_API_KEY is configured, callers should fall back to heuristic
matching in ``form_filler.py``.
"""

from __future__ import annotations

import json
from typing import Any

from .config import Settings


SYSTEM_PROMPT = """\
You are an assistant that fills out job application web forms on behalf of a \
candidate. You are given:
1. The candidate's profile as flat key/value pairs.
2. A list of form fields, each with an index, a human label, the input type, \
   and (for selects/radios) the available options.

Return STRICT JSON: an object with a "fields" array. For each form field that \
you can confidently fill, include an object:
  {"index": <int>, "value": "<string to type or option to choose>", "skip": false}
Rules:
- For select/radio/checkbox fields, "value" MUST exactly match one of the \
  provided options.
- If you cannot confidently determine a value, set "skip": true and omit value.
- Never invent personal data that isn't derivable from the profile.
- For yes/no authorization questions, use the profile's work_authorization data.
- Prefer leaving sensitive/demographic fields as "Decline to self-identify" \
  when that option exists.
Return ONLY the JSON object, no prose.
"""


def map_fields(
    settings: Settings,
    profile_flat: dict[str, str],
    fields: list[dict[str, Any]],
) -> dict[int, str]:
    """Return {field_index: value} suggested by the LLM. Empty on failure."""
    if not settings.llm_enabled:
        return {}
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        user_payload = {
            "profile": profile_flat,
            "fields": [
                {
                    "index": f["index"],
                    "label": f.get("label", ""),
                    "type": f.get("type", ""),
                    "options": f.get("options", []),
                }
                for f in fields
            ],
        }
        resp = client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        result: dict[int, str] = {}
        for item in data.get("fields", []):
            if item.get("skip"):
                continue
            idx = item.get("index")
            value = item.get("value")
            if isinstance(idx, int) and isinstance(value, str) and value.strip():
                result[idx] = value
        return result
    except Exception:
        # Any failure (network, quota, parse) -> silently fall back to heuristics.
        return {}
