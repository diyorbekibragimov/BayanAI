"""Bayan AI · wrap-up loop: clinic note, patient care plan, and the rendered outputs (PDFs, audio, links).

    run_wrapup(consult) ─► draft_note       schema'd JSON clinic note (one call; long consultations: map-reduce over
                                           ~6k-token transcript chunks in parallel), validated (every item cites
                                           utterance ids, A/P only from doctor turns), one retry, then a
                                           deterministic note from the structured record as the fallback
                       ─► build_care_plan  deterministic skeleton from state + ONE llm.chat_json call (plain English +
                                           patient-language lines); every medicine re-checked by the rule engine
                       ─► check_care_plan  numbers / stopped drugs / 999 / missing translations
                       ─► render_outputs   doctor PDF, patient PDF (QR to audio), WAV, wa.me + sms: links
    (note and care plan are independent and run in parallel)

agentic=True runs the steps as two coarse smolagents tools (draft_outputs, render_outputs) through agentkit.run_agent;
any failure, timeout or skipped step falls back to the fixed deterministic order, so the outputs always exist.
Files live only in bayan.outputs.retention.consult_dir(consult) (temp, auto-swept).
"""

from __future__ import annotations

import copy
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import llm
from .state import Consultation, fmt_t

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "data" / "safety_rules.json"
EMERGENCY = "999"
# gpt-oss reasoning tokens count against max_tokens; "high" effort measured 4x tokens + empty replies. Wrap-up makes
# two calls (clinic note + care plan, in parallel; long consultations add map calls) + the optional agent steps.
WRAPUP_REASONING = os.environ.get("BAYAN_WRAPUP_REASONING", "medium")
CARE_PLAN_MAX_TOKENS = int(os.environ.get("BAYAN_WRAPUP_MAX_TOKENS", "5000"))
WRAPUP_AGENT_MAX_TOKENS = int(os.environ.get("BAYAN_WRAPUP_AGENT_MAX_TOKENS", "6000"))
CARE_PLAN_INPUT_BUDGET = int(os.environ.get("BAYAN_WRAPUP_CAREPLAN_BUDGET", "12000"))   # est. tokens of doctor text


def LANG_NAME(code: str) -> str:  # noqa: N802 - small helper used by the renderer
    from bayan.outputs import LANG_NAMES
    return LANG_NAMES.get(code, code)


def clinic_name(consult: "Consultation | None" = None) -> str:
    """The facility name, only when one is configured (run_wrapup(clinic=...) or $BAYAN_CLINIC_NAME); else ""."""
    if consult is not None and consult.outputs.get("clinic"):
        return str(consult.outputs["clinic"])
    return os.environ.get("BAYAN_CLINIC_NAME", "").strip()

_ENGINE = None
_META: dict | None = None


# ====================================================================== helpers: drugs, rules
def _meta() -> dict:
    global _META
    if _META is None:
        _META = json.loads(RULES_PATH.read_text(encoding="utf-8"))["meta"]
    return _META


def _norm_drug(name: str) -> str:
    try:
        from .vocab import normalise_drug
        return normalise_drug(name)
    except Exception:  # noqa: BLE001 - vocab (agent A) missing or failing: minimal local normalisation
        n = re.sub(r"\b(tablets?|tabs?|capsules?|caps?|syrup|injection)\b", "", (name or "").lower()).strip()
        aliases = {k.lower(): v for k, v in _meta().get("brand_aliases_examples", {}).items() if not k.startswith("_")}
        return aliases.get(n, n)


def _gloss(literal_en: str) -> str:
    try:
        from .vocab import literal_gloss
        return literal_gloss(literal_en)
    except Exception:  # noqa: BLE001
        return str(literal_en or "").split("(")[0].strip()


def _classes(drug: str) -> list[str]:
    try:
        from .vocab import classes_of
        return list(classes_of(drug))
    except Exception:  # noqa: BLE001
        d = _norm_drug(drug)
        classes = _meta()["drug_classes"]
        out = [c for c, members in classes.items() if d in members]
        if d in classes:
            out.append(d)
        if d.endswith("s") and d[:-1] in classes:
            out.append(d[:-1])
        return out


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from .rules import RuleEngine
        _ENGINE = RuleEngine()
    return _ENGINE


def _rule_key(r: dict) -> str:
    return str(r.get("key") or r.get("rule_id") or r.get("id") or r)


def _fallback_check(state: dict, med: dict) -> list[dict]:
    """Minimal guard used only when the rule engine cannot be imported: allergy-class overlap and paracetamol
    ceilings (ALG-PEN-01-style / DOSE-PARA-01)."""
    fired = []
    med_classes = set(med.get("class") or []) | {_norm_drug(med.get("drug", ""))}
    for a in state.get("allergies", []):
        a_classes = set(a.get("class") or []) | set(_classes(a.get("substance", "")))
        if med_classes & a_classes:
            fired.append({"rule_id": "ALG-FALLBACK", "severity": "critical",
                          "message": f"{a.get('substance')} allergy recorded; {med.get('drug')} shares its class."})
    if med.get("drug") == "paracetamol" and ((med.get("dose_mg") or 0) > 1000 or (med.get("daily_dose_mg") or 0) > 4000):
        fired.append({"rule_id": "DOSE-PARA-01", "severity": "critical",
                      "message": "Paracetamol above 1 g per dose or 4 g/day."})
    return fired


def _prep_med(med: dict) -> dict:
    m = copy.deepcopy(med)
    m["drug"] = _norm_drug(m.get("drug") or m.get("name") or "")
    if not m.get("class"):
        m["class"] = _classes(m["drug"])
    if m.get("daily_dose_mg") is None and m.get("dose_mg") is not None and m.get("frequency_per_day"):
        m["daily_dose_mg"] = float(m["dose_mg"]) * float(m["frequency_per_day"])
    return m


def safety_check(state: dict, med: dict, others: list[dict], now_min: float) -> tuple[list[dict], str | None]:
    """Rules that fire BECAUSE of `med` (fired with it minus fired without it, others = rest of the plan).
    Returns (fired, note). Fails closed: an engine error counts as a firing."""
    base = copy.deepcopy(state)
    base["prescribed_meds"] = [_prep_med(o) for o in others]
    cand = _prep_med(med)
    try:
        eng = _engine()
    except Exception as e:  # noqa: BLE001
        return _fallback_check(base, cand), f"rule engine unavailable ({type(e).__name__}); built-in minimal check used"
    try:
        before = {_rule_key(r) for r in eng.check_prescription(base, [], now_min)}
        after = eng.check_prescription(base, [cand], now_min)
        return [r for r in after if _rule_key(r) not in before], None
    except Exception as e:  # noqa: BLE001
        return [{"rule_id": "CHECK-ERROR", "severity": "critical",
                 "message": f"safety check failed ({type(e).__name__}: {e})"}], None


def final_meds(state: dict) -> list[dict]:
    """prescribed_meds minus stopped_meds (by normalised drug name), first occurrence wins."""
    stopped = {_norm_drug(s.get("drug", "")) for s in state.get("stopped_meds", [])}
    out, seen = [], set()
    for m in state.get("prescribed_meds", []):
        d = _norm_drug(m.get("drug", ""))
        if d and d not in stopped and d not in seen:
            seen.add(d)
            out.append(m)
    return out


# ====================================================================== helpers: text
def _cite(evidence: list[dict] | None) -> str:
    ids = []
    for ev in evidence or []:
        u = ev.get("utt") if isinstance(ev, dict) else None
        if u and u not in ids:
            ids.append(u)
    return f" [{', '.join(ids)}]" if ids else ""


def _quote(evidence: list[dict] | None) -> str:
    for ev in evidence or []:
        q = (ev.get("quote") or "").strip() if isinstance(ev, dict) else ""
        if q:
            return q
    return ""


def _human(code: str) -> str:
    special = {"ecg_12lead": "ECG (12-lead)", "ecg": "ECG", "troponin": "Troponin", "cbc": "CBC", "ck": "CK",
               "bp": "Blood pressure", "urea_creatinine": "Urea & creatinine", "lft": "LFT"}
    c = (code or "").strip()
    return special.get(c.lower(), c.replace("_", " ").strip().capitalize())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?।])\s+", text or "") if s.strip()]


def _english(turn) -> str:
    return (turn.english or turn.text) if turn.lang != "en" else turn.text


def _fmt_mg(mg: float | None) -> str:
    if mg is None:
        return ""
    mg = float(mg)
    if mg >= 1000 and mg % 100 == 0:
        return f"{mg / 1000:g} g"
    return f"{mg:g} mg"


def _is_prn(med: dict) -> bool:
    if med.get("prn") or med.get("as_needed"):
        return True
    text = " ".join((ev.get("quote") or "") for ev in med.get("evidence", []) if isinstance(ev, dict))
    return bool(re.search(r"\b(up to|as needed|if needed|when needed|prn|if required)\b", text, re.I))


def _freq_en(n: Any, prn: bool) -> str:
    if not n:
        return "as directed"
    n = int(n)
    base = {1: "once a day", 2: "2 times a day"}.get(n, f"{n} times a day")
    return ("up to " + base) if prn else base


def _numbers(text: str) -> set[float]:
    """Numbers in any script (Devanagari ९९९, Bengali, Malayalam, Arabic-Indic digits ...) as floats."""
    ascii_text = "".join(str(unicodedata.digit(ch)) if ch.isdigit() and not ch.isascii() else ch for ch in text or "")
    out = set()
    for tok in re.findall(r"\d+(?:[.,]\d+)?", ascii_text):
        try:
            out.add(float(tok.replace(",", ".")))
        except ValueError:
            pass
    return out


# ====================================================================== SOAP note
_ASSESS_CUES = re.compile(r"\b(probably|likely|looks|seems|i think|diagnos\w*|impression|consistent with|suggests?)\b", re.I)
_ADVICE_CUES = re.compile(r"\b(drink|rest|avoid|eat|sleep|water|stay out|keep)\b", re.I)
_SAFETY_CUES = re.compile(r"\b(999|come (straight )?back|return|emergency)\b", re.I)
_FOLLOW_CUES = re.compile(r"\b(follow[- ]?up|review|see (you|your)|appointment|clinic in|in \d+ days?)\b", re.I)


def _doctor_sentences(consult: Consultation, include_held: bool = False) -> list[tuple[Any, str]]:
    out = []
    for t in consult.turns:
        if t.role != "doctor" or t.kind != "speech" or (t.held and not include_held):
            continue
        for s in _sentences(_english(t)):
            out.append((t, s))
    return out


# ====================================================================== cards / audit
def _cards(consult: Consultation) -> list[dict]:
    store = consult.cards
    fn = getattr(store, "all_cards", None) if store is not None else None
    if callable(fn):
        try:
            return list(fn())
        except Exception:  # noqa: BLE001
            return []
    return []


def _audit(consult: Consultation) -> list[dict]:
    seen, out = set(), []
    store_audit = getattr(consult.cards, "audit", None) if consult.cards is not None else None
    for entry in list(consult.audit or []) + list(store_audit or []):
        k = json.dumps(entry, sort_keys=True, default=str) if isinstance(entry, dict) else str(entry)
        if k not in seen:
            seen.add(k)
            out.append(entry)
    return out


def _card_id(entry: dict) -> str | None:
    for k in ("card_id", "card", "id"):
        v = entry.get(k)
        if isinstance(v, str):
            return v
    return None


def _item_ids(card: dict) -> list[str]:
    ids = []
    for it in card.get("items") or []:
        v = (it.get("rule_id") or it.get("grounding") or it.get("id")) if isinstance(it, dict) else str(it)
        if v and v not in ids:
            ids.append(str(v))
    return ids or list(card.get("rule_ids") or [])


def _compress_ids(ids: list[str]) -> str:
    """WORK-CHEST-01, -02, -03, -04 -> WORK-CHEST-01–04."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for i in ids:
        m = re.match(r"^(.*-)(\d+)$", i)
        key, num = (m.group(1), m.group(2)) if m else (i, "")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(num)
    out = []
    for key in order:
        nums = sorted(n for n in groups[key] if n)
        if len(nums) <= 1:
            out.append(key + (nums[0] if nums else ""))
        else:
            vals = [int(n) for n in nums]
            if vals == list(range(vals[0], vals[0] + len(vals))):
                out.append(f"{key}{nums[0]}–{nums[-1]}")
            else:
                out.append(key + ", ".join(nums))
    return ", ".join(out)


# Keys = the lexicon's red_flag_tags vocabulary (data/idiom_lexicon.json); legacy short keys kept as aliases.
_TAG_TEXT = {"acs": "cardiac pain", "gi_bleed": "GI bleeding", "stroke": "stroke",
             "sepsis_infection": "sepsis or serious infection", "heat_illness": "heat illness",
             "dehydration": "dehydration", "suicidality": "suicidal thoughts", "pe": "pulmonary embolism",
             "meningitis": "meningitis", "ectopic_pregnancy": "ectopic pregnancy",
             "metabolic": "a metabolic emergency (DKA or hypoglycaemia)", "malaria": "malaria",
             "neuro_psych_emergency": "a neurological or psychiatric emergency",
             "arrhythmia_syncope": "arrhythmia or syncope", "respiratory": "respiratory illness",
             "postpartum": "a postpartum complication",
             "sepsis": "sepsis", "suicide_risk": "suicidal thoughts", "ectopic": "ectopic pregnancy",
             "dka": "diabetic ketoacidosis"}


def _idiom_alert(consult: Consultation, card: dict) -> str:
    gid = card.get("grounding") or ""
    hit = next((h for h in consult.state.get("idiom_hits", []) if h.get("id") == gid), None)
    entry = None
    try:
        entry = _idiom_entry(gid)
    except Exception:  # noqa: BLE001
        entry = None
    word = (entry or {}).get("romanized") or (hit or {}).get("matched") or gid
    lit = _gloss((entry or {}).get("literal_en") or "")
    tags = (hit or {}).get("red_flag_tags") or (entry or {}).get("red_flag_tags") or []
    masks = " or ".join(dict.fromkeys(_TAG_TEXT.get(t, t.replace("_", " ")) for t in tags))
    return f"Patient used “{word}”" + (f" ({lit})" if lit and lit.lower() != str(word).lower() else "") + \
        (f", which can mask {masks}" if masks else "")


def _first_sentence(text: str) -> str:
    text = re.sub(r"\s*\([^)]*[“\"][^)]*\)", "", text or "")  # drop quoted evidence in brackets
    return (_sentences(text) or [""])[0].rstrip(".")


def _not_prescribing(items: list[dict]) -> bool:
    """Rule items that are not about a prescription (e.g. ALG-DOC-01 "reaction not captured", fire_on state_change):
    they must never be written up as "<drug> was then prescribed"."""
    return bool(items) and all(i.get("fire_on") not in (None, "on_prescribe") for i in items)


def decision_log(consult: Consultation) -> list[dict]:
    """Clinical decision support rows for the record: [{"time","level","alert","action","rule_ids"}]. One line per
    card; unused suggested questions collapse into one line; held turns are folded into the matching allergy row."""
    cards = _cards(consult)
    with consult.lock:
        st = copy.deepcopy(consult.state)
    audit = [e for e in _audit(consult) if isinstance(e, dict)]
    stopped = {_norm_drug(s.get("drug", "")) for s in st.get("stopped_meds", [])}
    held = [t for t in consult.turns if t.held]
    rows, unused_asks = [], 0
    for c in sorted(cards, key=lambda c: float(c.get("t_min") or 0)):
        kind, src, status = c.get("kind"), c.get("source"), str(c.get("status") or "")
        acts = [a for a in (c.get("actions") or []) if isinstance(a, dict) and a.get("action")] or \
            [e for e in audit if _card_id(e) == c.get("id") and e.get("action") and e.get("user") not in _SYSTEM_USERS]
        life = {e.get("action"): e.get("t_min") for e in audit if _card_id(e) == c.get("id")
                and e.get("action") in ("resolved",)}
        if kind == "ask" and src != "rules":
            if status in ("accepted",) or any(a.get("action") == "ask" for a in acts):
                t = next((a.get("t_min") for a in acts), c.get("updated_t_min"))
                rows.append({"time": fmt_t(c.get("t_min")), "level": "Info", "rule_ids": [],
                             "alert": f"Suggested question: {c.get('ask_text') or c.get('title')}",
                             "action": f"Asked {fmt_t(t)}"})
            else:
                unused_asks += 1
            continue
        ids = _item_ids(c) if src == "rules" else []
        items = [i for i in (c.get("items") or []) if isinstance(i, dict)]
        family = next((i.get("family") for i in items if i.get("family")), "")
        if family == "drug_allergy" and _not_prescribing(items):
            family = "allergy_record"
        if src == "lexicon" or kind == "idiom":
            alert = _idiom_alert(consult, c)
        elif family == "drug_allergy" or (kind == "safety" and family != "allergy_record"
                                          and any(i.startswith("ALG-") for i in ids)):
            key = next((str(i.get("key")) for i in items if "|" in str(i.get("key") or "")), "")
            drug = key.split("|", 1)[1] if key else ""
            alg = next((a for a in st.get("allergies", [])
                        if drug and set(_classes(drug)) & (set(a.get("class") or []) | set(_classes(a.get("substance", ""))))),
                       None)
            sub = (alg or {}).get("substance") or "Drug"
            alert = f"{sub.capitalize()} allergy vs {drug or 'prescribed drug'} prescription ({_compress_ids(ids)})"
        elif src == "rules" and len(items) > 1:
            gaps = list(dict.fromkeys(m.lower() for i in items for m in
                                      re.findall(r"\bno\s+(?:12-lead\s+)?([A-Za-z][\w-]*)", i.get("message") or "", re.I)))
            gap_txt = ", ".join(f"no {g.upper() if g.lower() == 'ecg' else g}" for g in gaps[:4])
            title = str(c.get("title") or "Workup").split(" · ")[0]
            alert = f"{title} incomplete" + (f": {gap_txt}" if gap_txt else "") + f" ({_compress_ids(ids)})"
        elif src == "rules":
            msg = _first_sentence(items[0].get("message", "")) if items else ""
            alert = (msg or str(c.get("title") or "").split(" · ")[0]) + (f" ({_compress_ids(ids)})" if ids else "")
        else:
            prefix = {"missed": "Possibly missed", "observation": "Observation"}.get(kind, "Note")
            alert = f"{prefix}: {c.get('title')}"
        parts = []
        for a in acts:
            verb = {"acknowledge": "Acknowledged", "override": "Overridden", "dismiss": "Dismissed",
                    "accept": "Accepted", "ask": "Asked", "wrong_fact": "Marked wrong fact"}.get(
                str(a.get("action")), str(a.get("action")).capitalize())
            parts.append(f"{verb} {fmt_t(a.get('t_min'))}" + (f" ({a['reason']})" if a.get("reason") else ""))
        if family == "drug_allergy" or alert.startswith(tuple(f"{s.capitalize()} allergy" for s in
                                                              [a.get("substance", "") for a in st.get("allergies", [])])):
            drug = next((str(i.get("key")).split("|", 1)[1] for i in items if "|" in str(i.get("key") or "")), "")
            if drug and _norm_drug(drug) in stopped:  # the stop says it all: drop a reason that repeats it
                parts = [re.sub(r" \([^)]*" + re.escape(drug) + r"[^)]*\)", "", x, flags=re.I) for x in parts]
            if held:
                parts.append("prescribing sentence held")
                held = []
            if drug and _norm_drug(drug) in stopped:
                parts.append(f"{drug} stopped")
        if not parts:
            if status == "resolved":
                parts.append(f"Resolved {fmt_t(life.get('resolved', c.get('updated_t_min')))}")
            elif status == "dismissed":
                parts.append("Dismissed")
            else:
                parts.append("Shown" if kind in ("idiom",) or src == "lexicon" else "Shown; no action")
        elif status == "resolved" and not any("stopped" in p for p in parts):
            parts.append(f"resolved {fmt_t(life.get('resolved', c.get('updated_t_min')))}")
        rows.append({"time": fmt_t(c.get("t_min")), "level": (c.get("severity") or "info").capitalize(),
                     "alert": alert, "action": "; ".join(parts), "rule_ids": ids})
    for t in held:
        rows.append({"time": fmt_t(t.t_min), "level": "Critical", "rule_ids": [],
                     "alert": "Prescribing sentence held by the safety gate (not interpreted)",
                     "action": "Plan revised by clinician"})
    if unused_asks:
        rows.append({"time": "", "level": "Info", "rule_ids": [],
                     "alert": f"{unused_asks} suggested question{'s' if unused_asks != 1 else ''} not used",
                     "action": ""})
    return rows


# The copilot's concerns as the doctor saw them, for the record (doctor PDF "Copilot concerns").
CONCERN_SOURCES = ("agent", "fallback", "rules")
_RETIRED = re.compile(r"\b(retired|superseded)\b", re.I)
_RULE_PREFIX = re.compile(r"^[A-Z]{2,}(?:-[A-Z0-9]+)+:\s*")
# status -> (order group, label): open first, then asked / addressed / acknowledged, then dismissed / overridden
CONCERN_STATUS = {"open": (0, "Open"), "asked": (1, "Asked"), "addressed": (1, "Addressed"),
                  "accepted": (1, "Accepted"), "acknowledged": (1, "Acknowledged"),
                  "dismissed": (2, "Dismissed by clinician"), "overridden": (2, "Overridden by clinician")}


def _words(text: str | None) -> str:
    return " ".join(re.findall(r"\w+", (text or "").lower()))


def _resolved_reason(card: dict, audit: list[dict]) -> str:
    if card.get("resolved_reason"):
        return str(card["resolved_reason"])
    for e in reversed(audit):
        if _card_id(e) == card.get("id") and e.get("action") == "resolved":
            return str(e.get("reason") or "")
    return ""


def _one_line(text: str, limit: int = 180) -> str:
    """First line, first sentence, rule-id prefix dropped; never more than `limit` characters."""
    first = next((ln for ln in str(text or "").splitlines() if ln.strip()), "")
    first = _RULE_PREFIX.sub("", first.strip())
    sent = (_sentences(first) or [first])[0].strip()
    out = " ".join(sent.split())
    return out if len(out) <= limit else out[:limit - 1].rstrip(" ,;:") + "…"


def copilot_concerns(consult: Consultation) -> list[dict]:
    """Every agent and rule card raised during the visit, for the record: [{"id","title","body","dimension","status",
    "label","reason","quote","time","severity","source","t_min"}]. Cards retired by the copilot itself (a question
    superseded by a better one, or a duplicate pushed off screen) are left out; everything else is listed with what
    happened to it: open (never addressed), asked (the doctor asked the suggested question), addressed (the
    conversation dealt with it / the rule stopped firing), accepted / acknowledged, dismissed or overridden by the
    clinician. Ordered open first, then asked / addressed, then dismissed; by time within each group."""
    audit = [e for e in _audit(consult) if isinstance(e, dict)]
    turns = {t.id: t for t in consult.turns}
    rows = []
    for c in _cards(consult):
        if c.get("source") not in CONCERN_SOURCES:
            continue
        status = str(c.get("status") or "open")
        reason = ""
        if status == "resolved":
            why = _resolved_reason(c, audit)
            if _RETIRED.search(why):
                continue
            status = "asked" if why.startswith("the doctor asked") else "addressed"
        elif status == "accepted" and c.get("kind") == "ask":
            status = "asked"
        if status in ("dismissed", "overridden", "acknowledged", "accepted"):
            acts = [a for a in (c.get("actions") or []) if isinstance(a, dict)] or \
                [e for e in audit if _card_id(e) == c.get("id") and e.get("action") and e.get("user") not in _SYSTEM_USERS]
            reason = next((str(a.get("reason")) for a in reversed(acts) if a.get("reason")), "")
        if status not in CONCERN_STATUS:
            status = "open"
        ev = next((e for e in (c.get("evidence") or []) if isinstance(e, dict) and e.get("utt")), None)
        quote, t_min = "", c.get("t_min")
        if ev is not None:
            turn = turns.get(ev.get("utt"))
            quote = " ".join(str(ev.get("quote") or (_english(turn) if turn else "")).split())
            if len(quote) > 160:
                quote = quote[:159].rstrip(" ,;:") + "…"
            t_min = ev.get("t_min") if ev.get("t_min") is not None else getattr(turn, "t_min", t_min)
        dim = str(c.get("dimension") or "")
        if not dim:
            g = str(c.get("grounding") or "")
            dim = g if g in ("safety", "history", "plan", "communication", "consistency") else \
                ("safety" if c.get("source") == "rules" and c.get("kind") == "safety" else
                 "workup" if c.get("source") == "rules" else str(c.get("kind") or ""))
        title = str(c.get("title") or "").strip()
        if c.get("kind") == "ask" and c.get("ask_text") and _words(c["ask_text"]) != _words(title):
            title = f"{title}: “{str(c['ask_text']).strip()}”" if title else str(c["ask_text"])
        group, label = CONCERN_STATUS[status]
        rows.append({"id": c.get("id"), "title": dedash(title), "body": dedash(_one_line(c.get("body") or "")),
                     "dimension": dim.replace("_", " "), "status": status, "label": label, "group": group,
                     "reason": dedash(reason), "quote": dedash(quote), "time": fmt_t(t_min) if quote else "",
                     "severity": c.get("severity") or "info", "source": c.get("source"),
                     "t_min": float(c.get("t_min") or 0)})
    rows.sort(key=lambda r: (r["group"], r["t_min"]))
    return rows


def dedash(text: str) -> str:
    """No em or en dashes in the documents: number ranges keep a hyphen, other dashes become commas."""
    if not text:
        return text
    t = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1-\2", str(text))
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r",\s*([.;:!?)])", r"\1", t)
    t = re.sub(r"^\s*,\s*", "", t)
    return t.strip()


_TAG_PLAIN = {"acs": "heart pain", "gi_bleed": "bleeding in the stomach or gut", "stroke": "a stroke",
              "sepsis_infection": "a serious infection", "heat_illness": "heat illness", "dehydration": "dehydration",
              "suicidality": "thoughts of self-harm", "pe": "a blood clot in the lung", "meningitis": "meningitis",
              "ectopic_pregnancy": "an ectopic pregnancy", "metabolic": "a sugar or salt emergency",
              "malaria": "malaria", "neuro_psych_emergency": "a brain or mental-health emergency",
              "arrhythmia_syncope": "a heart rhythm problem or fainting", "respiratory": "a breathing problem",
              "postpartum": "a problem after childbirth",
              "sepsis": "a serious infection", "suicide_risk": "thoughts of self-harm",
              "ectopic": "an ectopic pregnancy", "dka": "a diabetic emergency"}


def _gap_names(items: list[dict]) -> list[str]:
    names = []
    for i in items:
        for g in re.findall(r"\bno\s+(?:12-lead\s+)?([A-Za-z][\w-]*)", i.get("message") or "", re.I):
            g = "ECG" if g.lower() == "ecg" else g.lower()
            if g not in names:
                names.append(g)
    return names


def safety_alerts(consult: Consultation) -> list[str]:
    """The alerts that mattered, as plain sentences for the record: no rule ids, no times, no 'shown / no action',
    no unused suggestions, no resolved agent suggestions."""
    cards = _cards(consult)
    with consult.lock:
        st = copy.deepcopy(consult.state)
    audit = [e for e in _audit(consult) if isinstance(e, dict)]
    stopped = {_norm_drug(x.get("drug", "")) for x in st.get("stopped_meds", [])}
    invs = {str(i.get("code", "")).lower(): i for i in st.get("investigations", [])}
    held = any(t.held for t in consult.turns)
    out: list[str] = []
    for c in sorted(cards, key=lambda c: float(c.get("t_min") or 0)):
        kind, src = c.get("kind"), c.get("source")
        acts = [a for a in (c.get("actions") or []) if isinstance(a, dict) and a.get("action")] or \
            [e for e in audit if _card_id(e) == c.get("id") and e.get("action") and e.get("user") not in _SYSTEM_USERS]
        verbs = {str(a.get("action")) for a in acts}
        items = [i for i in (c.get("items") or []) if isinstance(i, dict)]
        family = next((i.get("family") for i in items if i.get("family")), "")
        if family == "drug_allergy" and _not_prescribing(items):
            family = "allergy_record"
        if kind == "ask":
            continue
        if src == "lexicon" or kind == "idiom":
            gid = c.get("grounding") or ""
            hit = next((h for h in st.get("idiom_hits", []) if h.get("id") == gid), None) or {}
            try:
                entry = _idiom_entry(gid) or {}
            except Exception:  # noqa: BLE001
                entry = {}
            word = entry.get("romanized") or hit.get("matched") or gid
            lit = _gloss(entry.get("literal_en") or "")
            sym = next((_human(x.get("code", "")).lower() for x in st.get("symptoms", [])
                        if any(e.get("utt") == hit.get("utt") for e in x.get("evidence", []))), "")
            tags = hit.get("red_flag_tags") or entry.get("red_flag_tags") or []
            mask = _TAG_PLAIN.get(tags[0], tags[0].replace("_", " ")) if tags else ""
            out.append((f"The patient described {sym} as \"{word}\"" if sym else f"The patient used the word \"{word}\"")
                       + (f" ({lit})" if lit and lit.lower() != str(word).lower() else "")
                       + (f", which can hide {mask}." if mask else "."))
            continue
        if src != "rules":
            if verbs & {"accept", "acknowledge"}:
                out.append(f"Suggested: {str(c.get('title') or '').rstrip('.')}. Accepted by the clinician.")
            continue
        if family == "drug_allergy" or (kind == "safety" and family != "allergy_record"
                                        and any(str(i.get("rule_id", "")).startswith("ALG-") for i in items)):
            key = next((str(i.get("key")) for i in items if "|" in str(i.get("key") or "")), "")
            drug = key.split("|", 1)[1] if key else "the medicine"
            alg = next((a for a in st.get("allergies", [])
                        if set(_classes(drug)) & (set(a.get("class") or []) | set(_classes(a.get("substance", ""))))),
                       None)
            line = f"{str((alg or {}).get('substance') or 'Drug').capitalize()} allergy reported; {drug} was then " \
                   "prescribed."
            gone = _norm_drug(drug) in stopped
            if held and gone:
                line += f" The instruction was held and {drug} stopped."
            elif held:
                line += " The instruction was held."
            elif gone:
                line += f" {drug.capitalize()} was stopped."
            elif "override" in verbs:
                why = next((a.get("reason") for a in acts if a.get("action") == "override" and a.get("reason")), "")
                line += " The clinician continued it" + (f" ({why})." if why else ".")
            out.append(line)
            continue
        if len(items) > 1 or family == "missing_workup":
            gaps = _gap_names(items)
            topic = re.sub(r"[-\s]*work-?up.*$", "", str(c.get("title") or ""), flags=re.I).replace("-", " ").strip()
            topic = topic[:1].upper() + topic[1:] if topic else "Workup"
            disch = any("discharge" in (i.get("message") or "").lower() for i in items)
            if gaps:
                g = _join(gaps)
                g = ("an " + g) if g[:1].upper() in "AEIOU" and g[:1].isupper() else g
                line = f"{topic}, with discharge planned before {g}." if disch else f"{topic}, without {g}."
                found = []
                for name in gaps:
                    inv = next((v for code, v in invs.items() if name.lower() in code or
                                (name == "ECG" and code.startswith("ecg"))), None)
                    found.append(inv)
                if found and all(f and f.get("status") == "resulted" for f in found):
                    results = [str(f.get("result") or "").lower() for f in found]
                    if all(r == "normal" for r in results):
                        line += " Both were then done and were normal." if len(found) == 2 else \
                            " All were then done and were normal." if len(found) > 2 else " It was then done and was normal."
                    else:
                        line += " Then done: " + "; ".join(f"{n}: {r or 'resulted'}" for n, r in zip(gaps, results)) + "."
                elif found and all(f for f in found):
                    line += " Then ordered."
                else:
                    line += " Not done during the consultation."
            else:
                line = f"{topic}: workup incomplete."
            out.append(line)
            continue
        msg = _first_sentence(items[0].get("message", "")) if items else str(c.get("title") or "")
        line = re.sub(r"\s*\([A-Z]+-[A-Z0-9-]+\)", "", msg).rstrip(".") + "."
        if "override" in verbs:
            why = next((a.get("reason") for a in acts if a.get("action") == "override" and a.get("reason")), "")
            line += " Overridden by the clinician" + (f" ({why})." if why else ".")
        elif verbs & {"acknowledge", "accept"}:
            line += " Acknowledged by the clinician."
        out.append(line)
    if held and not any("held" in x for x in out):
        out.append("A prescribing instruction was held and not interpreted to the patient.")
    return [dedash(x) for x in out]


# ====================================================================== structured record (tables of the note)
_AGREE = re.compile(r"\b(yes|agree[ds]?|ok(?:ay)?|sure|of course)\b", re.IGNORECASE)
_REFUSE = re.compile(r"\b(no|not|don'?t|do not|never|refuse[ds]?)\b", re.IGNORECASE)


def _consent(consult: Consultation) -> str:
    """One word for the record's panel: "Agreed" or "Not agreed". The exact consent sentence (what the patient heard
    and the doctor's screen showed) stays in the transcript's consent row, not repeated here."""
    rec = (consult.outputs or {}).get("consent") if isinstance(getattr(consult, "outputs", None), dict) else None
    if isinstance(rec, dict) and rec.get("en"):
        return "Agreed"
    for t in consult.turns:
        if t.role == "bayan" and "consent" in (t.english + t.text + t.kind).lower():
            ans = next((u for u in consult.turns if u.role == "patient" and u.t_min >= t.t_min), None)
            said = (ans.english or ans.text or "") if ans is not None else ""
            return "Agreed" if _AGREE.search(said) and not _REFUSE.search(said) else "Not agreed"
    return "Not agreed"


def _freq_clinical(m: dict) -> str:
    n = m.get("frequency_per_day")
    prn = _is_prn(m)
    if not n:
        return "As needed" if prn else "Not stated"
    n = int(n)
    base = {1: "once a day", 2: "twice a day"}.get(n, f"{n} times a day")
    return f"Up to {base}, as needed" if prn else base.capitalize()


def note_tables(consult: Consultation, care_plan: dict | None = None) -> dict:
    """Everything in the clinic note that comes straight from the structured record (never from the LLM)."""
    from bayan.outputs import LANG_NAMES

    with consult.lock:
        st = copy.deepcopy(consult.state)
        turns = list(consult.turns)
    pt = st.get("patient", {}) or {}
    age = f"{pt['age_years']:g}" if isinstance(pt.get("age_years"), (int, float)) else None
    sex = pt.get("sex") if pt.get("sex") not in (None, "unknown") else None
    dur = (turns[-1].t_min - turns[0].t_min) if turns else 0.0
    encounter = [
        ("Patient ID", f"P-{str(consult.id)[:6].upper()}"),
        ("Age / sex", " / ".join(x for x in (f"{age} years" if age else None, sex) if x) or "Not recorded"),
        ("Language", f"{LANG_NAMES.get(consult.patient_lang, consult.patient_lang)} (clinician: "
                     f"{LANG_NAMES.get(consult.doctor_lang, consult.doctor_lang)})"),
        ("Interpreter", "Bayan AI"),
        ("Consent to interpretation", _consent(consult)),
        ("Clinician", "________________"),
        ("Duration", f"{int(round(dur))} min"),
    ]
    if clinic_name(consult):
        encounter.append(("Facility", clinic_name(consult)))
    allergies = []
    for a in st.get("allergies", []):
        sub = str(a.get("substance") or ", ".join(a.get("class") or []) or "Unknown").capitalize()
        bits = [str(a["reaction"])] if a.get("reaction") else []
        if a.get("severity") not in (None, "", "unknown"):
            bits.append(f"reported as {a['severity']}")
        allergies.append(sub + (": " + ", ".join(bits) if bits else ""))
    v = st.get("vitals", {}) or {}
    vit = []
    if v.get("bp_sys") and v.get("bp_dia"):
        vit.append(f"BP {int(v['bp_sys'])}/{int(v['bp_dia'])} mmHg")
    for k, label, unit in (("hr", "HR", "/min"), ("rr", "RR", "/min"), ("spo2", "SpO2", "%"), ("temp_c", "Temp", " °C")):
        if v.get(k) is not None:
            vit.append(f"{label} {v[k]:g}{unit}" if isinstance(v[k], (int, float)) else f"{label} {v[k]}{unit}")
    tests = [(_human(i.get("code", "")), (i.get("status") or "ordered").capitalize(),
              (str(i["result"]) if i.get("result") else "Pending")) for i in st.get("investigations", [])]
    obs = []
    if v.get("bp_sys") and v.get("bp_dia"):
        obs.append(("Blood pressure", "Recorded", f"{int(v['bp_sys'])}/{int(v['bp_dia'])} mmHg"))
    for k, label, unit in (("hr", "Heart rate", "/min"), ("rr", "Respiratory rate", "/min"), ("spo2", "SpO2", "%"),
                           ("temp_c", "Temperature", " °C")):
        if v.get(k) is not None:
            obs.append((label, "Recorded", f"{v[k]:g}{unit}" if isinstance(v[k], (int, float)) else f"{v[k]}{unit}"))
    excluded = {_norm_drug(e.get("name") or ""): e for e in (care_plan or {}).get("excluded", [])}
    cards = _cards(consult)
    meds = []
    for m in final_meds(st):
        d = _norm_drug(m.get("drug", ""))
        status = "Started"
        if d in excluded:
            status = "Started, not on the patient sheet (" + ", ".join(excluded[d].get("rules", [])) + " alert)"
        meds.append({"medicine": str(m.get("drug", "")).capitalize(), "dose": _fmt_mg(m.get("dose_mg")) or "—",
                     "route": str(m.get("route") or "Not stated").capitalize(), "frequency": _freq_clinical(m),
                     "duration": f"{m['duration_days']:g} days" if m.get("duration_days") else "Not stated",
                     "status": status, "stopped": False, "reason": ""})
    for s in st.get("stopped_meds", []):
        drug = str(s.get("drug", ""))
        alg = next((c for c in cards if c.get("kind") == "safety" and any(
            drug.lower() in str(i.get("key", "")).lower() for i in (c.get("items") or []) if isinstance(i, dict))), None)
        sub = None
        if alg is not None:
            sub = next((a.get("substance") for a in st.get("allergies", [])
                        if set(_classes(drug)) & (set(a.get("class") or []) | set(_classes(a.get("substance", ""))))),
                       None)
        reason = f"{sub} allergy alert" if sub else ("safety alert" if alg else "stopped by clinician")
        meds.append({"medicine": drug.capitalize(), "dose": _fmt_mg(s.get("dose_mg")) or "—",
                     "route": str(s.get("route") or "—").capitalize(),
                     "frequency": _freq_clinical(s) if s.get("frequency_per_day") else "—", "duration": "—",
                     "status": f"Stopped: {reason}", "stopped": True, "reason": reason})
    return {"encounter": encounter, "allergies": allergies, "vitals": " · ".join(vit), "tests": tests,
            "observations": obs + tests, "med_changes": meds, "decision_support": decision_log(consult),
            "safety_alerts": safety_alerts(consult)}


# ====================================================================== the clinic note (LLM, bounded input)
NOTE_SECTIONS = ("presenting_complaint", "history", "examination", "assessment", "plan", "information_given")
MD_TITLES = [("allergies", "Allergies"), ("presenting_complaint", "Presenting complaint"), ("history", "History"),
             ("observations", "Observations and investigations"), ("assessment", "Assessment"), ("plan", "Plan"),
             ("medication_changes", "Medication changes"), ("information_given", "Information given to patient"),
             ("safety_alerts", "Safety alerts")]
FALLBACK_LABEL = "Auto-generated from structured record (AI summary unavailable)"
# keys run_wrapup / draft_note own in consult.outputs (other modules keep their own keys there, e.g. "metrics")
OUTPUT_KEYS = ("note_md", "note_txt", "clinic", "care_plan", "warnings", "doctor_pdf", "patient_pdf", "audio_wav", "wa_link",
               "sms_link", "pdf_url", "audio_url", "token", "expires_at", "out_dir", "agentic", "wrapup_metrics",
               "note_json", "note_info", "note_sections")
NOTE_MAX_TOKENS = int(os.environ.get("BAYAN_WRAPUP_NOTE_MAX_TOKENS", "4000"))
NOTE_INPUT_BUDGET = int(os.environ.get("BAYAN_WRAPUP_NOTE_BUDGET", "24000"))     # est. input tokens per call
CHUNK_TOKENS = int(os.environ.get("BAYAN_WRAPUP_CHUNK_TOKENS", "6000"))
MAP_MAX_TOKENS = int(os.environ.get("BAYAN_WRAPUP_MAP_MAX_TOKENS", "3000"))
MAP_WORKERS = int(os.environ.get("BAYAN_WRAPUP_MAP_WORKERS", "6"))
_ITEM = {"type": "object", "properties": {"text": {"type": "string"}, "utts": {"type": "array",
                                                                              "items": {"type": "string"}}},
         "required": ["text", "utts"]}
NOTE_SCHEMA = {"type": "object", "properties": {k: {"type": "array", "items": _ITEM} for k in NOTE_SECTIONS},
               "required": list(NOTE_SECTIONS)}
MAP_SCHEMA = {"type": "object", "properties": {"facts": {"type": "array", "items": {
    "type": "object", "properties": {"kind": {"type": "string", "enum": [
        "symptom", "history", "allergy", "medication", "exam", "vital", "result", "assessment", "plan", "advice",
        "other"]}, "text": {"type": "string"}, "utts": {"type": "array", "items": {"type": "string"}}},
    "required": ["kind", "text", "utts"]}}}, "required": ["facts"]}

NOTE_SYSTEM = """CLINIC NOTE WRITER. Write the English clinic note for an interpreted consultation, in the concise
style of a hospital clinic letter. Inputs: the structured clinical record (authoritative), the clinician's own
plan/assessment utterances verbatim, and either the full English transcript or per-chunk fact summaries covering ALL
of it. Each input line starts with an utterance id (uNNN): put the ids an item comes from in "utts" (used only for
checking). NEVER write utterance ids, rule ids or timestamps in "text".
Sections (short clinical phrases, one fact per item, no fact repeated in two sections). Write every item in the
third person as a clinician would, never as the speaker's own first- or second-person sentence: "Cough for 2 weeks,
worse at night", not "I have been coughing for two weeks". Keep the speaker's meaning and words for symptoms; add
nothing.
- presenting_complaint: ONE item, the main complaint in a few words (patient's own term in quotes if notable).
- history: symptoms with onset/duration, relevant history, exposures/occupation, current medicines. NOT allergies,
  vitals or test results (added from the record).
- examination: findings the clinician stated aloud other than vitals and tests, written as findings ("Chest clear",
  not "Your chest is clear"); usually empty.
- assessment: ONLY statements from "assessment_candidates" (the clinician's own assessment sentences), each
  copied with at most a light change to third person ("Your throat looks viral." -> "Throat looks viral.").
  Never combine, infer, generalise or add a conclusion; never write a negation or exclusion ("no cardiac cause",
  "ruled out", "unlikely") unless those exact words were said. A held or superseded impression may only appear
  labelled, e.g. "Initial impression 'probably gastric', later revised".
Do not use dashes (no em or en dashes); use commas, colons or full stops.
- plan: tests ordered, management decisions, disposition, follow-up, in the clinician's words. Do NOT list named
  medicines, doses or stopped medicines (a medication table is added from the record); a medicine or treatment
  given WITHOUT a drug name ("a nasal spray", "something for the pain") is not in that table and goes here.
- information_given: advice and safety-net instructions the clinician gave the patient, and a misunderstanding of
  the patient's that the clinician corrected (in the clinician's words).
"case_summary" is the live copilot's running summary of the visit (chief complaint, history positives and
negatives, working diagnosis and differential, plan including medicines given without a name, findings stated
aloud, the patient's understanding and affect), each line ending with the ids it came from. Use it as a MAP so
nothing discussed is missed: relevant negatives the patient gave (history: "No fever"), a medicine or treatment the
clinician gave without naming it (plan, in their words, e.g. "Nasal spray after lunch and dinner for 3 weeks"), a
finding the clinician stated aloud (examination). It is NOT a source and NOT a conclusion: every item must be
supported by the utterances it cites (never cite the summary), and never turn the summary's working diagnosis,
differential or the patient's affect into an assessment or a finding unless the clinician said it.
Never add anything that was not said. Held turns were never interpreted to the patient.
Return JSON: {"presenting_complaint": [{"text","utts"}], "history": [...], "examination": [...], "assessment": [...],
"plan": [...], "information_given": [...]}."""

MAP_SYSTEM = """CHUNK SUMMARISER. You read one consecutive chunk of an interpreted clinic consultation transcript
(English renderings, each line "uNNN [mm:ss] ROLE: text"). List EVERY clinically relevant fact in it, one per item,
with the utterance ids it comes from: symptoms (with onset/timing), history, allergies (+reaction), medicines
(prescribed, stopped, dose, frequency), exam findings, vitals and results as stated by the clinician, the doctor's
assessments, plan, advice and disposition. Do not interpret or add anything. Return JSON {"facts": [{"kind",
"text", "utts"}]}."""

_PLAN_CUES = re.compile(
    r"\b(take|give|prescrib\w*|tablet|mg|gram|dose|stop|no more|drink|rest|avoid|come back|return|999|follow|"
    r"review|discharg\w*|go home|admit|refer|test|ecg|tracing|troponin|x-?ray|blood|pressure|temperature|normal|"
    r"probably|likely|looks|seems|diagnos\w*|think|plan|tomorrow|days?|weeks?)\b", re.I)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_IDS_IN_TEXT = re.compile(r"\s*\[(?:u\d{3}[^\]]*)\]|\(\s*u\d{3}(?:\s*,\s*u\d{3})*\s*\)|\bu\d{3}\b")


def est_tokens(text: str) -> int:
    return int(len(text or "") / 3.5) + 1


def _turn_line(t, max_chars: int | None = None) -> str:
    text = _CTRL.sub(" ", _english(t) or "").strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + f" […{len(text) - max_chars} more chars]"
    held = " (HELD - never interpreted)" if t.held else ""
    return f"{t.id} [{fmt_t(t.t_min)}] {t.role.upper()}{held}: {text}"


def _doctor_plan_lines(consult: Consultation) -> list[str]:
    return [_turn_line(t, 1200) for t in consult.turns
            if t.role == "doctor" and t.kind == "speech" and _PLAN_CUES.search(_english(t) or "")]


def _compact_state(st: dict) -> dict:
    def trim(x):
        if isinstance(x, dict):
            out = {}
            for k, v in x.items():
                if v in (None, "", [], {}, "unknown"):
                    continue
                if k == "evidence" and isinstance(v, list):
                    out[k] = [{"utt": e.get("utt"), "quote": str(e.get("quote") or "")[:120]}
                              for e in v if isinstance(e, dict)][:3]
                else:
                    out[k] = trim(v)
            return out
        if isinstance(x, list):
            return [trim(i) for i in x]
        return x
    return trim(st)


_CASE_LABELS = (("history", "history"), ("working_diagnosis", "working_diagnosis"), ("differential", "differential"),
                ("plan", "plan"), ("exam_claims", "stated_findings"), ("patient_understanding", "patient_understanding"),
                ("patient_affect", "patient_affect"))
CASE_ITEM_CHARS = 220


def case_context(case: dict | None) -> dict:
    """The running case summary (state["case"]) as compact context for the note writer: one line per item, ending with
    the utterance ids it came from ("No fever (u004)"); history split into positives and negatives; plan items keep
    their type ("medicine: nasal spray after lunch and dinner (u006)"). Empty lists are left out."""
    if not isinstance(case, dict):
        return {}

    def line(x: dict, prefix: str = "") -> str:
        text = " ".join(str(x.get("text") or "").split())[:CASE_ITEM_CHARS]
        ids = list(dict.fromkeys(str(e.get("utt")) for e in (x.get("evidence") or [])
                                 if isinstance(e, dict) and e.get("utt")))
        return f"{prefix}{text}" + (f" ({', '.join(ids[:4])})" if ids else "") if text else ""

    out: dict = {}
    cc = case.get("chief_complaint")
    if isinstance(cc, dict) and line(cc):
        out["chief_complaint"] = line(cc)
    for key, label in _CASE_LABELS:
        items = [x for x in (case.get(key) or []) if isinstance(x, dict)]
        if key == "history":
            pos = [line(x) for x in items if x.get("present") is not False]
            neg = [line(x) for x in items if x.get("present") is False]
            if any(pos):
                out["history_positives"] = [x for x in pos if x]
            if any(neg):
                out["history_negatives"] = [x for x in neg if x]
            continue
        lines = [line(x, f"{x.get('type')}: " if key == "plan" and x.get("type") else "") for x in items]
        if any(lines):
            out[label] = [x for x in lines if x]
    return out


def chunk_lines(lines: list[str], max_tokens: int = CHUNK_TOKENS) -> list[list[str]]:
    """Split on turn boundaries into chunks of <= max_tokens (a single over-long line gets a chunk of its own)."""
    chunks, cur, cur_t = [], [], 0
    for ln in lines:
        t = est_tokens(ln)
        if cur and cur_t + t > max_tokens:
            chunks.append(cur)
            cur, cur_t = [], 0
        cur.append(ln)
        cur_t += t
    if cur:
        chunks.append(cur)
    return chunks


def _summarise_chunk(idx: int, lines: list[str]) -> dict:
    first, last = lines[0].split(" ", 1)[0], lines[-1].split(" ", 1)[0]
    try:
        js = llm.chat_json(MAP_SYSTEM, "\n".join(lines), schema=MAP_SCHEMA, max_tokens=MAP_MAX_TOKENS,
                           reasoning=WRAPUP_REASONING, **llm.brain_route())
        if not isinstance(js.get("facts"), list):
            raise ValueError("no facts list (truncated or invalid JSON)")
        facts = [f for f in js["facts"] if isinstance(f, dict) and str(f.get("text") or "").strip()]
        return {"chunk": idx, "range": f"{first}-{last}", "facts": facts, "ok": True}
    except Exception as e:  # noqa: BLE001 - never drop the chunk: pass its doctor lines verbatim instead
        doctor = [ln for ln in lines if re.match(r"^u\d+ \[[^\]]*\] DOCTOR", ln)][:40]
        return {"chunk": idx, "range": f"{first}-{last}", "facts": [], "ok": False, "error": str(e)[:120],
                "doctor_lines_verbatim": [ln[:600] for ln in doctor]}


_SYN = [
    ({"likely", "probably", "probable", "presumably", "possibly", "possible", "suspected", "suspect", "suspicious"},
     "likely"),
    ({"looks", "appears", "seems", "appear", "look", "seem", "looking"}, "looks"),
    ({"no", "not", "without", "negative", "none", "never", "denies", "denied", "don't", "doesn't", "isn't", "wasn't",
      "nil", "absent"}, "neg"),
    ({"unlikely", "improbable"}, "unlikely"),
    ({"excluded", "exclude", "excludes", "ruled", "rule"}, "excluded"),
    ({"cardiac", "heart", "coronary", "acs", "infarction", "infarct", "angina", "ischaemia", "ischemia", "ischaemic",
      "ischemic", "mi", "stemi", "nstemi"}, "cardiac"),
    ({"gastric", "gastritis", "reflux", "gerd", "gord", "dyspepsia", "acidity"}, "gastric"),
    # "impression" is a label ("Initial impression ...", the clinician's own words), not a diagnostic claim
    ({"diagnosis", "diagnosed", "diagnose", "consistent"}, "diagnosis"),
]
_CLAIM_KEYS = {"likely", "neg", "unlikely", "excluded", "cardiac", "gastric", "diagnosis"}
_DIAG_STEMS = ("viral", "virus", "bacte", "infec", "pneum", "sepsi", "septi", "strok", "fract", "malar", "diabe",
               "hyper", "hypot", "asthm", "migra", "appen", "covid", "influ", "dehyd", "pulmo", "embol", "menin",
               "renal", "kidne", "hepat", "anaem", "anemi", "ulcer", "cance", "tumou", "tumor", "synco", "tonsi",
               "phary", "laryn", "bronc", "cysti", "pyelo", "colic", "chole", "pancr", "panic", "anxie", "depre",
               "benig", "malig", "musc", "costo", "pleur", "pneumo", "heats", "heatst", "derma", "allerg", "anaph")
_NORM_WORDS = {"patient", "patients", "clinician", "doctor", "initial", "impression", "revised", "superseded",
               "earlier", "later", "first", "final", "says", "said", "stated", "states", "thinks", "considered",
               "noted", "which", "that", "this", "with", "were", "have", "been", "your", "their", "just"}
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "be", "it", "its", "it's",
         "at", "as", "by", "from", "but", "so", "very", "also", "any", "some", "than"}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'’-]*", (text or "").replace("’", "'"))


def _canon(w: str) -> str:
    w = w.lower().strip("'-")
    for group, key in _SYN:
        if w in group:
            return key
    return w[:5] if len(w) > 5 else w


def _is_claim(w: str) -> bool:
    c = _canon(w)
    return c in _CLAIM_KEYS or any(w.lower().startswith(st) for st in _DIAG_STEMS)


def unsupported_claims(text: str, source: str) -> list[str]:
    """Diagnostic / exclusion terms in `text` that the cited source utterances do not contain (synonym-tolerant:
    'likely' ~ 'probably', 'appears' ~ 'looks', 'heart' ~ 'cardiac'). A negation must also negate a word the source
    contains ("no cardiac cause" needs "cardiac"/"heart" in the source)."""
    stoks = _tokens(source)
    src = {_canon(w) for w in stoks}
    # what the source actually negates: "no amoxicillin" negates amoxicillin, not the heart
    negated = {_canon(nx) for i, w in enumerate(stoks) if _canon(w) == "neg"
               for nx in [t for t in stoks[i + 1:i + 4] if t.lower() not in _STOP][:2]}
    toks = _tokens(text)
    bad = []
    for i, w in enumerate(toks):
        c = _canon(w)
        if _is_claim(w) and c not in src:
            bad.append(w)
        if c == "neg":
            nxt = next((t for t in toks[i + 1:i + 4] if t.lower() not in _STOP), None)
            if nxt and _canon(nxt) not in negated:
                bad.append(f"{w} {nxt}")
    return list(dict.fromkeys(bad))


def _coverage(text: str, source: str) -> float:
    """Share of the item's content words found in the cited source (a light rewording keeps this high)."""
    src = {_canon(w) for w in _tokens(source)}
    words = [w for w in _tokens(text) if len(w) > 2 and w.lower() not in _STOP and w.lower() not in _NORM_WORDS]
    if not words:
        return 1.0
    return sum(1 for w in words if _canon(w) in src) / len(words)


def _third_person(s: str) -> str:
    s = re.sub(r"^(?:actually|so|well|ok|okay|right|now)\b[,\s]*", "", s.strip(), flags=re.I)
    s = re.sub(r"^your\s+", "", s, flags=re.I)
    s = re.sub(r"\byour\b", "the", s, flags=re.I)
    s = re.sub(r"\byou\b", "the patient", s, flags=re.I)
    s = s.strip()
    return (s[:1].upper() + s[1:]) if s else s


def assessment_candidates(consult: Consultation) -> list[dict]:
    """The clinician's own assessment-type sentences: [{"utt","text","held","superseded"}]. A held sentence (never
    interpreted) or any earlier impression followed by a later one counts as superseded."""
    out = []
    for t, sent in _doctor_sentences(consult, include_held=True):
        if _ASSESS_CUES.search(sent):
            out.append({"utt": t.id, "text": sent, "held": bool(t.held), "t_min": t.t_min})
    for i, c in enumerate(out):
        c["superseded"] = c["held"] or any(o["t_min"] > c["t_min"] and not o["held"] for o in out[i + 1:]) and \
            c["held"]
    return out


def assessment_from_candidates(consult: Consultation) -> list[str]:
    """Deterministic ASSESSMENT: the clinician's sentences, third person; superseded ones clearly labelled."""
    lines = []
    for c in assessment_candidates(consult):
        if c["superseded"]:
            q = re.sub(r"^(?:it'?s|it is)\s+", "", c["text"].strip().rstrip("."), flags=re.I)
            lines.append(f"Initial impression “{q}”, later revised")
        else:
            lines.append(_third_person(c["text"]))
    return lines


def _guard_section(key: str, items: list[dict], consult: Consultation, warnings: list[str]) -> list[dict]:
    """Drop items whose diagnostic/exclusion claims are not in the cited utterances; for ASSESSMENT also require the
    item to be (a light rewording of) the cited clinician sentence and label held impressions."""
    turns = {t.id: t for t in consult.turns}
    kept = []
    for it in items:
        src = " ".join(_english(turns[u]) for u in it["utts"] if u in turns)
        bad = unsupported_claims(it["text"], src)
        if key == "assessment" and not bad:
            # an assessment must be (a light rewording of) ONE clinician sentence, not a blend of several
            sents = [x for u in it["utts"] if u in turns for x in _sentences(_english(turns[u]))]
            best = max((_coverage(it["text"], x) for x in sents), default=0.0)
            if best < 0.75 or not any(not unsupported_claims(it["text"], x) for x in sents):
                bad = ["wording not found in a single clinician statement"]
        if bad:
            who = "the clinician" if key in ("assessment", "plan") else "anyone in the consultation"
            warnings.append(f"Dropped from {key.replace('_', ' ')}: “{it['text']}”: not stated by {who} "
                            f"({', '.join(bad[:3])}).")
            continue
        if key == "assessment" and any(turns[u].held for u in it["utts"] if u in turns) and \
                not re.search(r"initial|revised|supersed|earlier|first", it["text"], re.I):
            it = dict(it, text=f"Initial impression “{it['text'].rstrip('.')}”, later revised")
        kept.append(it)
    return kept


def _dedupe_plan(items: list[dict], consult: Consultation) -> list[dict]:
    """Plan items that only restate a medicine change (dose, frequency, stop) are in the medication table already."""
    with consult.lock:
        st = copy.deepcopy(consult.state)
    drugs = {_norm_drug(m.get("drug", "")) for m in st.get("prescribed_meds", []) + st.get("stopped_meds", [])}
    drugs.discard("")
    out = []
    for it in items:
        low = it["text"].lower()
        if any(d in low for d in drugs) and re.search(
                r"\d|\b(mg|grams?|times|daily|once|twice|stop\w*|withdraw\w*|no|discontinu\w*)\b", low):
            continue
        out.append(it)
    return out


def _validate_note(js: dict, consult: Consultation) -> tuple[dict | None, list[str]]:
    """All sections must be lists; items need text + >=1 real utterance id; assessment / plan / information given
    must cite a doctor turn. Ids are stripped from the text (they stay in "utts" for traceability)."""
    if not isinstance(js, dict) or any(not isinstance(js.get(k), list) for k in NOTE_SECTIONS):
        return None, ["note JSON incomplete (missing sections or truncated)"]
    roles = {t.id: t.role for t in consult.turns}
    out, dropped = {}, 0
    for k in NOTE_SECTIONS:
        items = []
        for it in js[k]:
            if not isinstance(it, dict):
                dropped += 1
                continue
            text = dedash(_IDS_IN_TEXT.sub("", _CTRL.sub(" ", str(it.get("text") or ""))).strip())
            utts = [u for u in (it.get("utts") or []) if isinstance(u, str) and u in roles]
            if not text or not utts:
                dropped += 1
                continue
            if k in ("assessment", "plan", "information_given") and not any(roles[u] == "doctor" for u in utts):
                dropped += 1
                continue
            items.append({"text": text, "utts": list(dict.fromkeys(utts))})
        out[k] = items
    out["presenting_complaint"] = out["presenting_complaint"][:1]
    if not any(out[k] for k in NOTE_SECTIONS):
        return None, ["note JSON had no sourced items"]
    warnings = [f"{dropped} unsourced note item(s) dropped"] if dropped else []
    for k in NOTE_SECTIONS:
        n0 = len(out[k])
        out[k] = _guard_section(k, out[k], consult, warnings)
        if k == "assessment" and (len(out[k]) < n0 or (not out[k] and assessment_candidates(consult))):
            # anything dropped: the assessment becomes the clinician's own sentences, verbatim (third person)
            cands = assessment_candidates(consult)
            out[k] = [{"text": line, "utts": [c["utt"]]} for line, c in
                      zip(assessment_from_candidates(consult), cands)]
    out["plan"] = _dedupe_plan(out["plan"], consult)
    return out, warnings


def _sections_from_state(consult: Consultation) -> dict[str, list[str]]:
    """Deterministic note sections from the structured record + the doctor's own sentences (no LLM)."""
    with consult.lock:
        st = copy.deepcopy(consult.state)
    syms = st.get("symptoms", [])
    pc = ", ".join(_human(s.get("code", "")).lower() for s in syms[:3]).capitalize()
    hits = st.get("idiom_hits", [])
    if pc and hits:
        pc += f" (described as “{hits[0].get('matched', '')}”)"
    hist = []
    for s in syms:
        extra = [str(x) for x in (s.get("onset"), s.get("severity")) if x and x != "unknown"]
        hist.append(_human(s.get("code", "")) + (f" ({'; '.join(extra)})" if extra else ""))
    pt = st.get("patient", {}) or {}
    if pt.get("heat_exposure"):
        hist.append("Works outdoors (heat exposure)")
    for m in st.get("current_meds", []):
        hist.append(f"Current medicine: {m.get('drug')} {_fmt_mg(m.get('dose_mg'))}".strip())
    assess = assessment_from_candidates(consult)  # the clinician's own words only (no coded diagnoses)
    plan = []
    invs = [_human(i.get("code", "")) for i in st.get("investigations", [])]
    if invs:
        plan.append("Investigations: " + ", ".join(invs))
    disp = (st.get("disposition") or {}).get("type")
    if disp:
        plan.append({"discharge": "Discharged home", "admit": "Admitted", "refer": "Referred",
                     "observe": "Kept for observation"}.get(disp, str(disp).capitalize()))
    info = []
    for _t, s in _doctor_sentences(consult):
        if _SAFETY_CUES.search(s) or (_ADVICE_CUES.search(s) and not re.search(r"\b(take|give)\b", s, re.I)):
            info.append(f"“{s}”")
    return {"presenting_complaint": [pc] if pc else [], "history": hist, "examination": [], "assessment": assess,
            "plan": plan, "information_given": info}


def _med_change_line(m: dict) -> str:
    if m.get("stopped"):
        dose = f" {m['dose']}" if m.get("dose") not in (None, "", "—") else ""
        return f"{m['medicine']}{dose}: stopped" + (f" ({m['reason']})" if m.get("reason") else "")
    bits = [f"{m['medicine']} {m['dose']}".replace("—", "").strip()]
    bits += [str(m[k]).lower() for k in ("route", "frequency") if m.get(k) not in (None, "", "—", "Not stated")]
    if m.get("duration") not in (None, "", "—", "Not stated"):
        bits.append(f"for {m['duration']}")
    return ", ".join(bits) + ": " + str(m.get("status", "started")).lower()


def _md_and_txt(consult: Consultation, sec: dict[str, list[str]], tabs: dict, fallback: bool) -> tuple[str, str]:
    """The note as editable markdown (Review screen) and as plain text (copy into the EMR). No utterance ids."""
    from bayan.outputs import LANG_NAMES

    lang = LANG_NAMES.get(consult.patient_lang, consult.patient_lang)
    started = datetime.fromtimestamp(consult.started_at)
    head = " · ".join(x for x in (f"Encounter {str(consult.id).upper()}", f"{started:%d %b %Y %H:%M}",
                                  clinic_name(consult), f"Patient language: {lang}",
                                  "Interpreter: Bayan AI") if x)
    body: dict[str, list[str]] = {
        "allergies": tabs["allergies"] or ["No known allergies recorded"],
        "presenting_complaint": sec.get("presenting_complaint", []),
        "history": sec.get("history", []),
        "observations": ([tabs["vitals"] + " (as stated by clinician)"] if tabs["vitals"] else []) +
                        list(sec.get("examination", [])) +
                        [f"{t}: {r}" + (" (as stated by clinician)" if r != "Pending" else "")
                         for t, _s, r in tabs["tests"]],
        "assessment": sec.get("assessment", []),
        "plan": sec.get("plan", []),
        "medication_changes": [_med_change_line(m) for m in tabs["med_changes"]],
        "information_given": list(sec.get("information_given", [])) +
                             [f"Care plan given in {LANG_NAME(lang)} (QR code to the plan page and PDF)."],
        "safety_alerts": list(tabs["safety_alerts"]),
    }
    md = ["# Consultation note", "", head, ""]
    txt = ["Consultation note", head, ""]
    if fallback:
        md += [f"> **{FALLBACK_LABEL}**", ""]
        txt += [FALLBACK_LABEL, ""]
    for key, title in MD_TITLES:
        lines = [dedash(str(x)) for x in body[key] if str(x).strip()]
        if not lines:
            continue
        md += [f"## {title}", ""]
        txt += [title]
        if key == "presenting_complaint":
            md += [lines[0], ""]
            txt += [lines[0], ""]
            continue
        md += [f"- {x}" for x in lines] + [""]
        txt += [f"- {x}" for x in lines] + [""]
    txt += ["Reviewed by: ____________    Signature: ____________    Date/time: ____________"]
    return "\n".join(md), "\n".join(txt)


def note_from_state(consult: Consultation, auto_label: bool = False) -> str:
    """Deterministic note (markdown) built purely from the structured record — the fallback."""
    return _md_and_txt(consult, _sections_from_state(consult), note_tables(consult), auto_label)[0]


def draft_note_llm(consult: Consultation) -> tuple[dict | None, dict]:
    """Note sections as schema'd JSON from bounded input (record + doctor plan utterances + the full English
    transcript if it fits the budget, else map-reduce chunk summaries covering all of it), validated; one retry with
    a larger cap and condensed input. Returns (validated JSON or None, info)."""
    with consult.lock:
        st = copy.deepcopy(consult.state)
        turns = list(consult.turns)
    info: dict = {"source": "fallback", "calls": 0, "chunks": 0, "warnings": []}
    case = case_context(st.pop("case", None))   # the running case summary: context for the writer, not a source
    state_js = _compact_state(st)
    plan_lines = _doctor_plan_lines(consult)
    transcript = [_turn_line(t) for t in turns]
    base = est_tokens(json.dumps(state_js, ensure_ascii=False)) + sum(est_tokens(x) for x in plan_lines) + 400 \
        + est_tokens(json.dumps(case, ensure_ascii=False))
    payload: dict = {"record": state_js, "case_summary": case, "clinician_utterances": plan_lines,
                     "assessment_candidates": [f"{c['utt']}{' (HELD, superseded)' if c['superseded'] else ''}: "
                                               f"{c['text']}" for c in assessment_candidates(consult)]}
    if base + sum(est_tokens(x) for x in transcript) <= NOTE_INPUT_BUDGET:
        payload["transcript"] = "\n".join(transcript)
    else:
        from concurrent.futures import ThreadPoolExecutor

        chunks = chunk_lines(transcript, CHUNK_TOKENS)
        info["chunks"] = len(chunks)
        with ThreadPoolExecutor(max_workers=max(1, min(MAP_WORKERS, len(chunks)))) as ex:
            summaries = list(ex.map(lambda a: _summarise_chunk(*a), list(enumerate(chunks))))
        info["calls"] += len(chunks)
        failed = [x["range"] for x in summaries if not x["ok"]]
        if failed:
            info["warnings"].append(f"{len(failed)} transcript chunk summary(ies) failed ({', '.join(failed)}); "
                                    "their doctor lines were used verbatim.")
        payload["chunk_summaries"] = summaries
        consult.log("tool", f"note map-reduce → {len(chunks)} chunk(s), {len(failed)} failed")
    attempts = [(NOTE_MAX_TOKENS, payload),
                (int(NOTE_MAX_TOKENS * 1.5), {k: v for k, v in payload.items() if k != "transcript"})]
    for i, (cap, pl) in enumerate(attempts):
        if "chunk_summaries" in pl and est_tokens(json.dumps(pl, ensure_ascii=False)) > NOTE_INPUT_BUDGET:
            pl = dict(pl, chunk_summaries=[dict(c, facts=c["facts"][:25]) for c in pl["chunk_summaries"]])
        info["calls"] += 1
        try:
            js = llm.chat_json(NOTE_SYSTEM, json.dumps(pl, ensure_ascii=False), schema=NOTE_SCHEMA, max_tokens=cap,
                               reasoning=WRAPUP_REASONING, **llm.brain_route())
        except Exception as e:  # noqa: BLE001
            info["warnings"].append(f"Clinic note writer failed ({type(e).__name__})")
            consult.log("error", f"note_llm attempt {i + 1} failed: {e}")
            break  # provider down: a retry would fail the same way
        note, issues = _validate_note(js, consult)
        if note is not None:
            info["source"] = ("llm" if i == 0 else "llm-retry") + ("+map-reduce" if info["chunks"] else "")
            info["warnings"] += issues
            consult.log("tool", f"note_llm → {sum(len(note[k]) for k in NOTE_SECTIONS)} items ({info['source']})")
            return note, info
        consult.log("error", f"note_llm attempt {i + 1}: {'; '.join(issues)}; "
                             + ("retrying with a larger cap" if i == 0 else "using the structured-record note"))
    info["warnings"].append(f"Clinic note: {FALLBACK_LABEL}.")
    return None, info


def draft_note(consult: Consultation, care_plan: dict | None = None) -> str:
    """The clinic note as markdown (contract; editable on the Review screen). Also stores consult.outputs:
    "note_txt" (plain text for the EMR), "note_sections", "note_json" (with utterance ids, for traceability only) and
    "note_info" (source, calls, chunks, warnings)."""
    js, info = draft_note_llm(consult)
    if js is not None:
        sec = {k: [it["text"] for it in js[k]] for k in NOTE_SECTIONS}
    else:
        sec = _sections_from_state(consult)
    md, txt = _md_and_txt(consult, sec, note_tables(consult, care_plan), js is None)
    with consult.lock:
        consult.outputs["note_json"] = js
        consult.outputs["note_sections"] = sec
        consult.outputs["note_info"] = info
        consult.outputs["note_txt"] = txt
    return md


def _idiom_entry(idiom_id: str | None) -> dict | None:
    if not idiom_id:
        return None
    from .idioms import IdiomIndex
    global _IDIOMS
    try:
        _IDIOMS
    except NameError:
        _IDIOMS = IdiomIndex()
    return _IDIOMS.get(idiom_id)


_SYSTEM_USERS = {"system", "rules", "agent", "fallback", "lexicon", None}


def refresh_note(consult: Consultation, care_plan: dict | None) -> str:
    """Re-render the note markdown/plain text with the final care plan (medication table marks medicines the safety
    check kept off the patient sheet). Uses the sections already drafted; no LLM call."""
    sec = consult.outputs.get("note_sections") or _sections_from_state(consult)
    fallback = (consult.outputs.get("note_info") or {}).get("source", "fallback") == "fallback"
    md, txt = _md_and_txt(consult, sec, note_tables(consult, care_plan), fallback)
    with consult.lock:
        consult.outputs["note_txt"] = txt
    return md


# ====================================================================== patient care plan
# Routine-anchored timetable (UMS / AHRQ pill card style): when you wake up, breakfast, lunch, dinner, bedtime.
SLOTS = ("wake", "breakfast", "lunch", "dinner", "bedtime")
_TIME_TO_SLOT = {"on_waking": "wake", "waking": "wake", "wake": "wake", "morning": "breakfast",
                 "breakfast": "breakfast", "midday": "lunch", "noon": "lunch", "lunch": "lunch", "afternoon": "lunch",
                 "evening": "dinner", "dinner": "dinner", "night": "bedtime", "bedtime": "bedtime"}
_FOOD_CELL = {"before_food": "before food", "with_food": "with food", "after_food": "after food",
              "empty_stomach": "on an empty stomach"}
_FOOD_WORD = {"before_food": "before", "with_food": "with", "after_food": "after"}
_MEAL = {"breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner"}
_PLURAL = {"capsule": "capsules", "tablet": "tablets", "spray": "sprays", "drop": "drops", "puff": "puffs",
           "sachet": "sachets", "patch": "patches", "suppository": "suppositories", "teaspoon": "teaspoons",
           "spoon": "spoons", "dose": "doses", "inhalation": "inhalations", "pessary": "pessaries",
           "application": "applications"}


def _num(x) -> str:
    try:
        return f"{float(x):g}"
    except (TypeError, ValueError):
        return str(x or "")


def schedule_slots(m: dict) -> list[str]:
    """Timetable columns for a regular medicine: from extracted times when present, else from the frequency
    (1/day breakfast; 2/day breakfast + dinner with a food relation, else breakfast + bedtime; 3/day the three meals;
    4/day meals + bedtime). Interval dosing ("every 8 hours") has no columns."""
    times = [t for t in (m.get("times") or []) if isinstance(t, str)]
    if times:
        return [s for s in SLOTS if s in {_TIME_TO_SLOT.get(t.lower(), "") for t in times}]
    if m.get("interval_hours"):
        return []
    n = m.get("frequency_per_day")
    try:
        n = int(n)
    except (TypeError, ValueError):
        return []
    food = m.get("food")
    return {1: ["breakfast"], 2: ["breakfast", "dinner"] if food else ["breakfast", "bedtime"],
            3: ["breakfast", "lunch", "dinner"], 4: ["breakfast", "lunch", "dinner", "bedtime"]}.get(n, [])


_USE_FORMS = ("spray", "inhaler", "drop", "cream", "ointment", "gel", "patch", "injection", "lotion")
_TIME_ONE = {"on_waking": "when you wake up", "morning": "every morning", "midday": "at midday",
             "evening": "every evening", "bedtime": "at bedtime"}
_TIME_MANY = {"on_waking": "when you wake up", "morning": "in the morning", "midday": "at midday",
              "evening": "in the evening", "bedtime": "at bedtime"}
_TIME_ORDER = ("on_waking", "morning", "midday", "evening", "bedtime")
_TIME_NORM = {"waking": "on_waking", "wake": "on_waking", "noon": "midday", "lunch": "midday", "afternoon": "midday",
              "breakfast": "morning", "dinner": "evening", "night": "bedtime"}
_FOOD_PHRASE = {"before_food": "before food", "with_food": "with food", "after_food": "after food",
                "empty_stomach": "on an empty stomach"}


def amount_en(m: dict) -> str:
    """"1 capsule", "2 sprays in each nostril", else the dose ("500 mg")."""
    amount, unit = m.get("amount"), (m.get("unit") or "").strip()
    if amount and unit:
        u = unit if _num(amount) == "1" else _PLURAL.get(unit.lower(), unit)
        text = f"{_num(amount)} {u}"
    else:
        text = _fmt_mg(m.get("dose_mg")) or str(m.get("dose_text") or "").strip() or "the dose"
    site = (m.get("site") or "").strip()
    if site and not re.match(r"^(in|into|on|onto|to|under|behind)\b", site, re.I):
        site = f"in {site}" if re.match(r"^(each|both|the|your|one)\b", site, re.I) else site
    return f"{text} {site}" if site else text


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _form_text(m: dict) -> str:
    form = (m.get("form") or "").strip().replace("_", " ").lower()
    return "" if form in ("", "other") else form


def medicine_title_en(m: dict) -> str:
    """Line 1 of the medicine block: name + strength + form ("Amoxicillin 500 mg capsule")."""
    name = str(m.get("name") or m.get("drug") or "").strip()
    strength = _fmt_mg(m.get("dose_mg")) or ("" if m.get("amount") else str(m.get("dose_text") or ""))
    return " ".join(x for x in (name, strength, _form_text(m)) if x)


def medicine_line_en(m: dict) -> str:
    """Line 2 of the medicine block: ONE plain instruction from the structured record (never from the LLM), e.g.
    "Take 1 capsule 3 times a day, after food. For 5 days." / "Take 1 capsule every morning before breakfast. For
    14 days." / "Use 2 sprays in each nostril when you wake up. For 1 month." / "Take 1 g only when needed for throat
    pain. No more than 3 times a day." The clinician's extra instructions follow as short sentences."""
    form = _form_text(m)
    verb = "Use" if any(f in form for f in _USE_FORMS) else "Take"
    amt = amount_en(m)
    food = m.get("food") or ""
    if m.get("prn"):
        why = (m.get("as_needed_for") or m.get("indication") or "").strip().rstrip(".")
        line = f"{verb} {amt} only when needed" + (f" for {why}" if why else "") + "."
        n = m.get("max_per_day") or m.get("frequency_per_day")
        if n:
            line += f" No more than {_num(n)} times a day."
        if m.get("min_hours_between"):
            line += f" Wait at least {_num(m['min_hours_between'])} hours between doses."
    else:
        times = []
        for t in m.get("times") or []:
            t = _TIME_NORM.get(str(t).lower(), str(t).lower())
            if t in _TIME_ONE and t not in times:
                times.append(t)
        times.sort(key=_TIME_ORDER.index)
        if times:
            when = _TIME_ONE[times[0]] if len(times) == 1 else _join([_TIME_MANY[t] for t in times])
            if times == ["morning"] and food in ("before_food", "with_food"):
                when += " before breakfast" if food == "before_food" else " with breakfast"
                food_txt = ""
            else:
                food_txt = _FOOD_PHRASE.get(food, "")
            line = f"{verb} {amt} {when}" + (f", {food_txt}" if food_txt else "") + "."
        else:
            n = m.get("frequency_per_day")
            if m.get("interval_hours"):
                when = f"every {_num(m['interval_hours'])} hours"
            elif n:
                when = {"1": "once a day"}.get(_num(n), f"{_num(n)} times a day")
            else:
                when = "as your doctor told you"
            food_txt = _FOOD_PHRASE.get(food, "")
            line = f"{verb} {amt} {when}" + (f", {food_txt}" if food_txt else "") + "."
        dur = (m.get("duration_en") or "").strip()
        if dur:
            line += f" {dur[:1].upper() + dur[1:]}." if dur.lower().startswith("until") else f" For {dur}."
    for i in m.get("instructions") or []:
        i = str(i).strip().rstrip(".")
        if i:
            line += f" {i[:1].upper() + i[1:]}."
    return line


def _duration_en(m: dict) -> str:
    if m.get("duration_text"):
        return str(m["duration_text"]).strip()
    d = m.get("duration_days")
    if not d:
        return ""
    d = float(d)
    return "1 day" if d == 1 else f"{d:g} days"


CARE_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {"type": "array", "items": {"type": "object", "properties": {
            "key": {"type": "string"}, "native": {"type": "string"}}, "required": ["key", "native"]}},
        "red_flags": {"type": "array", "items": {"type": "object", "properties": {
            "en": {"type": "string"}, "native": {"type": "string"}}, "required": ["en", "native"]}},
        "advice": {"type": "array", "items": {"type": "object", "properties": {
            "en": {"type": "string"}, "native": {"type": "string"}}, "required": ["en", "native"]}},
        "follow_up": {"type": "object", "properties": {"en": {"type": "string"}, "native": {"type": "string"}},
                      "required": ["en", "native"]},
    },
    "required": ["translations", "red_flags", "advice", "follow_up"],
}

CARE_PLAN_SYSTEM = """You write the patient's take-home medicine and care sheet for Bayan AI, a medical interpreter at
a clinic in Qatar. Patient language: {lang_name}.
1. "translations": translate EVERY item of "translate" ({{"key": English}}) into {lang_name} in its native script and
   return [{{"key", "native"}}]. Faithful and literal: do not add, drop, soften or explain anything; keep every number
   and unit; keep medicine names recognisable (native script). Keys ending in ".title" are a medicine name with
   strength and form; keys ending in ".line" are the instruction for taking it; keys ending in ".amount" are a
   single dose amount for a schedule table ("1 capsule").
2. "red_flags": each danger sign the clinician said should make the patient call 999 or come back, one per item,
   at most 6, as short plain English ("Your chest pain comes back.") plus a faithful translation.
3. "advice": the clinician's other instructions (not medicines, not danger signs), at most 4, same format. A
   medicine the clinician stopped, withdrew or ruled out ("let's not use amoxicillin") is NOT advice.
4. "follow_up": {{"en", "native"}}: when and where to come back, only if the clinician said it; else empty strings.
Plain English for about a 6th-grade reader, imperative, at most 12 words, numerals. Do not use dashes (no em or en
dashes); use commas, colons or full stops. Use ONLY the clinician's words; never add a danger sign or advice."""


def _skeleton(consult: Consultation, st: dict) -> tuple[dict, list[str]]:
    from bayan.outputs import LANG_NAMES, labels

    warnings: list[str] = []
    meds_in = final_meds(st)
    now = consult.now_min()
    lang = consult.patient_lang
    meds, excluded = [], []
    # Rules the clinician explicitly overrode ("Speak it anyway"): the doctor decided; keep the drug on the sheet.
    try:
        overridden = {rid for c in (consult.cards.all_cards() if consult.cards else [])
                      if c.get("status") == "overridden" for rid in (c.get("rule_ids") or [])}
    except Exception:  # noqa: BLE001
        overridden = set()
    for m in meds_in:
        others = [o for o in meds_in if o is not m]
        fired, note = safety_check(st, m, others, now)
        if note and note not in warnings:
            warnings.append(note)
        # Only CRITICAL rules keep a drug off the patient's sheet (info/caution, e.g. "no cross-reactivity" or
        # "allergies not asked", are for the doctor, not grounds to drop a prescribed medicine).
        kept = [r for r in fired if r.get("severity") == "critical" and r.get("rule_id") in overridden]
        if kept:
            warnings.append(f"{m.get('drug')} kept on the patient's sheet: "
                            f"{', '.join(sorted({r.get('rule_id') for r in kept}))} overridden by the clinician.")
        fired = [r for r in fired if r.get("severity") == "critical" and r.get("rule_id") not in overridden]
        if fired:
            ids = [r.get("rule_id") or "?" for r in fired]
            msg = "; ".join(f"{r.get('rule_id')} ({r.get('severity')}): {r.get('message') or r.get('message_en') or ''}"
                            for r in fired)
            warnings.append(f"EXCLUDED {m.get('drug')} {_fmt_mg(m.get('dose_mg'))} x{m.get('frequency_per_day')}/day "
                            f"from the patient care plan. {msg}. Review the prescription before sending.")
            excluded.append({"name": m.get("drug"), "rules": ids, "reason": msg})
            continue
        prn = bool(m.get("as_needed")) or _is_prn(m)
        n = m.get("frequency_per_day")
        med = {
            "name": str(m.get("drug", "")).capitalize(), "drug": m.get("drug"),
            "dose_text": _fmt_mg(m.get("dose_mg")) or str(m.get("dose_text") or "as directed"),
            "dose_mg": m.get("dose_mg"), "frequency_per_day": n, "daily_dose_mg": m.get("daily_dose_mg"),
            "duration_days": m.get("duration_days"), "prn": prn, "indication": str(m.get("indication") or ""),
            "freq_en": _freq_en(n, prn),
        }
        for k in ("form", "amount", "unit", "site", "times", "food", "interval_hours", "as_needed_for",
                  "max_per_day", "min_hours_between", "duration_text", "instructions"):
            if m.get(k) not in (None, "", []):
                med[k] = m[k]
        med["slots"] = [] if prn else schedule_slots(med)
        med["schedule"] = "prn" if prn else ("regular" if (med["slots"] or med.get("interval_hours")) else "other")
        med["duration_en"] = _duration_en(med)
        med["amount_en"] = amount_en(med)
        med["food_en"] = _FOOD_PHRASE.get(med.get("food") or "", "")
        med["title_en"] = medicine_title_en(med)
        med["dose_amount_en"] = amount_en({k: v for k, v in med.items() if k != "site"})
        med["note_en"] = medicine_line_en(med)   # timing from the extracted times, else from the frequency
        med["times"] = list(med["slots"])
        for k in ("name_native", "title_native", "note_native", "dose_amount_native"):
            med[k] = ""
        meds.append(med)
    avoid = []
    stopped = [s.get("drug") for s in st.get("stopped_meds", []) if s.get("drug")]
    for a in st.get("allergies", []):
        sub = a.get("substance") or ", ".join(a.get("class") or []) or "this medicine"
        a_classes = set(a.get("class") or []) | set(_classes(sub))
        same = [d for d in stopped if set(_classes(d)) & a_classes and _norm_drug(d) != _norm_drug(sub)]
        if not same:  # name one common member of the class so the patient recognises it on a box
            same = [mem for c in a_classes for mem in _meta()["drug_classes"].get(c, [])][:1]
        en = f"{sub.capitalize()} medicines" + (f", for example {', '.join(same)}" if same else "") + \
            ". You are allergic."
        avoid.append({"substance": sub, "en": en, "native": ""})
    plan = {"lang": lang, "lang_name": LANG_NAMES.get(lang, lang), "medicines": meds, "avoid": avoid,
            "red_flags": [], "advice": [], "follow_up": {"en": "", "native": ""}, "emergency": EMERGENCY,
            "title_native": labels(lang)["title"], "title_en": labels("en")["title"], "machine_translated": True,
            "date": datetime.fromtimestamp(consult.started_at).strftime("%Y-%m-%d"),
            "excluded": excluded, "warnings": warnings}
    return plan, warnings


def _fallback_lines(consult: Consultation) -> dict:
    """No LLM: the doctor's own sentences, English only."""
    red, adv, fu = [], [], {"en": "", "native": ""}
    for _t, s in _doctor_sentences(consult):
        if _SAFETY_CUES.search(s):
            red.append({"en": s, "native": ""})
        elif _ADVICE_CUES.search(s) and not re.search(r"\b(take|give)\b", s, re.I):
            adv.append({"en": s, "native": ""})
        elif _FOLLOW_CUES.search(s) and not fu["en"]:
            fu = {"en": s, "native": ""}
    return {"red_flags": red[:6], "advice": adv[:4], "follow_up": fu}


def _line_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _drugs_named(text: str, extra: set[str]) -> set[str]:
    """Generic names of the medicines a line names: known INNs/brands, plus the consultation's own drug names."""
    found: set[str] = set()
    try:
        from .vocab import drugs_in_text
        found |= {_norm_drug(d) for d in drugs_in_text(text)}
    except Exception:  # noqa: BLE001
        pass
    low = str(text or "").lower()
    for name in extra:
        if name and re.search(rf"(?<![a-z]){re.escape(name.lower())}(?![a-z])", low):
            found.add(_norm_drug(name))
    return found


def dedupe_plan_lines(plan: dict, st: dict) -> list[str]:
    """Keeps every instruction in ONE section of the sheet (mutates the plan; returns what was dropped).
    An "advice" line that names a medicine already covered by "medicines" or "avoid" (e.g. the doctor's withdrawal
    "Let's not use amoxicillin." next to "Penicillin medicines, for example amoxicillin. You are allergic.") is
    dropped: the medicine sections say it, in the checked template form. Advice and danger-sign lines that repeat a
    line already on the sheet are dropped too."""
    dropped: list[str] = []
    names = {str(x.get("drug") or "") for k in ("prescribed_meds", "stopped_meds") for x in st.get(k, [])}
    names |= {str(a.get("substance") or "") for a in st.get("allergies", [])}
    names.discard("")
    covered = {_norm_drug(m.get("drug") or m.get("name") or "") for m in plan.get("medicines", [])}
    avoid_classes: set[str] = set()
    for a in plan.get("avoid", []):
        sub = str(a.get("substance") or "")
        covered.add(_norm_drug(sub))
        avoid_classes |= set(_classes(sub))
        covered |= _drugs_named(a.get("en") or "", names)

    def _is_covered(drug: str) -> bool:
        return drug in covered or bool(set(_classes(drug)) & avoid_classes)

    seen = {_line_key(a.get("en")) for a in plan.get("avoid", [])}
    seen |= {_line_key(m.get(k)) for m in plan.get("medicines", []) for k in ("note_en", "title_en")}
    fu = _line_key((plan.get("follow_up") or {}).get("en"))
    for section in ("red_flags", "advice"):
        keep = []
        for line in plan.get(section, []):
            key = _line_key(line.get("en"))
            if not key or key in seen or key == fu:
                dropped.append(f"{section}: {line.get('en')} (repeated)")
                continue
            if section == "advice":
                named = _drugs_named(line.get("en") or "", names)
                if named and all(_is_covered(d) for d in named):
                    dropped.append(f"advice: {line.get('en')} (medicine already on the sheet)")
                    continue
            seen.add(key)
            keep.append(line)
        plan[section] = keep
    return dropped


def _pairs(items: Any, limit: int) -> list[dict]:
    out = []
    for it in items or []:
        if isinstance(it, dict) and str(it.get("en") or "").strip():
            out.append({"en": dedash(str(it["en"]).strip()), "native": dedash(str(it.get("native") or "").strip())})
        elif isinstance(it, str) and it.strip():
            out.append({"en": dedash(it.strip()), "native": ""})
    return out[:limit]


def _allowed_numbers(med: dict) -> set[float]:
    nums = set()
    for k in ("dose_mg", "frequency_per_day", "daily_dose_mg", "duration_days", "amount", "max_per_day",
              "min_hours_between", "interval_hours"):
        try:
            if med.get(k) is not None:
                nums.add(float(med[k]))
        except (TypeError, ValueError):
            pass
    for k in ("dose_mg", "daily_dose_mg"):
        if med.get(k):
            nums.add(float(med[k]) / 1000.0)
    for k in ("dose_text", "freq_en", "indication", "note_en", "title_en", "amount_en", "duration_en"):
        nums |= _numbers(str(med.get(k) or ""))
    return nums


def _translation_keys(plan: dict) -> dict[str, str]:
    keys: dict[str, str] = {}
    for i, m in enumerate(plan["medicines"]):
        keys[f"m{i}.name"] = m["name"]
        keys[f"m{i}.title"] = m["title_en"]
        keys[f"m{i}.line"] = m["note_en"]
        if m.get("slots"):
            keys[f"m{i}.amount"] = m["dose_amount_en"]
    for i, a in enumerate(plan["avoid"]):
        keys[f"a{i}"] = a["en"]
    return keys


def build_care_plan(consult: Consultation) -> dict:
    """Deterministic skeleton (meds = prescribed − stopped, each re-checked by the rule engine; regular medicines on
    the wake / breakfast / lunch / dinner / bedtime timetable; "as needed" medicines listed separately; avoid from
    allergies; 999). Every English line is a template from the record; ONE llm.chat_json call translates them
    (faithfully) and writes the danger signs and advice from the clinician's own words."""
    with consult.lock:
        st = copy.deepcopy(consult.state)
    plan, warnings = _skeleton(consult, st)
    doctor_said = [f"{t.id}: {s}" for t, s in _doctor_sentences(consult)]
    if sum(est_tokens(x) for x in doctor_said) > CARE_PLAN_INPUT_BUDGET:   # long consultation: plan-relevant only
        doctor_said = [x for x in doctor_said if _PLAN_CUES.search(x)]
        while doctor_said and sum(est_tokens(x) for x in doctor_said) > CARE_PLAN_INPUT_BUDGET:
            doctor_said.pop(0)  # the final plan is at the end of the consultation; drop the earliest first
        warnings.append("Long consultation: the care plan was written from the doctor's plan-related sentences only.")
    keys = _translation_keys(plan) if plan["lang"] != "en" else {}
    system = CARE_PLAN_SYSTEM.format(lang_name=plan["lang_name"])

    def _call(translate: dict, note: str = "") -> dict:
        # gpt-oss reasoning tokens count against max_tokens: "medium" + a generous cap (measured: "high" or small
        # caps give empty replies). Once per consultation, off the talk loop.
        payload = {"note": note} if note else {}
        payload.update({"translate": translate, "clinician_said": doctor_said})
        return llm.chat_json(system, json.dumps(payload, ensure_ascii=False, indent=1), schema=CARE_PLAN_SCHEMA,
                             max_tokens=CARE_PLAN_MAX_TOKENS, reasoning=WRAPUP_REASONING, **llm.brain_route())

    def _translated(reply: dict) -> dict:
        got = {}
        for item in reply.get("translations") or []:
            if isinstance(item, dict) and item.get("key") in keys:
                native = dedash(str(item.get("native") or "").strip())
                if native and native.strip() != keys[item["key"]].strip():   # an untranslated echo is not one
                    got[item["key"]] = native
        return got

    out: dict = {}
    t0 = time.time()
    plan["llm"] = {"calls": 1, "s": 0.0}
    try:
        # Measured live: without this explicit instruction the first reply often carried only red_flags/advice and
        # no translations, which cost a retry every time.
        out = _call(keys, "Return JSON with EVERY key in 'translate' translated in 'translations' (key + native), "
                          "plus the red_flags and advice lists from what the clinician said.")
        consult.log("tool", f"care_plan_llm → {len(out)} keys in {time.time() - t0:.1f}s")
        # Completeness check: every line translated and the danger signs written. A reply in the wrong shape
        # (measured live once: no usable translations, no red_flags) gets ONE retry asking only for what is missing.
        if out:
            missing = {k: v for k, v in keys.items() if k not in _translated(out)}
            if missing or not _pairs(out.get("red_flags"), 6):
                retry = _call(missing or keys, "Your previous reply was incomplete. Return JSON with EVERY key in "
                                               "'translate' translated in 'translations', plus the red_flags and "
                                               "advice lists from what the clinician said.")
                plan["llm"]["calls"] = 2
                if retry:
                    merged = dict(out)
                    merged["translations"] = list(out.get("translations") or []) + list(retry.get("translations") or [])
                    for k in ("red_flags", "advice", "follow_up"):
                        if not out.get(k) and retry.get(k):
                            merged[k] = retry[k]
                    out = merged
                consult.log("tool", f"care_plan_llm retry → {len(missing)} missing line(s) requested")
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"care_plan_llm failed: {e}")
        warnings.append(f"Care-plan writer unavailable ({type(e).__name__}); English lines taken verbatim from the "
                        "doctor and NOT translated. Explain them with an interpreter.")
    plan["llm"]["s"] = round(time.time() - t0, 3)
    if not out:
        fb = _fallback_lines(consult)
        plan["red_flags"], plan["advice"], plan["follow_up"] = fb["red_flags"], fb["advice"], fb["follow_up"]
        if not any("not translated" in w.lower() for w in warnings):
            warnings.append("Care-plan writer returned nothing; English lines taken verbatim from the doctor, "
                            "NOT translated. Explain them with an interpreter.")
    else:
        tr = _translated(out)
        for key, en in keys.items():
            native = tr.get(key, "")
            if native and _numbers(native) - _numbers(en):
                warnings.append(f"Translation of “{en}” changed a number; English shown instead.")
                native = ""
            if key.startswith("a"):
                plan["avoid"][int(key[1:])]["native"] = native
            else:
                i, field = key[1:].split(".", 1)
                m = plan["medicines"][int(i)]
                target = {"name": "name_native", "line": "note_native", "title": "title_native",
                          "amount": "dose_amount_native"}[field]
                m[target] = native
        plan["red_flags"] = _pairs(out.get("red_flags"), 6)
        plan["advice"] = _pairs(out.get("advice"), 4)
        fu = out.get("follow_up") if isinstance(out.get("follow_up"), dict) else {}
        plan["follow_up"] = {"en": dedash(str(fu.get("en") or "").strip()),
                             "native": dedash(str(fu.get("native") or "").strip())}
        if not plan["red_flags"]:
            plan["red_flags"] = _fallback_lines(consult)["red_flags"]
    try:
        dropped = dedupe_plan_lines(plan, st)
        if dropped:
            consult.log("tool", "care plan: dropped repeated line(s) → " + "; ".join(dropped)[:300])
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"care plan dedupe failed: {e}")
    plan["warnings"] = warnings
    return plan


def check_care_plan(consult: Consultation, plan: dict) -> list[str]:
    """Post-checks on the finished plan. Mutates the plan to the safe form (a translated line with a number that is
    not in the prescription is blanked, so the sheet shows the checked English). Returns new warnings."""
    with consult.lock:
        st = copy.deepcopy(consult.state)
    issues: list[str] = []
    stopped = {_norm_drug(s.get("drug", "")) for s in st.get("stopped_meds", [])}
    allowed_drugs = {_norm_drug(m.get("drug", "")) for m in final_meds(st)}
    keep = []
    for m in plan.get("medicines", []):
        d = _norm_drug(m.get("drug") or m.get("name") or "")
        if d in stopped or d not in allowed_drugs:
            issues.append(f"Removed {m.get('name')} from the care plan: not in the doctor's final prescription.")
            continue
        allowed = _allowed_numbers(m) | {float(EMERGENCY)}
        for field in ("note_native", "title_native", "dose_amount_native"):
            bad = _numbers(m.get(field, "")) - allowed
            if bad:
                issues.append(f"{m.get('name')}: a translated line has numbers not in the prescription "
                              f"({', '.join(f'{x:g}' for x in sorted(bad))}); English shown instead.")
                m[field] = ""
        keep.append(m)
    plan["medicines"] = keep
    if plan.get("emergency") != EMERGENCY:
        plan["emergency"] = EMERGENCY
        issues.append("Emergency number reset to 999.")
    missing = sum(1 for m in plan.get("medicines", []) if not m.get("note_native")) + \
        sum(1 for k in ("avoid", "red_flags", "advice") for x in plan.get(k, []) if not x.get("native"))
    if missing and plan.get("lang") != "en":
        issues.append(f"{missing} care-plan line(s) have no {plan.get('lang_name', plan.get('lang'))} translation; "
                      "they are shown in English.")
    plan.setdefault("warnings", [])
    for i in issues:
        if i not in plan["warnings"]:
            plan["warnings"].append(i)
    return issues


# ====================================================================== render + deliver
def share_text(plan: dict, pdf_url: str | None, audio_url: str | None, clinic: str = "") -> tuple[str, str]:
    """(WhatsApp text, SMS text). SMS stays short: native title + link (≤ 2 UCS-2 segments with a short URL)."""
    from bayan.outputs import labels

    lab = labels(plan.get("lang", "en"))
    title = plan.get("title_native") or lab["title"]
    wa = [title, f"Your medicines and care instructions{(' from ' + clinic) if clinic else ''}."]
    if pdf_url:
        wa.append(f"PDF: {pdf_url}")
    if audio_url:
        wa.append(f"Audio: {audio_url}")
    wa.append(f"Emergency: {EMERGENCY}")
    sms = f"{title}: " + (pdf_url if pdf_url else f"Emergency {EMERGENCY}")
    return "\n".join(wa), sms


def render_outputs(consult: Consultation, note_md: str, plan: dict, speak_fn: Callable | None = None,
                   link_base: str | None = None, phone: str | None = None, clinic: str = "") -> dict:
    """Doctor PDF + audio WAV + patient PDF (QR → audio URL, else PDF URL) + wa.me / sms: links.
    Files live only in retention.consult_dir(consult) (temp, auto-swept); URLs are <link_base>/<token>/<file> with an
    unguessable 128-bit token."""
    from bayan.outputs.delivery import care_plan_audio, sms_link, wa_link
    from bayan.outputs.report import render_care_plan_pdf, render_doctor_report, render_plain_pdf
    from bayan.outputs.retention import DEFAULT_MAX_AGE_S, consult_dir

    d = consult_dir(consult)
    try:
        from bayan.outputs.retention import start_sweeper
        start_sweeper()  # idempotent: old consultation folders are deleted even if the app never calls purge()
    except Exception:  # noqa: BLE001
        pass
    token = consult.outputs.get("token") or secrets.token_urlsafe(16)
    res: dict = {"token": token, "out_dir": str(d),
                 "expires_at": (datetime.now() + timedelta(seconds=DEFAULT_MAX_AGE_S)).isoformat(timespec="seconds")}
    warns: list[str] = []
    base = link_base.rstrip("/") + "/" + token if link_base else None
    try:
        res["audio_wav"] = care_plan_audio(plan, speak_fn, d / "care_plan.wav")
    except Exception as e:  # noqa: BLE001
        res["audio_wav"] = None
        warns.append(f"Audio failed: {e}")
    res["pdf_url"] = f"{base}/care_plan.pdf" if base else None
    res["audio_url"] = f"{base}/care_plan.wav" if base and res["audio_wav"] else None
    if clinic:
        plan["clinic"] = clinic
    try:
        res["patient_pdf"] = render_care_plan_pdf(plan, d / "care_plan.pdf", audio_url=res["audio_url"])
    except Exception as e:  # noqa: BLE001 - always a PDF: plain last-resort rendering
        warns.append(f"Patient PDF layout failed ({type(e).__name__}: {e}); plain version produced.")
        res["patient_pdf"] = render_plain_pdf("Care plan", _plan_text(plan), d / "care_plan.pdf")
    try:
        res["doctor_pdf"] = render_doctor_report(consult, note_md, d / "doctor_report.pdf", care_plan=plan)
    except Exception as e:  # noqa: BLE001
        warns.append(f"Doctor report layout failed ({type(e).__name__}: {e}); plain version produced.")
        res["doctor_pdf"] = render_plain_pdf("Consultation note", note_md, d / "doctor_report.pdf")
    (d / "note.md").write_text(note_md, encoding="utf-8")
    (d / "note.txt").write_text(consult.outputs.get("note_txt") or note_md, encoding="utf-8")
    wa_text, sms_text = share_text(plan, res["pdf_url"], res["audio_url"], clinic)
    res["wa_link"] = wa_link(wa_text, phone)
    res["sms_link"] = sms_link(sms_text, phone)
    res["render_warnings"] = warns
    return res


def _plan_text(plan: dict) -> str:
    L = [plan.get("title_native") or "", plan.get("title_en") or "Your medicines and care instructions", ""]
    for m in plan.get("medicines", []):
        when = ", ".join(m.get("times") or []) or ("only if needed" if m.get("prn") else "")
        L += [f"- {m.get('name')} {m.get('dose_text')} ({when})", f"  {m.get('note_native', '')}",
              f"  {m.get('note_en', '')}"]
    for a in plan.get("avoid", []):
        L += [f"DO NOT TAKE: {a.get('en')}", f"  {a.get('native', '')}"]
    for a in plan.get("advice", []):
        L += [f"- {a.get('en')}", f"  {a.get('native', '')}"]
    L += ["", f"Call {plan.get('emergency', EMERGENCY)} or come back now if:"]
    for f in plan.get("red_flags", []):
        L += [f"- {f.get('en')}", f"  {f.get('native', '')}"]
    return "\n".join(L)


# ====================================================================== orchestration
class _Ctx:
    """Shared state of one wrap-up run. Steps are idempotent; once closed, late agent threads cannot overwrite."""

    def __init__(self, consult, opts):
        self.consult = consult
        self.opts = opts
        self.r: dict = {}
        self.closed = False
        self.cancel = threading.Event()   # set by agentkit on timeout: late tool calls become no-ops
        self.timings: dict[str, float] = {}

    def _timed(self, name, fn):
        t0 = time.perf_counter()
        try:
            return fn()
        finally:
            self.timings[name] = round(self.timings.get(name, 0.0) + time.perf_counter() - t0, 3)

    def note(self) -> str:
        def safe_note() -> str:
            try:
                return draft_note(self.consult)
            except Exception as e:  # noqa: BLE001 - a bug here must never cost the doctor the note
                self.consult.log("error", f"draft_note crashed: {type(e).__name__}: {e}; structured-record note")
                try:
                    return note_from_state(self.consult, auto_label=True)
                except Exception:  # noqa: BLE001
                    return "# Consultation note (SOAP)\n\n> **" + FALLBACK_LABEL + "**\n\n## Transcript\n\n" + \
                        "\n".join(f"- {_turn_line(t, 600)}" for t in self.consult.turns)

        md = self._timed("draft_note_s", safe_note)
        if not self.closed:
            self.r["note_md"] = md
        self.consult.log("tool", f"draft_note → {md.count(chr(10)) + 1} lines")
        return md

    def plan(self) -> dict:
        def safe_plan() -> dict:
            try:
                return build_care_plan(self.consult)
            except Exception as e:  # noqa: BLE001
                self.consult.log("error", f"build_care_plan crashed: {type(e).__name__}: {e}; minimal plan")
                from bayan.outputs import LANG_NAMES, labels

                lang = self.consult.patient_lang
                return {"lang": lang, "lang_name": LANG_NAMES.get(lang, lang), "medicines": [], "avoid": [],
                        "red_flags": [], "advice": [], "follow_up": {"en": "", "native": ""}, "emergency": EMERGENCY,
                        "title_native": labels(lang)["title"], "machine_translated": True, "excluded": [],
                        "warnings": [f"Care plan could not be built ({type(e).__name__}); only the emergency number "
                                     "is shown. Explain the plan verbally."]}

        p = self._timed("care_plan_s", safe_plan)
        if not self.closed:
            self.r["care_plan"] = p
            self.r.pop("checked", None)
        self.consult.log("tool", f"build_care_plan → {len(p['medicines'])} medicine(s), {len(p['avoid'])} avoid, "
                                 f"{len(p['red_flags'])} red flag(s), {len(p.get('excluded', []))} excluded")
        return p

    def check(self) -> list[str]:
        if "care_plan" not in self.r:
            self.plan()
        def safe_check() -> list[str]:
            try:
                return check_care_plan(self.consult, self.r["care_plan"])
            except Exception as e:  # noqa: BLE001
                return [f"Care-plan check failed ({type(e).__name__}); review the plan manually."]

        issues = self._timed("check_s", safe_check)
        if not self.closed:
            self.r["checked"] = True
        self.consult.log("tool", "check_care_plan → " + ("; ".join(issues) if issues else "ok"))
        return issues

    def draft_all(self) -> dict:
        """note + care plan (two independent LLM calls, run in parallel) + checks, in one call (one agent step)."""
        todo = [f for k, f in (("note_md", self.note), ("care_plan", self.plan)) if k not in self.r]
        if len(todo) == 2:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=2) as ex:
                for fut in [ex.submit(f) for f in todo]:
                    fut.result()
        else:
            for f in todo:
                f()
        if not self.r.get("checked"):
            self.check()
            # the medication table in the note marks medicines the safety check kept off the patient sheet
            try:
                md = refresh_note(self.consult, self.r["care_plan"])
                if not self.closed:
                    self.r["note_md"] = md
            except Exception as e:  # noqa: BLE001
                self.consult.log("error", f"note refresh failed: {e}")
        return self.r["care_plan"]

    def render(self) -> dict:
        self.draft_all()
        files = self._timed("render_s", lambda: render_outputs(self.consult, self.r["note_md"], self.r["care_plan"],
                                                               **self.opts))
        if not self.closed:
            self.r["files"] = files
        self.consult.log("tool", "render_outputs → " + ", ".join(
            k for k in ("doctor_pdf", "patient_pdf", "audio_wav") if files.get(k)))
        return files


def _run_agent(tools, task, consult, **kwargs) -> dict:
    """agentkit.run_agent with the wrap-up model (the brain model via agentkit, reasoning medium for gpt-oss,
    6000-token cap)."""
    from . import agentkit

    if not agentkit.available():
        return {"ok": False, "steps": 0, "error": "no agent model (HF_TOKEN missing)", "final": None}
    model = agentkit.make_model()
    if isinstance(getattr(model, "kwargs", None), dict):
        model.kwargs["max_tokens"] = WRAPUP_AGENT_MAX_TOKENS
        extra = llm.reasoning_body(agentkit.AGENT_MODEL, WRAPUP_REASONING)   # gpt-oss only
        if extra:
            model.kwargs["extra_body"] = {**(model.kwargs.get("extra_body") or {}), **extra}
    return agentkit.run_agent(tools, task, consult, model=model, label="wrap-up agent", **kwargs)


def _make_tools(ctx: _Ctx) -> list:
    """Two coarse tools so a typical agent run is 2 tool steps + the final answer (≤3 steps)."""
    from smolagents import Tool

    def draft() -> str:
        if ctx.cancel.is_set() or ctx.closed:
            return "cancelled"
        p = ctx.draft_all()
        md = ctx.r.get("note_md", "")
        info = ctx.consult.outputs.get("note_info") or {}
        meds = ", ".join(f"{m['name']} {m['dose_text']}" for m in p["medicines"]) or "none"
        return (f"note drafted ({info.get('source', '?')}): 4 sections, {md.count(chr(10)) + 1} lines; care plan: "
                f"medicines {meds}; {len(p['avoid'])} avoid, {len(p['red_flags'])} red flags, "
                f"{len(p.get('excluded', []))} excluded; {len(p.get('warnings', []))} warning(s).")

    def render() -> str:
        if ctx.cancel.is_set() or ctx.closed:
            return "cancelled"
        f = ctx.render()
        made = [k for k in ("doctor_pdf", "patient_pdf", "audio_wav", "wa_link", "sms_link") if f.get(k)]
        return f"rendered: {', '.join(made)}; {len(f.get('render_warnings', []))} warning(s)."

    specs = [
        ("draft_outputs", "Draft the English SOAP note and the patient's translated care plan from the consultation "
                          "state, safety-check every medicine with the rule engine, and verify the plan. Call first.",
         draft),
        ("render_outputs", "Render the doctor PDF, the patient PDF, the care-plan audio and the WhatsApp/SMS links. "
                           "Call after draft_outputs.", render),
    ]
    # tolerant arguments: one optional, ignored string, so a model that sends {} or {"note": ...} both work
    inputs = {"note": {"type": "string", "description": "Optional remark; ignored.", "nullable": True}}
    tools = []
    for name, desc, fn in specs:
        cls = type(f"Wrapup_{name}", (Tool,), {
            "name": name, "description": desc, "inputs": inputs, "output_type": "string",
            "forward": (lambda f: (lambda self, note=None: f()))(fn),
        })
        tools.append(cls())
    return tools


AGENT_TASK = "The consultation has ended. Call draft_outputs, then render_outputs, then reply 'done'."
AGENT_INSTRUCTIONS = ("You are Bayan's wrap-up agent. Only call the given tools, one per step, each once. "
                      "Never write clinical content yourself.")


def run_wrapup(consult: Consultation, agentic: bool = True, speak_fn: Callable | None = None,
               link_base: str | None = None, phone: str | None = None, clinic: str = "",
               timeout_s: float = 25.0) -> dict:
    """End of consultation → {"note_md","care_plan","warnings","doctor_pdf","patient_pdf","audio_wav","wa_link",
    "sms_link", + "pdf_url","audio_url","token","expires_at","out_dir","agentic","wrapup_metrics"}; also stored in
    consult.outputs. agentic=True: smolagents run (2 tools, max_steps 4: typically 2 tool steps + final answer); any
    failure → fixed deterministic order (reusing whatever the agent already finished).
    Wrap-up makes at most one LLM call itself (the care-plan writer; the note is deterministic)."""
    t_start = time.perf_counter()
    usage0 = dict(llm.USAGE)
    clinic = (clinic or "").strip() or clinic_name()
    with consult.lock:
        if clinic:
            consult.outputs["clinic"] = clinic
        else:
            consult.outputs.pop("clinic", None)
    ctx = _Ctx(consult, {"speak_fn": speak_fn, "link_base": link_base, "phone": phone, "clinic": clinic})
    mode, agent_steps = "deterministic", 0
    if agentic:
        t0 = time.perf_counter()
        try:
            res = _run_agent(_make_tools(ctx), AGENT_TASK, consult, max_steps=4, timeout_s=timeout_s,
                             instructions=AGENT_INSTRUCTIONS, cancel=ctx.cancel)
            ok = bool(res and res.get("ok"))
            agent_steps = int((res or {}).get("steps") or 0)
            consult.log("agent", f"wrap-up agent: ok={ok} steps={agent_steps}"
                                 f"{' error=' + str(res.get('error')) if res and res.get('error') else ''}")
            mode = "agent" if ok else "agent→fallback"
        except Exception as e:  # noqa: BLE001
            consult.log("error", f"wrap-up agent failed: {type(e).__name__}: {e}; deterministic fallback")
            mode = "agent→fallback"
        ctx.timings["agent_s"] = round(time.perf_counter() - t0, 3)
        ctx.cancel.set()
    # fixed deterministic order for anything the agent did not finish
    if any(k not in ctx.r for k in ("note_md", "care_plan", "checked", "files")) and mode == "agent":
        mode = "agent+fallback"
    if "files" not in ctx.r:
        ctx.render()
    ctx.closed = True
    plan, files = ctx.r["care_plan"], ctx.r["files"]
    note_info = consult.outputs.get("note_info") or {}
    warnings = list(dict.fromkeys(list(note_info.get("warnings", [])) + list(plan.get("warnings", [])) +
                                  list(files.get("render_warnings", []))))
    metrics = {"total_s": round(time.perf_counter() - t_start, 3), **ctx.timings, "mode": mode,
               "agent_steps": agent_steps, "llm_calls": (plan.get("llm") or {}).get("calls", 0) + int(note_info.get("calls", 0)),
               "note_source": note_info.get("source"), "note_llm_calls": note_info.get("calls", 0),
               "note_chunks": note_info.get("chunks", 0),
               "care_plan_llm_s": (plan.get("llm") or {}).get("s", 0.0),
               **{f"llm_{k}": llm.USAGE.get(k, 0) - usage0.get(k, 0) for k in ("prompt_tokens", "completion_tokens")}}
    out = {"note_md": ctx.r["note_md"], "care_plan": plan, "warnings": warnings,
           **{k: files.get(k) for k in ("doctor_pdf", "patient_pdf", "audio_wav", "wa_link", "sms_link", "pdf_url",
                                         "audio_url", "token", "expires_at", "out_dir")},
           "agentic": mode, "wrapup_metrics": metrics}
    with consult.lock:
        consult.outputs.update(out)
    consult.log("system", f"wrap-up done ({mode}) in {metrics['total_s']:.1f}s: {len(warnings)} warning(s)")
    return out
