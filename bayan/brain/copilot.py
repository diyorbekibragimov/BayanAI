"""Bayan AI · the clinical copilot (think loop) and the synchronous prescription gate.

One think run (background, debounced ~1.2 s, at most one in flight per consultation; a turn arriving mid-run marks
it dirty -> exactly one rerun; it never delays speech):
  1. lookup_idiom       deterministic lexicon match on new patient turns -> idiom cards at once        (code)
  2. update_state       ONE LLM extraction call (json_schema) -> merge_delta: clinical facts AND the running case
                        summary (state["case"]: complaint, history, working diagnosis, plan, stated findings, the
                        patient's understanding and affect); courtesy turns skip it; if the call fails, a keyword
                        fallback still records chest-pain symptoms                                       (1 LLM call)
  3. check_safety_rules RuleEngine.evaluate -> CardStore.sync_rules (WORK-CHEST-* -> one grouped card)  (code)
  4. resolve            open questions the doctor has now asked, checklist items now done              (code)
  5. clinical review    on every substantive turn (not courtesy turns, not a doctor question still waiting for its
                        answer): smolagents ToolCallingAgent (gpt-oss-120b on Cerebras) reviews the case like a
                        second clinician along five general dimensions (safety, history, plan, communication,
                        consistency) and returns 0-2 candidate concerns, each QUOTING the transcript (quotes are
                        verified in code; rule / idiom / checklist ids are optional context, never required) plus
                        the ids of its earlier cards the conversation has addressed. Typically ONE LLM step.
  6. curate             bayan.brain.curator (code): score = severity x confidence x novelty x recency, threshold,
                        at most 1 new card per turn, <= 4 visible, ONE "Ask next" at a time, near-duplicates merged,
                        dismissed themes suppressed for the visit.
  7. fallback           agent off / failed / timed out / no valid card: at most one deterministic "ask" card from
                        the idiom's clarifying questions or the open checklist (source "fallback")
Steps 1-4 never depend on the LLM, so safety alerts cannot be skipped by the agent; rule cards stay the only source
of critical alerts. Held sentences come from the prescription gate's critical rules and, before speech, from the
coherence check (bayan.brain.coherence: one fast call on doctor plans / diagnoses / claims, caution card). Every
step is logged to consult.trace as "tool"/"agent"/"card" lines (the activity feed); per-run latency, tokens and cost go to consult.outputs["metrics"].

Talk-loop hooks: prescription_gate() (sync, no LLM) on doctor turns with drugs, record_allergies() (sync) on
patient turns with allergies, post_idioms() (sync lexicon idiom + "ask" card) on patient turns, on_turn() after every
turn, tick() on the UI timer, ask_card() when the doctor taps "Ask", withdraw_turn() / override_turn() for a held
sentence ("Say something else" / "Speak it anyway"). BAYAN_AGENT=off disables the LLM agent (deterministic fallback
only).
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import agentkit, curator, llm
from .cards import AGENT_KINDS, CardStore, norm_text, quote_in_turn
from .state import fmt_t
from .vocab import repair_drug_items

DEBOUNCE_S = float(os.environ.get("BAYAN_THINK_DEBOUNCE", "1.2"))
# Cost: a doctor's plain question ("Does it spread to your arm?") changes no safety-relevant fact, so its
# extraction waits and is batched with the patient's answer (one LLM call instead of two; the model then sees the
# question and the "yes" together). Prescriptions never wait: the synchronous prescription gate handles them.
DEFER_QUESTIONS = os.environ.get("BAYAN_DEFER_QUESTIONS", "on").lower() not in ("0", "off", "false", "no")
DEFER_MAX_S = float(os.environ.get("BAYAN_DEFER_MAX_S", "20"))   # unanswered question: extract it anyway after this
AGENT_TIMEOUT_S = float(os.environ.get("BAYAN_AGENT_TIMEOUT", "20"))
AGENT_MAX_STEPS = int(os.environ.get("BAYAN_AGENT_MAX_STEPS", "4"))
AGENT_CARDS_PER_RUN = 3
AGENT_TOKEN_CAP = int(os.environ.get("BAYAN_AGENT_TOKEN_CAP", "200000"))   # per consultation
FALLBACK_MAX = 1          # one "Ask next" at a time
TASK_TURNS = 10           # transcript window of the review (the case summary covers everything before it)

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bayan-think")
_DEPS: dict[str, Any] = {}
_DEPS_LOCK = threading.Lock()


def agent_enabled() -> bool:
    return os.environ.get("BAYAN_AGENT", "on").strip().lower() not in ("off", "0", "false", "no")


# ------------------------------------------------------------------ shared deterministic components (lazy)
def set_deps(**kw) -> None:
    """Test hook: engine=, idioms=, merge=, checklist=, normalise_drug=, classes_of=."""
    with _DEPS_LOCK:
        _DEPS.update(kw)


def _dep(name: str):
    with _DEPS_LOCK:
        if name not in _DEPS:
            if name == "engine":
                from .rules import RuleEngine
                _DEPS[name] = RuleEngine()
            elif name == "idioms":
                from .idioms import IdiomIndex
                _DEPS[name] = IdiomIndex()
            elif name == "merge":
                from .merge import merge_delta
                _DEPS[name] = merge_delta
            elif name == "checklist":
                from .checklist import checklist
                _DEPS[name] = checklist
            elif name == "normalise_drug":
                from .vocab import normalise_drug
                _DEPS[name] = normalise_drug
            elif name == "classes_of":
                from .vocab import classes_of
                _DEPS[name] = classes_of
            else:
                raise KeyError(name)
        return _DEPS[name]


def _checklist(consult) -> list[dict]:
    try:
        with consult.lock:
            return list(_dep("checklist")(consult.state, consult.now_min()) or [])
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"get_checklist failed: {e}")
        return []


def _evaluate(consult, now: float | None = None) -> list[dict]:
    with consult.lock:
        return list(_dep("engine").evaluate(consult.state, consult.now_min() if now is None else now) or [])


def _merge(consult, delta: dict) -> set:
    if not delta:
        return set()
    with consult.lock:
        return set(_dep("merge")(consult, delta) or set())


# ------------------------------------------------------------------ per-consultation runtime
class _Runtime:
    def __init__(self):
        self.lock = threading.Lock()
        self.think_lock = threading.Lock()
        self.timer: threading.Timer | None = None
        self.running = False
        self.dirty = False
        self.runs: list[dict] = []
        self.last_fired: set[str] = set()
        self.agent_tokens = 0
        self.last_state: dict | None = None     # state after the previous think run (gate changes count as news)
        self.deferred: list = []                # doctor/Bayan question turns waiting to be extracted with the answer
        self.deferred_since: float | None = None   # wall clock of the oldest deferred turn
        self.force_flush = False


def _rt(consult) -> _Runtime:
    rt = getattr(consult, "_copilot", None)
    if rt is None or getattr(consult, "cards", None) is None:
        attach(consult)
        rt = consult._copilot
    return rt


def _ref_ok(consult, g: str) -> bool:
    """A rule id, idiom id or checklist id: optional context a card may point at."""
    g = (g or "").strip()
    if not g:
        return False
    try:
        if any(r.get("id") == g for r in _dep("engine").rules):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        if _dep("idioms").get(g):
            return True
    except Exception:  # noqa: BLE001
        pass
    return any(c.get("id") == g for c in _checklist(consult))


def _grounding_ok(consult, kind: str, g: str) -> bool:
    """Agent cards are grounded in the transcript (their quotes are verified by CardStore); the grounding field
    holds the review dimension ("plan", "safety", ...) or, optionally, a rule / idiom / checklist id."""
    g = (g or "").strip()
    if g in curator.DIMENSIONS:
        return True
    if _ref_ok(consult, g):
        return True
    return kind == "observation" and consult.turn_by_id(g) is not None


def attach(consult) -> None:
    """Give the consultation a CardStore wired to the shared RuleEngine / IdiomIndex / checklist."""
    consult.cards = CardStore(
        grounding_check=lambda kind, g: _grounding_ok(consult, kind, g),
        turn_lookup=consult.turn_by_id,
        clock=consult.now_min,
        state_version=lambda: consult.state_version,
        log=consult.log,
        audit=consult.audit,
        max_open_ask=1,                  # exactly one "Ask next" on screen (the curator replaces, never stacks)
    )
    consult._copilot = _Runtime()
    for name in ("engine", "idioms"):     # warm the singletons; a missing module is logged, not raised
        try:
            _dep(name)
        except Exception as e:  # noqa: BLE001
            consult.log("error", f"copilot: {name} unavailable ({e})")


# ------------------------------------------------------------------ helpers
def _ev(turn) -> dict:
    return {"utt": turn.id, "t_min": turn.t_min, "quote": (turn.english or turn.text)[:200]}


def _num(x):
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return x
    m = re.search(r"\d+(?:\.\d+)?", str(x))
    return float(m.group(0)) if m else None


def _state_diff(before: dict, after: dict) -> list[str]:
    out: list[str] = []

    def codes(st, key, field="code"):
        return {str(x.get(field)) for x in st.get(key) or [] if isinstance(x, dict)}

    for code in sorted(codes(after, "symptoms") - codes(before, "symptoms")):
        out.append(f"+{code}")
    old_all = {a.get("substance"): a for a in before.get("allergies") or []}
    for a in after.get("allergies") or []:
        if a.get("substance") not in old_all:
            out.append(f"+allergy {a.get('substance')} ({a.get('reaction') or 'reaction unknown'}, "
                       f"{a.get('severity') or 'unknown'})")
    old_rx = {m.get("drug"): m for m in before.get("prescribed_meds") or []}
    new_rx = {m.get("drug"): m for m in after.get("prescribed_meds") or []}
    for d, m in new_rx.items():
        if d not in old_rx:
            dose = f" {m.get('dose_mg')} mg" if m.get("dose_mg") is not None else ""
            freq = f" x{m.get('frequency_per_day')}/day" if m.get("frequency_per_day") else ""
            out.append(f"+rx {d}{dose}{freq}")
    for d in old_rx:
        if d not in new_rx:
            out.append(f"-rx {d}")
    for d in sorted(codes(after, "current_meds", "drug") - codes(before, "current_meds", "drug")):
        out.append(f"+med {d}")
    old_inv = {i.get("code"): i.get("status") for i in before.get("investigations") or []}
    for i in after.get("investigations") or []:
        if old_inv.get(i.get("code")) != i.get("status"):
            out.append(f"{i.get('code')} {i.get('status')}" + (f" ({i.get('result')})" if i.get("result") else ""))
    for key in ("interventions", "assessments"):
        for code in sorted(codes(after, key) - codes(before, key)):
            out.append(f"+{code}")
    for k, v in (after.get("vitals") or {}).items():
        if k != "evidence" and (before.get("vitals") or {}).get(k) != v:
            out.append(f"{k}={v}")
    d_old = (before.get("disposition") or {}).get("type")
    d_new = (after.get("disposition") or {}).get("type")
    if d_new != d_old:
        out.append(f"disposition={d_new}")
    for k, v in (after.get("patient") or {}).items():
        if (before.get("patient") or {}).get(k) != v:
            out.append(f"{k}={v}")
    for q in after.get("questions_asked") or []:
        if q not in (before.get("questions_asked") or []):
            out.append(f"asked:{q}")
    for code in sorted(codes(after, "idiom_hits", "id") - codes(before, "idiom_hits", "id")):
        out.append(f"+idiom {code}")
    oc, nc = before.get("case") or {}, after.get("case") or {}
    cc_new = (nc.get("chief_complaint") or {}).get("text")
    if cc_new and cc_new != (oc.get("chief_complaint") or {}).get("text"):
        out.append(f"complaint: {cc_new[:48]}")
    for key, tag in (("history", "hx"), ("working_diagnosis", "dx"), ("differential", "ddx"), ("plan", "plan"),
                     ("exam_claims", "stated"), ("patient_understanding", "understanding"),
                     ("patient_affect", "affect")):
        old = {x.get("text") for x in oc.get(key) or [] if isinstance(x, dict)}
        for x in nc.get(key) or []:
            if isinstance(x, dict) and x.get("text") not in old:
                sign = {True: "+", False: "-"}.get(x.get("present"), "") if key == "history" else ""
                out.append(f"{tag}: {sign}{str(x.get('text'))[:48]}")
    return out


def _idiom_entry(hit: dict) -> dict | None:
    e = hit.get("entry")
    if isinstance(e, dict):
        return e
    try:
        return _dep("idioms").get(hit.get("id"))
    except Exception:  # noqa: BLE001
        return None


def _post_idiom_card(consult, hit: dict, turn) -> str:
    e = _idiom_entry(hit) or {}
    iid = hit.get("id") or e.get("id")
    rom, nat = e.get("romanized") or hit.get("matched") or iid, e.get("native") or ""
    interp = "; ".join(f"{i.get('meaning')} ({i.get('likelihood')})" for i in e.get("clinical_interpretations") or [])
    masks = "; ".join(e.get("masks_red_flags") or [])
    body = f"Literal: {e.get('literal_en') or '?'}."
    if interp:
        body += f" Likely meanings: {interp}."
    if masks:
        body += f" Can mask: {masks}."
    tags = list(hit.get("red_flag_tags") or e.get("red_flag_tags") or [])
    return consult.cards.post(
        "idiom", f"Idiom: {rom}" + (f" ({nat})" if nat else ""), body, [_ev(turn)], iid,
        severity="caution" if tags else "info", source="lexicon", t_min=turn.t_min,
        idiom={"id": iid, "native": nat, "romanized": rom, "literal_en": e.get("literal_en"),
               "language": e.get("language"), "interpretations": e.get("clinical_interpretations") or [],
               "masks": e.get("masks_red_flags") or [], "questions": e.get("clarifying_questions_en") or [],
               "evidence_level": e.get("evidence_level")},
        red_flag_tags=tags, source_urls=list(e.get("source_urls") or []),
    )


# ------------------------------------------------------------------ prescription gate (sync, no LLM)
def _talk_freq(d: dict, quote: str) -> float | None:
    """Deterministic frequency check on the translator's item: a frequency phrase in the dose as said ("100 mg QDS")
    or, when the model gave none, in the doctor's words about this drug ("tramadol 100 mg QDS, ..."). Returns the
    larger of the model's and the parsed value (dose ceilings must not be under-counted), or None."""
    from .merge import frequency_from_text
    from .vocab import clause_for
    llm_f = _num(d.get("frequency_per_day"))
    parsed = frequency_from_text(d.get("dose")) if d.get("dose") else None
    if parsed is None and llm_f is None and quote:
        parsed = frequency_from_text(clause_for(d.get("name") or d.get("drug") or "", quote))
    vals = [v for v in (llm_f, parsed) if v is not None and v > 0]
    return max(vals) if vals else None


def _talk_med(d: dict, ev: list[dict], quote: str = "") -> dict:
    out = {"drug": (d.get("name") or d.get("drug") or "").strip().lower(), "evidence": ev, "intent": "prescribe"}
    dose_mg = _num(d.get("dose_mg"))
    if dose_mg is not None:
        out["dose_mg"] = dose_mg
    elif d.get("dose"):
        out["dose_raw"] = str(d["dose"])
    for k in ("frequency_per_day", "duration_days", "route", "form", "amount", "unit", "site", "times", "food",
              "interval_hours", "as_needed", "as_needed_for", "max_per_day", "min_hours_between", "duration_text",
              "instructions"):
        if d.get(k) not in (None, "", []):
            out[k] = d[k]
    if d.get("frequency") and "frequency_per_day" not in out:
        out["frequency"] = d["frequency"]
    f = _talk_freq(d, quote)
    if f is not None:
        out["frequency_per_day"] = f
    return out


def prescription_gate(consult, drugs: list[dict], quote: str, utt: str) -> list[dict]:
    """SYNC, no LLM. Called by the talk loop on doctor turns with the translation JSON's drug items
    {"name","dose_mg","frequency_per_day","intent"}. Only intent == "prescribe" counts (a missing intent is treated
    as "prescribe": holding is the safe default); "stop" removes the drug from the state at once.
    Returns the CRITICAL on_prescribe rules that fire (the caller holds the sentence); every hit is carded now."""
    try:
        rt = _rt(consult)
        now = consult.now_min()
        turn = consult.turn_by_id(utt) if utt else None
        ev = [{"utt": utt, "t_min": turn.t_min if turn else now, "quote": quote or (turn.english if turn else "")}]
        said = [quote or "", (turn.english if turn else "") or "", (turn.text if turn else "") or ""]
        # brand / mangled names -> generics before the rules see them ("augmented" for "Augmentin 625")
        drugs = repair_drug_items([dict(d) for d in drugs or [] if isinstance(d, dict)], said)
        cands, stops = [], []
        for d in drugs or []:
            if not isinstance(d, dict) or not (d.get("name") or d.get("drug")):
                continue
            intent = str(d.get("intent") or "prescribe").strip().lower()
            if intent == "prescribe":
                cands.append(_talk_med(d, ev, quote or (turn.english if turn else "")))
            elif intent == "stop":
                stops.append({"drug": (d.get("name") or d.get("drug")).strip().lower(), "evidence": ev})
        hits: list[dict] = []
        if cands:
            with consult.lock:
                hits = list(_dep("engine").check_prescription(consult.state, cands, now) or [])
        delta: dict = {}
        if cands:
            delta["prescribed_meds"] = cands
        if stops:
            delta["remove"] = {"prescribed_meds": stops}
        if delta:
            with consult.lock:
                before = copy.deepcopy(consult.state)
                _merge(consult, delta)
                diff = _state_diff(before, consult.state)
            if diff:
                consult.log("tool", "update_state (prescription gate) → " + ", ".join(diff))
        if not delta:
            return []
        fired = _evaluate(consult, now)
        consult.cards.sync_rules(fired, now)
        if hits:
            consult.cards.add_rule_hits(hits, now)
        rt.last_fired = {f["rule_id"] for f in fired}
        critical = [h for h in hits if h.get("severity") == "critical"]
        names = ", ".join(c["drug"] for c in cands) or "-"
        consult.log("tool", f"check_prescription({names}) → "
                            + (", ".join(h["rule_id"] for h in hits) if hits else "no on_prescribe rule fires")
                            + (" · HOLD" if critical else ""))
        return critical
    except Exception as e:  # noqa: BLE001 - the talk loop must never break
        try:
            consult.log("error", f"prescription_gate failed: {type(e).__name__}: {e}")
        except Exception:  # noqa: BLE001
            pass
        return []


def record_allergies(consult, allergies: list[dict], quote: str, utt: str) -> None:
    """SYNC, no LLM: merge allergies from the talk loop's translation JSON on patient turns at once, so the
    prescription gate never waits for the background extractor. Never raises."""
    try:
        _rt(consult)
        turn = consult.turn_by_id(utt) if utt else None
        ev = [{"utt": utt, "t_min": turn.t_min if turn else consult.now_min(),
               "quote": quote or (turn.english if turn else "")}]
        items = [{"substance": a.get("substance"), "reaction": a.get("reaction"),
                  "severity": a.get("severity") or "unknown", "evidence": ev}
                 for a in allergies or [] if isinstance(a, dict) and a.get("substance")]
        if items:
            with consult.lock:
                before = copy.deepcopy(consult.state)
                _merge(consult, {"allergies": items})
                diff = _state_diff(before, consult.state)
            if diff:
                consult.log("tool", "update_state (talk loop) → " + ", ".join(diff))
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"record_allergies failed: {e}")


_RED_FLAG_Q = re.compile(r"\b(arm|jaw|sweat)", re.I)


def red_flag_question(entry: dict) -> str:
    """One clarifying question for an idiom, red-flag first: an idiom that can hide heart pain gets the question
    about spread / sweating before the others."""
    qs = [q for q in entry.get("clarifying_questions_en") or [] if isinstance(q, str) and q.strip()]
    if not qs:
        return ""
    if "acs" in (entry.get("red_flag_tags") or []):
        for q in qs:
            if _RED_FLAG_Q.search(q):
                return q
    return qs[0]


def post_idioms(consult, turn) -> list[str]:
    """SYNC, no LLM: lexicon match on one patient turn, posted at once (the background think run would post the
    same idiom card ~1-2 s later; CardStore dedupes it). Per matched idiom: the idiom card plus ONE red-flag-first
    "ask" card from its clarifying questions (source "fallback": deterministic, grounded in the idiom id), so the
    doctor's "Ask next" never waits for the agent. Returns the new card ids. Never raises."""
    posted: list[str] = []
    try:
        _rt(consult)
        if getattr(turn, "role", "") != "patient":
            return []
        for m in _dep("idioms").match(turn.text, turn.english, lang=turn.lang) or []:
            e = _idiom_entry(m) or {}
            consult.log("tool", f"lookup_idiom('{m.get('matched')}') → {m.get('id')} (talk loop)")
            res = _post_idiom_card(consult, m, turn)
            if not res.startswith(("rejected", "duplicate")):
                posted.append(res)
            q = red_flag_question(e)
            if q:
                why = (f"'{e.get('romanized') or m.get('matched')}' can mask: "
                       f"{'; '.join(e.get('masks_red_flags') or [])[:160]}")
                res = curator.offer(consult, [{"kind": "ask", "dimension": "safety", "title": q, "body": why,
                                               "evidence": [_ev(turn)], "grounding": m.get("id"), "ask_text": q,
                                               "severity": "info", "confidence": curator.FALLBACK_CONFIDENCE}],
                                    source="fallback")[0]
                if res.startswith("c"):
                    posted.append(res)
    except Exception as e:  # noqa: BLE001
        try:
            consult.log("error", f"post_idioms failed: {type(e).__name__}: {e}")
        except Exception:  # noqa: BLE001
            pass
    return posted


def held_card_ids(consult, hits: list[dict]) -> list[str]:
    """Rule cards that show the given prescription-gate hits (matched on the hit keys, e.g. ALG-PEN-01|amoxicillin)."""
    keys = {str(h.get("key") or h.get("rule_id")) for h in hits or []}
    out = []
    for c in consult.cards.all_cards() if consult.cards is not None else []:
        if c.get("source") == "rules" and any(str(i.get("key")) in keys for i in c.get("items") or []):
            out.append(c["id"])
    return out


def withdraw_turn(consult, utt: str, card_ids: list[str], reason: str) -> None:
    """The doctor chose "Say something else" on a held sentence: it is never interpreted and never extracted
    (kind "system", still in the transcript as held), the medicines the gate recorded from it are taken back out of
    the state, the doctor's choice is audited on the alert cards, and rule cards are re-synced (the allergy
    conflict resolves once the drug is gone). Never raises."""
    try:
        _rt(consult)
        turn = consult.turn_by_id(utt)
        with consult.lock:
            if turn is not None:
                turn.held, turn.kind = True, "system"
            before = copy.deepcopy(consult.state)
            keep = []
            for m in consult.state.get("prescribed_meds") or []:
                ev = [e for e in m.get("evidence") or [] if isinstance(e, dict)]
                rest = [e for e in ev if e.get("utt") != utt]
                if ev and not rest:
                    continue                     # only this sentence prescribed it
                if len(rest) != len(ev):
                    m = dict(m, evidence=rest)
                keep.append(m)
            consult.state["prescribed_meds"] = keep
            diff = _state_diff(before, consult.state)
            if diff:
                consult.state_version += 1
        for cid in card_ids or []:
            card = consult.cards.get(cid)
            if card and card.get("status") == "open":
                consult.cards.act(cid, "acknowledge", reason=reason, user="doctor")
        now = consult.now_min()
        fired = _evaluate(consult, now)
        consult.cards.sync_rules(fired, now)
        _rt(consult).last_fired = {f["rule_id"] for f in fired}
        consult.log("tool", f"withdraw {utt} ({reason})" + (" → " + ", ".join(diff) if diff else ""))
    except Exception as e:  # noqa: BLE001
        try:
            consult.log("error", f"withdraw_turn failed: {type(e).__name__}: {e}")
        except Exception:  # noqa: BLE001
            pass


def override_turn(consult, utt: str, card_ids: list[str], reason: str) -> None:
    """The doctor chose "Speak it anyway": the sentence is interpreted after all (no longer held), the override is
    recorded on every alert card that held it, and the think loop picks the turn up. Never raises."""
    try:
        _rt(consult)
        turn = consult.turn_by_id(utt)
        if turn is not None:
            with consult.lock:
                turn.held = False
        for cid in card_ids or []:
            card = consult.cards.get(cid)
            if card and card.get("status") in ("open", "acknowledged"):
                consult.cards.act(cid, "override", reason=reason, user="doctor")
        consult.log("tool", f"override {utt} ({reason})")
        on_turn(consult, turn)
    except Exception as e:  # noqa: BLE001
        try:
            consult.log("error", f"override_turn failed: {type(e).__name__}: {e}")
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ agent tools (closures per run)
def _j(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, default=str, separators=(",", ":"))


_UTT_RX = re.compile(r"u\d{3,}")


def _parse_evidence(evidence: Any) -> list[dict]:
    """Tolerant evidence parsing -> [{"utt", "quote"}]. Accepts a list of {utt, quote} objects (the schema), a JSON
    string of it, or "u007: words" strings. Bare ids come back with an empty quote (rejected later)."""
    if evidence is None:
        return []
    if isinstance(evidence, str):
        st = evidence.strip()
        if st.startswith(("[", "{")):
            try:
                evidence = json.loads(st)
            except ValueError:
                evidence = [st]
        else:
            evidence = [st]
    if isinstance(evidence, dict):
        evidence = [evidence]
    out = []
    for e in evidence if isinstance(evidence, list) else []:
        if isinstance(e, str):
            m = re.match(r"\s*(u\d{3,})\s*[:\-–]?\s*(.*)$", e, re.S)
            if m:
                out.append({"utt": m.group(1), "quote": m.group(2).strip().strip("\"'“”‘’ ")})
            else:
                out.extend({"utt": u, "quote": ""} for u in _UTT_RX.findall(e))
        elif isinstance(e, dict) and (e.get("utt") or e.get("id")):
            out.append({"utt": str(e.get("utt") or e.get("id")).strip(),
                        "quote": str(e.get("quote") or e.get("text") or "").strip().strip("\"'“”‘’ ")})
    return out


def _parse_utts(evidence: Any) -> list:      # kept for callers of the old helper
    return [{"utt": e["utt"], "quote": e["quote"]} for e in _parse_evidence(evidence)]


def verify_quotes(consult, evidence: list[dict]) -> tuple[list[dict], str | None]:
    """Every quote must really be in the transcript. A quote found in another utterance than the one cited is
    re-pointed there (the words are real; the id was a slip). Returns (evidence, error or None)."""
    if not evidence:
        return [], 'evidence must quote the transcript: [{"utt": "u002", "quote": "<words copied verbatim>"}]'
    with consult.lock:
        turns = [t for t in consult.turns if t.kind != "system"]
    out = []
    for e in evidence:
        q = e.get("quote") or ""
        if not q:
            return [], (f"evidence must quote the transcript: {e.get('utt')} has no quote (copy the few words "
                        "that show the problem)")
        turn = consult.turn_by_id(e.get("utt") or "")
        if not quote_in_turn(turn, q):
            turn = next((t for t in reversed(turns) if quote_in_turn(t, q)), None)
            if turn is None:
                return [], (f"evidence quote not found in the transcript: '{q[:60]}' (copy the words verbatim "
                            f"from {e.get('utt') or 'the utterance'})")
        out.append({"utt": turn.id, "t_min": turn.t_min, "quote": q[:200]})
    return out, None


CARD_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(AGENT_KINDS)},
        "dimension": {"type": "string", "enum": list(curator.DIMENSIONS)},
        "title": {"type": "string", "description": "plain words, at most 8"},
        "body": {"type": "string", "description": "one sentence: why it matters in this consultation"},
        "severity": {"type": "string", "enum": ["info", "caution"]},
        "confidence": {"type": "number", "description": "0-1: would a senior clinician want this raised now?"},
        "evidence": {"type": "array", "items": {"type": "object", "properties": {
            "utt": {"type": "string", "description": "utterance id, e.g. u007"},
            "quote": {"type": "string", "description": "a few words copied verbatim from that utterance"}},
            "required": ["utt", "quote"]}},
        "ask_text": {"type": "string", "description": "kind ask: ONE short plain-English question to the patient"},
        "ref": {"type": "string", "description": "optional: a rule, idiom or checklist id from CONTEXT"},
    },
    "required": ["kind", "dimension", "title", "body", "severity", "confidence", "evidence"],
}
# rejections the model can fix in one retry (vs duplicate / dismissed / held back, which it must simply accept)
_FIXABLE = ("kind ", "severity", "only the rule engine", "title is required", "evidence must", "evidence quote",
            "ask cards need", "each card", "cards must")


def _covered_by_fired(consult) -> dict[str, str]:
    """{code or checklist id: rule id} for workup the fired rules already flag (none_in clauses), so the agent
    cannot post a "missed ECG" card next to the rule card that says the same."""
    out: dict[str, str] = {}
    try:
        engine = _dep("engine")
        by_id = {r["id"]: r for r in engine.rules}
        for rid in _rt(consult).last_fired:
            stack = [by_id.get(rid, {}).get("trigger")]
            while stack:
                n = stack.pop()
                if isinstance(n, list):
                    stack.extend(n)
                elif isinstance(n, dict):
                    if n.get("none_in") and isinstance(n.get("where"), dict):
                        vals = n["where"].get("value")
                        for v in vals if isinstance(vals, list) else [vals]:
                            if isinstance(v, str):
                                out.setdefault(v, rid)
                    for k in ("all", "any", "none"):
                        stack.extend(n.get(k) or [])
        for item in _checklist(consult):        # checklist ids whose code is covered (troponin_hs -> troponin)
            if item.get("status") != "done" and item.get("kind") != "question":
                iid = str(item.get("id") or "")
                hit = next((rid for code, rid in out.items() if code == iid or code.startswith(iid)
                            or iid.startswith(code)), None)
                if hit:
                    out.setdefault(iid, hit)
    except Exception:  # noqa: BLE001
        pass
    return out


def _candidate(consult, c: dict, covered: dict) -> tuple[dict | None, str | None]:
    """One proposed card -> (validated candidate, None) or (None, rejection reason)."""
    ask_text = str(c.get("ask_text") or c.get("question") or "").strip() or None
    kind = str(c.get("kind") or ("ask" if ask_text else "")).strip().lower()
    title = " ".join(str(c.get("title") or ask_text or "").split())[:90]
    body = " ".join(str(c.get("body") or c.get("why") or "").split())[:300]
    severity = str(c.get("severity") or ("info" if kind == "ask" else "caution")).strip().lower()
    ref = str(c.get("ref") or c.get("grounding") or c.get("grounding_id") or "").strip()
    dim = str(c.get("dimension") or "").strip().lower()
    if kind in curator.DIMENSIONS:              # the dimension written into "kind": unambiguous, repaired
        dim, kind = dim or kind, ("ask" if ask_text else "observation")
    if kind not in AGENT_KINDS:
        return None, f"kind '{kind}' must be one of {', '.join(AGENT_KINDS)}"
    if severity == "critical":
        return None, "only the rule engine can raise critical alerts (use caution)"
    if severity not in ("info", "caution"):
        return None, "severity must be info or caution"
    if not title:
        return None, "title is required"
    if kind == "ask" and not ask_text:
        if title.endswith("?"):
            ask_text = title
        else:
            return None, "ask cards need ask_text: one plain English question for the patient"
    if kind == "missed" and ref in covered:
        return None, f"duplicate (already on screen as rule {covered[ref]})"
    ev, err = verify_quotes(consult, _parse_evidence(c.get("evidence")))
    if err:
        return None, err
    grounding = ref if ref and ref not in curator.DIMENSIONS and _ref_ok(consult, ref) else ""
    if dim not in curator.DIMENSIONS:
        dim = ref if ref in curator.DIMENSIONS else ("history" if kind == "ask" else "consistency")
    return {"kind": kind, "dimension": dim, "title": title, "body": body or title, "severity": severity,
            "confidence": c.get("confidence"), "evidence": ev, "ask_text": ask_text,
            "grounding": grounding or dim}, None


def post_cards(consult, cards: Any, cancel: threading.Event | None = None, source: str = "agent",
               cap: int = AGENT_CARDS_PER_RUN, addressed: Any = None) -> list[str]:
    """Validate agent-proposed concerns (kind, severity <= caution, verified transcript quotes) and hand them to the
    curator, which decides what reaches the screen. Tolerant of sloppy tool calls: JSON strings, a single object,
    missing optional fields. Returns one result per card: card id, "duplicate ...", "held back: ...", or
    "rejected: <why>"."""
    if cancel is not None and cancel.is_set():
        return ["cancelled: this copilot run timed out"]
    if isinstance(addressed, str):
        addressed = re.findall(r"c\d{3,}", addressed)
    addressed = [str(a) for a in addressed or [] if a]
    if cards is None:
        cards = []
    if isinstance(cards, str):
        try:
            cards = json.loads(cards) if cards.strip() else []
        except ValueError:
            return ["rejected: cards must be a JSON list of card objects"]
    if isinstance(cards, dict):
        cards = cards["cards"] if isinstance(cards.get("cards"), list) else [cards]
    if not isinstance(cards, list):
        return ["rejected: cards must be a list of card objects"]
    covered = _covered_by_fired(consult)
    out: list[str | None] = [None] * len(cards)
    valid: list[tuple[int, dict]] = []
    now = consult.now_min()
    for i, c in enumerate(cards):
        if i >= cap:
            out[i] = f"rejected: at most {cap} cards per review"
            continue
        if not isinstance(c, dict):
            out[i] = "rejected: each card must be an object"
            continue
        cand, why = _candidate(consult, c, covered)
        if cand is None:
            if why.startswith("duplicate"):
                out[i] = why
            else:
                out[i] = consult.cards.reject(str(c.get("kind") or ""), str(c.get("title") or ""), why,
                                              source=source, severity=str(c.get("severity") or ""),
                                              grounding=str(c.get("ref") or c.get("grounding") or ""), t_min=now)
            continue
        valid.append((i, cand))
    if valid or addressed:
        res = curator.offer(consult, [c for _i, c in valid], addressed=addressed, source=source)
        for (i, _c), r in zip(valid, res):
            out[i] = r
    return [r or "rejected" for r in out]


def build_tools(consult, cancel: threading.Event, outcome: dict | None = None) -> list:
    """The copilot's smolagents tools, bound to this consultation: read-only lookups + final_answer, which hands
    the concerns to the curator and ends the run (it replaces smolagents' default final_answer, so a typical run is
    ONE LLM step). A fixable mistake (missing or invented quote, missing kind, critical severity) raises once with a
    short message, which smolagents shows the model as the step error: one retry."""
    from smolagents import tool

    attempts = {"n": 0}
    outcome = outcome if outcome is not None else {}

    @tool
    def lookup_idiom(phrase: str, lang: str = "") -> str:
        """Lexicon entry for a patient's idiom of distress: literal meaning, likely meanings, red flags it can mask,
        clarifying questions.

        Args:
            phrase: The idiom as said, native script or romanized, e.g. "gyastrik".
            lang: ISO 639-1 code of the patient's language, e.g. "ne" (optional).
        """
        r = _dep("idioms").lookup(phrase, lang or None)
        if not r:
            return _j({"match": None})
        e = r.get("entry") if isinstance(r.get("entry"), dict) else r
        return _j({"id": e.get("id"), "native": e.get("native"), "romanized": e.get("romanized"),
                   "literal_en": e.get("literal_en"), "clinical_interpretations": e.get("clinical_interpretations"),
                   "masks_red_flags": e.get("masks_red_flags"),
                   "clarifying_questions_en": e.get("clarifying_questions_en"), "red_flag_tags": e.get("red_flag_tags")})

    @tool
    def lookup_drug(name: str, dose_mg: float = None, frequency_per_day: float = None) -> str:  # noqa: RUF013
        """Generic name and classes of a drug, the curated safety rules that mention it, and the prescribing rules
        that WOULD fire for THIS patient (allergies, current medicines, pregnancy, dose ceilings) if it were given.

        Args:
            name: Drug name as said (brand or generic), e.g. "Augmentin".
            dose_mg: Single dose in mg, if known (optional).
            frequency_per_day: Doses per day, if known (optional).
        """
        inn = _dep("normalise_drug")(name)
        classes = list(_dep("classes_of")(inn) or [])
        needles = {f'"{x}"' for x in [inn] + classes if x}
        rules = []
        for r in _dep("engine").rules:
            blob = json.dumps(r.get("trigger"), ensure_ascii=False).lower()
            if any(n in blob for n in needles):
                rules.append(f"{r['id']} ({r.get('severity')}): {(r.get('message_en') or '')[:120]}")
        cand = {"drug": inn or name, "intent": "prescribe"}
        if dose_mg is not None:
            cand["dose_mg"] = dose_mg
        if frequency_per_day is not None:
            cand["frequency_per_day"] = frequency_per_day
        try:
            with consult.lock:
                hits = _dep("engine").check_prescription(consult.state, [cand], consult.now_min()) or []
        except Exception:  # noqa: BLE001
            hits = []
        return _j({"id": inn, "classes": classes, "rules": rules[:8],
                   "would_fire_for_this_patient": [f"{h.get('rule_id')} ({h.get('severity')}): "
                                                    f"{(h.get('message') or '')[:140]}" for h in hits[:5]]})

    @tool
    def check_safety_rules() -> str:
        """Safety rules firing on the current state (read-only; already listed in the task and on screen)."""
        return _j([f"{f.get('rule_id')} ({f.get('severity')}): {f.get('message')}" for f in _evaluate(consult)])

    @tool
    def final_answer(cards: list = None, addressed: list = None) -> str:  # noqa: RUF013 - smolagents needs bare `list`
        """Hand your review to Bayan and end this run. Call it once; cards=[] when nothing needs the doctor now.

        Args:
            cards: 0-2 concerns {kind, dimension, title, body, severity, confidence, evidence: [{utt, quote}], ask_text, ref}, most important first.
            addressed: ids of YOUR CARDS ON SCREEN that the conversation has now dealt with (e.g. ["c004"]).
        """
        res = post_cards(consult, cards, cancel, addressed=addressed)
        attempts["n"] += 1
        outcome.setdefault("results", []).extend(res)
        bad = [f"card {i + 1}: {r[len('rejected: '):]}" for i, r in enumerate(res)
               if r.startswith("rejected: ") and any(k in r for k in _FIXABLE)]
        if bad and attempts["n"] == 1 and not (cancel is not None and cancel.is_set()):
            ok = [r for r in res if not r.startswith("rejected")]
            raise ValueError(("Accepted: " + ", ".join(ok) + ". " if ok else "")
                             + "Fix and call final_answer again with only the corrected cards: " + "; ".join(bad))
        return "; ".join(res) if res else "no cards"

    final_answer.inputs["cards"]["items"] = CARD_ITEM_SCHEMA     # full item schema for the provider
    final_answer.inputs["addressed"]["items"] = {"type": "string"}
    return [lookup_idiom, lookup_drug, check_safety_rules, final_answer]


INSTRUCTIONS = """You are Bayan's clinical copilot: a senior clinician quietly reviewing a consultation while it happens, in
an urgent-care clinic in Qatar. Bayan interprets between a licensed doctor (English or Arabic) and a patient who speaks
another language (Nepali, Hindi, Bengali, Tagalog, Russian, ...). You see the running CASE SUMMARY, the recent
TRANSCRIPT and what is already on the doctor's screen. You propose at most two short cards; deterministic code then
decides which one, if any, the doctor sees. Reason about THIS patient and THIS conversation, whatever the complaint.

Review it like a second clinician along five dimensions:
1. safety: dangerous causes of this complaint that nobody has ruled out yet (red flags, can't-miss diagnoses).
2. history: the single most useful next question for this complaint, if a key question is still missing (kind "ask").
3. plan: does the treatment fit the complaint and the working diagnosis (right problem, right body part, a reason
   for it)? Is each prescription complete (named drug, strength, dose, route, frequency, duration)? Any
   contraindication with this patient's allergies, medicines, pregnancy or age (lookup_drug checks the rule engine)?
4. communication: does the patient understand what to do and why? Confusion or a question left unanswered, no
   explanation or teach-back, mood or safety cues (hopelessness, low mood, feeling a burden) said in passing and
   not followed up.
5. consistency: claims not backed by any finding (a value or result stated but never measured or reported in this
   visit), contradictions between what the doctor says and what the patient said, a diagnosis the history argues
   against, a symptom the patient raised (especially more than once) that the doctor has not responded to.

Patient turns show the words AS SAID ("said (ne): ...") and Bayan's live English rendering ("EN rendering: ...").
Judge the ORIGINAL meaning. If the rendering softens, drops or changes something clinically important (a mood or
safety cue, a symptom, a "no" that became "yes"), that is itself a card: an "observation" (communication) saying
what the patient actually said, quoting the original words, so the doctor can ask again.

Each review, check ALL five dimensions against the whole conversation so far, then report what matters most:
- Compare EVERY clinical claim the doctor makes (a finding, a vital sign, a test result, "normal", "fine", "you
  have X") with what was actually measured or reported in this visit (RECORDED FACTS, CASE SUMMARY, transcript).
  A claim with nothing behind it is a consistency concern, whatever the claim is about.
- Evaluate each distinct problem separately: a plan that does not fit, an incomplete prescription and a patient
  who misunderstood are separate concerns when the evidence differs; propose the most important first.
- Something that does not make sense or could harm (plan, consistency, communication) outranks a routine history
  question. A doctor stating a finding (temperature, blood pressure, a test result) that RECORDED FACTS and the
  transcript do not show was measured is a consistency problem. A plan that treats another body part or another
  problem than the complaint is a plan problem.
- Feelings said in passing ("no mood", "no point living", "tension", "my heart feels heavy") are clinically
  important cues even in a visit about something else: words about the heart, chest or head are often idioms for
  emotions, so weigh the emotional meaning (and ask about it) before a cardiac or neurological one when the rest
  of the sentence is about mood.
- Complete means the patient could take it correctly and safely: a medicine with no name, no dose or no frequency is
  incomplete; do not demand details a clinician would not normally say (the strength of a standard product). A
  standard as-needed instruction ("two puffs when needed", "one tablet up to three times a day if needed") is
  complete.
- Propose an "ask" only when its answer would change management or safety now (a red flag, a contraindication, a
  diagnosis that hinges on it). Routine completeness questions a competent doctor will ask anyway are not worth a
  card; in a routine follow-up or refill, the usual right answer is no question at all.
Raise a card only if a careful senior colleague would lean over and say it now. A routine, coherent visit deserves
no card: an empty list is the most common correct answer. Never nitpick wording, style or generic advice, and do
not ask about things the transcript already answers. A missing routine history question is "info" with modest
confidence (0.5-0.7), not "caution".

Authority rules (enforced in code; breaking them gets the card rejected):
- You never diagnose, prescribe, change a dose, reassure, or speak to the patient. You only PROPOSE to the doctor.
- Critical alerts come only from the deterministic rule engine. Your severity is "caution" (could harm the patient,
  or clearly does not make sense) or "info" (useful, not urgent). Never "critical".
- Every card quotes the transcript: evidence = [{"utt": "u007", "quote": "<a few words copied verbatim from that
  utterance>"}] (from its EN rendering or the words as said). Invented or paraphrased quotes are rejected.
- Do not repeat what is on screen (RULE ALERTS, YOUR CARDS ON SCREEN, ASK NEXT); never raise a DISMISSED theme again.

Card fields:
- kind: "ask" (a question for the patient; ask_text = ONE short plain-English question a patient with little
  schooling understands: no jargon, not two questions in one), "missed" (something not done or not asked that
  matters now), "observation" (something that does not add up, or a cue to notice).
- dimension: safety | history | plan | communication | consistency.
- title: plain words, at most 8. body: one sentence, why it matters here.
- confidence: 0-1, how sure you are a senior clinician would want this raised now (0.9 clear problem or danger,
  0.6 useful, below 0.4 do not post it). Calibrate: most questions are 0.5-0.7; reserve 0.8+ for questions whose
  answer could change what happens to the patient today. Questions ("ask") are suggestions: severity "info".
- ref (optional): a fired rule id, idiom id or checklist id from CONTEXT when the card is about it.
Also return addressed: the ids of YOUR CARDS ON SCREEN that the conversation has dealt with since (the doctor asked
it, explained it, measured it, or changed the plan).

Edge cases:
- A companion may answer for the patient: that is history; on sensitive topics (self-harm, pregnancy, abuse, money)
  suggest asking the patient directly.
- Code-switching and idioms are normal ("gyastrik", "pressure", "tension"): read the EN rendering and IDIOM HITS;
  an idiom can hide a red flag.
- A bare "yes" to a long two-part question may not mean yes to both parts.
- Doctor turns ending in "?" mean that topic is being covered: do not propose the same question.
- Once the plan is given, history that no longer changes anything is noise; plan fit, understanding and
  safety-netting matter.

Examples (shape only; use the real ids and words of the transcript):
{"kind": "ask", "dimension": "safety", "title": "Ask about weakness or speech change", "body": "A sudden severe headache needs a bleed or stroke excluded; no neurological question yet.", "severity": "info", "confidence": 0.8, "evidence": [{"utt": "u002", "quote": "worst headache of my life"}], "ask_text": "Is one arm or leg weak, or is your speech different?"}
{"kind": "observation", "dimension": "consistency", "title": "Onset differs from the patient's account", "body": "The patient said the cough began two weeks ago; the doctor's summary says since yesterday.", "severity": "caution", "confidence": 0.7, "evidence": [{"utt": "u002", "quote": "for two weeks"}, {"utt": "u006", "quote": "since yesterday"}]}
{"kind": "missed", "dimension": "communication", "title": "No advice on when to come back", "body": "Sent home with breathlessness and no return advice if it worsens.", "severity": "info", "confidence": 0.6, "evidence": [{"utt": "u008", "quote": "you can go home"}]}

Answer with ONE call: final_answer(cards=[...], addressed=[...]) with 0-2 cards, most important first. Use a
lookup tool before it only when you really need it. If final_answer returns an error, fix only those cards and call
it once more."""


def _task_prompt(consult, new_turns: list, fired: list[dict], checklist_items: list[dict]) -> str:
    from .extract import _compact_state, case_text, said_line
    new_ids = {t.id for t in new_turns}
    with consult.lock:
        state_txt = _compact_state(consult.state)
        case_txt = case_text(consult.state)
        hits = list(consult.state.get("idiom_hits") or [])
        turns = [t for t in consult.turns if t.kind != "system"]
    recent = turns[-max(TASK_TURNS, len(new_turns)):]
    lines = ["CASE SUMMARY:", case_txt, "", "RECORDED FACTS (structured; vitals and results only if stated):",
             state_txt, "",
             f"TRANSCRIPT ({'last ' + str(len(recent)) + ' of ' + str(len(turns)) if len(recent) < len(turns) else 'all'}"
             " turns; * = new since your last review):"]
    lines += [("* " if t.id in new_ids else "  ") + said_line(t) for t in recent]
    cards = consult.cards.all_cards()
    lines += ["", "ON SCREEN NOW", "RULE ALERTS: " + ("; ".join(
        f"{c['title'].split(' · ')[0]} ({', '.join(c.get('rule_ids') or [])})" for c in cards
        if c["source"] == "rules" and c["status"] == "open") or "none")]
    mine = [c for c in cards if c["source"] in ("agent", "fallback") and c["status"] == "open"]
    lines.append("YOUR CARDS ON SCREEN: " + ("; ".join(
        f"{c['id']} [{c.get('dimension') or c['kind']}] {c['title']}" for c in mine if c["kind"] != "ask") or "none"))
    ask = next((c for c in mine if c["kind"] == "ask"), None)
    lines.append("ASK NEXT: " + (f"{ask['id']} \"{ask.get('ask_text')}\"" if ask else "none"))
    lines.append("DISMISSED BY THE DOCTOR (never again): " + ("; ".join(
        c["title"] for c in cards if c["status"] == "dismissed") or "none"))
    lines += ["", "CONTEXT (optional references; not a list of what to look for)", "FIRED RULES: " + (", ".join(
        f.get("rule_id") for f in fired) or "none")]
    idi = []
    for h in hits:
        e = _idiom_entry(h) or {}
        qs = " | ".join((e.get("clarifying_questions_en") or [])[:2])
        means = "; ".join(f"{i.get('meaning')} ({i.get('likelihood')})" for i in e.get("clinical_interpretations")
                          or [] if isinstance(i, dict) and i.get("meaning"))[:220]
        idi.append(f"{h.get('id')} '{e.get('romanized') or h.get('matched')}' ({h.get('utt')})"
                   + (f" literally '{e.get('literal_en')}'" if e.get("literal_en") else "")
                   + (f": usually means {means}" if means else "")
                   + f"; can mask {'; '.join(m.split(':')[0] for m in e.get('masks_red_flags') or []) or '-'}"
                   + (f"; ask: {qs}" if qs else ""))
    lines.append("IDIOM HITS: " + ("; ".join(idi) or "none"))
    covered = _covered_by_fired(consult)
    open_items = [c for c in checklist_items if c.get("status") != "done" and c.get("id") not in covered]
    lines.append("OPEN CHECKLIST: " + (", ".join(f"{c.get('id')} ({c.get('label')})" for c in open_items[:10])
                                       or "none"))
    return "\n".join(lines)


# ------------------------------------------------------------------ deterministic fallback
_TOPIC_QUESTIONS = [
    (("radiat", "spread"), "Does the pain spread to your arm, jaw, neck or back?"),
    (("exert", "exercise", "effort"), "Does it come on when you work, walk or climb stairs, and ease with rest?"),
    (("sweat", "breath", "dyspn"), "Do you sweat or feel short of breath when it happens?"),
    (("allerg",), "Are you allergic to any medicine?"),
    (("onset", "start"), "When did it start?"),
    (("black_stool", "melaena", "vomit", "haemat"), "Have you had black stools or vomited blood?"),
]
_RED_FLAG_WORDS = ("arm", "jaw", "sweat", "breath", "back", "neck", "black", "blood", "faint", "work", "walk")


def _question_for(item: dict) -> str | None:
    if item.get("ask_en"):
        return item["ask_en"]
    if item.get("kind") and item.get("kind") != "question":
        return None
    key = f"{item.get('id', '')} {item.get('label', '')}".lower()
    if any(w in key for w in ("ecg", "troponin", "bp", "blood pressure", "temperature", "test")) \
            and not any(w in key for w in ("ask", "question")):
        return None
    for words, q in _TOPIC_QUESTIONS:
        if any(w in key for w in words):
            return q
    return None


def fallback_cards(consult, reason: str) -> list[str]:
    """At most one "ask" card from the idioms' clarifying questions and the open checklist (no LLM), only when no
    "Ask next" question is open."""
    posted: list[str] = []
    try:
        open_items = [c for c in _checklist(consult) if c.get("status") != "done"]
        open_keys = " ".join(f"{c.get('id', '')} {c.get('label', '')}" for c in open_items).lower()
        with consult.lock:
            hits = list(consult.state.get("idiom_hits") or [])
            symptoms = list(consult.state.get("symptoms") or [])
        cands: list[tuple[float, str, str, str, list[dict]]] = []   # (score, question, grounding, why, evidence)
        for h in reversed(hits):
            e = _idiom_entry(h) or {}
            turn = consult.turn_by_id(h.get("utt") or "")
            ev = [_ev(turn)] if turn else []
            for i, q in enumerate(e.get("clarifying_questions_en") or []):
                ql = q.lower()
                score = sum(w in ql for w in _RED_FLAG_WORDS) + sum(
                    any(w in ql for w in words) and any(w in open_keys for w in words) for words, _ in _TOPIC_QUESTIONS)
                cands.append((score - 0.01 * i, q, h.get("id"),
                              f"'{e.get('romanized') or h.get('matched')}' can mask: "
                              f"{'; '.join(e.get('masks_red_flags') or [])[:160]}", ev))
        sym_ev = next((s.get("evidence") for s in symptoms if s.get("evidence")), [])
        for c in open_items:
            q = _question_for(c)
            if q:
                cands.append((1.5, q, c.get("id"), f"Checklist: {c.get('label')} is still open.", sym_ev))
        cands.sort(key=lambda x: -x[0])
        if any(c["kind"] == "ask" for c in consult.cards.open_cards()):
            cands = []                           # one "Ask next" at a time: the open one stays
        seen: list[str] = []
        for _score, q, grounding, why, ev in cands:
            if len(posted) >= FALLBACK_MAX:
                break
            if not ev or any(norm_text(q) == s for s in seen):
                continue
            seen.append(norm_text(q))
            res = curator.offer(consult, [{"kind": "ask", "dimension": "safety", "title": q, "body": why,
                                           "evidence": ev, "grounding": grounding, "ask_text": q, "severity": "info",
                                           "confidence": curator.FALLBACK_CONFIDENCE}], source="fallback")[0]
            if res.startswith("c"):
                posted.append(res)
        consult.log("agent", f"fallback ({reason}): {len(posted)} ask card(s)" + (f" {', '.join(posted)}" if posted else ""))
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"fallback failed: {e}")
    return posted


# ------------------------------------------------------------------ the think run
_TRIVIAL_WORDS = {
    "yes", "yeah", "yep", "no", "nope", "ok", "okay", "thank", "thanks", "you", "doctor", "sir", "madam", "maam",
    "fine", "alright", "all", "right", "sure", "hmm", "mm", "i", "agree", "understand", "understood", "good", "very",
    "much", "please", "hello", "hi", "bye", "goodbye", "namaste", "dhanyabad", "dhanyavad", "huncha", "ho", "hajur",
}


_ANSWER_WORDS = {"yes", "yeah", "yep", "no", "nope", "ho", "hajur", "haan", "na", "hindi", "oo"}


def is_trivial(turn, consult=None) -> bool:
    """Courtesy turns that cannot change the clinical picture ("okay, thank you, doctor"). A bare yes/no that
    answers a question from the doctor (or Bayan) is NOT trivial: "Does it spread to your arm?" - "Yes"."""
    words = norm_text(turn.english or turn.text).split()
    if not (len(words) <= 6 and all(w in _TRIVIAL_WORDS | _ANSWER_WORDS for w in words)):
        return False
    if consult is not None and any(w in _ANSWER_WORDS for w in words):
        with consult.lock:
            idx = next((i for i, t in enumerate(consult.turns) if t.id == turn.id), None)
            prev = next((t for t in reversed(consult.turns[:idx]) if t.role != turn.role and t.kind != "system"),
                        None) if idx else None
        if prev is not None and (prev.english or prev.text).strip().endswith(("?", "؟")):
            return False
    return True


_FACT_WORDS = re.compile(
    r"\b(ecg|ekg|tracing|troponin|test|blood|urine|x-?ray|scan|ct|mri|ultrasound|admit|home|refer|discharge|"
    r"give|prescrib\w*|take|tablet|capsule|injection|drip|mg|gram|grams|ml|dose|stop|no more|result|normal|"
    r"pressure|temperature|pulse|oxygen|sugar)\b", re.I)


def is_deferrable(turn) -> bool:
    """A doctor (or doctor-approved Bayan) QUESTION with no fact in it: no number, no test/order/result/
    disposition/medicine word. Its extraction can wait for the patient's answer without delaying any alert."""
    if not DEFER_QUESTIONS or turn.role not in ("doctor", "bayan"):
        return False
    text = (turn.english or turn.text or "").strip()
    return bool(text) and text.endswith(("?", "؟")) and not re.search(r"\d", text) and not _FACT_WORDS.search(text)


def _record_metrics(consult, summary: dict) -> None:
    ein, eout = summary["extract_tokens"]
    ain, aout = summary["agent_tokens"]
    agent = summary.get("agent") or {}
    m = {"t_min": round(consult.now_min(), 2), "kind": "think", "turns": summary["new_turns"],
         "latency_s": round(summary["latency_s"], 2), "extract_s": round(summary.get("extract_s", 0.0), 2),
         "agent_s": round(agent.get("latency_s", 0.0), 2), "agent_steps": agent.get("steps", 0),
         "agent_ran": bool(agent), "agent_skipped": summary.get("agent_skipped"),
         "agent_cards": sum(1 for r in summary.get("curation") or [] if re.match(r"c\d+$", r)),
         "held_back": sum(1 for r in summary.get("curation") or [] if r.startswith("held back")),
         "fallback": len(summary.get("fallback") or []),
         "input_tokens": ein + ain, "output_tokens": eout + aout,
         "extract_tokens": [ein, eout], "agent_tokens": [ain, aout],
         "cost_usd": round(summary.get("extract_cost", llm.cost_usd(llm.LLM_PROVIDER, ein, eout))
                           + agentkit.cost_usd(ain, aout), 6)}
    try:
        with consult.lock:
            lst = consult.outputs.setdefault("metrics", [])
            if not isinstance(lst, list):      # someone stored a dict there (wrap-up): keep ours separately
                lst = consult.outputs.setdefault("think_metrics", [])
            lst.append(m)
    except Exception:  # noqa: BLE001
        pass


def think_now(consult, flush: bool = False) -> dict:
    """Synchronous think run over the turns not yet processed. Never raises; returns a summary dict (also
    appended to consult.outputs["metrics"] as latency/token/cost numbers). flush=True also extracts any doctor
    questions still waiting for an answer (wrap-up, or a question left unanswered for DEFER_MAX_S)."""
    from .extract import extract_delta_ex, keyword_delta
    rt = _rt(consult)
    summary: dict[str, Any] = {"new_turns": [], "state_changes": [], "fired": [], "idiom_hits": [],
                               "cards": [], "agent": None, "agent_skipped": None, "fallback": [], "latency_s": 0.0,
                               "extract_s": 0.0, "extract_tokens": [0, 0], "agent_tokens": [0, 0]}
    with rt.think_lock:
        t0 = time.time()
        try:
            with consult.lock:
                new_turns = [t for t in consult.turns[consult.agent_seen:] if t.kind != "system"]
                consult.agent_seen = len(consult.turns)
            summary["new_turns"] = [t.id for t in new_turns]
            cards_before = {c["id"] for c in consult.cards.all_cards()}
            now = consult.now_min()
            speech = [t for t in new_turns if t.kind in ("speech", "ask")]

            # 1. idioms (deterministic) on new patient turns
            hits: list[tuple[dict, Any]] = []
            known = {h.get("id") for h in consult.state.get("idiom_hits") or []}
            for t in new_turns:
                if t.role != "patient":
                    continue
                try:
                    matches = _dep("idioms").match(t.text, t.english, lang=t.lang) or []
                except Exception as e:  # noqa: BLE001
                    consult.log("error", f"lookup_idiom failed: {e}")
                    matches = []
                for m in matches:
                    consult.log("tool", f"lookup_idiom('{m.get('matched')}') → {m.get('id')}")
                    hits.append((m, t))
            idiom_delta = [{"id": m.get("id"), "red_flag_tags": list(m.get("red_flag_tags") or []), "utt": t.id,
                            "t_min": t.t_min, "matched": m.get("matched"), "evidence": [_ev(t)]}
                           for m, t in hits if m.get("id") not in known]
            summary["idiom_hits"] = [m.get("id") for m, _t in hits]
            for m, t in hits:            # idiom cards go up at once, before the LLM extraction call
                _post_idiom_card(consult, m, t)

            # 2. extraction (one LLM call, skipped for courtesy turns, plain doctor questions batched with the
            #    answer) + merge
            candidates = [t for t in speech if not is_trivial(t, consult)]
            with rt.lock:
                flush = flush or rt.force_flush
                rt.force_flush = False
                if candidates and not flush and all(is_deferrable(t) for t in candidates):
                    rt.deferred.extend(candidates)
                    rt.deferred_since = rt.deferred_since or time.time()
                    consult.log("tool", "update_state deferred: " + ", ".join(t.id for t in candidates)
                                + " (question, batched with the answer)")
                    candidates = []
                elif candidates or (flush and rt.deferred):
                    candidates = sorted({t.id: t for t in rt.deferred + candidates}.values(), key=lambda t: t.id)
                    rt.deferred, rt.deferred_since = [], None
            to_extract = candidates
            delta: dict = {}
            if to_extract:
                u0 = (llm.USAGE["prompt_tokens"], llm.USAGE["completion_tokens"], llm.USAGE["cost_usd"])
                te = time.time()
                delta, err = extract_delta_ex(consult, to_extract)
                summary["extract_s"] = time.time() - te
                if err is not None:
                    delta = keyword_delta(consult, to_extract)
                    summary["extract_error"] = err
                    if delta:
                        consult.log("tool", "update_state (keyword fallback) → "
                                            + ", ".join(["+" + x["code"] for x in delta.get("symptoms") or []]
                                                      + [f"{k}={v}" for k, v in (delta.get("patient") or {}).items()]))
                summary["extract_tokens"] = [llm.USAGE["prompt_tokens"] - u0[0],
                                             llm.USAGE["completion_tokens"] - u0[1]]
                summary["extract_cost"] = llm.USAGE["cost_usd"] - u0[2]   # priced at the provider actually used
            if idiom_delta:
                delta = dict(delta)
                delta["idiom_hits"] = list(delta.get("idiom_hits") or []) + idiom_delta
            with consult.lock:
                before = copy.deepcopy(consult.state)
                since_last = rt.last_state if rt.last_state is not None else before
                try:
                    _merge(consult, delta)
                except Exception as e:  # noqa: BLE001
                    consult.log("error", f"update_state merge failed: {e}")
                diff = _state_diff(before, consult.state)
                news_diff = _state_diff(since_last, consult.state)
                rt.last_state = copy.deepcopy(consult.state)
            summary["state_changes"] = diff
            if to_extract or idiom_delta:
                consult.log("tool", "update_state → " + (", ".join(diff) if diff else "no new facts"))

            # 3. rules -> rule cards
            fired = _evaluate(consult, now)
            ids = [f.get("rule_id") for f in fired]
            summary["fired"] = ids
            consult.log("tool", "check_safety_rules → " + (", ".join(ids) if ids else "none"))
            consult.cards.sync_rules(fired, now)
            rt.last_fired = set(ids)

            # 4. agent/fallback ask and missed cards whose checklist item is now done resolve themselves
            #    (e.g. "Troponin not ordered" once the doctor orders it); rule cards resolve via sync_rules; the
            #    open "Ask next" resolves when the doctor asks the same thing in their own words
            done = {c.get("id") for c in _checklist(consult) if c.get("status") == "done"}
            for c in consult.cards.open_cards():
                if c["kind"] in ("ask", "missed") and c["source"] != "rules" and c["grounding"] in done:
                    consult.cards.resolve(c["id"], "checklist item done", now)
            curator.resolve_asked(consult, speech)

            # 5. clinical review (agent) + curation / 6. fallback, on every substantive turn: not courtesy turns,
            #    not a doctor question still waiting for its answer (reviewed together with the answer)
            waiting = {t.id for t in rt.deferred}
            substantive = [t for t in speech if t.id not in waiting and not is_trivial(t, consult)]
            summary["news"] = [d for d in news_diff if not d.startswith("asked:")][:12]
            if speech and not substantive:
                summary["agent_skipped"] = "nothing new"
                consult.log("agent", "copilot skipped: nothing new in " + ", ".join(t.id for t in speech))
            elif speech:
                reason = None
                if not agent_enabled():
                    reason = "agent off"
                elif not agentkit.available():
                    reason = "no model (HF_TOKEN not set)"
                elif rt.agent_tokens >= AGENT_TOKEN_CAP:
                    reason = "token cap reached"
                if reason is None:
                    cancel = threading.Event()
                    task = _task_prompt(consult, speech, fired, _checklist(consult))
                    outcome: dict = {}
                    res = agentkit.run_agent(build_tools(consult, cancel, outcome), task, consult,
                                             max_steps=AGENT_MAX_STEPS, timeout_s=AGENT_TIMEOUT_S,
                                             instructions=INSTRUCTIONS, cancel=cancel, label="copilot")
                    summary["agent"] = res
                    summary["agent_tokens"] = [res.get("input_tokens", 0), res.get("output_tokens", 0)]
                    summary["curation"] = list(outcome.get("results") or [])
                    rt.agent_tokens += res.get("input_tokens", 0) + res.get("output_tokens", 0)
                    results = summary["curation"]
                    if not res.get("ok"):
                        reason = "agent timed out" if res.get("timed_out") else "agent failed"
                    elif results and all(r.startswith(("rejected", "cancelled")) for r in results) \
                            and not any("dismissed" in r for r in results):
                        reason = "agent made no valid card"
                if reason is not None:
                    summary["fallback"] = fallback_cards(consult, reason)
            summary["cards"] = [c["id"] for c in consult.cards.all_cards() if c["id"] not in cards_before]
        except Exception as e:  # noqa: BLE001 - never break the caller
            summary["error"] = f"{type(e).__name__}: {e}"
            try:
                consult.log("error", f"think run failed: {summary['error']}")
            except Exception:  # noqa: BLE001
                pass
        summary["latency_s"] = time.time() - t0
        rt.runs.append(summary)
        _record_metrics(consult, summary)
        return summary


# ------------------------------------------------------------------ background scheduling
def _loop(consult) -> None:
    """Runs in the executor; _kick already claimed rt.running for us."""
    rt = _rt(consult)
    try:
        while True:
            think_now(consult)
            with rt.lock:
                if rt.dirty:
                    rt.dirty = False
                    continue
                rt.running = False
                return
    except Exception as e:  # noqa: BLE001
        with rt.lock:
            rt.running = False
        consult.log("error", f"think loop failed: {e}")


def _kick(consult) -> None:
    try:
        rt = _rt(consult)
        with rt.lock:
            rt.timer = None
            if rt.running:              # a run is in flight: it reruns once when done
                rt.dirty = True
                return
            rt.running = True           # claimed before submit, so idle()/on_turn never see a gap
            rt.dirty = False
        try:
            _EXECUTOR.submit(_loop, consult)
        except Exception:
            with rt.lock:
                rt.running = False
            raise
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"think scheduling failed: {e}")


def on_turn(consult, turn=None) -> None:
    """Non-blocking: (re)start the debounce timer; a turn arriving mid-run marks the run dirty (one rerun after)."""
    try:
        rt = _rt(consult)
        with rt.lock:
            if rt.running:
                rt.dirty = True
                return
            if rt.timer is not None:
                rt.timer.cancel()
            rt.timer = threading.Timer(DEBOUNCE_S, _kick, args=(consult,))
            rt.timer.daemon = True
            rt.timer.start()
    except Exception as e:  # noqa: BLE001
        try:
            consult.log("error", f"on_turn failed: {e}")
        except Exception:  # noqa: BLE001
            pass


def idle(consult, timeout_s: float = 30.0) -> bool:
    """Wait until no think run is pending or running (tests / replay). True if idle."""
    rt = _rt(consult)
    end = time.time() + timeout_s
    while time.time() < end:
        with rt.lock:
            if rt.timer is None and not rt.running:
                return True
        time.sleep(0.02)
    return False


def tick(consult) -> None:
    """Re-evaluate timer rules (UI timer / replay clock). Cheap, no LLM; logs only when the fired set changes."""
    try:
        rt = _rt(consult)
        now = consult.now_min()
        fired = _evaluate(consult, now)
        ids = {f.get("rule_id") for f in fired}
        if ids != rt.last_fired:
            added = sorted(ids - rt.last_fired)
            gone = sorted(rt.last_fired - ids)
            consult.log("tool", f"check_safety_rules (clock {fmt_t(now)}) → "
                                + ", ".join([f"+{i}" for i in added] + [f"-{i}" for i in gone]))
            rt.last_fired = ids
        consult.cards.sync_rules(fired, now)
        with rt.lock:   # a question nobody answered: extract it on its own after DEFER_MAX_S
            stale = bool(rt.deferred and rt.deferred_since and time.time() - rt.deferred_since > DEFER_MAX_S)
            if stale:
                rt.force_flush = True
        if stale:
            on_turn(consult)
    except Exception as e:  # noqa: BLE001
        try:
            consult.log("error", f"tick failed: {e}")
        except Exception:  # noqa: BLE001
            pass


def flush(consult) -> dict | None:
    """Synchronously extract everything still pending, including deferred doctor questions. Call before the
    wrap-up so the note sees every question the doctor asked. Never raises."""
    try:
        rt = _rt(consult)
        with consult.lock:
            pending = len(consult.turns) > consult.agent_seen
        if rt.deferred or pending:
            return think_now(consult, flush=True)
    except Exception as e:  # noqa: BLE001
        try:
            consult.log("error", f"flush failed: {e}")
        except Exception:  # noqa: BLE001
            pass
    return None


def ask_card(consult, card_id: str) -> str | None:
    """Doctor tapped "Ask": marks the card and returns the English question for the UI to translate + speak."""
    try:
        card = consult.cards.get(card_id) if consult.cards is not None else None
        if not card or not card.get("ask_text"):
            return None
        consult.cards.act(card_id, "ask", user="doctor")
        return card["ask_text"]
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"ask_card failed: {e}")
        return None


def stats(consult) -> dict:
    """Runs, latency and token usage so far (smoke script / UI cost meter)."""
    rt = _rt(consult)
    runs = list(rt.runs)
    ein = sum(r["extract_tokens"][0] for r in runs)
    eout = sum(r["extract_tokens"][1] for r in runs)
    ain = sum(r["agent_tokens"][0] for r in runs)
    aout = sum(r["agent_tokens"][1] for r in runs)
    return {"runs": len(runs), "latency_s": [round(r["latency_s"], 2) for r in runs],
            "extract_tokens": [ein, eout], "agent_tokens": [ain, aout],
            "cost_usd": agentkit.cost_usd(ein + ain, eout + aout)}
