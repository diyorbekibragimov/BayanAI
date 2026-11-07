"""Bayan AI · controlled vocabularies and drug-name normalisation, derived from data/safety_rules.json.

The extractor's enums come from `codes()`, which harvests every code the rules test for, so the extractor
can never emit a code the rules do not know (or miss one they need). A small set of extra, rule-neutral
codes is added so ordinary findings (e.g. a sore throat) can still be recorded.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RULES_PATH = DATA_DIR / "safety_rules.json"
LEXICON_PATH = DATA_DIR / "idiom_lexicon.json"

# Collections whose items carry a `code` fact -> codes() key.
_CODE_COLLECTIONS = {
    "symptoms": "symptoms",
    "investigations": "investigations",
    "interventions": "interventions",
    "assessments": "assessments",
}

DISPOSITION_TYPES = ["discharge", "admit", "refer", "observe"]

# Rule-neutral codes the extractor may also emit (findings, tests and treatments no rule tests for).
EXTRA_CODES = {
    "symptoms": [
        "sore_throat", "cough", "fever", "headache", "nausea", "vomiting", "diarrhoea", "abdominal_pain",
        "back_pain", "shortness_of_breath", "sweating", "palpitations", "rash", "body_swelling", "weakness",
        "fatigue", "muscle_cramps", "dysuria", "heartburn", "epigastric_pain", "haematemesis", "melaena",
        "low_mood", "anxiety", "insomnia", "tingling", "joint_pain",
    ],
    "investigations": [
        "temp_tympanic", "temp_oral", "fbc", "crp", "blood_glucose", "urinalysis", "chest_xray", "lfts",
        "d_dimer", "ultrasound_abdomen",
    ],
    "interventions": ["iv_fluids", "oral_rehydration", "oxygen", "analgesia"],
    "assessments": ["pain_assessment", "airway_assessment"],
}

# Classes the rules reference that meta.drug_classes does not define, plus umbrella classes.
_SUPPLEMENTARY_CLASSES = {
    "nsaid": ["aspirin", "ibuprofen", "diclofenac", "naproxen", "ketorolac", "mefenamic acid", "indometacin",
              "ketoprofen", "piroxicam", "meloxicam"],
    "aspirin": ["aspirin"],
    "maoi": ["phenelzine", "tranylcypromine", "isocarboxazid", "selegiline", "moclobemide", "linezolid"],
    "triptan": ["sumatriptan", "rizatriptan", "zolmitriptan", "naratriptan", "eletriptan", "almotriptan"],
    "topiramate": ["topiramate"],
    "iv_fluid": ["sodium chloride 0.9%", "normal saline", "hartmann's solution", "ringer's lactate",
                 "dextrose 5%", "plasma-lyte"],
}

# Generic synonyms (US names, combination spellings, common brands beyond the file's examples).
_SYNONYMS = {
    "acetaminophen": "paracetamol", "apap": "paracetamol", "calpol": "paracetamol",
    "albuterol": "salbutamol", "epinephrine": "adrenaline", "epipen": "adrenaline",
    "amoxycillin": "amoxicillin", "amoxil": "amoxicillin",
    "amoxicillin-clavulanate": "co-amoxiclav", "amoxicillin/clavulanate": "co-amoxiclav",
    "amoxicillin clavulanate": "co-amoxiclav", "amoxicillin-clavulanic acid": "co-amoxiclav",
    "amoxicillin and clavulanate": "co-amoxiclav", "amoxicillin and clavulanic acid": "co-amoxiclav",
    "amoxiclav": "co-amoxiclav", "coamoxiclav": "co-amoxiclav", "co amoxiclav": "co-amoxiclav",
    "trimethoprim-sulfamethoxazole": "co-trimoxazole", "sulfamethoxazole-trimethoprim": "co-trimoxazole",
    "tmp-smx": "co-trimoxazole", "bactrim": "co-trimoxazole", "cotrimoxazole": "co-trimoxazole",
    "co trimoxazole": "co-trimoxazole",
    "piperacillin/tazobactam": "piperacillin-tazobactam", "pip-tazo": "piperacillin-tazobactam",
    "tazocin": "piperacillin-tazobactam", "zosyn": "piperacillin-tazobactam",
    "penicillin v": "phenoxymethylpenicillin", "penicillin g": "benzylpenicillin",
    "cefalexin": "cephalexin", "keflex": "cephalexin", "cefadroxyl": "cefadroxil",
    "gtn": "glyceryl trinitrate", "nitroglycerin": "glyceryl trinitrate", "nitroglycerine": "glyceryl trinitrate",
    "indomethacin": "indometacin", "advil": "ibuprofen", "motrin": "ibuprofen", "nurofen": "ibuprofen",
    "cataflam": "diclofenac", "aleve": "naproxen", "ponstan": "mefenamic acid",
    "sodium valproate": "valproate", "valproic acid": "valproate", "depakote": "divalproex",
    "frusemide": "furosemide", "lasix": "furosemide", "hctz": "hydrochlorothiazide",
    "salbutamol inhaler": "salbutamol", "nexium": "esomeprazole", "prilosec": "omeprazole",
    "potassium chloride": "potassium_chloride", "kcl": "potassium_chloride",
    "normal saline": "sodium chloride 0.9%", "0.9% saline": "sodium chloride 0.9%", "saline": "sodium chloride 0.9%",
    "sodium chloride": "sodium chloride 0.9%", "ns": "sodium chloride 0.9%",
    "ringer lactate": "ringer's lactate", "hartmann's": "hartmann's solution", "hartmanns": "hartmann's solution",
    "viagra": "sildenafil", "cialis": "tadalafil", "coumadin": "warfarin", "zantac": "ranitidine",
    "septra": "co-trimoxazole", "cipro": "ciprofloxacin", "ciproxin": "ciprofloxacin",
    # common brands in the Gulf / South Asia (the talk loop's translator is told to give generics, but a brand or a
    # mangled brand can still come through; see repair_drug_items)
    "augmentin": "co-amoxiclav", "augmentin duo": "co-amoxiclav", "clavulin": "co-amoxiclav",
    "co-amoxyclav": "co-amoxiclav", "brufen": "ibuprofen", "panadol": "paracetamol", "adol": "paracetamol",
    "tylenol": "paracetamol", "biogesic": "paracetamol", "crocin": "paracetamol", "dolo": "paracetamol",
    "fevadol": "paracetamol", "voltaren": "diclofenac", "voltarol": "diclofenac", "septrin": "co-trimoxazole",
    "zithromax": "azithromycin", "azithral": "azithromycin", "ventolin": "salbutamol", "klacid": "clarithromycin",
    "rocephin": "ceftriaxone", "zinnat": "cefuroxime", "flagyl": "metronidazole", "tramal": "tramadol",
    "ultram": "tramadol", "naprosyn": "naproxen", "glucophage": "metformin", "norvasc": "amlodipine",
    "losec": "omeprazole", "zofran": "ondansetron", "plavix": "clopidogrel", "lipitor": "atorvastatin",
    "zocor": "simvastatin", "tegretol": "carbamazepine", "eltroxin": "levothyroxine", "synthroid": "levothyroxine",
    "ponstan forte": "mefenamic acid", "arcoxia": "etoricoxib", "celebrex": "celecoxib", "aspro": "aspirin",
    "disprin": "aspirin",
}

# Allergy wording -> class or INN.
_ALLERGY_TERMS = {
    "sulfa": "sulfonamide_antibiotic", "sulpha": "sulfonamide_antibiotic", "sulfa drugs": "sulfonamide_antibiotic",
    "sulpha drugs": "sulfonamide_antibiotic", "sulfonamide": "sulfonamide_antibiotic",
    "sulphonamide": "sulfonamide_antibiotic", "sulfonamide antibiotic": "sulfonamide_antibiotic",
    "pcn": "penicillin", "penicilin": "penicillin", "penicillin injection": "penicillin",
    "anti-inflammatory": "nsaid", "anti-inflammatories": "nsaid", "nsaids": "nsaid", "painkiller nsaid": "nsaid",
    "cephalosporins": "cephalosporin",
}

_SALTS = {
    "hydrochloride", "hcl", "sodium", "potassium", "trihydrate", "dihydrate", "monohydrate", "besylate",
    "besilate", "maleate", "tartrate", "succinate", "calcium", "magnesium", "citrate", "phosphate", "sulfate",
    "sulphate", "hyclate", "acetate", "fumarate", "mesylate", "mesilate", "hydrobromide", "bitartrate",
}
_FORMS = {
    "tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "caps", "syrup", "suspension", "injection",
    "inj", "cream", "ointment", "gel", "drops", "inhaler", "puffer", "oral", "iv", "im", "po", "sr", "er", "xr",
    "mr", "ir", "dispersible", "effervescent", "solution", "infusion", "vial", "ampoule", "sachet", "medicine",
    "mg", "g", "mcg", "ug", "ml", "gram", "grams", "milligram", "milligrams", "microgram", "micrograms",
}


@lru_cache(maxsize=1)
def _rules_data() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _lexicon_tags() -> list[str]:
    try:
        with open(LEXICON_PATH, encoding="utf-8") as f:
            lex = json.load(f)
    except OSError:
        return []
    return sorted({t for e in lex.get("entries", []) for t in e.get("red_flag_tags", [])})


@lru_cache(maxsize=1)
def _brand_map() -> dict[str, str]:
    raw = _rules_data()["meta"].get("brand_aliases_examples", {})
    out = {k.lower(): v.lower() for k, v in raw.items() if not k.startswith("_")}
    out.update(_SYNONYMS)
    return out


@lru_cache(maxsize=1)
def drug_classes() -> dict[str, list[str]]:
    """meta.drug_classes plus the supplementary classes the rules reference (all lowercase)."""
    classes = {k: [d.lower() for d in v] for k, v in _rules_data()["meta"].get("drug_classes", {}).items()}
    for k, v in _SUPPLEMENTARY_CLASSES.items():
        classes.setdefault(k, [])
        classes[k] = classes[k] + [d for d in v if d not in classes[k]]
    return classes


@lru_cache(maxsize=1)
def _class_keys() -> dict[str, str]:
    """lowercase class name -> class key exactly as spelled in the rules (e.g. ..._like_R1)."""
    return {k.lower(): k for k in drug_classes()}


def _clean(name: str) -> str:
    s = str(name or "").strip().lower()
    s = s.replace("’", "'").replace("_", " ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:/\s*\d+(?:[.,]\d+)?)?\s*(?:mg|g|mcg|µg|ug|ml|%)?\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .,-")
    return s


def normalise_drug(name: str) -> str:
    """Brand or synonym -> INN (lowercase), with salts, dosage forms and strengths stripped."""
    if not name:
        return ""
    return _normalise_drug(str(name))


@lru_cache(maxsize=4096)
def _normalise_drug(name: str) -> str:
    raw = str(name).strip().lower().replace("_", " ")
    brands = _brand_map()
    if raw in brands:
        return brands[raw]
    if raw in _known_drugs():
        return raw
    s = _clean(name)
    if s in brands:
        return brands[s]
    keys = _class_keys()
    for cand in (s, s.replace(" ", "_"), _singular(s), _singular(s).replace(" ", "_")):
        if cand in keys:
            return keys[cand]
    words = [w for w in s.split(" ") if w and w not in _FORMS]
    s2 = " ".join(words)
    if s2 in brands:
        return brands[s2]
    if s2 in _known_drugs():
        return s2
    stripped = " ".join(w for w in words if w not in _SALTS) or s2
    if stripped in brands:
        return brands[stripped]
    if stripped in _known_drugs():
        return stripped
    # first word is a brand ("augmentin duo", "panadol extra")
    if words and words[0] in brands:
        return brands[words[0]]
    return stripped


@lru_cache(maxsize=1)
def _known_drugs() -> set[str]:
    known = {d for v in drug_classes().values() for d in v}
    known |= set(_brand_map().values())
    for r in _rules_data()["rules"]:
        for node in _walk(r.get("trigger")):
            if node.get("fact") == "drug" and isinstance(node.get("value"), (list, str)):
                vals = node["value"] if isinstance(node["value"], list) else [node["value"]]
                known |= {str(v).lower() for v in vals}
    return known


def _singular(s: str) -> str:
    if s.endswith("ies"):
        return s[:-3] + "y"
    if s.endswith("s") and not s.endswith("ss") and len(s) > 4:
        return s[:-1]
    return s


def is_known_drug(name: str) -> bool:
    """True when the name (brand, synonym or INN) normalises to a drug or class the rules know."""
    n = normalise_drug(name)
    return bool(n) and (n in _known_drugs() or n.lower() in _class_keys())


@lru_cache(maxsize=1)
def _name_index() -> dict[str, str]:
    """Every spelling the rules know (INNs, synonyms, brands; lowercase) -> generic."""
    idx = {d: d for d in _known_drugs()}
    idx.update(_brand_map())
    return idx


_TOKEN_RE = re.compile(r"[a-z][a-z'\-]*[a-z]|[a-z]")
FUZZY_CUTOFF = 88


def fuzzy_drug(name: str, cutoff: float = FUZZY_CUTOFF) -> str:
    """A misspelt INN or brand ("amoxicilin", "augmentine") -> generic, or "" when nothing is close enough.
    Short names (< 6 letters) are never fuzzy-matched (too many near neighbours)."""
    s = _clean(name)
    if len(s) < 6:
        return ""
    try:
        from rapidfuzz import fuzz, process
    except Exception:  # noqa: BLE001 - rapidfuzz missing: exact matching only
        return ""
    best = process.extractOne(s, list(_name_index()), scorer=fuzz.ratio, score_cutoff=cutoff)
    return _name_index()[best[0]] if best else ""


def drugs_in_text(text: str) -> list[str]:
    """Generics whose INN, synonym or brand appears as a whole word (or two-word phrase) in the text, in order of
    appearance. Exact matching only: free text is full of words one letter away from a drug name."""
    toks = _TOKEN_RE.findall(str(text or "").lower().replace("’", "'"))
    idx, out = _name_index(), []
    i = 0
    while i < len(toks):
        two = f"{toks[i]} {toks[i + 1]}" if i + 1 < len(toks) else ""
        if two and two in idx:
            g, i = idx[two], i + 2
        elif toks[i] in idx and toks[i] not in _FORMS:
            g, i = idx[toks[i]], i + 1
        else:
            i += 1
            continue
        if g not in out:
            out.append(g)
    return out


def clause_for(drug: str, text: str) -> str:
    """The part of `text` about one drug: from its first mention (INN, synonym or brand) up to the next drug
    mention or the end of the sentence. "" when the drug is not named in the text."""
    low = str(text or "").lower().replace("’", "'")
    g = normalise_drug(drug)
    if not low or not g:
        return ""
    spans = []
    for name, gen in _name_index().items():
        for m in re.finditer(rf"(?<![a-z]){re.escape(name)}(?![a-z])", low):
            spans.append((m.start(), m.end(), gen))
    mine = sorted(sp for sp in spans if sp[2] == g)
    if not mine:
        return ""
    start, end0 = mine[0][0], mine[0][1]
    stops = [sp[0] for sp in spans if sp[0] >= end0 and sp[2] != g]
    m = re.search(r"[.;!?](\s|$)", low[end0:])
    if m:
        stops.append(end0 + m.start())
    return str(text)[start:min(stops) if stops else len(low)]


def _said(name: str, texts: list[str]) -> bool:
    n = str(name or "").strip().lower()
    return bool(n) and any(re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", t.lower()) for t in texts if t)


def repair_drug_items(drugs: list[dict], texts: list[str] | tuple = ()) -> list[dict]:
    """Deterministic safety net for the translator's drug names (mutates and returns the list).

    The LLM sometimes "normalises" a brand into an ordinary word ("Augmentin 625" -> name "augmented"), and an
    unknown name silently passes the prescription gate. For each item whose name the rules do not know:
      1. fuzzy match against every known INN / brand (misspellings), unless the speaker literally said that name
         (a real drug the rules do not list, e.g. nitrofurantoin, is left alone);
      2. else, when the name is not in what was said, take the known drug / brand that IS in the speaker's words
         (`texts`: original utterance and its English rendering) and that no other item accounts for.
    A repaired item keeps the model's name in "name_llm". Known names are left as they are."""
    texts = [str(t) for t in texts or [] if t]
    items = [d for d in drugs or [] if isinstance(d, dict) and str(d.get("name") or d.get("drug") or "").strip()]
    key = lambda d: "name" if d.get("name") else "drug"  # noqa: E731
    claimed = {normalise_drug(d[key(d)]) for d in items if is_known_drug(d[key(d)])}
    unresolved = []
    for d in items:
        name = str(d[key(d)]).strip()
        if is_known_drug(name) or (texts and _said(name, texts)):
            continue
        g = fuzzy_drug(name)
        if g:
            d["name_llm"], d[key(d)] = name, g
            claimed.add(g)
        else:
            unresolved.append(d)
    if unresolved and texts:
        spare = [g for g in drugs_in_text(" \n ".join(texts)) if g not in claimed]
        if len(spare) == len(unresolved):       # one-to-one, in order of appearance
            for d, g in zip(unresolved, spare):
                d["name_llm"], d[key(d)] = str(d[key(d)]).strip(), g
    return drugs


def literal_gloss(literal_en: str) -> str:
    """Short plain gloss of an idiom's literal_en for alert text: the quoted word when there is one, else the text
    without brackets, up to any semicolon. "'gastric' (English loanword)" -> "gastric"; "heat (in the body)" -> "heat"."""
    lit = str(literal_en or "").strip()
    m = re.search(r"[‘'“\"]([^’'”\"]+)[’'”\"]", lit)
    if m and lit.startswith(m.group(0)[0]):
        return m.group(1).strip()
    short = re.sub(r"\s*\([^)]*\)", "", lit)
    return re.split(r"\s*;", short, 1)[0].strip(" ,.") or lit


def classes_of(drug_or_class: str) -> list[str]:
    """Classes for a drug (via meta.drug_classes); a class name (singular or plural) maps to itself."""
    if not drug_or_class:
        return []
    return list(_classes_of(str(drug_or_class)))


@lru_cache(maxsize=4096)
def _classes_of(drug_or_class: str) -> tuple[str, ...]:
    keys = _class_keys()
    s = str(drug_or_class).strip().lower()
    s = re.sub(r"\s*(allergy|allergic|hypersensitivity)\s*$", "", s).strip()
    for cand in (s, s.replace(" ", "_"), _singular(s), _singular(s).replace(" ", "_")):
        cand = _ALLERGY_TERMS.get(cand, cand).lower()
        if cand in keys:
            key = keys[cand]
            return tuple([key] + [c for c in _classes_containing(cand) if c != key])
    drug = normalise_drug(s)
    if drug.lower() in keys:
        key = keys[drug.lower()]
        return tuple([key] + [c for c in _classes_containing(drug.lower()) if c != key])
    return tuple(_classes_containing(drug))


def _classes_containing(drug: str) -> list[str]:
    return [c for c, members in drug_classes().items() if drug in members]


def _walk(node):
    """Yield every dict node of a trigger tree (including nodes inside `where`)."""
    if isinstance(node, dict):
        yield node
        for k in ("all", "any", "none"):
            for ch in node.get(k, []) or []:
                yield from _walk(ch)
        if "where" in node:
            yield from _walk(node["where"])
    elif isinstance(node, list):
        for ch in node:
            yield from _walk(ch)


def _collect(node, coll: str | None, out: dict[str, set]) -> None:
    if isinstance(node, list):
        for ch in node:
            _collect(ch, coll, out)
        return
    if not isinstance(node, dict):
        return
    q = node.get("exists_in") or node.get("none_in")
    if q:
        _collect(node.get("where"), q, out)
    for k in ("all", "any", "none"):
        if k in node:
            _collect(node[k], coll, out)
    fact = node.get("fact")
    if fact is None:
        return
    vals = node.get("value")
    vals = vals if isinstance(vals, list) else [vals]
    vals = [v for v in vals if isinstance(v, str)]
    if fact == "code" and coll in _CODE_COLLECTIONS:
        out[_CODE_COLLECTIONS[coll]].update(vals)
    elif fact == "disposition.type":
        out["disposition"].update(vals)
    elif fact == "red_flag_tags":
        out["idiom_tags"].update(vals)


@lru_cache(maxsize=1)
def _codes_cached() -> dict[str, tuple[str, ...]]:
    out: dict[str, set] = {k: set() for k in ("symptoms", "investigations", "interventions", "assessments",
                                              "disposition", "idiom_tags")}
    for r in _rules_data()["rules"]:
        _collect(r.get("trigger"), None, out)
        _collect(r.get("escalate_to_critical_if"), None, out)
    rule_codes = {k: set(v) for k, v in out.items()}
    for k, extra in EXTRA_CODES.items():
        out[k].update(extra)
    out["disposition"].update(DISPOSITION_TYPES)
    out["idiom_tags"].update(_lexicon_tags())
    result = {k: tuple(sorted(v)) for k, v in out.items()}
    result["_rule_codes"] = tuple(sorted(f"{k}:{c}" for k, v in rule_codes.items() for c in v))
    return result


def codes() -> dict[str, list[str]]:
    """{"symptoms","investigations","interventions","assessments","disposition","idiom_tags"} -> sorted codes.
    Every code tested by any rule is included (harvested from triggers and escalations), plus EXTRA_CODES."""
    c = _codes_cached()
    return {k: list(v) for k, v in c.items() if not k.startswith("_")}


def rule_codes() -> dict[str, list[str]]:
    """Only the codes the rules themselves test for (no extras)."""
    out: dict[str, list[str]] = {}
    for item in _codes_cached()["_rule_codes"]:
        k, c = item.split(":", 1)
        out.setdefault(k, []).append(c)
    return out


# Code aliases the validator folds into the rule vocabulary.
CODE_ALIASES = {
    "investigations": {
        "ecg": "ecg_12lead", "12_lead_ecg": "ecg_12lead", "ekg": "ecg_12lead", "ecg12": "ecg_12lead",
        "heart_tracing": "ecg_12lead", "12lead_ecg": "ecg_12lead",
        "hs_troponin": "troponin_hs", "high_sensitivity_troponin": "troponin_hs", "hstroponin": "troponin_hs",
        "troponin_i": "troponin", "troponin_t": "troponin", "trop": "troponin",
        "rectal_temperature": "temp_rectal", "core_temperature": "temp_core",
        "u_and_e": "urea_creatinine", "ue": "urea_creatinine", "u&e": "urea_creatinine", "renal_function": "urea_creatinine",
        "creatine_kinase": "ck", "cpk": "ck", "beta_hcg": "pregnancy_test", "hcg": "pregnancy_test",
        "urine_pregnancy_test": "pregnancy_test", "upt": "pregnancy_test", "ct_brain": "ct_head",
        "malaria_test": "malaria_rdt", "blood_cultures": "blood_culture",
    },
    "interventions": {"cooling": "active_cooling", "ice_bath": "cold_water_immersion"},
    "assessments": {"risk_assessment": "suicide_risk_assessment"},
    "symptoms": {"chest_burn": "chest_burning", "burning_chest": "chest_burning", "dizzy": "dizziness",
                 "faint": "syncope", "fainting": "syncope", "fainted": "syncope", "passed_out": "syncope",
                 "collapsed": "collapse", "disorientation": "confusion", "disoriented": "confusion",
                 "confused": "confusion", "acute_confusion": "confusion"},
}


def normalise_code(collection: str, code: str) -> str:
    c = re.sub(r"[\s\-]+", "_", str(code or "").strip().lower())
    return CODE_ALIASES.get(collection, {}).get(c, c)
