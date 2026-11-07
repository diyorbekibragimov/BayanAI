"""Bayan copilot hook: suggestions for the doctor, shown in the Notes panel.

MVP: deterministic. When the patient uses an idiom from data/idiom_lexicon.json, Bayan explains it
under the English line and suggests one clarifying question ("Ask next").

The smolagents clinical copilot (docs/11-clinical-copilot-agent.md) plugs in here: implement
`suggest(consult, turn)` to return more suggestion dicts of the same shape. The UI only reads
{"id", "kind", "label", "text", "status"}; kind "ask" renders "Ask the patient in <language>".
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

_LEX = json.loads((Path(__file__).resolve().parent.parent / "data" / "idiom_lexicon.json").read_text())
ENTRIES: list[dict] = _LEX["entries"]

LANG_TO_LEXICON = {"ne": "Nepali", "hi": "Hindi", "ur": "Urdu", "bn": "Bengali", "ml": "Malayalam", "tl": "Filipino"}

# Red-flag questions first: when an idiom can hide heart pain, ask about spread and sweating.
_RED_FLAG_Q = re.compile(r"\b(arm|jaw|sweat)", re.I)


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def explain(entry: dict) -> str:
    """One plain sentence: what the idiom usually means and what it can hide."""
    word = (entry.get("romanized") or entry.get("native") or "").strip()
    usual = next((i["meaning"] for i in entry.get("clinical_interpretations", []) if i.get("likelihood") == "high"), "")
    hide = (entry.get("masks_red_flags") or [""])[0].split(":")[0].split("(")[0].strip()
    out = f"{word[:1].upper()}{word[1:]} usually means {_lower_first(usual)}" if usual else f"{word[:1].upper()}{word[1:]} is an idiom"
    if hide:
        out += f", but it can also hide {_lower_first(hide)}"
    return out.rstrip(". ") + "."


def pick_question(entry: dict) -> str:
    qs = entry.get("clarifying_questions_en") or []
    if not qs:
        return ""
    if "acs" in (entry.get("red_flag_tags") or []):
        for q in qs:
            if _RED_FLAG_Q.search(q):
                return q
    return qs[0]


def match_idiom(native: str, english: str, lang: str) -> dict | None:
    """First lexicon entry for this language whose native form (or romanisation) appears in the turn."""
    language = LANG_TO_LEXICON.get(lang)
    if not language:
        return None
    native = native or ""
    english_l = (english or "").lower()
    for e in ENTRIES:
        if e.get("language") != language:
            continue
        form = (e.get("native") or "").strip()
        rom = (e.get("romanized") or "").strip().lower()
        if len(form) >= 3 and form in native:
            return e
        if len(rom) >= 5 and re.search(rf"\b{re.escape(rom)}\b", english_l):
            return e
    return None


def suggest(consult, turn: dict) -> list[dict]:
    """Suggestions for one patient turn. `turn` = {"role", "native", "english"}.

    Hook for the smolagents copilot: extend or replace this function; keep the dict shape.
    """
    if turn.get("role") != "patient":
        return []
    e = match_idiom(turn.get("native", ""), turn.get("english", ""), consult.lang)
    if not e:
        return []
    q = pick_question(e)
    if not q:
        return []
    return [{"id": uuid.uuid4().hex[:8], "kind": "ask", "label": "Ask next", "text": q,
             "status": "open", "source": e["id"]}]
