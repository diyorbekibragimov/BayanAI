"""Bayan web assets: HTML templates (templates/), CSS, JavaScript and SVG (static/), read once at import.

Nothing is served from here: the stage head, the stage and the patient page inline these files exactly as before.
Templates use {name} placeholders filled by fill() in one pass (inserted values are never re-scanned, so CSS, JS
or user text containing braces is safe). Every asset file ends with one newline, which is not part of the asset.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def read(rel: str) -> str:
    """bayan/web/<rel> as text (utf-8), without the file's final newline."""
    text = (WEB / rel).read_text(encoding="utf-8")
    return text[:-1] if text.endswith("\n") else text


def fill(template: str, **values) -> str:
    """Replace every {name} that has a value (one pass); unknown {names} stay as they are."""
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), template)
