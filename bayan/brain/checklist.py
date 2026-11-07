"""Bayan AI · presenting-complaint workup checklists, derived deterministically from the clinical state.

Each group opens when its presenting complaint is in the state (e.g. any chest-pain-group symptom) and lists
the workup items the rules care about plus the history questions a clinician would expect. Items close from
the state: an investigation ordered or resulted, a vital recorded, an intervention/assessment documented, or a
question topic in `questions_asked` (or the answer already volunteered as a symptom). Decision support only.
"""

from __future__ import annotations

from typing import Any, Callable

from .vocab import _rules_data

# questions_asked vocabulary the extractor may emit (topic codes of questions the DOCTOR asked).
QUESTION_TOPICS: list[str] = [
    "pain_radiation", "exertional_pattern", "sweating_breathlessness", "pain_onset", "pain_character",
    "previous_episodes", "allergies", "current_medications", "work_heat_exposure", "fluid_intake",
    "last_menstrual_period", "vomiting_blood_black_stools", "suicidal_thoughts", "travel_history",
    "headache_onset", "syncope_circumstances", "chemical_exposure", "family_history_cardiac",
]
_TOPIC_ALIASES = {
    "sweating": "sweating_breathlessness", "breathlessness": "sweating_breathlessness",
    "shortness_of_breath": "sweating_breathlessness", "radiation": "pain_radiation",
    "exertion": "exertional_pattern", "lmp": "last_menstrual_period", "suicide": "suicidal_thoughts",
    "travel": "travel_history", "allergy": "allergies", "medications": "current_medications",
}


def _rule_codes(rule_id: str, coll: str = "symptoms") -> list[str]:
    """Codes of the first exists_in clause over `coll` in a rule (keeps the checklist in step with the rules)."""
    for r in _rules_data()["rules"]:
        if r["id"] != rule_id:
            continue
        stack = [r["trigger"]]
        while stack:
            n = stack.pop(0)
            if isinstance(n, dict):
                if n.get("exists_in") == coll and isinstance(n.get("where"), dict) and n["where"].get("fact") == "code":
                    return list(n["where"]["value"])
                for k in ("all", "any"):
                    stack.extend(n.get(k, []) or [])
    return []


CHEST_CODES = _rule_codes("WORK-CHEST-01") or ["chest_pain", "chest_discomfort", "chest_pressure", "chest_burning",
                                               "epigastric_pain_exertional", "jaw_arm_pain"]
HEAT_CNS_CODES = _rule_codes("WORK-HEAT-01") or ["confusion", "collapse", "seizure", "ataxia",
                                                 "altered_mental_status", "vomiting_in_heat", "temp_ge_40"]
PREG_CODES = _rule_codes("WORK-PREG-01") or ["abdominal_pain", "pelvic_pain", "vaginal_bleeding", "syncope", "dizziness"]
STROKE_CODES = _rule_codes("WORK-STROKE-01") or ["sudden_unilateral_weakness", "facial_droop", "speech_disturbance",
                                                 "sudden_unilateral_numbness"]
TLOC_CODES = ["syncope", "transient_loss_of_consciousness"]
HEADACHE_FLAGS = ["thunderclap_onset", "fever_with_neck_stiffness", "focal_neuro_deficit", "new_headache_age_over_50",
                  "headache_in_pregnancy_postpartum", "papilloedema", "head_trauma", "immunosuppression"]


# ----------------------------------------------------------------------------- state probes
def _codes(state: dict, coll: str) -> dict[str, dict]:
    return {str(x.get("code")): x for x in state.get(coll) or [] if isinstance(x, dict) and x.get("code")}


def _utt(item: dict) -> str:
    ev = item.get("evidence") or []
    return f" ({ev[0].get('utt')})" if ev and isinstance(ev[0], dict) and ev[0].get("utt") else ""


def _topics(state: dict) -> set[str]:
    out = set()
    for q in state.get("questions_asked") or []:
        q = str(q).strip().lower().replace(" ", "_")
        out.add(_TOPIC_ALIASES.get(q, q))
    return out


def _inv(*codes: str) -> Callable[[dict], str | None]:
    def probe(state: dict) -> str | None:
        have = _codes(state, "investigations")
        for c in codes:
            if c in have:
                return f"{c} {have[c].get('status') or 'ordered'}{_utt(have[c])}"
        return None
    return probe


def _coll(coll: str, *codes: str) -> Callable[[dict], str | None]:
    def probe(state: dict) -> str | None:
        have = _codes(state, coll)
        for c in codes:
            if c in have:
                return f"{coll[:-1]} {c}{_utt(have[c])}"
        return None
    return probe


def _vital(key: str) -> Callable[[dict], str | None]:
    def probe(state: dict) -> str | None:
        v = (state.get("vitals") or {}).get(key)
        if v is None:
            return None
        if key == "bp_sys" and (state.get("vitals") or {}).get("bp_dia") is not None:
            return f"BP {v}/{state['vitals']['bp_dia']}"
        return f"{key} {v}"
    return probe


def _asked(topic: str, *symptoms: str) -> Callable[[dict], str | None]:
    def probe(state: dict) -> str | None:
        if topic in _topics(state):
            return f"asked: {topic}"
        have = _codes(state, "symptoms")
        for s in symptoms:
            if s in have:
                return f"reported: {s}{_utt(have[s])}"
        return None
    return probe


def _patient_known(key: str) -> Callable[[dict], str | None]:
    def probe(state: dict) -> str | None:
        v = (state.get("patient") or {}).get(key)
        return f"{key} = {v}" if v not in (None, "unknown", "") else None
    return probe


def _any(*probes: Callable[[dict], str | None]) -> Callable[[dict], str | None]:
    def probe(state: dict) -> str | None:
        for p in probes:
            r = p(state)
            if r:
                return r
        return None
    return probe


def _has_symptom(state: dict, codes: list[str]) -> bool:
    have = _codes(state, "symptoms")
    return any(c in have for c in codes)


def _p(state: dict) -> dict:
    return state.get("patient") or {}


def _is_true(v: Any) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes"))


def _num(v: Any) -> float | None:
    try:
        return None if v is None or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------- group definitions
# (id, label, kind, probe, ask_en)
_Item = tuple[str, str, str, Callable[[dict], str | None], str | None]


def _chest(state: dict) -> bool:
    return _has_symptom(state, CHEST_CODES)


def _heat(state: dict) -> bool:
    p = _p(state)
    return (_is_true(p.get("heat_illness_suspected")) or _is_true(p.get("heat_stroke_suspected"))
            or (_is_true(p.get("heat_exposure")) and _has_symptom(state, HEAT_CNS_CODES)))


def _heat_severe(state: dict) -> bool:
    p = _p(state)
    return _is_true(p.get("heat_stroke_suspected")) or (_is_true(p.get("heat_exposure"))
                                                        and _has_symptom(state, HEAT_CNS_CODES))


def _preg(state: dict) -> bool:
    p = _p(state)
    age = _num(p.get("age_years"))
    return (str(p.get("sex") or "").lower() == "female" and age is not None and 12 <= age <= 55
            and _has_symptom(state, PREG_CODES))


def _tloc(state: dict) -> bool:
    return _has_symptom(state, TLOC_CODES)


def _headache(state: dict) -> bool:
    return _has_symptom(state, ["headache"]) and _has_symptom(state, HEADACHE_FLAGS)


def _fever_travel(state: dict) -> bool:
    d = _num(_p(state).get("travel_malaria_endemic_days"))
    return _has_symptom(state, ["fever", "rigors"]) and d is not None and d <= 90


def _sepsis(state: dict) -> bool:
    v = state.get("vitals") or {}
    rr, bp, hr = _num(v.get("rr")), _num(v.get("bp_sys")), _num(v.get("hr"))
    high_risk = (rr is not None and rr >= 25) or (bp is not None and bp <= 90) or (hr is not None and hr > 130) \
        or _has_symptom(state, ["new_confusion"])
    return _has_symptom(state, ["fever", "rigors", "hypothermia"]) and high_risk


def _suicide(state: dict) -> bool:
    if _has_symptom(state, ["suicidal_ideation", "self_harm"]):
        return True
    return any("suicidality" in (h.get("red_flag_tags") or []) for h in state.get("idiom_hits") or [])


def _stroke(state: dict) -> bool:
    return _has_symptom(state, STROKE_CODES)


def _fluids(state: dict) -> bool:
    if str(_p(state).get("dehydration") or "").lower() == "severe":
        return True
    return any("iv_fluid" in (m.get("class") or []) for m in state.get("prescribed_meds") or [])


GROUPS: list[tuple[str, str, Callable[[dict], bool], list[_Item]]] = [
    ("chest_pain", "Chest pain", _chest, [
        ("ecg_12lead", "12-lead ECG (within 10 min)", "investigation", _inv("ecg_12lead"), None),
        ("troponin", "Troponin (hs-troponin)", "investigation", _inv("troponin_hs", "troponin"), None),
        ("bp", "Blood pressure", "vital", _vital("bp_sys"), None),
        ("ask_pain_radiation", "Asked: does the pain spread (arm, jaw, back)?", "question",
         _asked("pain_radiation", "jaw_arm_pain"), "Does the pain spread anywhere, such as your arm, jaw, neck or back?"),
        ("ask_exertional_pattern", "Asked: worse on exertion, better with rest?", "question",
         _asked("exertional_pattern", "epigastric_pain_exertional"),
         "Does the pain come on when you work, walk or climb stairs, and ease when you rest?"),
        ("ask_sweating_breathlessness", "Asked: sweating or breathlessness with the pain?", "question",
         _asked("sweating_breathlessness", "sweating", "shortness_of_breath"),
         "When the pain comes, do you sweat or feel short of breath?"),
    ]),
    ("heat_illness", "Heat illness", _heat, [
        ("temp_core", "Core (rectal) temperature", "investigation", _inv("temp_rectal", "temp_core"), None),
        ("active_cooling", "Active cooling started", "intervention",
         _coll("interventions", "cold_water_immersion", "active_cooling"), None),
        ("ck", "Creatine kinase (CK)", "investigation", _inv("ck"), None),
        ("creatinine", "Creatinine / renal function", "investigation", _inv("creatinine", "urea_creatinine"), None),
        ("electrolytes", "Electrolytes (sodium, potassium)", "investigation", _inv("electrolytes"), None),
        ("ask_fluid_intake", "Asked: fluid intake and hours worked in the heat", "question",
         _asked("fluid_intake"), "How much water did you drink during your shift, and how many hours were you working in the heat?"),
    ]),
    ("pregnancy_check", "Pregnancy status (woman 12-55)", _preg, [
        ("pregnancy_test", "Pregnancy test (or status confirmed)", "investigation",
         _any(_inv("pregnancy_test"), _patient_known("pregnant")), None),
        ("ask_lmp", "Asked: last menstrual period", "question", _asked("last_menstrual_period"),
         "When was your last period?"),
    ]),
    ("syncope", "Transient loss of consciousness", _tloc, [
        ("ecg_12lead", "12-lead ECG", "investigation", _inv("ecg_12lead"), None),
        ("ask_syncope_circumstances", "Asked: what happened before and during the faint", "question",
         _asked("syncope_circumstances"), "What were you doing just before you fainted, and did you have chest pain or palpitations?"),
    ]),
    ("headache_red_flags", "Headache with red flag", _headache, [
        ("neuro_exam", "Neurological exam documented", "investigation", _inv("neuro_exam_documented"), None),
        ("head_imaging", "Imaging / LP decision", "investigation", _inv("ct_head", "lumbar_puncture", "mri_brain"), None),
    ]),
    ("fever_travel", "Fever after travel to a malaria area", _fever_travel, [
        ("malaria_test", "Malaria test (RDT or smear)", "investigation", _inv("malaria_rdt", "malaria_smear"), None),
    ]),
    ("sepsis", "Possible sepsis", _sepsis, [
        ("lactate", "Lactate", "investigation", _inv("lactate"), None),
        ("blood_culture", "Blood cultures", "investigation", _inv("blood_culture"), None),
    ]),
    ("suicide_risk", "Possible suicidal ideation", _suicide, [
        ("suicide_risk_assessment", "Risk / psychosocial assessment", "assessment",
         _coll("assessments", "suicide_risk_assessment", "psychosocial_assessment"), None),
        ("ask_suicidal_thoughts", "Asked directly about thoughts of self-harm", "question",
         _asked("suicidal_thoughts", "suicidal_ideation"),
         "Sometimes when people feel like this they think life is not worth living. Have you had thoughts like that?"),
    ]),
    ("stroke", "Sudden focal neurological symptom", _stroke, [
        ("brain_imaging", "Brain imaging (CT/MRI)", "investigation", _inv("ct_head", "mri_brain"), None),
    ]),
    ("fluids", "IV fluids / severe dehydration", _fluids, [
        ("u_and_e", "Electrolytes, urea and creatinine", "investigation", _inv("electrolytes", "urea_creatinine"), None),
    ]),
]


def checklist(state: dict, now_min: float | None = None) -> list[dict]:
    """[{"id","group","label","status":"open"|"done","closed_by","kind","ask_en"}] for each presenting-complaint
    group present in the state. Item ids are unique across groups (a shared item appears in the first group)."""
    state = state or {}
    out: list[dict] = []
    seen: set[str] = set()
    for group, group_label, active, items in GROUPS:
        if not active(state):
            continue
        for iid, label, kind, probe, ask in items:
            if iid in seen:
                continue
            if iid == "active_cooling" and not _heat_severe(state):
                continue
            seen.add(iid)
            closed = probe(state)
            row = {"id": iid, "group": group, "group_label": group_label, "label": label,
                   "status": "done" if closed else "open", "closed_by": closed, "kind": kind, "ask_en": ask}
            if iid == "ecg_12lead" and group == "chest_pain" and not closed and now_min is not None:
                firsts = [s.get("first_mention_min") for s in state.get("symptoms") or []
                          if s.get("code") in CHEST_CODES and isinstance(s.get("first_mention_min"), (int, float))]
                row["overdue"] = bool(firsts) and now_min - min(firsts) > 10
            out.append(row)
    return out


def open_items(state: dict, now_min: float | None = None) -> list[dict]:
    return [r for r in checklist(state, now_min) if r["status"] == "open"]
