"""Wrap-up + outputs (agent C): SOAP note, care plan, PDFs, links, audio, retention. Offline: fake LLM backend.

Runs against the real RuleEngine / CardStore / agentkit when those modules import, else against small stubs
(see ENGINE_MODE / CARDS_MODE printed by test_report_modes).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bayan.brain import llm, wrapup  # noqa: E402
from bayan.brain.state import Consultation  # noqa: E402
from bayan.outputs import delivery, retention  # noqa: E402

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


# ====================================================================== golden path (docs/02 §8, after step 6)
def ev(utt, t, quote):
    return {"utt": utt, "t_min": t, "quote": quote}


TURNS = [
    ("bayan", "ne", "नमस्ते। म बयान हुँ, कम्प्युटर दोभाषे। म डाक्टर र तपाईंको कुरा अनुवाद गर्छु। के तपाईं सहमत हुनुहुन्छ?",
     "Hello. I am Bayan, a computer interpreter. I will translate between you and the doctor. Do you agree? (consent)",
     0.0, False),
    ("patient", "ne", "हो, म सहमत छु।", "Yes, I agree.", 0.2, False),
    ("doctor", "en", "Hello, I'm Dr Sara. What brings you in today?", "", 1.0, False),
    ("patient", "ne", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ। खाना खाएपछि सुरु भयो, अनि रिँगटा लागेको छ।",
     "My chest is burning, like gyastrik (gastric). It started after lunch, and I feel dizzy.", 1.2, False),
    ("doctor", "en", "Do you work outdoors? Are you allergic to any medicine?", "", 2.0, False),
    ("patient", "ne", "हो, म बाहिर साइटमा काम गर्छु। एक पटक पेनिसिलिनको सुई लगाउँदा मेरो जिउ सुन्निएको थियो। अनि तीन "
                      "दिनदेखि घाँटी दुखेको छ।",
     "Yes, I work outside on a site. Once, after a penicillin injection, my body swelled up. And my throat has hurt "
     "for three days.", 2.2, False),
    ("doctor", "en", "It's probably just gastric, and a throat infection. I'll give you amoxicillin 500 mg three times "
                     "a day for your throat, and you can go home.", "", 12.0, True),
    ("doctor", "en", "Actually, no amoxicillin. Your throat looks viral. Before you go, we'll check your blood pressure, "
                     "do a heart tracing, and a blood test for the heart called troponin.", "", 13.0, False),
    ("doctor", "en", "Your blood pressure is 128 over 82, your heart tracing is normal, and the troponin test is normal.",
     "", 75.0, False),
    ("doctor", "en", "Take paracetamol, one gram, up to three times a day, for your throat. Drink plenty of water and "
                     "rest out of the sun for two days. If the chest pain comes back, spreads to your arm or jaw, you "
                     "feel faint or sweaty, or you vomit blood or pass black stools, call 999 or come straight back.",
     "", 75.5, False),
    ("patient", "ne", "हुन्छ, धन्यवाद डाक्टर।", "Okay, thank you, doctor.", 76.0, False),
]

E_ALLERGY = ev("u006", 2.2, "after a penicillin injection, my body swelled up")
E_CHEST = ev("u004", 1.2, "My chest is burning, like gyastrik")
E_AMOX = ev("u007", 12.0, "I'll give you amoxicillin 500 mg three times a day")
E_STOP = ev("u008", 13.0, "Actually, no amoxicillin.")
E_RESULTS = ev("u009", 75.0, "Your blood pressure is 128 over 82, your heart tracing is normal, and the troponin test "
                             "is normal.")
E_PARA = ev("u010", 75.5, "Take paracetamol, one gram, up to three times a day, for your throat.")


def golden_state() -> dict:
    from bayan.brain.state import empty_state

    st = empty_state()
    st["allergies"] = [{"substance": "penicillin", "class": ["penicillin"], "reaction": "body swelling",
                        "severity": "severe", "evidence": [E_ALLERGY], "confidence": 0.9}]
    st["prescribed_meds"] = [{"drug": "paracetamol", "class": [], "dose_mg": 1000, "frequency_per_day": 3,
                              "daily_dose_mg": 3000, "route": "oral", "duration_days": None,
                              "indication": "sore throat", "evidence": [E_PARA]}]
    st["stopped_meds"] = [{"drug": "amoxicillin", "evidence": [E_STOP]}]
    st["symptoms"] = [
        {"code": "chest_burning", "severity": None, "onset": "after lunch", "first_mention_min": 1.2, "evidence": [E_CHEST]},
        {"code": "dizziness", "severity": None, "onset": None, "first_mention_min": 1.2,
         "evidence": [ev("u004", 1.2, "I feel dizzy")]},
        {"code": "sore_throat", "severity": None, "onset": "3 days", "first_mention_min": 2.2,
         "evidence": [ev("u006", 2.2, "my throat has hurt for three days")]},
    ]
    st["vitals"] = {"bp_sys": 128, "bp_dia": 82}
    st["investigations"] = [
        {"code": "ecg_12lead", "status": "resulted", "result": "normal", "evidence": [E_STOP, E_RESULTS]},
        {"code": "troponin", "status": "resulted", "result": "normal", "evidence": [E_STOP, E_RESULTS]},
    ]
    st["assessments"] = [{"code": "viral_pharyngitis", "evidence": [ev("u008", 13.0, "Your throat looks viral.")]}]
    st["disposition"] = {"type": "discharge", "evidence": [E_PARA]}
    st["patient"]["heat_exposure"] = True
    st["patient"]["heat_illness_suspected"] = False
    st["idiom_hits"] = [{"id": "npi-005", "red_flag_tags": ["acs", "gi_bleed"], "utt": "u004", "t_min": 1.2,
                         "matched": "ग्यास्ट्रिक"}]
    st["questions_asked"] = ["allergies", "occupation"]
    return st


def _fired(rule_id, sev, msg, evidence, family, key=None):
    return {"rule_id": rule_id, "family": family, "severity": sev, "message": msg, "rationale": "",
            "source_urls": [], "fire_on": "on_prescribe" if family == "drug_allergy" else "state_change",
            "verification": "label_or_guideline_checked", "evidence": evidence,
            "group": "chest_pain_workup" if rule_id.startswith("WORK-CHEST") else None, "key": key or rule_id}


class FakeCards:
    """Minimal CardStore stand-in (used only if bayan.brain.cards does not import)."""

    def __init__(self, consult):
        self.audit = consult.audit
        self.cards = [
            {"id": "c001", "kind": "idiom", "severity": "info", "title": "“gyastrik” can mask cardiac pain",
             "body": "Lexicon npi-005: usually dyspepsia; can mask ACS.", "evidence": [E_CHEST], "grounding": "npi-005",
             "items": [], "status": "open", "source": "lexicon", "t_min": 1.2, "actions": []},
            {"id": "c002", "kind": "missed", "severity": "critical", "title": "Chest-pain workup",
             "body": "No ECG / troponin before discharge.", "evidence": [E_CHEST, E_AMOX],
             "grounding": "chest_pain_workup", "items": [{"rule_id": r} for r in
                                                         ("WORK-CHEST-02", "WORK-CHEST-03", "WORK-CHEST-01",
                                                          "WORK-CHEST-04")],
             "status": "resolved", "source": "rules", "t_min": 1.2,
             "actions": [{"action": "acknowledge", "reason": "ordering ECG and troponin", "user": "doctor",
                          "t_min": 12.6}]},
            {"id": "c003", "kind": "safety", "severity": "critical", "title": "Allergy conflict · ALG-PEN-01",
             "body": "Penicillin allergy reported. Amoxicillin is a penicillin.", "evidence": [E_ALLERGY, E_AMOX],
             "grounding": "ALG-PEN-01", "items": [{"rule_id": "ALG-PEN-01", "key": "ALG-PEN-01|amoxicillin"}],
             "status": "resolved", "source": "rules", "t_min": 12.0,
             "actions": [{"action": "acknowledge", "reason": "amoxicillin withdrawn", "user": "doctor", "t_min": 12.6}]},
        ]

    def all_cards(self):
        return [dict(c) for c in self.cards]


def attach_cards(c: Consultation) -> str:
    try:
        from bayan.brain.cards import CardStore
    except Exception:  # noqa: BLE001
        c.cards = FakeCards(c)
        return "stub"
    store = CardStore(turn_lookup=c.turn_by_id, clock=c.now_min, state_version=lambda: c.state_version,
                      log=c.log, audit=c.audit)
    c.cards = store
    w4 = _fired("WORK-CHEST-04", "caution", "Idiom tagged ACS (gyastrik) and no ECG yet.", [E_CHEST], "missing_workup")
    w1 = _fired("WORK-CHEST-01", "caution", "No 12-lead ECG 10 min after chest pain was first mentioned.", [E_CHEST],
                "missing_workup")
    w2 = _fired("WORK-CHEST-02", "critical", "Discharge planned with no ECG.", [E_AMOX], "missing_workup")
    w3 = _fired("WORK-CHEST-03", "critical", "Discharge planned with no troponin.", [E_AMOX], "missing_workup")
    alg = _fired("ALG-PEN-01", "critical", "Penicillin allergy reported (“…my body swelled up”, 02:12). Amoxicillin "
                                           "is a penicillin.", [E_ALLERGY, E_AMOX], "drug_allergy",
                 key="ALG-PEN-01|amoxicillin")
    c.set_scenario_time(1.2)
    store.post("idiom", "“gyastrik” (ग्यास्ट्रिक) can mask cardiac pain",
               "Lexicon npi-005: usually dyspepsia or reflux; can mask cardiac ischaemia. Not a diagnosis.",
               [E_CHEST], "npi-005", severity="info", source="lexicon", t_min=1.2)
    store.sync_rules([w4], 1.2)
    c.set_scenario_time(11.2)
    store.sync_rules([w4, w1], 11.2)
    c.set_scenario_time(12.0)
    store.sync_rules([w4, w1, w2, w3, alg], 12.0)
    c.set_scenario_time(12.6)
    for card in store.open_cards():
        if card["source"] == "rules":
            reason = "amoxicillin withdrawn" if "ALG" in card["title"] else "ordering ECG and troponin"
            store.act(card["id"], "acknowledge", reason)
    c.set_scenario_time(13.0)
    store.sync_rules([], 13.0)
    return "real"


def golden_consult(lang: str = "ne", cards: bool = True) -> Consultation:
    c = Consultation(patient_lang=lang)
    c.started_at = time.mktime((2026, 8, 14, 21, 0, 0, 0, 0, -1))
    for role, lg, text, en, t, held in TURNS:
        c.add_turn(role, lg, text, english=en, held=held, t_min=t)
    c.state = golden_state()
    if cards:
        attach_cards(c)
    c.set_scenario_time(76.5)
    return c


PRN_EN = "Take 1 g only when needed for sore throat. No more than 3 times a day."
NE_PLAN = {
    # what the fake "translator" returns for each English line it is asked to translate
    "tr": {"Paracetamol": "प्यारासिटामोल",
           "Paracetamol 1 g": "प्यारासिटामोल 1 g",
           PRN_EN: "घाँटी दुखेको बेला मात्र 1 g खानुहोस्। दिनमा 3 पटकभन्दा बढी नखानुहोस्।",
           "Penicillin medicines, for example amoxicillin. You are allergic.":
               "पेनिसिलिन औषधि, जस्तै एमोक्सिसिलिन। तपाईंलाई यसको एलर्जी छ।"},
    "red_flags": [
        {"en": "Your chest pain comes back.", "native": "छातीको दुखाइ फेरि आयो भने।"},
        {"en": "The pain spreads to your arm or jaw.", "native": "दुखाइ पाखुरा वा बङ्गारासम्म फैलियो भने।"},
        {"en": "You feel faint or sweaty.", "native": "तपाईंलाई रिँगटा लाग्यो वा पसिना आयो भने।"},
        {"en": "You vomit blood or pass black stools.", "native": "रगत बान्ता भयो वा कालो दिसा भयो भने।"},
    ],
    "advice": [{"en": "Drink plenty of water.", "native": "प्रशस्त पानी पिउनुहोस्।"},
               {"en": "Rest out of the sun for 2 days.", "native": "2 दिन घाममा नबसी आराम गर्नुहोस्।"}],
    "follow_up": {"en": "", "native": ""},
}


NOTE_JSON = {
    "presenting_complaint": [{"text": "Chest burning (\u201cgyastrik\u201d) since lunch, with dizziness",
                              "utts": ["u004"]}],
    "history": [{"text": "Burning chest discomfort, onset after lunch; dizziness", "utts": ["u004"]},
                {"text": "Sore throat for 3 days", "utts": ["u006"]},
                {"text": "Works outdoors on a building site (heat exposure)", "utts": ["u006"]}],
    "examination": [],
    "assessment": [{"text": "Throat looks viral", "utts": ["u008"]},
                   {"text": "Initial impression 'probably just gastric, and a throat infection' — revised",
                    "utts": ["u007"]}],
    "plan": [{"text": "No amoxicillin", "utts": ["u008"]},
             {"text": "Blood pressure, 12-lead ECG and troponin before discharge", "utts": ["u008"]},
             {"text": "Discharge home", "utts": ["u010"]}],
    "information_given": [
        {"text": "Drink plenty of water; rest out of the sun for 2 days", "utts": ["u010"]},
        {"text": "Call 999 or return if chest pain recurs or spreads to the arm or jaw, faintness or sweating, "
                 "vomiting blood or black stools", "utts": ["u010"]}],
}


def kind_of(messages) -> str:
    system = messages[0]["content"]
    if system.startswith(("SOAP NOTE WRITER", "CLINIC NOTE WRITER")):
        return "note"
    if system.startswith("CHUNK SUMMARISER"):
        return "map"
    return "plan"


def make_backend(reply: dict | None = None, calls: list | None = None, raise_exc: bool = False,
                 note=None, note_replies: list | None = None):
    """Routes by system prompt: note -> NOTE_JSON (or the next of note_replies: dict, raw str, or Exception),
    chunk summariser -> one fact citing the chunk's first utterance, care plan -> NE_PLAN (or `reply`)."""
    lock = __import__("threading").Lock()

    def fn(messages, schema, max_tokens):
        kind = kind_of(messages)
        with lock:
            if calls is not None:
                calls.append({"kind": kind, "messages": messages, "schema": schema, "max_tokens": max_tokens})
        if raise_exc:
            raise RuntimeError("provider down")
        if kind == "map":
            first = messages[1]["content"].split(" ", 1)[0]
            return json.dumps({"facts": [{"kind": "other", "text": f"chunk starting {first}", "utts": [first]}]})
        if kind == "note":
            if note_replies:
                with lock:
                    r = note_replies.pop(0)
                if isinstance(r, Exception):
                    raise r
                return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
            return json.dumps(note if note is not None else NOTE_JSON, ensure_ascii=False)
        plan = reply if reply is not None else NE_PLAN
        asked = json.loads(messages[1]["content"]).get("translate", {})
        tr = plan.get("tr", {})
        return json.dumps({"translations": [{"key": k, "native": tr.get(en, "")} for k, en in asked.items()],
                           **{k: plan[k] for k in ("red_flags", "advice", "follow_up") if k in plan}},
                          ensure_ascii=False)
    return fn


def fake_speak(text, lang):
    sr = 16000
    n = max(160, int(sr * 0.02 * min(len(text), 50)))
    return sr, (0.1 * np.sin(np.linspace(0, 200 * np.pi, n))).astype(np.float32)


# ====================================================================== stubs for teammates' modules
class StubEngine:
    """ALG-PEN-01 + DOSE-PARA-01 only, with the contract's fired-rule shape (used if bayan.brain.rules is missing)."""

    def check_prescription(self, state, candidate_meds, now_min):
        meds = list(state.get("prescribed_meds", [])) + list(candidate_meds)
        out = []
        pen_allergy = any("penicillin" in (a.get("class") or []) for a in state.get("allergies", []))
        for m in meds:
            cls = set(m.get("class") or [])
            if pen_allergy and ("penicillin" in cls or m.get("drug") == "amoxicillin"):
                out.append({"rule_id": "ALG-PEN-01", "severity": "critical", "key": f"ALG-PEN-01|{m['drug']}",
                            "message": f"Penicillin allergy reported. {m['drug']} is a penicillin."})
            if m.get("drug") == "paracetamol" and ((m.get("dose_mg") or 0) > 1000 or (m.get("daily_dose_mg") or 0) > 4000):
                out.append({"rule_id": "DOSE-PARA-01", "severity": "critical", "key": "DOSE-PARA-01|paracetamol",
                            "message": "Paracetamol exceeds 1 g per dose or 4 g/day."})
        return out


def _engine_mode() -> str:
    try:
        from bayan.brain.rules import RuleEngine  # noqa: F401
        return "real"
    except Exception:  # noqa: BLE001
        return "stub"


ENGINE_MODE = _engine_mode()


@pytest.fixture
def tmp_path():
    """Own temp dir (pytest's default basetemp under %TEMP%/pytest-of-<user> is not accessible on some Windows
    setups); removed after the test."""
    import shutil
    import tempfile

    d = Path(tempfile.mkdtemp(prefix="bayan_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYAN_OUTPUT_ROOT", str(tmp_path / "out"))
    wrapup._ENGINE = None if ENGINE_MODE == "real" else StubEngine()
    llm.set_backend(make_backend())
    yield
    llm.set_backend(None)
    wrapup._ENGINE = None


# ====================================================================== tests
def _pdf_text(path) -> str:
    import pymupdf

    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def test_report_modes():
    print(f"ENGINE_MODE={ENGINE_MODE}")
    try:
        import bayan.brain.cards  # noqa: F401
        print("CARDS_MODE=real")
    except Exception:  # noqa: BLE001
        print("CARDS_MODE=stub")


def test_golden_path_deterministic():
    c = golden_consult()
    calls: list = []
    llm.set_backend(make_backend(calls=calls))
    out = run = wrapup.run_wrapup(c, agentic=False, speak_fn=fake_speak, link_base="https://bayan.example/f",
                                  phone="+974 5555 1234")
    assert run is c.outputs or c.outputs["patient_pdf"] == out["patient_pdf"]
    assert sorted(c["kind"] for c in calls) == ["note", "plan"]  # two LLM calls (note + care plan), each schema'd
    assert all(c["schema"] is not None for c in calls)
    for k in ("doctor_pdf", "patient_pdf", "audio_wav"):
        assert out[k] and Path(out[k]).exists(), k
    root = Path(os.environ["BAYAN_OUTPUT_ROOT"]).resolve()
    assert Path(out["patient_pdf"]).resolve().parent == root / c.id
    plan = out["care_plan"]
    names = [m["drug"] for m in plan["medicines"]]
    assert names == ["paracetamol"]
    assert "amoxicillin" not in names
    para = plan["medicines"][0]
    # "up to three times a day" -> as needed: NOT on the timed grid (AHRQ pill card / UMS), listed separately
    assert para["prn"] and para["schedule"] == "prn" and para["times"] == [] and para["dose_text"] == "1 g"
    assert any("penicillin" in a["en"].lower() for a in plan["avoid"])
    assert plan["emergency"] == "999" and plan["red_flags"]
    assert not any("EXCLUDED" in w for w in out["warnings"])

    import pymupdf

    with pymupdf.open(out["patient_pdf"]) as doc:
        assert doc.page_count == 1  # golden path fits one A4 page
        ptxt = doc[0].get_text()
    assert "999" in ptxt and DEVANAGARI.search(ptxt)
    assert "Paracetamol 1 g" in ptxt and PRN_EN in ptxt and "Your medicines" in ptxt and "Penicillin medicines" in ptxt
    assert "Only when needed" not in ptxt and "Daily schedule" not in ptxt  # one medicine list; as-needed only
    assert "Scan to listen" not in ptxt
    assert "only if for" not in ptxt and "—" not in ptxt and "–" not in ptxt
    assert "Morning" not in ptxt  # no regular-schedule grid: the only medicine is "as needed"
    for meta in ("Page", "Bayan AI", "Translated by machine", "Demo clinic", "synthetic", "Language"):
        assert meta not in ptxt, meta  # no footer, branding, disclaimer or placeholder on the patient sheet
    with pymupdf.open(out["doctor_pdf"]) as doc:
        pages = [pg.get_text() for pg in doc]
    body = "\n".join(pages[:-1]) if len(pages) > 1 else pages[0]
    body = body.split("Transcript\n")[0]
    assert not re.search(r"\bu0\d\d\b", body), "utterance ids leaked into the note body"
    assert "128/82" in body and "Stopped" in body and "Presenting complaint" in body and "Safety alerts" in body
    assert "Penicillin allergy reported; amoxicillin was then prescribed." in body.replace("\n", " ")
    assert "ALG-PEN" not in body and "WORK-CHEST" not in body and "Shown" not in body
    dtxt = "\n".join(pages)
    assert DEVANAGARI.search(dtxt) and "Transcript" in dtxt and "Page 1 of" in dtxt and "—" not in dtxt
    assert not re.search(r"\b[A-Z]{4,}\b(?<!\bECG)", dtxt.replace("BAYAN", "").replace(str(c.id).upper(), "").replace(str(c.id).upper()[:6], "")), \
        "no all-caps words"
    for meta in ("Draft for clinician", "synthetic", "Demo clinic", "interpreted encounter", "decision support, not",
                 "utterances", "as heard", "clinician's words only", "Auto-generated"):
        assert meta not in dtxt, meta
    assert "Result (as stated by clinician)" in dtxt and dtxt.count("as stated by clinician") == 1

    note = out["note_md"]
    for s in ("## Allergies", "## Presenting complaint", "## History", "## Observations and investigations",
              "## Assessment", "## Plan", "## Medication changes", "## Information given to patient",
              "## Safety alerts"):
        assert s in note, s
    assert "Penicillin: body swelling, reported as severe" in note and "—" not in note
    assert "BP 128/82 mmHg (as stated by clinician)" in note and "ECG (12-lead): normal (as stated by clinician)" in note
    assert "Amoxicillin" in note and "stopped" in note and "viral" in note.split("## Assessment")[1].split("## Plan")[0]
    assert "The instruction was paused and amoxicillin stopped." in note
    assert "Both were then done and were normal." in note and "which can hide heart pain" in note
    assert not re.search(r"\bu0\d\d\b", note) and "[u" not in note
    assert c.outputs["note_info"]["source"] == "llm" and c.outputs["note_json"]["plan"]
    txt = c.outputs["note_txt"]
    assert "\nAllergies\n" in txt and "\nMedication changes\n" in txt and "**" not in txt and "ALLERGIES" not in txt
    assert (Path(out["out_dir"]) / "note.txt").read_text(encoding="utf-8").startswith("Consultation note")

    wa = urlparse(out["wa_link"])
    assert wa.scheme == "https" and wa.netloc == "wa.me" and wa.path == "/97455551234"
    wa_text = parse_qs(wa.query)["text"][0]
    assert "https://bayan.example/f/" in wa_text and "999" in wa_text and DEVANAGARI.search(wa_text)
    assert out["sms_link"].startswith("sms:+97455551234?body=")
    assert "https://bayan.example/f/" + out["token"] in unquote(out["sms_link"])
    assert len(out["token"]) >= 22  # >= 128 bits
    m = out["wrapup_metrics"]
    assert m["llm_calls"] == 2 and m["mode"] == "deterministic" and m["total_s"] < 30
    assert m["note_source"] == "llm" and m["note_chunks"] == 0

    import soundfile as sf
    audio, sr = sf.read(out["audio_wav"])
    assert sr == 16000 and len(audio) > sr * 0.4


def test_overdose_excluded_with_warning():
    c = golden_consult(cards=False)
    c.state["prescribed_meds"][0].update(dose_mg=2000, frequency_per_day=4, daily_dose_mg=8000)
    plan = wrapup.build_care_plan(c)
    assert plan["medicines"] == []
    assert plan["excluded"] and plan["excluded"][0]["name"] == "paracetamol"
    assert any("EXCLUDED paracetamol" in w and "DOSE-PARA-01" in w for w in plan["warnings"])


def test_penicillin_still_prescribed_is_excluded():
    c = golden_consult(cards=False)
    c.state["stopped_meds"] = []
    c.state["prescribed_meds"].append({"drug": "amoxicillin", "class": ["penicillin"], "dose_mg": 500,
                                       "frequency_per_day": 3, "daily_dose_mg": 1500, "evidence": [E_AMOX]})
    plan = wrapup.build_care_plan(c)
    assert [m["drug"] for m in plan["medicines"]] == ["paracetamol"]
    assert any("EXCLUDED amoxicillin" in w and "ALG-PEN-01" in w for w in plan["warnings"])


def test_agentic_failure_falls_back(monkeypatch):
    c = golden_consult()

    def boom(*a, **k):
        raise RuntimeError("no HF token")

    monkeypatch.setattr(wrapup, "_run_agent", boom)
    out = wrapup.run_wrapup(c, agentic=True)
    assert out["agentic"] == "agent→fallback"
    assert Path(out["doctor_pdf"]).exists() and Path(out["patient_pdf"]).exists()
    assert out["audio_wav"] is None and out["wa_link"].startswith("https://wa.me/?text=")
    assert c.outputs["care_plan"]["medicines"][0]["drug"] == "paracetamol"


def test_agentic_not_ok_falls_back(monkeypatch):
    c = golden_consult()
    monkeypatch.setattr(wrapup, "_run_agent", lambda *a, **k: {"ok": False, "steps": 1, "error": "timeout",
                                                               "final": None})
    out = wrapup.run_wrapup(c, agentic=True)
    assert out["agentic"] == "agent→fallback" and Path(out["patient_pdf"]).exists()


def test_agentic_tools_path(monkeypatch):
    pytest.importorskip("smolagents")
    c = golden_consult()
    seen = {}

    def fake_agent(tools, task, consult, max_steps=4, timeout_s=20.0, instructions="", **kw):
        seen["names"] = [t.name for t in tools]
        seen["max_steps"] = max_steps
        for t in tools:
            seen[t.name] = t.forward()
        return {"ok": True, "steps": 3, "error": None, "final": "done"}

    monkeypatch.setattr(wrapup, "_run_agent", fake_agent)
    out = wrapup.run_wrapup(c, agentic=True)
    assert seen["names"] == ["draft_outputs", "render_outputs"] and seen["max_steps"] >= 3
    assert seen["render_outputs"].startswith("rendered:") and "patient_pdf" in seen["render_outputs"]
    assert seen["draft_outputs"].startswith("note drafted") and len(seen["draft_outputs"]) < 400
    assert out["agentic"] == "agent" and out["wrapup_metrics"]["llm_calls"] == 2


def _agentkit():
    try:
        from bayan.brain import agentkit
        return agentkit
    except Exception:  # noqa: BLE001
        pytest.skip("agentkit not available yet")


def test_agentic_real_smolagents_scripted_model():
    """Agent B's run_agent + smolagents ToolCallingAgent with a scripted (offline) model calling our two tools."""
    agentkit = _agentkit()
    if not hasattr(agentkit, "scripted_model"):
        pytest.skip("agentkit.scripted_model missing")
    c = golden_consult()
    agentkit.set_model_factory(lambda: agentkit.scripted_model([[("draft_outputs", {})],
                                                                 [("render_outputs", {"note": "go"})]]))
    try:
        out = wrapup.run_wrapup(c, agentic=True, timeout_s=60)
    finally:
        agentkit.set_model_factory(None)
    assert out["agentic"] == "agent", out["agentic"]
    assert Path(out["patient_pdf"]).exists() and out["wrapup_metrics"]["llm_calls"] == 2
    assert any("draft_outputs" in e["text"] for e in c.trace)


def test_agentic_no_model_falls_back_fast(monkeypatch):
    agentkit = _agentkit()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(agentkit, "available", lambda: False)
    c = golden_consult()
    out = wrapup.run_wrapup(c, agentic=True, timeout_s=5)
    assert out["agentic"] == "agent→fallback" and out["wrapup_metrics"]["agent_s"] < 1.0
    assert Path(out["patient_pdf"]).exists() and out["care_plan"]["medicines"]


def test_llm_failure_keeps_english_plan():
    c = golden_consult(cards=False)
    llm.set_backend(make_backend(raise_exc=True))
    out = wrapup.run_wrapup(c, agentic=False)
    plan = out["care_plan"]
    assert plan["medicines"][0]["drug"] == "paracetamol" and plan["red_flags"]
    assert all(f["native"] == "" for f in plan["red_flags"])
    assert any("NOT translated" in w for w in out["warnings"])
    assert "999" in _pdf_text(out["patient_pdf"])


def test_wrong_number_in_translation_is_blanked():
    bad = json.loads(json.dumps(NE_PLAN))
    bad["tr"][PRN_EN] = "प्यारासिटामोल २ ग्राम दिनमा ४ पटक खानुहोस्।"
    llm.set_backend(make_backend(bad))
    c = golden_consult(cards=False)
    plan = wrapup.build_care_plan(c)
    assert plan["medicines"][0]["note_native"] == ""
    assert any("changed a number" in w for w in plan["warnings"])


def test_render_other_scripts(tmp_path):
    from bayan.outputs.report import render_care_plan_pdf

    for lang, title, flag in [("bn", "আপনার চিকিৎসা পরিকল্পনা", "বুকে ব্যথা ফিরে এলে।"),
                              ("ml", "നിങ്ങളുടെ ചികിത്സാ പദ്ധതി", "നെഞ്ചുവേദന വീണ്ടും വന്നാൽ."),
                              ("ur", "آپ کا علاج کا منصوبہ", "سینے کا درد واپس آئے۔")]:
        plan = {"lang": lang, "title_native": title, "medicines": [], "avoid": [], "emergency": "999",
                "red_flags": [{"en": "Your chest pain comes back.", "native": flag}], "advice": [], "follow_up": {}}
        p = render_care_plan_pdf(plan, tmp_path / f"{lang}.pdf", audio_url="https://bayan.example/a.wav")
        assert "999" in _pdf_text(p)


# ---------------------------------------------------------------------- delivery
def test_links_well_formed():
    assert delivery.wa_link("hi there") == "https://wa.me/?text=hi%20there"
    assert delivery.wa_link("x&y", "+974 5555-1234") == "https://wa.me/97455551234?text=x%26y"
    assert delivery.sms_link("a b") == "sms:?body=a%20b"
    assert delivery.sms_link("नमस्ते", "+97455551234").startswith("sms:+97455551234?body=%E0%A4")


def test_audio_none_without_voice(tmp_path):
    plan = {"lang": "tl", "title_native": "Plano", "medicines": [], "red_flags": [{"en": "x", "native": "y"}]}
    assert delivery.care_plan_audio(plan, lambda t, l: None, tmp_path / "a.wav") is None
    assert delivery.care_plan_audio(plan, None, tmp_path / "a.wav") is None
    assert not (tmp_path / "a.wav").exists()


def test_audio_concatenates_with_gaps_and_resamples(tmp_path):
    import soundfile as sf

    plan = {"lang": "ne", "title_native": "शीर्षक", "medicines": [{"note_native": "औषधि"}],
            "red_flags": [{"native": "खतरा"}], "advice": [], "follow_up": {}}
    rates = iter([16000, 16000, 16000, 22050, 16000, 16000, 16000])

    def speak(text, lang):
        sr = next(rates)
        return sr, np.ones(sr // 10, dtype=np.float32) * 0.1

    p = delivery.care_plan_audio(plan, speak, tmp_path / "plan.wav")
    audio, sr = sf.read(p)
    lines = delivery.audio_lines(plan)
    assert sr == 16000 and len(lines) == 6  # title, header, medicine x2, red-flag header, flag
    expected = len(lines) * 1600 + (len(lines) - 1) * int(0.4 * 16000)
    assert abs(len(audio) - expected) <= 2


# ---------------------------------------------------------------------- retention
def test_purge_removes_files():
    c = golden_consult(cards=False)
    out = wrapup.run_wrapup(c, agentic=False)
    d = Path(out["out_dir"])
    assert d.exists() and any(d.iterdir())
    c.outputs["metrics"] = [{"run": 1}]  # another module's key must survive
    retention.purge(c)
    assert not d.exists() and c.outputs == {"metrics": [{"run": 1}]}
    retention.purge(c)  # safe when already gone


def test_sweep_only_old_children(tmp_path):
    root = retention.root()
    old, new = root / "oldconsult", root / "newconsult"
    for d in (old, new):
        d.mkdir()
        (d / "f.pdf").write_bytes(b"x")
    stray = root / "loose.txt"
    stray.write_text("keep")
    outside = tmp_path / "outside"
    outside.mkdir()
    past = time.time() - 3 * 86400
    os.utime(old, (past, past))
    os.utime(outside, (past, past))
    os.utime(stray, (past, past))
    assert retention.sweep(86400) == 1
    assert not old.exists() and new.exists() and stray.exists() and outside.exists() and root.exists()
    os.utime(root, (past, past))
    retention.sweep(0)
    assert root.exists() and outside.exists()


def test_consult_dir_rejects_traversal():
    class Bad:
        id = "../escape"
        outputs = {}

    with pytest.raises(ValueError):
        retention.consult_dir(Bad())
    retention.purge(Bad())  # no error, nothing deleted


def test_start_sweeper_idempotent():
    t1 = retention.start_sweeper(interval_s=3600)
    t2 = retention.start_sweeper(interval_s=3600)
    assert t1 is t2 and t1.daemon and t1.is_alive()


# ---------------------------------------------------------------------- SOAP note: retry, fallback, map-reduce
def test_fallback_note_from_state_content():
    c = golden_consult()
    md = wrapup.note_from_state(c, auto_label=True)
    assert wrapup.FALLBACK_LABEL in md
    assert "Penicillin: body swelling, reported as severe" in md
    assert "BP 128/82 mmHg (as stated by clinician)" in md
    assert "Amoxicillin" in md and "stopped" in md
    assert "viral" in md.split("## Assessment")[1].split("## Plan")[0]
    assert not re.search(r"\bu0\d\d\b", md)


def test_safety_alerts_are_plain_sentences():
    c = golden_consult()
    alerts = wrapup.safety_alerts(c)
    assert "Penicillin allergy reported; amoxicillin was then prescribed. The instruction was paused and amoxicillin " \
           "stopped." in alerts
    assert "Chest pain, with discharge planned before an ECG and troponin. Both were then done and were normal." \
        in alerts
    assert any(a.startswith('The patient described chest burning as "gyastrik" (gastric), which can hide heart pain')
               for a in alerts)
    assert len(alerts) == 3
    text = " ".join(alerts)
    assert not re.search(r"[A-Z]{3}-[A-Z]+-\d", text) and "—" not in text and ":" not in text.replace("(", "")


def test_note_truncated_json_retries_once():
    calls: list = []
    truncated = json.dumps(NOTE_JSON)[:180]  # what a finish_reason="length" reply looks like
    llm.set_backend(make_backend(calls=calls, note_replies=[truncated, NOTE_JSON]))
    c = golden_consult(cards=False)
    out = wrapup.run_wrapup(c, agentic=False)
    notes = [x for x in calls if x["kind"] == "note"]
    assert len(notes) == 2 and notes[1]["max_tokens"] > notes[0]["max_tokens"]
    assert '"transcript"' not in notes[1]["messages"][1]["content"]  # condensed input on retry
    assert out["wrapup_metrics"]["note_source"] == "llm-retry"
    assert wrapup.FALLBACK_LABEL not in out["note_md"] and Path(out["doctor_pdf"]).exists()


def test_note_invalid_twice_falls_back():
    llm.set_backend(make_backend(note_replies=["{not json", {"subjective": []}]))
    c = golden_consult(cards=False)
    out = wrapup.run_wrapup(c, agentic=False)
    assert out["wrapup_metrics"]["note_source"] == "fallback" and wrapup.FALLBACK_LABEL in out["note_md"]


def test_llm_raises_fallback_note_and_pdfs():
    llm.set_backend(make_backend(raise_exc=True))
    c = golden_consult()
    out = wrapup.run_wrapup(c, agentic=False)
    assert wrapup.FALLBACK_LABEL in out["note_md"]
    dtxt = _pdf_text(out["doctor_pdf"])
    assert "128/82" in dtxt and "Consultation note" in dtxt  # the fallback label stays on screen, not in the PDF
    assert "999" in _pdf_text(out["patient_pdf"])


def test_note_drops_unsourced_and_non_doctor_plan_items():
    bad = json.loads(json.dumps(NOTE_JSON))
    bad["plan"].append({"text": "Start omeprazole.", "utts": []})            # no source
    bad["assessment"].append({"text": "Heat stroke.", "utts": ["u004"]})      # patient turn, not the doctor's words
    bad["history"].append({"text": "Invented.", "utts": ["u999"]})            # unknown utterance
    llm.set_backend(make_backend(note=bad))
    c = golden_consult(cards=False)
    md = wrapup.draft_note(c)
    assert "omeprazole" not in md and "Heat stroke" not in md and "Invented" not in md
    assert any("3 unsourced" in w for w in c.outputs["note_info"]["warnings"])


def _long_consult(n: int = 450) -> Consultation:
    c = golden_consult()
    long_ne = "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ र रिँगटा लाग्छ। " * 40              # ~2,000 chars
    long_en = "The burning comes and goes, worse after meals and at work in the heat. " * 28
    start = len(c.turns)
    for i in range(start, n):
        k = i % 6
        t = 2.5 + i * 0.13
        if i == start:
            c.add_turn("doctor", "en", "FIRSTMARK001 Tell me more about the pain.", t_min=t)
        elif i == n - 1:
            c.add_turn("patient", "ne", "धन्यवाद। LASTMARK450", english="Thank you. LASTMARK450", t_min=t)
        elif k == 0:
            c.add_turn("doctor", "en", f"Question {i}: does it get worse when you climb stairs? Rest for {i % 5} days.",
                       t_min=t)
        elif k == 1:
            c.add_turn("patient", "ne", long_ne if i % 12 == 1 else "कहिलेकाहीँ मात्र दुख्छ।",
                       english=long_en if i % 12 == 1 else "It hurts only sometimes.", t_min=t)
        elif k == 2:
            c.add_turn("doctor", "ar", "هل الألم يزداد مع الجهد؟", english="Does the pain increase with effort?",
                       t_min=t)
        elif k == 3:
            c.add_turn("patient", "ne", "हो 😀 अलि अलि\x07 दुख्छ", english="Yes \U0001F600 a little\x07 it hurts",
                       t_min=t)
        elif k == 4:
            url = "https://example.org/" + "verylongpath" * 30
            c.add_turn("doctor", "en", f"See {url} for the leaflet, word{'x' * 120}end.", t_min=t)
        else:
            c.add_turn("patient", "ne", "ठिक छ।", english="Okay.", t_min=t)
    return c


def test_stress_450_turns_map_reduce_and_pdfs(capsys):
    import pymupdf

    calls: list = []
    llm.set_backend(make_backend(calls=calls))
    c = _long_consult(450)
    t0 = time.perf_counter()
    out = wrapup.run_wrapup(c, agentic=False)
    total = time.perf_counter() - t0
    m = out["wrapup_metrics"]
    kinds = [x["kind"] for x in calls]
    assert m["note_chunks"] >= 2 and kinds.count("map") == m["note_chunks"] and kinds.count("note") == 1
    assert kinds.count("plan") == 1 and m["note_source"] == "llm+map-reduce"
    note_call = next(x for x in calls if x["kind"] == "note")
    summaries = json.loads(note_call["messages"][1]["content"])["chunk_summaries"]
    assert [s["chunk"] for s in summaries] == list(range(m["note_chunks"]))  # every chunk summarised, in order
    assert summaries[0]["range"].startswith("u001") and summaries[-1]["range"].endswith("u450")
    with pymupdf.open(out["doctor_pdf"]) as doc:
        pages = doc.page_count
        text = "\n".join(pg.get_text() for pg in doc)
    assert 10 <= pages <= 250
    assert "FIRSTMARK001" in text and "LASTMARK450" in text
    assert Path(out["patient_pdf"]).exists()
    with capsys.disabled():
        print(f"\n[stress] 450 turns: doctor PDF {pages} pages; render {m.get('render_s')} s; "
              f"note {m.get('draft_note_s')} s; total wrap-up {total:.1f} s; chunks {m['note_chunks']}")
    assert m["render_s"] < 30


def test_map_reduce_chunk_failure_keeps_doctor_lines(monkeypatch):
    calls: list = []
    base = make_backend(calls=calls)
    state = {"n": 0}

    def flaky(messages, schema, max_tokens):
        if kind_of(messages) == "map":
            state["n"] += 1
            if state["n"] == 2:
                return '{"facts": [{"kind": "symptom", "text": "trunc'
        return base(messages, schema, max_tokens)

    llm.set_backend(flaky)
    monkeypatch.setattr(wrapup, "NOTE_INPUT_BUDGET", 3000)
    monkeypatch.setattr(wrapup, "CHUNK_TOKENS", 1500)
    monkeypatch.setattr(wrapup, "MAP_WORKERS", 1)
    c = _long_consult(120)
    md, info = wrapup.draft_note_llm(c)
    assert info["chunks"] >= 2 and info["source"] == "llm+map-reduce"
    assert any("chunk summary" in w for w in info["warnings"])
    note_call = next(x for x in calls if x["kind"] == "note")
    summaries = json.loads(note_call["messages"][1]["content"])["chunk_summaries"]
    failed = [s for s in summaries if not s["ok"]]
    assert len(failed) == 1 and failed[0]["doctor_lines_verbatim"]


def test_pdf_renderers_survive_hostile_content(tmp_path):
    from bayan.outputs.report import render_care_plan_pdf

    plan = {"lang": "ne", "title_native": "शीर्षक\x00😀", "emergency": "999",
            "medicines": [{"name": "X" * 300, "drug": "x", "dose_text": "1 g", "times": ["morning"], "prn": False,
                           "name_native": "क" * 80, "duration_en": "z" * 90, "duration_native": "😀" * 10},
                          {"name": "Y", "drug": "y", "dose_text": "2 g", "times": [], "prn": True,
                           "note_en": "https://example.org/" + "a" * 400, "note_native": "😀" * 50}],
            "avoid": [{"substance": "y" * 200, "en": "\x07" * 10, "native": "𝔘𝔫𝔨𝔫𝔬𝔴𝔫"}],
            "red_flags": [{"en": "z " * 900, "native": "ग " * 900}], "advice": [], "follow_up": {}}
    p = render_care_plan_pdf(plan, tmp_path / "hostile.pdf", audio_url="https://e.x/" + "q" * 300)
    assert "999" in _pdf_text(p)


def test_regular_medicine_list_and_schedule_table(tmp_path, monkeypatch):
    """Every medicine is a pharmacy-label block; regular ones are also summarised in a compact daily schedule with
    only the slots used (2/day without a food relation: breakfast + bedtime). The table can be switched off."""
    import pymupdf

    c = golden_consult(cards=False)
    c.state["prescribed_meds"].append({"drug": "omeprazole", "class": [], "dose_mg": 20, "frequency_per_day": 2,
                                       "daily_dose_mg": 40, "duration_days": 14,
                                       "evidence": [ev("u010", 75.5, "omeprazole 20 mg twice a day for 14 days")]})
    plan = wrapup.build_care_plan(c)
    ome = next(m for m in plan["medicines"] if m["drug"] == "omeprazole")
    assert ome["schedule"] == "regular" and ome["slots"] == ["breakfast", "bedtime"] and ome["duration_en"] == "14 days"
    assert ome["title_en"] == "Omeprazole 20 mg" and ome["note_en"] == "Take 20 mg 2 times a day. For 14 days."
    from bayan.outputs.report import render_care_plan_pdf

    p = render_care_plan_pdf(plan, tmp_path / "list.pdf")
    with pymupdf.open(p) as doc:
        text = doc[0].get_text()
    assert "Take 20 mg 2 times a day. For 14 days." in text and PRN_EN in text
    assert "Daily schedule" in text and "Breakfast" in text and "Bedtime" in text
    assert "Lunch" not in text and "Dinner" not in text and "When you wake up" not in text  # unused slots omitted
    monkeypatch.setenv("BAYAN_PDF_SCHEDULE_TABLE", "off")
    p2 = render_care_plan_pdf(plan, tmp_path / "list2.pdf")
    with pymupdf.open(p2) as doc:
        text2 = doc[0].get_text()
    assert "Daily schedule" not in text2 and "Take 20 mg 2 times a day. For 14 days." in text2


# ---------------------------------------------------------------- v3 regressions (live-run findings)
HALLUCINATED = "Throat infection appears viral; chest symptoms likely gastric, no cardiac cause"


def test_assessment_never_contains_unstated_conclusions():
    """Live run: the model wrote 'no cardiac cause' although the clinician never said it. It must not reach the
    note text or the PDF; the assessment falls back to the clinician's own sentences."""
    import pymupdf

    bad = json.loads(json.dumps(NOTE_JSON))
    bad["assessment"] = [{"text": HALLUCINATED, "utts": ["u008", "u007"]}]
    bad["plan"].append({"text": "No cardiac cause; reassured", "utts": ["u008"]})
    llm.set_backend(make_backend(note=bad))
    c = golden_consult()
    out = wrapup.run_wrapup(c, agentic=False)
    for text in (out["note_md"], c.outputs["note_txt"]):
        assert "no cardiac cause" not in text.lower() and "likely gastric" not in text.lower()
        assess = re.split(r"assessment\s*\n", text.lower(), maxsplit=1)[1]
        assess = re.split(r"\n#* ?plan\s*\n", assess, maxsplit=1)[0]
        assert "throat looks viral." in assess and "initial impression" in assess and "revised" in assess
    with pymupdf.open(out["doctor_pdf"]) as doc:
        pdf_text = "\n".join(pg.get_text() for pg in doc).lower()
    assert "no cardiac cause" not in pdf_text and "likely gastric" not in pdf_text
    assert any("Dropped from assessment" in w for w in out["warnings"])
    assert any("Dropped from plan" in w and "No cardiac" in w for w in out["warnings"])


def test_claim_guard_scopes_negations():
    u8 = "Actually, no amoxicillin. Your throat looks viral. Before you go, we'll check your blood pressure, do a " \
         "heart tracing, and a blood test for the heart called troponin."
    assert wrapup.unsupported_claims("No amoxicillin", u8) == []
    assert "No cardiac" in wrapup.unsupported_claims("No cardiac cause", u8)           # 'no' + 'heart' != 'no heart'
    assert wrapup.unsupported_claims("Throat looks viral", u8) == []
    assert wrapup.unsupported_claims("Throat appears viral", u8) == []                 # looks ~ appears
    assert "unlikely" in wrapup.unsupported_claims("ACS unlikely", u8)
    assert wrapup.unsupported_claims("Blood pressure, ECG and troponin before discharge", u8) == []


def test_assessment_from_candidates_labels_superseded():
    c = golden_consult()
    lines = wrapup.assessment_from_candidates(c)
    assert lines == ["Initial impression “probably just gastric, and a throat infection”, later revised",
                     "Throat looks viral."]
    md = wrapup.note_from_state(c, auto_label=True)
    assess = md.split("## Assessment")[1].split("## Plan")[0]
    assert "Throat looks viral." in assess and "pharyngitis" not in assess.lower()


def test_medicine_lines_are_templates():
    L, T = wrapup.medicine_line_en, wrapup.medicine_title_en
    assert L({"name": "Paracetamol", "dose_mg": 1000, "prn": True, "frequency_per_day": 3,
              "indication": "sore throat"}) == PRN_EN
    assert L({"name": "Paracetamol", "dose_mg": 1000, "prn": True, "max_per_day": 3, "as_needed_for": "throat pain",
              "min_hours_between": 4}) == \
        "Take 1 g only when needed for throat pain. No more than 3 times a day. Wait at least 4 hours between doses."
    assert L({"name": "Paracetamol", "dose_mg": 1000, "prn": True, "frequency_per_day": 3}) == \
        "Take 1 g only when needed. No more than 3 times a day."
    amox = {"name": "Amoxicillin", "dose_mg": 500, "form": "capsule", "amount": 1, "unit": "capsule",
            "frequency_per_day": 3, "food": "after_food", "duration_en": "5 days"}
    assert T(amox) == "Amoxicillin 500 mg capsule"
    assert L(amox) == "Take 1 capsule 3 times a day, after food. For 5 days."
    ome = {"name": "Omeprazole", "dose_mg": 20, "form": "capsule", "amount": 1, "unit": "capsule",
           "times": ["morning"], "food": "before_food", "duration_en": "14 days"}
    assert L(ome) == "Take 1 capsule every morning before breakfast. For 14 days."
    flu = {"name": "Fluticasone", "form": "nasal_spray", "amount": 2, "unit": "spray", "site": "each nostril",
           "times": ["on_waking"], "duration_en": "1 month", "instructions": ["shake well"]}
    assert T(flu) == "Fluticasone nasal spray"
    assert L(flu) == "Use 2 sprays in each nostril when you wake up. For 1 month. Shake well."
    assert L({"name": "X", "dose_mg": 5, "times": ["morning", "bedtime"]}) == "Take 5 mg in the morning and at bedtime."
    assert L({"name": "X", "dose_mg": 400, "interval_hours": 8, "food": "with_food"}) == \
        "Take 400 mg every 8 hours, with food."
    assert L({"name": "X", "dose_mg": 10, "frequency_per_day": 1, "duration_en": "until finished"}) == \
        "Take 10 mg once a day. Until finished."
    assert wrapup.schedule_slots({"frequency_per_day": 2}) == ["breakfast", "bedtime"]
    assert wrapup.schedule_slots({"frequency_per_day": 2, "food": "with_food"}) == ["breakfast", "dinner"]
    assert wrapup.schedule_slots({"times": ["evening", "on_waking"]}) == ["wake", "dinner"]
    assert wrapup.schedule_slots({"frequency_per_day": 3, "interval_hours": 8}) == []
    c = golden_consult(cards=False)
    plan = wrapup.build_care_plan(c)
    assert plan["medicines"][0]["note_en"] == PRN_EN and plan["medicines"][0]["note_native"]
    assert plan["medicines"][0]["title_en"] == "Paracetamol 1 g" and plan["medicines"][0]["title_native"]


def test_medication_change_lines_have_no_placeholders():
    c = golden_consult()
    md = wrapup.note_from_state(c)
    meds = md.split("## Medication changes")[1].split("##")[0]
    assert "Paracetamol 1 g, oral, up to 3 times a day, as needed: started" in meds
    assert "Amoxicillin: stopped (penicillin allergy alert)" in meds
    assert "—," not in meds and "not stated" not in meds.lower()


def test_clinic_name_only_when_configured(monkeypatch):
    monkeypatch.delenv("BAYAN_CLINIC_NAME", raising=False)
    c = golden_consult(cards=False)
    out = wrapup.run_wrapup(c, agentic=False)
    for path in (out["patient_pdf"], out["doctor_pdf"]):
        assert "Facility" not in _pdf_text(path) and "Demo" not in _pdf_text(path)
    assert "Facility" not in out["note_md"]
    c2 = golden_consult(cards=False)
    out2 = wrapup.run_wrapup(c2, agentic=False, clinic="Al Wakra Health Centre")
    assert "Al Wakra Health Centre" in _pdf_text(out2["patient_pdf"])
    assert "Al Wakra Health Centre" in _pdf_text(out2["doctor_pdf"]) and "Al Wakra Health Centre" in out2["note_md"]
    monkeypatch.setenv("BAYAN_CLINIC_NAME", "QRC Workers Clinic")
    c3 = golden_consult(cards=False)
    out3 = wrapup.run_wrapup(c3, agentic=False)
    assert "QRC Workers Clinic" in _pdf_text(out3["patient_pdf"])


def test_incomplete_care_plan_reply_is_retried_once():
    """Live regression: the care-plan model once replied in the wrong shape (no usable translations, no red flags),
    so the patient sheet fell back to English. One retry asks only for what is missing."""
    good = make_backend()
    calls = []

    def flaky(messages, schema, max_tokens):
        if kind_of(messages) == "plan":
            calls.append(json.loads(messages[1]["content"]))
            if len(calls) == 1:
                return json.dumps({"lines": ["wrong shape"]})
        return good(messages, schema, max_tokens)

    llm.set_backend(flaky)
    plan = wrapup.build_care_plan(golden_consult("ne"))
    assert len(calls) == 2 and "previous reply was incomplete" in calls[1]["note"]
    assert plan["llm"]["calls"] == 2
    assert plan["red_flags"] and all(r["native"] for r in plan["red_flags"])
    assert all(m.get("note_native") for m in plan["medicines"]) and all(a["native"] for a in plan["avoid"])
    assert not any("translation" in w for w in plan.get("warnings", []))


def test_complete_care_plan_reply_is_not_retried():
    calls = []
    llm.set_backend(make_backend(calls=calls))
    wrapup.build_care_plan(golden_consult("ne"))
    assert sum(1 for c in calls if c["kind"] == "plan") == 1


def test_no_pseudonymous_or_machine_wording():
    c = golden_consult()
    out = wrapup.run_wrapup(c, agentic=False)
    texts = [out["note_md"], c.outputs["note_txt"], _pdf_text(out["doctor_pdf"])]
    for t in texts:
        assert "pseudonymous" not in t and "(machine)" not in t and "clinician-supervised" not in t
    assert "Bayan AI" in texts[2] and f"P-{str(c.id)[:6].upper()}" in texts[2]


def test_care_plan_withdrawal_is_not_repeated_as_advice():
    # demo bug: "Let's not use amoxicillin." under "Other instructions" as well as under "Do not take"
    st = {"allergies": [{"substance": "penicillin", "class": ["penicillin"]}],
          "stopped_meds": [{"drug": "amoxicillin"}],
          "prescribed_meds": [{"drug": "azithromycin"}, {"drug": "paracetamol"}]}
    plan = {"medicines": [{"drug": "azithromycin", "name": "Azithromycin", "note_en": "Take 1 tablet once a day."}],
            "avoid": [{"substance": "penicillin", "en": "Penicillin medicines, for example amoxicillin. You are "
                                                       "allergic."}],
            "red_flags": [{"en": "Your lips or face swell.", "native": ""},
                          {"en": "Your lips or face swell.", "native": ""}],
            "advice": [{"en": "Let's not use amoxicillin.", "native": ""},
                       {"en": "Do not take Augmentin.", "native": ""},
                       {"en": "Take azithromycin after food.", "native": ""},
                       {"en": "Drink plenty of water.", "native": ""},
                       {"en": "Drink plenty of water!", "native": ""},
                       {"en": "Avoid ibuprofen for now.", "native": ""}],
            "follow_up": {"en": "Come back in 3 days.", "native": ""}}
    dropped = wrapup.dedupe_plan_lines(plan, st)
    assert [a["en"] for a in plan["advice"]] == ["Drink plenty of water.", "Avoid ibuprofen for now."]
    assert [r["en"] for r in plan["red_flags"]] == ["Your lips or face swell."]
    assert len(dropped) == 5
