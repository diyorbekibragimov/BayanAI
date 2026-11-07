"""Bayan AI · the validator: merges an extractor delta into the consultation state (docs/05 §2.3).

Plain Python, no LLM. It normalises drug names (brand -> INN, class list from meta.drug_classes),
converts units (g -> mg, mcg), computes daily_dose_mg = dose_mg x frequency_per_day, keeps the earliest
first_mention_min per symptom, dedupes, applies `remove`, and never overwrites a known value with
null/"unknown". It returns the events the change implies so the caller knows which rules to run.
"""

from __future__ import annotations

import contextlib
import difflib
import re
from typing import Any, Iterable

from .vocab import classes_of, normalise_code, normalise_drug

STATE_CHANGE, ON_PRESCRIBE, ON_DISPOSITION = "state_change", "on_prescribe", "on_disposition"

_UNKNOWN = {None, "", "unknown", "null", "none_known", "n/a", "na", "?"}
_MED_DOSE_FIELDS = ("dose_mg", "frequency_per_day", "daily_dose_mg", "route", "dose_mcg", "duration_days",
                    "concentration_mg_per_ml", "daily_clavulanate_mg", "clavulanate_mg", "puffs", "daily_puffs")
_SEVERITIES = {"mild", "moderate", "severe", "anaphylaxis", "scar", "unknown"}
_SEVERITY_ALIASES = {
    "anaphylactic": "anaphylaxis", "anaphylactic shock": "anaphylaxis", "life-threatening": "anaphylaxis",
    "sjs": "scar", "ten": "scar", "dress": "scar", "stevens-johnson": "scar", "stevens-johnson syndrome": "scar",
    "toxic epidermal necrolysis": "scar", "severe cutaneous": "scar", "minor": "mild", "medium": "moderate",
    "serious": "severe", "high": "severe", "low": "mild",
}
_ROUTES = {
    "po": "oral", "by mouth": "oral", "orally": "oral", "oral": "oral", "tablet": "oral", "mouth": "oral",
    "iv": "iv", "intravenous": "iv", "intravenously": "iv", "drip": "iv",
    "im": "im", "intramuscular": "im", "intramuscularly": "im", "injection": "im",
    "sc": "sc", "subcut": "sc", "subcutaneous": "sc", "inhaled": "inhaled", "inhaler": "inhaled",
    "topical": "topical", "pr": "rectal", "rectal": "rectal", "sl": "sublingual", "sublingual": "sublingual",
}
_FREQ_WORDS = [
    (r"\b(od|qd|once|daily|nocte|mane|once a day|once daily|every day|at night|at bedtime|before bed)\b", 1),
    (r"\b(bd|bid|twice|two times|2 times)\b", 2),
    (r"\b(tds|tid|three times|thrice|3 times)\b", 3),
    (r"\b(qds|qid|four times|4 times)\b", 4),
    (r"\b(five times|5 times)\b", 5),
    (r"\b(six times|6 times)\b", 6),
]
_FREQ_NUM_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "eight": "8",
                   "twelve": "12", "twenty-four": "24", "twenty four": "24"}
_DISPOSITIONS = {
    "discharge": "discharge", "discharged": "discharge", "home": "discharge", "go home": "discharge",
    "send home": "discharge", "discharge home": "discharge",
    "admit": "admit", "admission": "admit", "admitted": "admit", "admit to ward": "admit",
    "refer": "refer", "referral": "refer", "referred": "refer", "transfer": "refer", "transferred": "refer",
    "observe": "observe", "observation": "observe", "observed": "observe",
}
_INV_STATUS_RANK = {"ordered": 1, "pending": 1, "requested": 1, "resulted": 2, "done": 2, "performed": 2,
                    "normal": 2, "abnormal": 2, "completed": 2}
_WORD_NUMS = {"half a": "0.5", "half": "0.5", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
              "six": "6", "eight": "8", "ten": "10"}
_PATIENT_BOOL = {"heat_exposure", "heat_illness_suspected", "heat_stroke_suspected", "chronic_alcohol",
                 "malnourished"}
_PATIENT_NUM = {"age_years", "gestation_weeks", "weight_kg", "egfr", "travel_malaria_endemic_days"}
_VITAL_NUM = {"hr", "bp_sys", "bp_dia", "rr", "spo2", "temp_c"}


# ----------------------------------------------------------------------------- small helpers
def _is_unknown(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in _UNKNOWN
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return v is None


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v).replace(",", "") if re.search(r"\d,\d{3}", str(v)) else str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def _clean_num(x: float | None) -> float | int | None:
    if x is None:
        return None
    return int(x) if float(x).is_integer() else round(float(x), 4)


def _bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "y", "1", "positive"):
            return True
        if s in ("false", "no", "n", "0", "negative"):
            return False
    return None


def parse_time_min(t: Any) -> float | None:
    """"00:01:12" (h:m:s) or "01:12" (m:s) or a number -> consultation minutes."""
    if t is None:
        return None
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    parts = str(t).strip().split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 60 + nums[1] + nums[2] / 60
    if len(nums) == 2:
        return nums[0] + nums[1] / 60
    if len(nums) == 1:
        return nums[0]
    return None


def frequency_from_text(text: Any) -> float | None:
    """Doses per day from a frequency PHRASE only (never a bare number): clinical abbreviations (OD/QD/nocte/mane = 1,
    BD/BID = 2, TDS/TID = 3, QDS/QID = 4, with or without dots), intervals ("q4h", "every 6 hours", "4-hourly",
    "every 4 to 6 hours" -> the shorter interval) and counts ("up to 4 times a day", "x3/day")."""
    if text is None or isinstance(text, bool):
        return None
    s = " " + str(text).strip().lower() + " "
    s = re.sub(r"\b([a-z])\.(?=[a-z]\b\.?)", r"\1", s)            # q.d.s. / t.i.d. -> qds / tid
    s = re.sub(r"\b([a-z]{2,3})\.", r"\1", s)
    for word, n in _FREQ_NUM_WORDS.items():
        s = re.sub(rf"\b{word}\b", n, s)
    m = re.search(r"(?:\bevery|\bq)\s*(\d+(?:\.\d+)?)(?:\s*(?:-|to|or)\s*\d+(?:\.\d+)?)?\s*(?:h|hr|hrs|hrly|hour|hours|hourly)\b"
                  r"|\b(\d+(?:\.\d+)?)\s*-?\s*(?:hourly|hrly)\b", s)
    if m:
        h = float(m.group(1) or m.group(2))
        if h > 0:
            return round(24 / h, 3)
    for pat, n in _FREQ_WORDS[1:] + _FREQ_WORDS[:1]:
        if re.search(pat, s):
            return float(n)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|times)\b", s) or re.search(r"\bx\s*(\d+(?:\.\d+)?)\b", s)
    if m and float(m.group(1)) > 0:
        return float(m.group(1))
    return None


def parse_frequency(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    f = frequency_from_text(v)
    if f is not None:
        return f
    n = _num(str(v).strip().lower())
    return n if n and n > 0 else None


def _unit_kind(u: Any) -> str | None:
    if not u:
        return None
    s = str(u).strip().lower().replace("µ", "u").replace("μ", "u")
    if s in ("g", "gm", "gram", "grams", "gr", "gms"):
        return "g"
    if s in ("mg", "milligram", "milligrams", "mgs"):
        return "mg"
    if s in ("mcg", "ug", "microgram", "micrograms", "mcgs"):
        return "mcg"
    return None


def parse_dose(raw: Any) -> tuple[float | None, str | None, float | None]:
    """'1 g' -> (1.0, 'g', None); '500/125 mg' -> (500.0, 'mg', 125.0); '100 micrograms' -> (100.0, 'mcg', None);
    '50 to 100 mg' -> (100.0, 'mg', None) (the upper bound of a range)."""
    if raw is None:
        return None, None, None
    s = str(raw).strip().lower().replace("µ", "u").replace("μ", "u")
    for word, n in _WORD_NUMS.items():
        s = re.sub(rf"\b{word}\b", n, s)
    # a range with a unit ("50 to 100 mg", "50-100mg"): the upper bound, so dose ceilings are never under-counted
    r = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:-|–|to|or)\s*(\d+(?:[.,]\d+)?)\s*(mcg|ug|micrograms?|mg|milligrams?|grams?|gm|g)\b", s)
    if r:
        return float(r.group(2).replace(",", ".")), _unit_kind(r.group(3)), None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:/\s*(\d+(?:[.,]\d+)?))?\s*(mcg|ug|micrograms?|mg|milligrams?|grams?|gm|g)?\b", s)
    if not m:
        return None, None, None
    val = float(m.group(1).replace(",", "."))
    combo = float(m.group(2).replace(",", ".")) if m.group(2) else None
    return val, _unit_kind(m.group(3)), combo


def _concentration(raw: Any) -> float | None:
    if not raw:
        return None
    s = str(raw).lower()
    m = re.search(r"1\s*:\s*(1\s*0{3,})", s.replace(",", ""))
    if m:
        return round(1000.0 / float(m.group(1).replace(" ", "")), 4)
    m = re.search(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*(\d+(?:\.\d+)?)?\s*ml", s)
    if m:
        return float(m.group(1)) / float(m.group(2) or 1)
    return None


# ----------------------------------------------------------------------------- evidence
def _turn_lookup(consult: Any, utt: str):
    fn = getattr(consult, "turn_by_id", None)
    return fn(utt) if fn and utt else None


def normalise_evidence(ev: Any, consult: Any = None) -> list[dict]:
    """Evidence -> [{"utt","t_min","quote"}]; fills t_min/quote from the transcript when missing."""
    if ev is None:
        return []
    if isinstance(ev, (str, dict)):
        ev = [ev]
    out: list[dict] = []
    for e in ev:
        if isinstance(e, str):
            e = {"utt": e}
        if not isinstance(e, dict):
            continue
        utt = e.get("utt") or e.get("utterance_id") or e.get("id")
        t_min = e.get("t_min")
        if t_min is None:
            t_min = parse_time_min(e.get("t"))
        quote = e.get("quote") or e.get("text")
        turn = _turn_lookup(consult, utt)
        if turn is not None:
            if t_min is None:
                t_min = turn.t_min
            if not quote:
                quote = turn.text
        item = {"utt": utt, "t_min": float(t_min) if isinstance(t_min, (int, float)) else t_min, "quote": quote or ""}
        if item["utt"] or item["quote"]:
            out.append(item)
    return out


def _merge_ev(old: list[dict], new: list[dict]) -> bool:
    seen = {(e.get("utt"), e.get("quote")) for e in old}
    changed = False
    for e in new:
        k = (e.get("utt"), e.get("quote"))
        if k not in seen:
            old.append(e)
            seen.add(k)
            changed = True
    return changed


def _earliest(ev: Iterable[dict]) -> float | None:
    ts = [e.get("t_min") for e in ev if isinstance(e.get("t_min"), (int, float))]
    return min(ts) if ts else None


# ----------------------------------------------------------------------------- items
def _drug_classes(drug: str, given: Any = None) -> list[str]:
    out = list(classes_of(drug)) if drug else []
    given_list = given if isinstance(given, list) else ([given] if given else [])
    for g in given_list:
        for c in classes_of(str(g)):
            if c not in out:
                out.append(c)
    return out


def _clavulanate_per_dose(dose_mg: float | None, combo: float | None, route: str | None) -> float | None:
    if combo:
        return combo
    if not dose_mg:
        return None
    if dose_mg in (625, 1000):
        return 125.0
    if dose_mg == 1200 or (route == "iv" and dose_mg == 1000):
        return 200.0
    if dose_mg % 375 == 0:
        return dose_mg / 375 * 125
    return None


# ----------------------------------------------------------------------------- medication instructions
# Fields the patient care plan renders (agent C). All optional; only what the doctor said; normalised defensively.
MED_FORMS = ("tablet", "capsule", "liquid", "nasal_spray", "inhaler", "eye_drops", "ear_drops", "cream", "patch",
             "injection", "sachet", "other")
MED_UNITS = ("tablet", "capsule", "ml", "spray", "puff", "drop", "sachet", "application", "patch", "mg", "g")
MED_TIMES = ("on_waking", "morning", "midday", "evening", "bedtime")
MED_FOOD = ("before_food", "with_food", "after_food", "empty_stomach")
MED_DETAIL_SCALARS = ("form", "amount", "unit", "site", "food", "interval_hours", "as_needed", "as_needed_for",
                      "max_per_day", "min_hours_between", "duration_text")
MED_DETAIL_FIELDS = MED_DETAIL_SCALARS + ("times", "instructions")

_FORM_SYNONYMS = [   # (substring, form) - first match wins, so specific phrases come first
    ("nasal spray", "nasal_spray"), ("nose spray", "nasal_spray"), ("nasal_spray", "nasal_spray"),
    ("eye drop", "eye_drops"), ("eye_drop", "eye_drops"), ("eyedrop", "eye_drops"),
    ("ear drop", "ear_drops"), ("ear_drop", "ear_drops"), ("eardrop", "ear_drops"),
    ("inhaler", "inhaler"), ("puffer", "inhaler"), ("nebul", "inhaler"),
    ("capsule", "capsule"), ("cap", "capsule"),
    ("tablet", "tablet"), ("tab", "tablet"), ("pill", "tablet"), ("caplet", "tablet"),
    ("syrup", "liquid"), ("suspension", "liquid"), ("solution", "liquid"), ("liquid", "liquid"),
    ("mixture", "liquid"), ("elixir", "liquid"),
    ("cream", "cream"), ("ointment", "cream"), ("gel", "cream"), ("lotion", "cream"),
    ("patch", "patch"), ("injection", "injection"), ("inject", "injection"), ("jab", "injection"), ("shot", "injection"),
    ("sachet", "sachet"), ("powder", "sachet"), ("ors", "sachet"), ("granule", "sachet"),
]
_UNIT_SYNONYMS = {
    "tablet": "tablet", "tablets": "tablet", "tab": "tablet", "tabs": "tablet", "pill": "tablet", "pills": "tablet",
    "capsule": "capsule", "capsules": "capsule", "cap": "capsule", "caps": "capsule",
    "ml": "ml", "mls": "ml", "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "milliliters": "ml", "cc": "ml",
    "spray": "spray", "sprays": "spray", "squirt": "spray", "squirts": "spray",
    "puff": "puff", "puffs": "puff", "inhalation": "puff", "inhalations": "puff",
    "drop": "drop", "drops": "drop",
    "sachet": "sachet", "sachets": "sachet", "packet": "sachet", "packets": "sachet",
    "application": "application", "applications": "application", "layer": "application", "thin layer": "application",
    "patch": "patch", "patches": "patch",
    "mg": "mg", "milligram": "mg", "milligrams": "mg", "g": "g", "gram": "g", "grams": "g", "gm": "g",
}
_UNIT_TO_ML = {"teaspoon": 5.0, "teaspoons": 5.0, "tsp": 5.0, "tablespoon": 15.0, "tablespoons": 15.0, "tbsp": 15.0}
_TIME_SYNONYMS = [
    (r"\b(on waking|when you wake|wake up|waking|on_waking|first thing)\b", "on_waking"),
    (r"\b(morning|breakfast|a\.?m\.?)\b", "morning"),
    (r"\b(midday|noon|lunch|afternoon)\b", "midday"),
    (r"\b(evening|dinner|supper)\b", "evening"),
    (r"\b(bedtime|bed time|before bed|at night|night|nightly|nocte|sleep)\b", "bedtime"),
]
_FOOD_SYNONYMS = [
    (r"empty[\s_]stomach|without food|fasting", "empty_stomach"),
    (r"before[\s_](food|meals?|eating|breakfast|lunch|dinner)|\bac\b|before_food", "before_food"),
    (r"after[\s_](food|meals?|eating|breakfast|lunch|dinner)|\bpc\b|after_food", "after_food"),
    (r"with[\s_](food|meals?|breakfast|lunch|dinner|milk)|with_food", "with_food"),
]
_DURATION_UNITS = {"day": 1, "days": 1, "week": 7, "weeks": 7, "fortnight": 14, "month": 30, "months": 30}


def _words_to_num(s: str) -> str:
    s = str(s).lower()
    for word, n in _WORD_NUMS.items():
        s = re.sub(rf"\b{word}\b", n, s)
    return s


def _form(v: Any, site: str | None) -> str | None:
    if _is_unknown(v):
        return None
    s = str(v).strip().lower().replace("-", " ")
    if s in MED_FORMS:
        return s
    if "spray" in s:
        return "nasal_spray" if ("nos" in s or "nasal" in s or "nostril" in (site or "").lower()) else "other"
    if re.search(r"\bdrops?\b", s):
        site_l = (site or "").lower()
        return "eye_drops" if "eye" in site_l else "ear_drops" if "ear" in site_l else "other"
    for sub, form in _FORM_SYNONYMS:
        if re.search(rf"\b{re.escape(sub)}", s):
            return form
    return "other"


def _amount_unit(amount: Any, unit: Any) -> tuple[float | None, str | None]:
    """("two", "sprays") -> (2, "spray"); ("2 sprays", None) -> (2, "spray"); ("1", "teaspoon") -> (5, "ml")."""
    u_raw = "" if _is_unknown(unit) else str(unit).strip().lower()
    a_raw = None if _is_unknown(amount) else amount
    val = _num(_words_to_num(a_raw)) if isinstance(a_raw, str) else _num(a_raw)
    if isinstance(a_raw, str) and not u_raw:          # unit folded into the amount string
        m = re.search(r"[a-z][a-z ]*$", _words_to_num(a_raw).strip())
        u_raw = m.group(0).strip() if m else ""
    if u_raw in _UNIT_TO_ML and val is not None:
        return val * _UNIT_TO_ML[u_raw], "ml"
    u = _UNIT_SYNONYMS.get(u_raw) or _UNIT_SYNONYMS.get(u_raw.rstrip("s")) or (u_raw if u_raw in MED_UNITS else None)
    if u is None and u_raw in ("mcg", "microgram", "micrograms", "ug") and val is not None:
        return val / 1000, "mg"
    return val, u


def _times(v: Any) -> list[str]:
    items = v if isinstance(v, list) else ([v] if not _is_unknown(v) else [])
    found: set[str] = set()
    for it in items:
        s = str(it).strip().lower().replace("_", " ") if it is not None else ""
        if s.replace(" ", "_") in MED_TIMES:
            found.add(s.replace(" ", "_"))
            continue
        for pat, slot in _TIME_SYNONYMS:
            if re.search(pat, s):
                found.add(slot)
                break
    return [t for t in MED_TIMES if t in found]


def _food(v: Any) -> str | None:
    if _is_unknown(v):
        return None
    s = str(v).strip().lower()
    if s in MED_FOOD:
        return s
    for pat, food in _FOOD_SYNONYMS:
        if re.search(pat, s):
            return food
    return None


def _duration_days_from_text(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(days?|weeks?|fortnight|months?)\b", _words_to_num(text))
    if m:
        return float(m.group(1)) * _DURATION_UNITS[m.group(2)]
    m = re.search(r"\b(a|an)\s+(day|week|fortnight|month)\b", text.lower())
    if m:
        return float(_DURATION_UNITS[m.group(2)])
    return None


def _instructions(v: Any) -> list[str]:
    items = v if isinstance(v, list) else ([v] if not _is_unknown(v) else [])
    out: list[str] = []
    for it in items:
        s = " ".join(str(it).split()).strip(" .;") if it is not None else ""
        if s and s.lower() not in (x.lower() for x in out):
            out.append(s)
    return out


def normalise_med_details(item: dict) -> dict:
    """Care-plan instruction fields of one med item -> normalised subset (unknown values dropped, never guessed)."""
    item = item or {}
    out: dict = {}
    site = None if _is_unknown(item.get("site")) else " ".join(str(item["site"]).split())
    if site:
        out["site"] = site
    form = _form(item.get("form"), site)
    if form:
        out["form"] = form
    amount, unit = _amount_unit(item.get("amount"), item.get("amount_unit") or item.get("unit"))
    if amount is not None and amount > 0:
        out["amount"] = _clean_num(amount)
    if unit:
        out["unit"] = unit
    times = _times(item.get("times"))
    if times:
        out["times"] = times
    food = _food(item.get("food"))
    if food:
        out["food"] = food
    for k in ("interval_hours", "max_per_day", "min_hours_between"):
        n = _num(_words_to_num(item[k])) if isinstance(item.get(k), str) else _num(item.get(k))
        if n is not None and n > 0:
            out[k] = _clean_num(n)
    an = item.get("as_needed")
    if isinstance(an, str):
        s = an.strip().lower()
        an = True if s in ("prn", "as needed", "when needed", "if needed") else _bool(s)
    if isinstance(an, bool):
        out["as_needed"] = an
    for k in ("as_needed_for", "duration_text"):
        if not _is_unknown(item.get(k)):
            out[k] = " ".join(str(item[k]).split())
    ins = _instructions(item.get("instructions"))
    if ins:
        out["instructions"] = ins
    return out


def normalise_med(item: dict, consult: Any = None) -> dict:
    """One med item (extractor or talk-loop shape) -> normalised state item (rule fields + care-plan instruction
    fields from normalise_med_details: form, amount/unit, site, times, food, interval/as-needed, duration_text...)."""
    item = dict(item or {})
    drug = normalise_drug(item.get("drug") or item.get("name") or item.get("substance") or "")
    route_raw = item.get("route")
    route = _ROUTES.get(str(route_raw).strip().lower(), str(route_raw).strip().lower()) if not _is_unknown(route_raw) else None
    unit = _unit_kind(item.get("unit_raw") or item.get("unit") or item.get("dose_unit"))
    p_val, p_unit, p_combo = parse_dose(item.get("dose_raw"))
    unit = unit or p_unit

    dose_mg = _num(item.get("dose_mg"))
    dose_mcg = _num(item.get("dose_mcg"))
    if dose_mg is None:
        val = _num(item.get("dose"))
        if val is None and p_val is not None:
            val = p_val
        if val is not None:
            if unit == "g":
                dose_mg = val * 1000
            elif unit == "mcg":
                dose_mcg = dose_mcg if dose_mcg is not None else val
                dose_mg = val / 1000
            elif unit == "mg":
                dose_mg = val
            # unit unknown -> ambiguous: leave dose_mg None rather than guess
    else:
        if unit == "g" and dose_mg <= 10:
            dose_mg *= 1000          # extractor put the gram figure in the mg field
        elif unit == "mcg" and dose_mcg is None:
            if dose_mg >= 1:         # the mcg figure was put in the mg field
                dose_mcg, dose_mg = dose_mg, dose_mg / 1000
    details = normalise_med_details(item)
    if dose_mg is None and details.get("amount") is not None and details.get("unit") in ("mg", "g"):
        dose_mg = float(details["amount"]) * (1000 if details["unit"] == "g" else 1)   # "one gram" -> 1000 mg
    if dose_mcg is None and dose_mg is not None:
        dose_mcg = dose_mg * 1000

    freq = parse_frequency(item.get("frequency_per_day", item.get("frequency")))
    if freq is None and details.get("interval_hours"):
        freq = round(24 / float(details["interval_hours"]), 3)          # "every 8 hours" -> 3/day
    if freq is None and details.get("as_needed") and details.get("max_per_day"):
        freq = float(details["max_per_day"])                             # dose ceilings use the maximum
    if freq is None and details.get("times") and not details.get("as_needed"):
        freq = float(len(details["times"]))                              # "every morning" -> 1/day
    daily = _num(item.get("daily_dose_mg"))
    if dose_mg is not None and freq is not None:
        daily = dose_mg * freq
    combined = _num(item.get("combined_daily_mg"))     # same drug twice in one order (combine_same_drug)
    if combined is not None and (daily is None or combined > daily):
        daily = combined
    else:
        combined = None

    out: dict = {
        "drug": drug,
        "class": _drug_classes(drug, item.get("class")),
        "dose_mg": _clean_num(dose_mg),
        "frequency_per_day": _clean_num(freq),
        "daily_dose_mg": _clean_num(daily),
        "route": route,
        "evidence": normalise_evidence(item.get("evidence"), consult),
    }
    if dose_mcg is not None:
        out["dose_mcg"] = _clean_num(dose_mcg)
    if combined is not None:
        out["combined_daily_mg"] = _clean_num(combined)
    dur = _num(item.get("duration_days"))
    if dur is not None:
        out["duration_days"] = _clean_num(dur)
    conc = _num(item.get("concentration_mg_per_ml"))
    if conc is None:
        conc = _concentration(item.get("dose_raw")) or _concentration(item.get("concentration"))
    if conc is not None:
        out["concentration_mg_per_ml"] = _clean_num(conc)
    if drug == "co-amoxiclav":
        clav = _num(item.get("clavulanate_mg")) or _clavulanate_per_dose(dose_mg, p_combo, route)
        if _num(item.get("daily_clavulanate_mg")) is not None:
            out["daily_clavulanate_mg"] = _clean_num(_num(item["daily_clavulanate_mg"]))
        elif clav is not None and freq is not None:
            out["daily_clavulanate_mg"] = _clean_num(clav * freq)
    puffs = _num(item.get("puffs") or item.get("puffs_per_dose"))
    if puffs is None and details.get("unit") == "puff":
        puffs = _num(details.get("amount"))
    if _num(item.get("daily_puffs")) is not None:
        out["daily_puffs"] = _clean_num(_num(item["daily_puffs"]))
    elif puffs is not None and freq is not None:
        out["daily_puffs"] = _clean_num(puffs * freq)
    for k in ("dose_raw", "unit_raw", "indication", "confidence", "intent"):
        if not _is_unknown(item.get(k)):
            out[k] = item[k]
    out.update(details)
    if "duration_days" not in out and details.get("duration_text"):
        d = _duration_days_from_text(details["duration_text"])
        if d is not None:
            out["duration_days"] = _clean_num(d)
    return out


# Reaction wording that makes an allergy severe whatever the model said (a drug reaction with swelling is treated as
# angioedema until proven otherwise; breathing difficulty / collapse = anaphylaxis). Deterministic, so a non-severe
# label from the LLM can never keep a cross-reactivity alert (e.g. ALG-PEN-02) from escalating.
_ANAPHYLAXIS_RX = re.compile(
    r"anaphyla|\b(could|can)(n'?t| ?not)\b.{0,12}\bbreath|\bbreath\w*\s+(difficult|trouble|problem|stopp)"
    r"|\b(difficult\w*|trouble|problem\w*|hard|struggl\w*|unable|short(ness)? of)\b.{0,15}\bbreath|\bbreathless"
    r"|\bwheez|\bthroat\b.{0,25}\b(clos|tight|swell|swoll)|\b(collaps|faint|passed out|unconscious|blacked out)"
    r"|\bblood pressure\b.{0,15}\b(drop|fell|low)|\bshock\b|\bepipen|\badrenaline\b", re.I)
_SEVERE_RX = re.compile(
    r"angio-?o?edema|\b(swell|swelled|swelling|swellings|swollen|swole|puff(ed|y|ing)? up|bloat(ed)? up)\b"
    r"|\b(blister\w*|peel\w*|skin came off|sjs|stevens|necrolysis)\b|\badmitted\b|\bhospitali[sz]ed\b", re.I)
_SEV_RANK = {"unknown": 0, "mild": 1, "moderate": 2, "severe": 3, "scar": 4, "anaphylaxis": 4}


def reaction_severity(reaction: Any) -> str | None:
    """Severity floor implied by the reaction as told: "anaphylaxis", "severe" or None (no severe feature)."""
    text = " ".join(str(x) for x in reaction) if isinstance(reaction, (list, tuple)) else str(reaction or "")
    if not text.strip():
        return None
    if _ANAPHYLAXIS_RX.search(text):
        return "anaphylaxis"
    if _SEVERE_RX.search(text):
        return "severe"
    return None


def _floor_severity(sev: str, reaction: Any) -> str:
    floor = reaction_severity(reaction)
    if floor and _SEV_RANK.get(floor, 0) > _SEV_RANK.get(sev, 0):
        return floor
    return sev


def _normalise_allergy(item: dict, consult: Any) -> dict:
    sub_raw = item.get("substance") or item.get("drug") or item.get("name") or ""
    substance = normalise_drug(sub_raw) or str(sub_raw).strip().lower()
    sev = str(item.get("severity") or "unknown").strip().lower()
    sev = _SEVERITY_ALIASES.get(sev, sev)
    if sev not in _SEVERITIES:
        sev = "unknown"
    reaction = item.get("reaction")
    if not _is_unknown(reaction):
        sev = _floor_severity(sev, reaction)
    out = {
        "substance": substance,
        "class": _drug_classes(substance, item.get("class")),
        "reaction": None if _is_unknown(reaction) else reaction,
        "severity": sev,
        "evidence": normalise_evidence(item.get("evidence"), consult),
    }
    if item.get("confidence") is not None:
        out["confidence"] = item["confidence"]
    return out


def _fill(old: dict, new: dict, keys: Iterable[str]) -> bool:
    """Copy known new values over; never overwrite a known value with null/unknown."""
    changed = False
    for k in keys:
        if k not in new or _is_unknown(new[k]):
            continue
        if old.get(k) != new[k]:
            old[k] = new[k]
            changed = True
    return changed


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _drug_of(x: Any) -> str:
    if isinstance(x, dict):
        x = x.get("drug") or x.get("name") or ""
    return normalise_drug(str(x))


# ----------------------------------------------------------------------------- same drug, two schedules
def _dose_freq(item: dict) -> tuple[float | None, float | None]:
    m = normalise_med(item)
    return m.get("dose_mg"), m.get("frequency_per_day")


def combine_same_drug(items: list) -> list:
    """One order that names the same drug twice ("tramadol 100 mg QDS, plus another 100 mg at night if needed") is
    ONE prescription whose daily total is the sum: 100 x 4 + 100 x 1 = 500 mg/day, which the dose-ceiling rules must
    see (otherwise the second item replaces the first and each looks safe on its own). Prescribe items of the same
    drug that both carry a dose and a frequency are folded into the first: its schedule stays as said, the extra
    doses become an instruction ("plus 100 mg at night if needed"), combined_daily_mg = the summed daily dose
    (normalise_med uses it for daily_dose_mg) and dose_mg = the larger single dose (single-dose ceilings).
    Items without both (extra detail such as "take it after food") are left alone for the field merge."""
    out: list = []
    first: dict[str, dict] = {}
    parts: dict[str, list[tuple[float, float]]] = {}
    for raw in items or []:
        if not isinstance(raw, dict) or str(raw.get("intent") or "prescribe").lower() != "prescribe":
            out.append(raw)
            continue
        drug = normalise_drug(raw.get("drug") or raw.get("name") or "")
        dose, freq = _dose_freq(raw)
        if not drug or dose is None or freq is None:
            out.append(raw)
            continue
        if drug not in first:
            first[drug] = dict(raw)
            parts[drug] = [(float(dose), float(freq))]
            out.append(first[drug])
            continue
        base = first[drug]
        parts[drug].append((float(dose), float(freq)))
        if float(dose) > float(_dose_freq(base)[0] or 0):
            base["dose_mg"] = _clean_num(dose)
        base["combined_daily_mg"] = _clean_num(sum(d * f for d, f in parts[drug]))
        extra = str(raw.get("dose_raw") or raw.get("dose") or f"{_clean_num(dose)} mg x{_clean_num(freq)}/day").strip()
        said = str(base.get("dose_raw") or base.get("dose") or "").strip()
        base["dose_raw"] = f"{said}; plus {extra}" if said else f"plus {extra}"
        ins = base.get("instructions")
        ins = list(ins) if isinstance(ins, list) else ([ins] if isinstance(ins, str) and ins.strip() else [])
        base["instructions"] = ins + [f"plus {extra}" + ("" if re.search(r"\bif\b|need", extra, re.I) or
                                                         not raw.get("as_needed") else " if needed")]
        ev = list(base.get("evidence") or [])
        base["evidence"] = ev + [e for e in (raw.get("evidence") or []) if e not in ev]
    return out


# ----------------------------------------------------------------------------- merge
def merge_delta(consult: Any, delta: dict) -> set[str]:
    """Merge an extractor delta into consult.state (or into a bare state dict). Returns the events implied:
    ⊆ {"state_change", "on_prescribe", "on_disposition"}. Bumps consult.state_version if anything changed."""
    if not delta:
        return set()
    state = consult.state if hasattr(consult, "state") else consult
    lock = getattr(consult, "lock", None) or contextlib.nullcontext()
    with lock:
        events: set[str] = set()
        changed = False
        now = consult.now_min() if hasattr(consult, "now_min") else None

        # --- removals first (so "no amoxicillin ... paracetamol instead" in one delta works)
        removals = dict(delta.get("remove") or {})
        stopped = list(delta.get("stopped_meds") or [])
        for med in delta.get("prescribed_meds") or []:
            if isinstance(med, dict) and str(med.get("intent", "")).lower() == "stop":
                stopped.append(med)
        if stopped:
            removals["prescribed_meds"] = list(removals.get("prescribed_meds") or []) + stopped
        for coll, items in removals.items():
            if _apply_remove(state, coll, _as_list(items), consult):
                changed = True

        # --- allergies
        for raw in delta.get("allergies") or []:
            if not isinstance(raw, dict):
                raw = {"substance": raw}
            a = _normalise_allergy(raw, consult)
            if not a["substance"]:
                continue
            old = next((x for x in state["allergies"] if x.get("substance") == a["substance"]), None)
            if old is None:
                state["allergies"].append(a)
                changed = True
            else:
                c = _fill(old, a, ("reaction", "confidence"))
                if a["severity"] != "unknown" and old.get("severity") != a["severity"]:
                    old["severity"] = a["severity"]
                    c = True
                # a later, milder label never drops a severe feature already told (either reaction wording counts)
                sev = _floor_severity(_floor_severity(old.get("severity") or "unknown", old.get("reaction")),
                                      a.get("reaction"))
                if sev != old.get("severity"):
                    old["severity"] = sev
                    c = True
                for cl in a["class"]:
                    if cl not in old.setdefault("class", []):
                        old["class"].append(cl)
                        c = True
                c = _merge_ev(old.setdefault("evidence", []), a["evidence"]) or c
                changed = changed or c

        # --- medications
        for coll in ("current_meds", "prescribed_meds"):
            items = delta.get(coll) or []
            if coll == "prescribed_meds":
                items = combine_same_drug(items)
            for raw in items:
                if not isinstance(raw, dict):
                    raw = {"drug": raw}
                intent = str(raw.get("intent", "")).lower()
                if coll == "prescribed_meds" and intent in ("stop", "mention", "ask"):
                    continue
                m = normalise_med(raw, consult)
                if not m["drug"]:
                    continue
                old = next((x for x in state[coll] if x.get("drug") == m["drug"]), None)
                if old is None:
                    state[coll].append(m)
                    changed = True
                    if coll == "prescribed_meds":
                        events.add(ON_PRESCRIBE)
                else:
                    dose_changed = _fill(old, m, _MED_DOSE_FIELDS + ("combined_daily_mg",))
                    if (old.get("combined_daily_mg") is not None and m.get("combined_daily_mg") is None
                            and (m.get("frequency_per_day") is not None or m.get("dose_mg") is not None)):
                        old.pop("combined_daily_mg")       # a new schedule replaces the combined order
                        dose_changed = True
                    if dose_changed and old.get("dose_mg") is not None and old.get("frequency_per_day") is not None:
                        old["daily_dose_mg"] = _clean_num(max(old["dose_mg"] * old["frequency_per_day"],
                                                              _num(old.get("combined_daily_mg")) or 0))
                    c = _fill(old, m, ("dose_raw", "unit_raw", "indication", "confidence"))
                    c = _fill(old, m, MED_DETAIL_SCALARS) or c       # more detail on the same drug: merge
                    if m.get("times") and old.get("times") != m["times"]:
                        old["times"] = list(m["times"])
                        c = True
                    if m.get("instructions"):
                        ins = _instructions(list(old.get("instructions") or []) + list(m["instructions"]))
                        if ins != old.get("instructions"):
                            old["instructions"] = ins
                            c = True
                    for cl in m["class"]:
                        if cl not in old.setdefault("class", []):
                            old["class"].append(cl)
                            c = True
                    c = _merge_ev(old.setdefault("evidence", []), m["evidence"]) or c
                    if dose_changed and coll == "prescribed_meds":
                        events.add(ON_PRESCRIBE)
                    changed = changed or c or dose_changed
                if coll == "prescribed_meds":
                    before = len(state["stopped_meds"])
                    state["stopped_meds"] = [s for s in state["stopped_meds"] if s.get("drug") != m["drug"]]
                    changed = changed or len(state["stopped_meds"]) != before

        # --- symptoms
        for raw in delta.get("symptoms") or []:
            if not isinstance(raw, dict):
                raw = {"code": raw}
            code = normalise_code("symptoms", raw.get("code"))
            if not code:
                continue
            ev = normalise_evidence(raw.get("evidence"), consult)
            first = raw.get("first_mention_min")
            first = float(first) if isinstance(first, (int, float)) and not isinstance(first, bool) else parse_time_min(raw.get("first_mention_t"))
            if first is None:
                first = _earliest(ev)
            if first is None:
                first = now
            old = next((x for x in state["symptoms"] if x.get("code") == code), None)
            if old is None:
                item = {"code": code, "severity": raw.get("severity"), "onset": raw.get("onset"),
                        "first_mention_min": first, "evidence": ev}
                if raw.get("confidence") is not None:
                    item["confidence"] = raw["confidence"]
                state["symptoms"].append(item)
                changed = True
            else:
                c = _fill(old, raw, ("severity", "onset", "confidence"))
                if first is not None and (old.get("first_mention_min") is None or first < old["first_mention_min"]):
                    old["first_mention_min"] = first
                    c = True
                c = _merge_ev(old.setdefault("evidence", []), ev) or c
                changed = changed or c

        # --- vitals
        vit = dict(delta.get("vitals") or {})
        bp = vit.pop("bp", None) or vit.pop("blood_pressure", None)
        if isinstance(bp, str) and "/" in bp:
            s_, d_ = bp.split("/", 1)
            vit.setdefault("bp_sys", s_)
            vit.setdefault("bp_dia", d_)
        for k, v in vit.items():
            if k == "evidence" or _is_unknown(v):
                continue
            val = _clean_num(_num(v)) if k in _VITAL_NUM else v
            if val is None:
                continue
            if state["vitals"].get(k) != val:
                state["vitals"][k] = val
                changed = True
        if vit.get("evidence"):
            ev = normalise_evidence(vit["evidence"], consult)
            changed = _merge_ev(state["vitals"].setdefault("evidence", []), ev) or changed

        # --- investigations / interventions / assessments
        for coll in ("investigations", "interventions", "assessments"):
            for raw in delta.get(coll) or []:
                if not isinstance(raw, dict):
                    raw = {"code": raw}
                code = normalise_code(coll, raw.get("code"))
                if not code:
                    continue
                ev = normalise_evidence(raw.get("evidence"), consult)
                old = next((x for x in state[coll] if x.get("code") == code), None)
                if coll == "investigations":
                    status = str(raw.get("status") or "ordered").strip().lower()
                    status = "resulted" if _INV_STATUS_RANK.get(status, 1) == 2 else "ordered"
                    if old is None:
                        item = {"code": code, "status": status, "result": raw.get("result"), "evidence": ev}
                        state[coll].append(item)
                        changed = True
                    else:
                        c = False
                        if _INV_STATUS_RANK.get(status, 1) > _INV_STATUS_RANK.get(old.get("status") or "ordered", 1):
                            old["status"] = status
                            c = True
                        c = _fill(old, raw, ("result",)) or c
                        c = _merge_ev(old.setdefault("evidence", []), ev) or c
                        changed = changed or c
                else:
                    if old is None:
                        state[coll].append({"code": code, "evidence": ev})
                        changed = True
                    else:
                        changed = _merge_ev(old.setdefault("evidence", []), ev) or changed

        # --- disposition (replaced when given)
        disp = delta.get("disposition")
        if disp:
            if not isinstance(disp, dict):
                disp = {"type": disp}
            t = disp.get("type")
            t = _DISPOSITIONS.get(str(t).strip().lower()) if not _is_unknown(t) else None
            if t:
                ev = normalise_evidence(disp.get("evidence"), consult)
                cur = state.get("disposition") or {"type": None, "evidence": []}
                if cur.get("type") != t:
                    state["disposition"] = {"type": t, "evidence": ev}
                    changed = True
                    events.add(ON_DISPOSITION)
                else:
                    changed = _merge_ev(cur.setdefault("evidence", []), ev) or changed

        # --- patient
        for k, v in (delta.get("patient") or {}).items():
            if _is_unknown(v):
                continue
            val: Any = v
            if k in _PATIENT_BOOL:
                val = _bool(v)
            elif k in _PATIENT_NUM:
                val = _clean_num(_num(v))
            elif k == "pregnant":
                b = _bool(v)
                if b is None and isinstance(v, str):
                    s = v.strip().lower()
                    b = True if s == "pregnant" else False if s in ("not pregnant", "not_pregnant") else None
                val = b
            elif k == "hepatic_impairment":
                val = "severe" if str(v).strip().lower() == "severe" else _bool(v)
            elif k == "sex":
                s = str(v).strip().lower()
                val = {"m": "male", "man": "male", "f": "female", "woman": "female"}.get(s, s)
            elif k == "dehydration":
                val = str(v).strip().lower()
            if val is None:
                continue
            if state["patient"].get(k) != val:
                state["patient"][k] = val
                changed = True

        # --- idiom hits (dedupe by id, earliest kept)
        for raw in delta.get("idiom_hits") or []:
            if not isinstance(raw, dict):
                raw = {"id": raw}
            iid = raw.get("id")
            if not iid:
                continue
            old = next((x for x in state["idiom_hits"] if x.get("id") == iid), None)
            if old is None:
                hit = {"id": iid, "red_flag_tags": list(raw.get("red_flag_tags") or []), "utt": raw.get("utt"),
                       "t_min": raw.get("t_min"), "matched": raw.get("matched")}
                if hit["t_min"] is None:
                    turn = _turn_lookup(consult, hit["utt"])
                    hit["t_min"] = turn.t_min if turn is not None else now
                state["idiom_hits"].append(hit)
                changed = True
            elif raw.get("red_flag_tags") and not old.get("red_flag_tags"):
                old["red_flag_tags"] = list(raw["red_flag_tags"])
                changed = True

        # --- questions asked
        for q in delta.get("questions_asked") or []:
            if isinstance(q, dict):
                q = q.get("topic") or q.get("code")
            if not q:
                continue
            q = re.sub(r"[\s\-/]+", "_", str(q).strip().lower())
            if q not in state["questions_asked"]:
                state["questions_asked"].append(q)
                changed = True

        if delta.get("case"):
            changed = merge_case(state, delta["case"], consult, now) or changed

        changed = _derive_heat(state) or changed

        if changed:
            events.add(STATE_CHANGE)
            if hasattr(consult, "state_version"):
                consult.state_version += 1
        else:
            events.discard(ON_PRESCRIBE)
            events.discard(ON_DISPOSITION)
        return events


# ----------------------------------------------------------------------------- running case summary
CASE_LISTS = ("history", "working_diagnosis", "differential", "plan", "exam_claims", "patient_understanding",
              "patient_affect")
CASE_MAX_ITEMS = 12          # per list: the oldest items drop off a very long visit


def _case_key(text: Any) -> str:
    return " ".join(re.findall(r"\w+", str(text or "").lower()))


def _case_same(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b or (len(a) > 12 and (a in b or b in a)):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def merge_case(state: dict, case: dict, consult: Any = None, now: float | None = None) -> bool:
    """Merge a case delta into state["case"]. Free-text items dedupe on normalised text (near-identical wording
    merges its evidence); a history item whose present/absent flips is updated; a new chief complaint replaces the
    old one (the old one stays in history). Never raises on odd shapes. Returns True if anything changed."""
    from .state import empty_case
    cur = state.setdefault("case", empty_case())
    for k, v in empty_case().items():
        cur.setdefault(k, v)
    changed = False
    cc = case.get("chief_complaint") if isinstance(case, dict) else None
    if isinstance(cc, dict) and str(cc.get("text") or "").strip():
        ev = normalise_evidence(cc.get("evidence"), consult)
        old = cur.get("chief_complaint")
        if old and _case_same(_case_key(old.get("text")), _case_key(cc["text"])):
            changed = _merge_ev(old.setdefault("evidence", []), ev) or changed
        else:
            if old and old.get("text"):
                cur["history"].append({"text": f"earlier complaint: {old['text']}", "present": True,
                                       "evidence": list(old.get("evidence") or []), "t_min": old.get("t_min")})
            cur["chief_complaint"] = {"text": str(cc["text"]).strip(), "evidence": ev,
                                      "t_min": _earliest(ev) if _earliest(ev) is not None else now}
            changed = True
    for key in CASE_LISTS:
        for raw in (case.get(key) or []) if isinstance(case, dict) else []:
            if isinstance(raw, str):
                raw = {"text": raw}
            if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
                continue
            text = " ".join(str(raw["text"]).split())
            ev = normalise_evidence(raw.get("evidence"), consult)
            k = _case_key(text)
            old = next((x for x in cur[key] if _case_same(_case_key(x.get("text")), k)
                        and (key != "plan" or x.get("type") == raw.get("type"))), None)
            if old is not None:
                c = _merge_ev(old.setdefault("evidence", []), ev)
                if key == "history" and isinstance(raw.get("present"), bool) and old.get("present") != raw["present"]:
                    old["present"] = raw["present"]
                    c = True
                changed = changed or c
                continue
            item = {"text": text, "evidence": ev, "t_min": _earliest(ev) if _earliest(ev) is not None else now}
            if key == "history" and isinstance(raw.get("present"), bool):
                item["present"] = raw["present"]
            if key == "plan":
                item["type"] = str(raw.get("type") or "advice")
            cur[key].append(item)
            changed = True
        if len(cur[key]) > CASE_MAX_ITEMS:
            cur[key] = cur[key][-CASE_MAX_ITEMS:]
    return changed


# Symptoms that mean something more in a heat-exposed patient (the codes WORK-HEAT-01 tests for).
_HEAT_DERIVED = {"vomiting": "vomiting_in_heat", "syncope": "collapse"}


def _derive_heat(state: dict) -> bool:
    """Deterministic: in a heat-exposed patient (patient.heat_exposure true) vomiting is also vomiting_in_heat and a
    faint is also a collapse, with the same evidence. Returns True if a symptom was added."""
    if (state.get("patient") or {}).get("heat_exposure") is not True:
        return False
    syms = state.get("symptoms") or []
    have = {s.get("code") for s in syms}
    added = False
    for src, derived in _HEAT_DERIVED.items():
        base = next((s for s in syms if s.get("code") == src), None)
        if base is not None and derived not in have:
            syms.append({"code": derived, "severity": base.get("severity"), "onset": base.get("onset"),
                         "first_mention_min": base.get("first_mention_min"),
                         "evidence": [dict(e) for e in base.get("evidence") or []], "derived_from": src})
            have.add(derived)
            added = True
    return added


def _apply_remove(state: dict, coll: str, items: list, consult: Any) -> bool:
    changed = False
    if coll in ("prescribed_meds", "current_meds"):
        for it in items:
            drug = _drug_of(it)
            if not drug:
                continue
            ev = normalise_evidence(it.get("evidence"), consult) if isinstance(it, dict) else []
            before = len(state[coll])
            state[coll] = [m for m in state[coll] if m.get("drug") != drug]
            removed = len(state[coll]) != before
            existing = next((s for s in state["stopped_meds"] if s.get("drug") == drug), None)
            if existing is None and (removed or coll == "prescribed_meds"):
                state["stopped_meds"].append({"drug": drug, "evidence": ev})
                changed = True
            elif existing is not None:
                changed = _merge_ev(existing.setdefault("evidence", []), ev) or changed
            changed = changed or removed
    elif coll in ("symptoms", "investigations", "interventions", "assessments"):
        codes = {normalise_code(coll, it.get("code") if isinstance(it, dict) else it) for it in items}
        before = len(state[coll])
        state[coll] = [x for x in state[coll] if x.get("code") not in codes]
        changed = len(state[coll]) != before
    elif coll == "allergies":
        subs = {normalise_drug(it.get("substance") if isinstance(it, dict) else str(it)) for it in items}
        before = len(state[coll])
        state[coll] = [x for x in state[coll] if x.get("substance") not in subs]
        changed = len(state[coll]) != before
    elif coll == "idiom_hits":
        ids = {it.get("id") if isinstance(it, dict) else it for it in items}
        before = len(state[coll])
        state[coll] = [x for x in state[coll] if x.get("id") not in ids]
        changed = len(state[coll]) != before
    elif coll == "disposition":
        if (state.get("disposition") or {}).get("type") is not None:
            state["disposition"] = {"type": None, "evidence": []}
            changed = True
    return changed
