"""Bayan AI · coherence check: should the patient hear the doctor's sentence as is?

SYNC, in the talk loop, before a doctor's sentence is spoken. The live translation (bayan.talk.translate) already
labels what the sentence does (`statement`: plan | diagnosis | claim | question | other); only plans, diagnoses and
clinical claims are checked. ONE fast gpt-oss-120b call (reasoning low, small JSON) reads the running case summary,
the recorded facts and the last few turns (the patient's own words + English) and answers as a senior clinician:
hold only for a clear contradiction with what the patient said, a treatment that does not fit the complaint or the
diagnosis, a clinical claim nothing in the consultation supports, or an instruction likely to be misunderstood in a
harmful way. A hold (confidence >= HOLD_MIN) uses the same held screen as the prescription gate; the concern is also
posted as a caution card (source agent) so it appears in the notes and in the doctor PDF's Copilot concerns.

Never blocks the consultation: any error, bad JSON or a reply slower than TIMEOUT_S -> None (the sentence is
spoken). Never raises.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from . import curator, llm

CHECKED = ("plan", "diagnosis", "claim")          # translation `statement` values that are checked
STATEMENTS = ("plan", "diagnosis", "claim", "question", "other")
HOLD_MIN = float(os.environ.get("BAYAN_COHERENCE_MIN", "0.85"))   # confidence needed to hold the sentence
TIMEOUT_S = float(os.environ.get("BAYAN_COHERENCE_TIMEOUT", "3.0"))
MAX_TOKENS = 450
CONTEXT_TURNS = 8
RULE_ID = "COHERENCE"
KINDS = ("contradiction", "unsupported_claim", "plan_mismatch", "unclear_instruction", "other")
DIMENSION = {"contradiction": "consistency", "unsupported_claim": "consistency", "plan_mismatch": "plan",
             "unclear_instruction": "communication", "other": "safety"}
SAME_ISSUE_SIM = 0.35        # an overridden hold of the same kind with this much shared wording is not re-held

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bayan-coherence")


def enabled() -> bool:
    return os.environ.get("BAYAN_COHERENCE", "on").strip().lower() not in ("off", "0", "false", "no")


def checked(statement: str | None) -> bool:
    return str(statement or "").strip().lower() in CHECKED


SYSTEM = """You are a senior clinician standing beside a doctor during a consultation. An interpreter is about to say
the doctor's newest sentence to the patient in the patient's language. Decide whether the patient should hear this
sentence as it is, or whether it should be held for a moment so the doctor can look at it again.

Judge the sentence against what the patient actually said (their original words, not only the English rendering),
the facts recorded so far and the case summary. Hold ONLY when the sentence clearly:
  - contradicts what the patient said ("contradiction");
  - gives a verdict on a measurement, examination or test ("normal", "fine", "high", "you have a fever") with no
    value, when nothing in the transcript shows it was measured, examined, tested or reported, or when it
    contradicts what the patient reports ("unsupported_claim"). Doctors measure silently: a sentence that reads out
    a value ("120 over 80", "38.5 degrees", "your sugar was 6.1") IS the measurement being reported, so it is
    supported; never hold it as unsupported;
  - gives a treatment or diagnosis that does not fit the patient's complaint or the diagnosis discussed
    ("plan_mismatch");
  - gives an instruction the patient is likely to misunderstand in a way that could harm them ("unclear_instruction").
Do NOT hold for: a reasonable plan that is only incomplete (no dose or duration yet), clinical choices a colleague
might simply make differently, reassurance that fits the history, findings the doctor states with a value or an
examination the doctor describes, wording, tone or politeness, anything that is a matter of opinion, or a point the
doctor has already chosen to say anyway (listed below). When in doubt, do not hold: most sentences are fine.

Return ONLY a JSON object:
  "hold": true or false,
  "reason": for the doctor, at most 18 plain English words, what does not add up (empty when hold is false),
  "kind": "contradiction" | "unsupported_claim" | "plan_mismatch" | "unclear_instruction" | "other",
  "confidence": 0-1, how sure you are that a careful senior clinician would stop this sentence before the patient
     hears it (0.85 or more only when the problem is clear-cut),
  "evidence": up to 3 items {"utt": "<id, e.g. u004>", "quote": "<a few words copied verbatim from that line's EN
     rendering when it has one>"}:
     the patient's words that conflict first, then the doctor's words that are the problem ([] when hold is false)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "hold": {"type": "boolean"},
        "reason": {"type": "string"},
        "kind": {"type": "string", "enum": list(KINDS)},
        "confidence": {"type": "number"},
        "evidence": {"type": "array", "items": {"type": "object", "properties": {
            "utt": {"type": "string"}, "quote": {"type": "string"}}, "required": ["utt", "quote"]}},
    },
    "required": ["hold", "reason", "kind", "confidence", "evidence"],
}


# ------------------------------------------------------------------ prompt
def _overridden(consult) -> list[dict]:
    """Coherence concerns the doctor already chose to speak anyway in this visit."""
    if consult.cards is None:
        return []
    return [c for c in consult.cards.all_cards() if c.get("coherence") and c.get("status") == "overridden"]


def build_prompt(consult, turn, statement: str) -> str:
    from .extract import _compact_state, case_text, said_line
    with consult.lock:
        turns = [t for t in consult.turns if t.kind != "system" and t.id != turn.id][-CONTEXT_TURNS:]
        facts = _compact_state(consult.state)
        case = case_text(consult.state)
    lines = [said_line(t) for t in turns] or ["(no earlier turns)"]
    spoken = [f"- {c.get('title')}" for c in _overridden(consult)]
    return (f"CASE SUMMARY (may lag a turn behind the transcript):\n{case}\n\n"
            f"RECORDED FACTS:\n{facts}\n\n"
            "TRANSCRIPT (oldest first):\n" + "\n".join(lines) + "\n\n"
            + ("ALREADY SAID ANYWAY BY THE DOCTOR (never hold for these points again):\n" + "\n".join(spoken) + "\n\n"
               if spoken else "")
            + f"DOCTOR'S SENTENCE TO CHECK ({statement}):\n{said_line(turn)}")


# ------------------------------------------------------------------ result cleaning
def _clamp(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    v = v / 100.0 if v > 1.0 else v
    return min(1.0, max(0.0, v))


def _short(text: str, words: int = 18) -> str:
    w = " ".join(str(text or "").split()).split(" ")
    out = " ".join(w[:words]).strip()
    if len(w) > words:
        out = out.rstrip(" ,;:") + "…"
    return out


def verified_evidence(consult, evidence, turn) -> list[dict]:
    """Keep only quotes really in the transcript (cards.quote_in_turn; a quote cited under the wrong id is re-pointed
    to the line that has it). Nothing usable left: the doctor's sentence itself."""
    from .copilot import _parse_evidence, verify_quotes
    out: list[dict] = []
    for e in _parse_evidence(evidence)[:3]:
        ok, err = verify_quotes(consult, [e])
        if not err and ok and not any(o["utt"] == ok[0]["utt"] and o["quote"] == ok[0]["quote"] for o in out):
            out.extend(ok)
    if not out and turn is not None:
        out = [{"utt": turn.id, "t_min": turn.t_min, "quote": (turn.english or turn.text or "")[:200]}]
    return out


def _same_issue(consult, kind: str, reason: str) -> dict | None:
    for c in _overridden(consult):
        sim = curator.theme_sim(reason, c.get("title"))
        if sim >= 0.6 or (c.get("coherence_kind") == kind and sim >= SAME_ISSUE_SIM):
            return c
    return None


# ------------------------------------------------------------------ the check
def check(consult, turn, statement: str, timeout_s: float | None = None) -> dict | None:
    """One coherence check of a doctor turn. Returns {"hold", "reason", "kind", "confidence", "evidence",
    "latency_s"} (hold already False below HOLD_MIN or for an issue the doctor overrode before), or None when the
    check was skipped, failed or timed out (the caller speaks the sentence). Never raises."""
    statement = str(statement or "").strip().lower()
    if not enabled() or turn is None or turn.role != "doctor" or statement not in CHECKED:
        return None
    t0 = time.time()
    try:
        user = build_prompt(consult, turn, statement)
        fut = _EXECUTOR.submit(llm.chat_json, SYSTEM, user, SCHEMA, MAX_TOKENS, "low",
                               llm.LLM_PROVIDER, llm.LLM_PROVIDER)
        raw = fut.result(timeout=TIMEOUT_S if timeout_s is None else timeout_s)
    except FutureTimeout:
        consult.log("error", f"coherence check {turn.id}: no answer in {TIMEOUT_S:.1f} s, spoken unchecked")
        return None
    except Exception as e:  # noqa: BLE001 - never block the consultation
        consult.log("error", f"coherence check {turn.id} failed: {type(e).__name__}: {e}")
        return None
    latency = round(time.time() - t0, 2)
    try:
        if not isinstance(raw, dict) or "hold" not in raw:
            consult.log("error", f"coherence check {turn.id}: unusable reply, spoken unchecked ({latency:.2f} s)")
            return None
        kind = str(raw.get("kind") or "other").strip().lower()
        kind = kind if kind in KINDS else "other"
        reason = _short(raw.get("reason") or "")
        conf = _clamp(raw.get("confidence"))
        hold = raw.get("hold") is True or str(raw.get("hold")).lower() == "true"
        out = {"hold": False, "reason": reason, "kind": kind, "confidence": conf, "evidence": [],
               "latency_s": latency, "statement": statement}
        note = ""
        if hold and not reason:
            note = "no reason given"
        elif hold and conf < HOLD_MIN:
            note = f"confidence {conf:.2f} < {HOLD_MIN:.2f}"
        elif hold:
            dup = _same_issue(consult, kind, reason)
            if dup is not None:
                note = f"already spoken anyway ({dup['id']})"
            else:
                out["hold"] = True
                out["evidence"] = verified_evidence(consult, raw.get("evidence"), turn)
        consult.log("tool", f"coherence check {turn.id} ({statement}) → "
                            + (f"HOLD {kind} {conf:.2f}: {reason}" if out["hold"]
                               else ("no hold" + (f" ({kind} {conf:.2f}: {reason}; {note})" if hold else "")))
                            + f" · {latency:.2f} s")
        return out
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"coherence check {turn.id}: {type(e).__name__}: {e}")
        return None


def post_card(consult, turn, result: dict) -> str | None:
    """The hold's concern as a caution card (source agent, kind observation), so it is in the notes and the doctor
    PDF's Copilot concerns; the held screen hides it until the doctor chooses. Returns the card id or None."""
    if consult.cards is None:
        return None
    kind = result.get("kind") or "other"
    dim = DIMENSION.get(kind, "consistency")
    try:
        res = consult.cards.post(
            "observation", result.get("reason") or "Sentence held",
            (result.get("reason") or "") + " The sentence was held before the patient heard it.",
            result.get("evidence") or [], dim, severity="caution", source="agent", t_min=consult.now_min(),
            dimension=dim, confidence=result.get("confidence"), coherence=True, coherence_kind=kind,
            held_utt=turn.id if turn is not None else "")
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"coherence card failed: {type(e).__name__}: {e}")
        return None
    if res.startswith(("rejected", "duplicate")):
        consult.log("card", f"coherence card not posted: {res}")
        return None
    return res

