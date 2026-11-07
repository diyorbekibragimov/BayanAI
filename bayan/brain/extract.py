"""Bayan AI · clinical-state extraction (the `update_state` step).

One gpt-oss-120b call per think run: the last ~8 transcript turns as context, the NEW turns to extract from,
and a compact summary of the current state. Output is a *delta* in the shape of `empty_state()` (lists of new
items, each with evidence utterance ids and quotes) plus an optional {"remove": {"prescribed_meds": [...]}}.
`bayan.brain.merge.merge_delta` normalises and merges it. Unknown stays unknown: nulls are dropped here.
"""

from __future__ import annotations

import json
import os
import re

from . import llm

try:   # enums shared with the validator (merge.py) so the extractor and the care plan agree
    from .merge import MED_DETAIL_FIELDS, MED_FOOD, MED_FORMS, MED_TIMES, MED_UNITS
except Exception:  # noqa: BLE001
    MED_FORMS = ("tablet", "capsule", "liquid", "nasal_spray", "inhaler", "eye_drops", "ear_drops", "cream", "patch",
                 "injection", "sachet", "other")
    MED_UNITS = ("tablet", "capsule", "ml", "spray", "puff", "drop", "sachet", "application", "patch", "mg", "g")
    MED_TIMES = ("on_waking", "morning", "midday", "evening", "bedtime")
    MED_FOOD = ("before_food", "with_food", "after_food", "empty_stomach")
    MED_DETAIL_FIELDS = ("form", "amount", "unit", "site", "food", "interval_hours", "as_needed", "as_needed_for",
                         "max_per_day", "min_hours_between", "duration_text", "times", "instructions")

CONTEXT_TURNS = 6      # total transcript window (new turns + earlier context)
EXTRACT_REASONING = os.environ.get("BAYAN_EXTRACT_REASONING", "medium")   # never "high"
EXTRACT_MAX_TOKENS = int(os.environ.get("BAYAN_EXTRACT_MAX_TOKENS", "3000"))   # reasoning counts against it
# Same model (gpt-oss-120b), cheaper host: Groq input is $0.15/1M vs Cerebras $0.35 (output equal), JSON-schema mode
# verified live; it runs in the background, so Groq's lower throughput (~1.3 s vs ~0.9 s) never touches the talk loop.
EXTRACT_PROVIDER = os.environ.get("BAYAN_EXTRACT_PROVIDER", "groq")
EXTRACT_FALLBACK = os.environ.get("BAYAN_EXTRACT_FALLBACK", "cerebras")
SEVERITY_VALUES = ["mild", "moderate", "severe", "anaphylaxis", "scar", "unknown"]
DISPOSITION_VALUES = ["discharge", "admit", "refer", "observe"]
# Common presenting symptoms the rules do not mention but the note and checklist still need.
EXTRA_SYMPTOMS = [
    "sore_throat", "cough", "nausea", "vomiting", "sweating", "breathlessness", "palpitations", "back_pain",
    "fatigue", "diarrhoea", "rash", "itching", "abdominal_bloating", "body_ache", "numbness", "weakness",
    "black_stools", "vomiting_blood", "epigastric_pain", "heartburn", "chills", "loss_of_appetite",
]
FALLBACK_QUESTION_TOPICS = [
    "pain_radiation", "exertional_pattern", "sweating", "breathlessness", "allergies", "current_medications",
    "onset", "severity", "occupation", "pregnancy", "black_stools_or_vomiting_blood",
]
PATIENT_KEYS = ["age_years", "sex", "pregnant", "gestation_weeks", "weight_kg", "egfr", "hepatic_impairment",
                "heat_exposure", "heat_illness_suspected", "heat_stroke_suspected", "dehydration",
                "travel_malaria_endemic_days", "travel_country", "ancestry_region", "chronic_alcohol"]
VITAL_KEYS = ["hr", "bp_sys", "bp_dia", "rr", "spo2", "temp_c", "temp_site"]


def _vocab() -> dict[str, list[str]]:
    try:
        from . import vocab
        return {k: list(v) for k, v in vocab.codes().items()}
    except Exception:  # noqa: BLE001 - deterministic core not there yet: permissive strings
        return {}


def _question_topics() -> list[str]:
    try:
        from . import checklist
        topics = list(getattr(checklist, "QUESTION_TOPICS", []) or [])
        return topics or FALLBACK_QUESTION_TOPICS
    except Exception:  # noqa: BLE001
        return FALLBACK_QUESTION_TOPICS


def _code(values: list[str] | None, extra: list[str] | None = None) -> dict:
    vals = list(dict.fromkeys((values or []) + (extra or [])))
    return {"type": "string", "enum": vals} if values else {"type": "string"}


_EV = {"type": "array", "items": {"type": "object", "properties": {
    "utt": {"type": "string"}, "quote": {"type": "string"}}, "required": ["utt", "quote"]}}
# Plain types only (no type unions / null enums): providers' structured-output validators differ, and every field
# is optional, so "unknown" is expressed by omitting the key.
_NUM = {"type": "number"}
_STR = {"type": "string"}


def build_schema() -> dict:
    v = _vocab()
    med_props = {"drug": {"type": "string"}, "dose_mg": _NUM, "dose_raw": _STR, "frequency_per_day": _NUM,
                 "duration_days": _NUM, "route": _STR, "indication": _STR, "evidence": _EV,
                 "confidence": {"type": "number"},
                 # care-plan instructions (only what the doctor said; normalised again in merge.normalise_med)
                 "form": {"type": "string", "enum": list(MED_FORMS)}, "amount": _NUM,
                 "unit": {"type": "string", "enum": list(MED_UNITS)}, "site": _STR,
                 "times": {"type": "array", "items": {"type": "string", "enum": list(MED_TIMES)}},
                 "food": {"type": "string", "enum": list(MED_FOOD)}, "interval_hours": _NUM,
                 "as_needed": {"type": "boolean"}, "as_needed_for": _STR, "max_per_day": _NUM,
                 "min_hours_between": _NUM, "duration_text": _STR,
                 "instructions": {"type": "array", "items": {"type": "string"}}}
    return {
        "type": "object",
        "properties": {
            "allergies": {"type": "array", "items": {"type": "object", "properties": {
                "substance": {"type": "string"}, "reaction": _STR,
                "severity": {"type": "string", "enum": SEVERITY_VALUES},
                "evidence": _EV, "confidence": {"type": "number"}}, "required": ["substance", "evidence"]}},
            "current_meds": {"type": "array", "items": {"type": "object", "properties": med_props,
                                                        "required": ["drug", "evidence"]}},
            "prescribed_meds": {"type": "array", "items": {"type": "object", "properties": med_props,
                                                           "required": ["drug", "evidence"]}},
            "remove": {"type": "object", "properties": {
                "prescribed_meds": {"type": "array", "items": {"type": "string"}}}},
            "symptoms": {"type": "array", "items": {"type": "object", "properties": {
                "code": _code(v.get("symptoms"), EXTRA_SYMPTOMS), "severity": _STR, "onset": _STR,
                "evidence": _EV, "confidence": {"type": "number"}}, "required": ["code", "evidence"]}},
            "vitals": {"type": "object", "properties": {
                "hr": _NUM, "bp_sys": _NUM, "bp_dia": _NUM, "rr": _NUM, "spo2": _NUM, "temp_c": _NUM,
                "temp_site": _STR, "evidence": _EV}},
            "investigations": {"type": "array", "items": {"type": "object", "properties": {
                "code": _code(v.get("investigations")), "status": {"type": "string", "enum": ["ordered", "resulted"]},
                "result": _STR, "evidence": _EV}, "required": ["code", "status", "evidence"]}},
            "interventions": {"type": "array", "items": {"type": "object", "properties": {
                "code": _code(v.get("interventions")), "evidence": _EV}, "required": ["code", "evidence"]}},
            "assessments": {"type": "array", "items": {"type": "object", "properties": {
                "code": _code(v.get("assessments")), "evidence": _EV}, "required": ["code", "evidence"]}},
            "disposition": {"type": "object", "properties": {
                "type": {"type": "string", "enum": DISPOSITION_VALUES}, "evidence": _EV}},
            "patient": {"type": "object", "properties": {
                "age_years": _NUM, "sex": {"type": "string", "enum": ["male", "female"]},
                "pregnant": {"type": "boolean"}, "gestation_weeks": _NUM, "weight_kg": _NUM,
                "heat_exposure": {"type": "boolean"}, "heat_illness_suspected": {"type": "boolean"},
                "dehydration": {"type": "string", "enum": ["none", "mild", "moderate", "severe"]}, "travel_malaria_endemic_days": _NUM,
                "travel_country": _STR, "ancestry_region": _STR, "evidence": _EV}},
            "questions_asked": {"type": "array", "items": {"type": "object", "properties": {
                "topic": _code(_question_topics()), "evidence": _EV}, "required": ["topic"]}},
        },
    }


EXTRACT_SCHEMA: dict = build_schema()

SYSTEM = """You extract clinical facts for Bayan, an interpreter assisting a licensed doctor in Qatar. Return ONLY JSON
with facts newly stated in the NEW turns (earlier turns are context). Omit keys you have nothing for. Never guess:
an unsaid dose, frequency, reaction, age, pregnancy status or result stays out. Every item has evidence
[{"utt": "<NEW turn id>", "quote": "<short exact English quote>"}].

Medicines (doctor) - decide the INTENT:
- PRESCRIBE/give/take ("I'll give you amoxicillin 500 three times a day") -> prescribed_meds: drug, dose_mg
  ("five hundred milligrams" -> 500, "one gram" -> 1000), dose_raw, frequency_per_day ("(up to) three times a day"
  -> 3), duration_days, route, indication.
- WITHDRAW ("Actually, no amoxicillin", "stop the ibuprofen") -> remove.prescribed_meds: ["amoxicillin"] only.
- Merely NAMED or ASKED ("any reaction to penicillin before?") -> nothing.
- Medicines the patient already takes -> current_meds.
- HOW to take it, only the parts the doctor actually said (never add advice): form (tablet, capsule, liquid,
  nasal_spray, inhaler, eye_drops, ear_drops, cream, patch, injection, sachet, other); amount + unit per dose ("two
  sprays" -> 2 spray, "one capsule" -> 1 capsule, "one gram" -> 1 g and dose_mg 1000); site ("each nostril", "both
  eyes"); times ONLY when timing is stated ("when you wake up" -> on_waking, "with breakfast"/"every morning" ->
  morning, "at night"/"before bed" -> bedtime; omit when only a frequency was said); food (before_food, with_food,
  after_food, empty_stomach); interval_hours ("every 8 hours" -> 8); as-needed ("up to three times a day for your
  throat" -> as_needed true, max_per_day 3, as_needed_for "throat pain", frequency_per_day 3; "at least 4 hours
  apart" -> min_hours_between 4); duration_days ("for five days" -> 5, "two weeks" -> 14, "one month" -> 30) or
  duration_text when not a number of days ("until finished"); instructions = other short instructions said about
  THIS medicine ("shake well", "rinse your mouth after using it"); general advice (water, rest) is not one.
- More detail about a medicine already in the state ("take it after food"): repeat it in prescribed_meds with its
  drug name and only the new fields; it is merged into the same item.
Allergies: only reactions the PATIENT reports. substance = lowercase drug/class; reaction in English as said ("body
swelling"); severity: anaphylaxis (breathing difficulty/collapse), severe (generalised, face, lip or throat
swelling), moderate (rash, hives, spots), mild (itch), else unknown.
Symptoms (patient): closest code. "chest burning like gastric/gyastrik" -> chest_burning; tightness/pressure ->
chest_pressure; dizzy -> dizziness; throat hurts -> sore_throat; onset as said. Never record denied symptoms.
Investigations: ordered ("we'll do a heart tracing (ECG)" -> ecg_12lead ordered; "blood test for the heart called
troponin" -> troponin ordered) or resulted ("your heart tracing is normal" -> resulted, result "normal").
Vitals: only stated numbers ("128 over 82" -> bp_sys 128, bp_dia 82).
Disposition: "you can go home" -> discharge; admit; refer; observe. "Come back if..." is not a disposition.
Patient: "I work outside on a site" -> heat_exposure true. heat_illness_suspected only if the doctor says so.
questions_asked: topics the DOCTOR (or BAYAN for the doctor) asked in the NEW turns, from the topic list.
Edge cases: a bare "yes" answers the previous question - record what it affirms (Doctor: "Does it spread to your
arm?" Patient: "Yes" -> symptom jaw_arm_pain, evidence both turns); a bare "no" records nothing. A companion speaking
for the patient counts as the patient's report. Code-switching is normal: use the EN rendering when present; keep
drug names exactly as said. BAYAN turns are questions the doctor approved."""


def _compact_state(state: dict) -> str:
    parts = []
    if state.get("allergies"):
        parts.append("allergies: " + "; ".join(
            f"{a.get('substance')} ({a.get('reaction') or 'reaction unknown'})" for a in state["allergies"]))
    for key in ("current_meds", "prescribed_meds"):
        if state.get(key):
            parts.append(f"{key}: " + "; ".join(
                f"{m.get('drug')} {m.get('dose_mg') or '?'} mg x{m.get('frequency_per_day') or '?'}/day"
                for m in state[key]))
    if state.get("stopped_meds"):
        parts.append("stopped_meds: " + ", ".join(str(m.get("drug")) for m in state["stopped_meds"]))
    if state.get("symptoms"):
        parts.append("symptoms: " + ", ".join(str(s.get("code")) for s in state["symptoms"]))
    if state.get("investigations"):
        parts.append("investigations: " + ", ".join(
            f"{i.get('code')} {i.get('status')}" + (f" ({i.get('result')})" if i.get("result") else "")
            for i in state["investigations"]))
    for key in ("interventions", "assessments"):
        if state.get(key):
            parts.append(f"{key}: " + ", ".join(str(i.get("code")) for i in state[key]))
    vit = {k: v for k, v in (state.get("vitals") or {}).items() if v not in (None, "", "unknown")}
    if vit:
        parts.append("vitals: " + ", ".join(f"{k}={v}" for k, v in vit.items()))
    disp = (state.get("disposition") or {}).get("type")
    if disp:
        parts.append(f"disposition: {disp}")
    pat = {k: v for k, v in (state.get("patient") or {}).items() if v not in (None, "", "unknown")}
    if pat:
        parts.append("patient: " + ", ".join(f"{k}={v}" for k, v in pat.items()))
    if state.get("questions_asked"):
        parts.append("questions_asked: " + ", ".join(
            q if isinstance(q, str) else str(q.get("topic")) for q in state["questions_asked"]))
    return "\n".join(parts) or "(empty)"


def build_prompt(consult, new_turns: list) -> str:
    new_ids = {t.id for t in new_turns}
    with consult.lock:
        turns = [t for t in consult.turns if t.kind != "system"]
        state_txt = _compact_state(consult.state)
    first_new = next((i for i, t in enumerate(turns) if t.id in new_ids), len(turns))
    n_ctx = max(0, CONTEXT_TURNS - len(new_turns))
    context = turns[max(0, first_new - n_ctx):first_new] if n_ctx else []
    topics = ", ".join(_question_topics())
    ctx = "\n".join(t.line() for t in context) or "(none)"
    new = "\n".join(t.line() for t in new_turns)
    return (f"CURRENT STATE (already recorded; do not repeat unless it changed):\n{state_txt}\n\n"
            f"EARLIER TURNS (context only):\n{ctx}\n\nNEW TURNS (extract from these):\n{new}\n\n"
            f"question topics: {topics}\nReturn the JSON delta.")


# ------------------------------------------------------------------ post-processing
def _num(x):
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return int(x) if float(x).is_integer() else float(x)
    m = re.search(r"-?\d+(?:\.\d+)?", str(x))
    if not m:
        return None
    f = float(m.group(0))
    return int(f) if f.is_integer() else f


def _code_str(x) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(x or "").strip().lower()).strip("_")


class _Ev:
    def __init__(self, consult, new_turns: list):
        self.consult = consult
        self.new = list(new_turns)

    def fix(self, evidence, prefer_role: str | None = None) -> list[dict]:
        out = []
        if isinstance(evidence, (dict, str)):
            evidence = [evidence]
        for ev in evidence or []:
            if isinstance(ev, str):
                ev = {"utt": ev}
            if not isinstance(ev, dict):
                continue
            utt = str(ev.get("utt") or "").strip()
            quote = str(ev.get("quote") or "").strip()
            turn = self.consult.turn_by_id(utt) if utt else None
            if turn is None and quote:
                q = quote.lower()
                turn = next((t for t in reversed(self.new) if q[:40] in (t.english or "").lower()
                             or q[:40] in (t.text or "").lower()), None)
            if turn is None:
                continue
            out.append({"utt": turn.id, "t_min": turn.t_min,
                        "quote": quote or (turn.english or turn.text)[:200]})
        if not out:
            pool = [t for t in self.new if prefer_role is None or t.role == prefer_role] or self.new
            if pool:
                t = pool[-1]
                out.append({"utt": t.id, "t_min": t.t_min, "quote": (t.english or t.text)[:200]})
        return out


def _clean_med(m: dict, ev: _Ev) -> dict | None:
    if not isinstance(m, dict) or not str(m.get("drug") or m.get("name") or "").strip():
        return None
    out = {"drug": str(m.get("drug") or m.get("name")).strip().lower()}
    for k in ("dose_mg", "frequency_per_day", "duration_days"):
        v = _num(m.get(k))
        if v is not None:
            out[k] = v
    for k in ("dose_raw", "route", "indication"):
        if m.get(k):
            out[k] = str(m[k]).strip().lower() if k == "route" else str(m[k]).strip()
    for k in MED_DETAIL_FIELDS:          # passed through; merge.normalise_med_details validates the values
        v = m.get(k)
        if v is None or v == "" or v == [] or (isinstance(v, str) and v.strip().lower() in ("unknown", "null", "none")):
            continue
        out[k] = v
    out["evidence"] = ev.fix(m.get("evidence"), "doctor")
    if m.get("confidence") is not None:
        out["confidence"] = m["confidence"]
    return out


def clean_delta(raw: dict, consult, new_turns: list) -> dict:
    """Validate/trim the model's JSON into a merge-ready delta. Nulls and 'unknown' are dropped (never guessed)."""
    ev = _Ev(consult, new_turns)
    raw = raw if isinstance(raw, dict) else {}
    delta: dict = {}

    allergies = []
    for a in raw.get("allergies") or []:
        if not isinstance(a, dict) or not str(a.get("substance") or "").strip():
            continue
        sev = str(a.get("severity") or "unknown").lower()
        item = {"substance": str(a["substance"]).strip().lower(), "reaction": (a.get("reaction") or None),
                "severity": sev if sev in SEVERITY_VALUES else "unknown",
                "evidence": ev.fix(a.get("evidence"), "patient")}
        if a.get("confidence") is not None:
            item["confidence"] = a["confidence"]
        allergies.append(item)
    if allergies:
        delta["allergies"] = allergies

    for key in ("current_meds", "prescribed_meds"):
        meds = [m for m in (_clean_med(x, ev) for x in raw.get(key) or []) if m]
        if meds:
            delta[key] = meds

    rem = raw.get("remove") or {}
    if isinstance(rem, dict):
        names = []
        for x in rem.get("prescribed_meds") or []:
            n = x.get("drug") or x.get("name") if isinstance(x, dict) else x
            if n and str(n).strip():
                names.append(str(n).strip().lower())
        if names:
            delta["remove"] = {"prescribed_meds": list(dict.fromkeys(names))}
            # a withdrawn drug must not come back in the same delta
            if "prescribed_meds" in delta:
                delta["prescribed_meds"] = [m for m in delta["prescribed_meds"] if m["drug"] not in names]
                if not delta["prescribed_meds"]:
                    del delta["prescribed_meds"]

    symptoms = []
    for s in raw.get("symptoms") or []:
        if not isinstance(s, dict) or not s.get("code"):
            continue
        evs = ev.fix(s.get("evidence"), "patient")
        item = {"code": _code_str(s["code"]), "evidence": evs,
                "first_mention_min": min((e["t_min"] for e in evs if e.get("t_min") is not None), default=None)}
        for k in ("severity", "onset"):
            if s.get(k) and str(s[k]).lower() != "unknown":
                item[k] = s[k]
        if s.get("confidence") is not None:
            item["confidence"] = s["confidence"]
        symptoms.append(item)
    if symptoms:
        delta["symptoms"] = symptoms

    vit_raw = raw.get("vitals") or {}
    if isinstance(vit_raw, dict):
        vit = {}
        for k in VITAL_KEYS:
            v = vit_raw.get(k)
            if k == "temp_site":
                if v and str(v).lower() != "unknown":
                    vit[k] = str(v).lower()
            else:
                v = _num(v)
                if v is not None:
                    vit[k] = v
        if vit:
            vit["evidence"] = ev.fix(vit_raw.get("evidence"), "doctor")
            delta["vitals"] = vit

    invs = []
    for i in raw.get("investigations") or []:
        if not isinstance(i, dict) or not i.get("code"):
            continue
        st = str(i.get("status") or "ordered").lower()
        item = {"code": _code_str(i["code"]), "status": st if st in ("ordered", "resulted") else "ordered",
                "evidence": ev.fix(i.get("evidence"), "doctor")}
        if i.get("result"):
            item["result"] = str(i["result"])
        invs.append(item)
    if invs:
        delta["investigations"] = invs

    for key in ("interventions", "assessments"):
        items = [{"code": _code_str(i["code"]), "evidence": ev.fix(i.get("evidence"), "doctor")}
                 for i in raw.get(key) or [] if isinstance(i, dict) and i.get("code")]
        if items:
            delta[key] = items

    disp = raw.get("disposition") or {}
    if isinstance(disp, dict) and str(disp.get("type") or "").lower() in DISPOSITION_VALUES:
        delta["disposition"] = {"type": str(disp["type"]).lower(), "evidence": ev.fix(disp.get("evidence"), "doctor")}

    pat_raw = raw.get("patient") or {}
    if isinstance(pat_raw, dict):
        pat = {}
        for k in PATIENT_KEYS:
            v = pat_raw.get(k)
            if v is None or (isinstance(v, str) and v.strip().lower() in ("", "unknown", "null", "none")
                             and k not in ("dehydration",)):
                continue
            if isinstance(v, str) and v.strip().lower() == "unknown":
                continue
            if k in ("age_years", "gestation_weeks", "weight_kg", "egfr", "travel_malaria_endemic_days"):
                v = _num(v)
                if v is None:
                    continue
            pat[k] = v
        if pat:
            delta["patient"] = pat

    topics = []
    for q in raw.get("questions_asked") or []:
        t = q.get("topic") if isinstance(q, dict) else q
        if t:
            topics.append(_code_str(t))
    if topics:
        delta["questions_asked"] = list(dict.fromkeys(topics))
    return delta


_CHEST_KEYWORDS = [
    (re.compile(r"\bchest\b.{0,40}\bburn|\bburn\w*\b.{0,30}\bchest\b|\bheartburn\b", re.I), "chest_burning"),
    (re.compile(r"\bchest\b.{0,40}\b(tight|pressure|heavy|squeez)|\b(tight|pressure|heav)\w*\b.{0,30}\bchest\b", re.I),
     "chest_pressure"),
    (re.compile(r"\bchest\b.{0,40}\b(pain|hurt|ache|aching|sore)|\b(pain|hurt|ache)\w*\b.{0,30}\bchest\b", re.I),
     "chest_pain"),
]


def keyword_delta(consult, new_turns: list) -> dict:
    """Deterministic last resort when the LLM extractor fails: chest-pain-group symptoms from the English rendering
    of patient turns, so the chest-pain workup rules still fire. Nothing else is guessed."""
    symptoms = []
    for t in new_turns:
        if t.role != "patient":
            continue
        text = t.english or t.text or ""
        for rx, code in _CHEST_KEYWORDS:
            if rx.search(text):
                symptoms.append({"code": code, "first_mention_min": t.t_min,
                                 "evidence": [{"utt": t.id, "t_min": t.t_min, "quote": text[:200]}]})
                break
    return {"symptoms": symptoms} if symptoms else {}


def extract_delta_ex(consult, new_turns: list) -> tuple[dict, str | None]:
    """(delta, error). One LLM call; never raises."""
    turns = [t for t in new_turns if getattr(t, "kind", "speech") != "system" and (t.text or t.english)]
    if not turns:
        return {}, None
    try:
        raw = llm.chat_json(SYSTEM, build_prompt(consult, turns), schema=EXTRACT_SCHEMA,
                            max_tokens=EXTRACT_MAX_TOKENS, reasoning=EXTRACT_REASONING,
                            provider=EXTRACT_PROVIDER, fallback=EXTRACT_FALLBACK)
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"update_state failed: {e}")
        return {}, str(e)
    try:
        return clean_delta(raw, consult, turns), None
    except Exception as e:  # noqa: BLE001
        consult.log("error", f"update_state: bad extractor output ({e}): {json.dumps(raw)[:200]}")
        return {}, str(e)


def extract_delta(consult, new_turns: list) -> dict:
    """One LLM call -> merge-ready delta. Returns {} (and logs) on any failure; never raises."""
    return extract_delta_ex(consult, new_turns)[0]
