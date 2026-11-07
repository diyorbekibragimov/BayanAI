"""Bayan copilot, UI adapter: turns the brain's decision-support cards into what the stage shows.

This is the thin view layer the stage reads. The engine is `bayan.brain.copilot` (rules, lexicon, smolagents
clinical copilot, CardStore with guardrails); nothing clinical is decided here. Cards arrive asynchronously from
the background think run; the stage re-renders when `consult.cards.version` changes (see bayan.consult.poll_render).

Mapping (deduped by card id, reflecting card status):
  kind "ask"                     -> Notes-panel suggestion ("Ask the patient in <language>"), open until asked;
                                    exactly one is open at a time (bayan.brain.curator retires the older one)
  kind "idiom"                   -> the explanation under the patient's English line (+ the idiom underlined)
  kind "missed" / "observation"  -> a note in "Noted in this visit" (agent / fallback cards)
  source "rules" (safety cards)  -> an alert note (red if critical / caution) while the card is open (the card of a
                                    held sentence is shown on the held screen instead)
The UI reads suggestions as {"id", "kind", "label", "text", "status"} and notes as {"kind", "text"}.
"""

from __future__ import annotations

import re

_SUG_STATUS = {"open": "open", "accepted": "asked"}
MAX_AGENT_NOTES = 4          # the curator's visible budget (bayan.brain.curator.MAX_VISIBLE)


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def explain(idiom: dict) -> str:
    """One plain sentence: what the idiom usually means and what it can hide. `idiom` is the card's "idiom" dict
    (or a lexicon entry)."""
    word = (idiom.get("romanized") or idiom.get("native") or "").strip()
    interps = idiom.get("interpretations") or idiom.get("clinical_interpretations") or []
    usual = next((i.get("meaning") for i in interps if isinstance(i, dict) and i.get("likelihood") == "high"), "")
    masks = idiom.get("masks") or idiom.get("masks_red_flags") or [""]
    hide = (masks[0] or "").split(":")[0].split("(")[0].strip()
    out = f"{word[:1].upper()}{word[1:]} usually means {_lower_first(usual)}" if usual else f"{word[:1].upper()}{word[1:]} is an idiom"
    if hide:
        out += f", but it can also hide {_lower_first(hide)}"
    return out.rstrip(". ") + "."


def _cards(consult) -> list[dict]:
    cards = getattr(consult, "cards", None)
    return cards.all_cards() if cards is not None else []


def suggest(consult, turn: dict | None = None) -> list[dict]:
    """Every "ask" card of the brain consultation as a Notes-panel suggestion, oldest first (the deterministic
    lexicon question comes before the agent's). Status: open -> "open", asked -> "asked", anything else
    (resolved, dismissed) -> "closed". `turn` is accepted for the hook signature and not needed: the cards already
    cite their turns."""
    out = []
    for c in _cards(consult):
        if c.get("kind") != "ask" or not c.get("ask_text"):
            continue
        out.append({"id": c["id"], "kind": "ask", "label": "Ask next", "text": c["ask_text"],
                    "status": _SUG_STATUS.get(c.get("status"), "closed"), "source": c.get("grounding")})
    # exactly ONE "Ask next" is offered (the curator keeps one open; this view guarantees it): the newest open one
    opened = [x for x in out if x["status"] == "open"]
    for x in opened[:-1]:
        x["status"] = "closed"
    return out


def idiom_for(consult, utt: str | None, native: str = "") -> tuple[str | None, str]:
    """(idiom as written in the patient's words or None, explanation) for one patient turn."""
    if not utt:
        return None, ""
    for c in _cards(consult):
        if c.get("kind") != "idiom" or c.get("status") == "dismissed":
            continue
        if not any(e.get("utt") == utt for e in c.get("evidence") or []):
            continue
        idiom = c.get("idiom") or {}
        form = (idiom.get("native") or "").strip()
        return (form if form and form in (native or "") else None), explain(idiom)
    return None, ""


def _first_sentence(text: str, limit: int = 140) -> str:
    s = re.split(r"(?<=[.!?])\s", (text or "").strip(), maxsplit=1)[0]
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"


def notes(consult, hide: set[str] | frozenset = frozenset()) -> list[dict]:
    """Card notes for "Noted in this visit": open rule alerts (minus `hide`, e.g. the card on the held screen), then
    the agent's / fallback's missed and observation cards that are still relevant."""
    alerts, others = [], []
    for c in _cards(consult):
        if c["id"] in hide:
            continue
        if c.get("source") == "rules":
            if c.get("status") != "open":
                continue
            items = c.get("items") or []
            title = str(c.get("title") or "").split(" · ")[0]
            if len(items) == 1:
                text = _first_sentence(items[0].get("message", "")) or title
            else:   # grouped workup card: "Chest-pain workup: no ECG, no troponin"
                gaps = list(dict.fromkeys(g.lower() for i in items for g in re.findall(
                    r"\bno\s+(?:12-lead\s+)?([A-Za-z][\w-]*)", i.get("message") or "", re.I)))
                text = title + (": " + ", ".join(f"no {g.upper() if g == 'ecg' else g}" for g in gaps[:4])
                                if gaps else "")
            # critical / caution rule cards are red alerts; info-level rules (e.g. "reaction not captured") are notes
            kind = "alert" if c.get("severity") in ("critical", "caution") else "rule"
            alerts.append({"kind": kind, "text": text, "id": c["id"]})
        elif c.get("kind") in ("missed", "observation") and c.get("status") not in ("dismissed", "resolved"):
            others.append({"kind": c["kind"], "text": c.get("title") or "", "id": c["id"]})
    return alerts + others[-MAX_AGENT_NOTES:]
