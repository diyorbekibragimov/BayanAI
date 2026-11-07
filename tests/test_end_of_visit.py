"""End-of-visit outputs: the doctor report's "Copilot concerns" section, the case summary as note-writer context,
the one-word consent cell, and the Review screen's plain-text care plan (layout + round trip through the /plan
parser). Offline: fake LLM backend from test_outputs."""

from __future__ import annotations

import json
import re

from test_outputs import (  # noqa: F401
    E_ALLERGY,
    E_AMOX,
    E_CHEST,
    E_PARA,
    E_STOP,
    NE_PLAN,
    _env,
    _pdf_text,
    attach_cards,
    golden_consult,
    make_backend,
    tmp_path,
)

from bayan import careplan
from bayan.brain import llm, wrapup
from bayan.brain.state import empty_case


# ====================================================================== copilot concerns (doctor report)
def _concern_consult():
    """The golden visit (rule cards acknowledged, then resolved) plus agent cards in every status."""
    c = golden_consult()
    store = c.cards
    c.set_scenario_time(20.0)
    open_id = store.post("missed", "No advice on when to come back", "Sent home with chest pain and no return advice "
                         "yet. A second sentence that must not print.", [E_PARA], "communication", severity="caution",
                         source="agent", t_min=20.0, dimension="communication")
    asked_id = store.post("ask", "Ask whether the pain spreads", "Radiation to the arm or jaw changes the picture.",
                          [E_CHEST], "history", severity="info", ask_text="Does the pain spread to your arm or jaw?",
                          source="agent", t_min=20.5, dimension="history")
    addr_id = store.post("observation", "Onset differs from the patient's account", "The patient said after lunch.",
                         [E_CHEST], "consistency", severity="caution", source="agent", t_min=21.0,
                         dimension="consistency")
    dis_id = store.post("missed", "Heat exposure not explored", "Outdoor worker with dizziness.",
                        [{"utt": "u006", "quote": "I work outside on a site"}], "safety", severity="caution",
                        source="agent", t_min=21.5, dimension="safety")
    retired_id = store.post("ask", "Ask about vomiting", "Vomiting in the heat matters.", [E_CHEST], "history",
                            severity="info", ask_text="Have you vomited?", source="agent", t_min=22.0,
                            dimension="history")
    ids = [open_id, asked_id, addr_id, dis_id, retired_id]
    assert all(i.startswith("c") for i in ids), ids
    c.set_scenario_time(23.0)
    store.resolve(asked_id, "the doctor asked it (u009)", 23.0)
    store.resolve(addr_id, "addressed in the conversation (copilot review)", 23.5)
    store.act(dis_id, "dismiss", "not relevant today")
    store.resolve(retired_id, "retired: newer concerns are more relevant", 24.0)
    return c, dict(zip(("open", "asked", "addressed", "dismissed", "retired"), ids))


def test_copilot_concerns_rows_status_and_order():
    c, ids = _concern_consult()
    rows = wrapup.copilot_concerns(c)
    by_id = {r["id"]: r for r in rows}
    assert ids["retired"] not in by_id                                   # retired: not listed
    assert by_id[ids["open"]]["label"] == "Open"
    assert by_id[ids["asked"]]["label"] == "Asked"
    assert by_id[ids["addressed"]]["label"] == "Addressed"
    assert by_id[ids["dismissed"]]["label"] == "Dismissed by clinician"
    assert by_id[ids["dismissed"]]["reason"] == "not relevant today"
    # open first, then asked / addressed / acknowledged, then dismissed
    groups = [r["group"] for r in rows]
    assert groups == sorted(groups)
    assert rows[0]["id"] == ids["open"] and rows[-1]["id"] == ids["dismissed"]
    # one-line body, dimension, quote with its time
    op = by_id[ids["open"]]
    assert op["body"] == "Sent home with chest pain and no return advice yet."
    assert op["dimension"] == "communication"
    assert op["quote"].startswith("Take paracetamol") and op["time"] == "75:30"
    # the suggested question is shown with its wording
    assert "Does the pain spread to your arm or jaw?" in by_id[ids["asked"]]["title"]
    # rule cards are listed too (the golden visit: allergy conflict + chest-pain workup, resolved = addressed)
    rules = [r for r in rows if r["source"] == "rules"]
    assert rules and all(r["label"] == "Addressed" for r in rules)
    assert all("WORK-CHEST" not in r["body"][:12] for r in rules)          # "RULE-ID: " prefix dropped
    # lexicon idiom cards are not copilot concerns (they have their own place in the note)
    assert all(r["source"] != "lexicon" for r in rows)


def test_copilot_concerns_rule_card_statuses():
    c = golden_consult(cards=False)
    from bayan.brain.cards import CardStore
    store = CardStore(turn_lookup=c.turn_by_id, clock=c.now_min, state_version=lambda: c.state_version,
                      log=c.log, audit=c.audit)
    c.cards = store
    fired = [{"rule_id": "ALG-PEN-01", "family": "drug_allergy", "severity": "critical", "key": "ALG-PEN-01|amoxicillin",
              "message": "Penicillin allergy reported. Amoxicillin is a penicillin.", "evidence": [E_ALLERGY, E_AMOX],
              "fire_on": "on_prescribe"},
             {"rule_id": "DOSE-PARA-01", "family": "dose_ceiling", "severity": "critical",
              "key": "DOSE-PARA-01|paracetamol", "message": "Paracetamol above 4 g a day.", "evidence": [E_PARA],
              "fire_on": "on_prescribe"}]
    store.sync_rules(fired, 12.0)
    cards = {cd["rule_ids"][0]: cd["id"] for cd in store.all_cards()}
    store.act(cards["ALG-PEN-01"], "override", "tolerated amoxicillin before")
    rows = wrapup.copilot_concerns(c)
    by = {r["id"]: r for r in rows}
    assert by[cards["DOSE-PARA-01"]]["label"] == "Open" and by[cards["DOSE-PARA-01"]]["dimension"] == "safety"
    assert by[cards["ALG-PEN-01"]]["label"] == "Overridden by clinician"
    assert by[cards["ALG-PEN-01"]]["reason"] == "tolerated amoxicillin before"
    assert rows[0]["id"] == cards["DOSE-PARA-01"]


def test_doctor_report_has_copilot_concerns_section(tmp_path):  # noqa: F811 - fixture from test_outputs
    from bayan.outputs.report import render_doctor_report

    c, _ids = _concern_consult()
    path = render_doctor_report(c, wrapup.note_from_state(c), tmp_path / "doctor_report.pdf")
    text = _pdf_text(path)
    assert "Copilot concerns" in text and "could not be printed" not in text
    flat = " ".join(text.split())
    for needle in ("No advice on when to come back", "Dismissed by clinician", "not relevant today", "Addressed",
                   "Asked", "Communication", "Consistency"):
        assert needle in flat, needle
    assert "Ask about vomiting" not in flat                      # retired
    assert "must not print" not in flat                          # one-line body
    # order on the page: the open concern before the dismissed one; the section before the transcript
    assert flat.index("No advice on when to come back") < flat.index("Heat exposure not explored")
    assert flat.index("Copilot concerns") < flat.index("Transcript")


def test_doctor_report_without_cards_has_no_concerns_section(tmp_path):  # noqa: F811
    from bayan.outputs.report import render_doctor_report

    c = golden_consult(cards=False)
    text = _pdf_text(render_doctor_report(c, wrapup.note_from_state(c), tmp_path / "d.pdf"))
    assert "Copilot concerns" not in text


# ====================================================================== consent cell
def test_consent_is_one_word(tmp_path):  # noqa: F811
    from bayan.outputs.report import render_doctor_report

    c = golden_consult(cards=False)
    assert wrapup._consent(c) == "Agreed"                       # golden visit: "Yes, I agree."
    c.outputs["consent"] = {"en": "Bayan will interpret. Do you agree?"}
    assert wrapup._consent(c) == "Agreed"
    text = _pdf_text(render_doctor_report(c, wrapup.note_from_state(c), tmp_path / "d.pdf"))
    i = text.index("Consent to interpretation")
    assert text[i:i + 60].split("\n")[1].strip() == "Agreed"     # one line, one word, no quoted sentence
    from bayan.brain.state import Consultation

    bare = Consultation(patient_lang="ne")
    bare.add_turn("doctor", "en", "Hello.", t_min=0.0)
    assert wrapup._consent(bare) == "Not agreed"
    asked = Consultation(patient_lang="ne")
    asked.add_turn("bayan", "ne", "...", english="Do you agree? (consent)", t_min=0.0)
    asked.add_turn("patient", "ne", "होइन", english="No, I don't want that.", t_min=0.1)
    assert wrapup._consent(asked) == "Not agreed"


# ====================================================================== case summary -> note writer context
def _with_case(c):
    case = empty_case()
    case["chief_complaint"] = {"text": "burning chest pain after lunch", "evidence": [E_CHEST]}
    case["history"] = [{"text": "sore throat for 3 days", "present": True, "evidence": [{"utt": "u006"}]},
                       {"text": "no vomiting", "present": False, "evidence": [{"utt": "u006"}]}]
    case["working_diagnosis"] = [{"text": "viral pharyngitis", "evidence": [E_STOP]}]
    case["plan"] = [{"text": "something for the throat pain", "type": "medicine", "evidence": [E_PARA]}]
    case["patient_affect"] = [{"text": "worried", "evidence": []}]
    with c.lock:
        c.state["case"] = case
    return c


def test_case_context_is_compact_and_cited():
    ctx = wrapup.case_context(_with_case(golden_consult(cards=False)).state["case"])
    assert ctx["chief_complaint"] == "burning chest pain after lunch (u004)"
    assert ctx["history_positives"] == ["sore throat for 3 days (u006)"]
    assert ctx["history_negatives"] == ["no vomiting (u006)"]
    assert ctx["plan"] == ["medicine: something for the throat pain (u010)"]
    assert ctx["patient_affect"] == ["worried"]
    assert "differential" not in ctx and "stated_findings" not in ctx   # empty lists left out
    assert wrapup.case_context(None) == {}


def test_note_writer_gets_case_summary_in_the_same_call():
    calls: list = []
    llm.set_backend(make_backend(calls=calls))
    c = _with_case(golden_consult(cards=False))
    _js, info = wrapup.draft_note_llm(c)
    notes = [x for x in calls if x["kind"] == "note"]
    assert len(notes) == 1 and info["calls"] == 1                     # no extra call
    payload = json.loads(notes[0]["messages"][1]["content"])
    assert payload["case_summary"]["working_diagnosis"] == ["viral pharyngitis (u008)"]
    assert "case" not in payload["record"]                            # not mixed into the record
    assert "case_summary" in notes[0]["messages"][0]["content"]       # the writer is told what it is (and is not)


def test_note_still_drops_claims_only_the_case_summary_makes():
    """The summary is context, not a source: an assessment taken from it (not said by the clinician) is dropped."""
    bad = json.loads(json.dumps(__import__("test_outputs").NOTE_JSON))
    bad["assessment"] = [{"text": "Viral pharyngitis, cardiac cause excluded", "utts": ["u008"]}]
    llm.set_backend(make_backend(note=bad))
    c = _with_case(golden_consult(cards=False))
    js, _info = wrapup.draft_note_llm(c)
    text = " ".join(it["text"] for it in js["assessment"])
    assert "excluded" not in text and "Throat looks viral" in text


# ====================================================================== review-screen text (plan_text) + /plan parser
NE_REVIEW_PLAN = {
    "lang": "ne",
    "medicines": [{"title_en": "Paracetamol 1 g", "note_en": "Take 1 g only when needed for sore throat. No more "
                   "than 3 times a day.", "title_native": "प्यारासिटामोल 1 g",
                   "note_native": "घाँटी दुखेको बेला मात्र 1 g खानुहोस्।\n दिनमा 3 पटकभन्दा बढी नखानुहोस्। "}],
    "avoid": [{"en": "Penicillin medicines, for example amoxicillin. You are allergic.",
               "native": "पेनिसिलिन औषधि, जस्तै एमोक्सिसिलिन। तपाईंलाई यसको एलर्जी छ।"}],
    "advice": [{"en": "Drink plenty of water.", "native": "प्रशस्त पानी पिउनुहोस्।"}],
    "follow_up": {"en": "Come back in 3 days.", "native": "3 दिनपछि फेरि आउनुहोस्।"},
    "red_flags": [{"en": "Your chest pain comes back.", "native": "छातीको दुखाइ फेरि आयो भने।"},
                  {"en": "You vomit blood or pass black stools.", "native": "रगत बान्ता भयो वा कालो दिसा भयो भने।"}],
}


def test_plan_text_layout():
    from bayan.outputs import labels

    t = careplan.plan_text(NE_REVIEW_PLAN)
    L, E = labels("ne"), labels("en")
    lines = t.split("\n")
    assert "·" not in t                                                  # no separators anywhere
    assert all(ln == ln.rstrip() for ln in lines)                         # no trailing spaces
    assert "\n\n\n" not in t and not t.startswith("\n") and not t.endswith("\n")
    # heading on its own line, the patient-language heading on the next; items "- English" + 2-space native line
    assert lines[0] == E["medicines"] and lines[1] == L["medicines"]
    assert lines[2].startswith("- Paracetamol 1 g: Take 1 g")
    assert lines[3] == "  प्यारासिटामोल 1 g: घाँटी दुखेको बेला मात्र 1 g खानुहोस्। दिनमा 3 पटकभन्दा बढी नखानुहोस्।"
    assert lines[4] == ""                                                 # one blank line between sections
    assert lines[5] == E["avoid"] and lines[6] == L["avoid"]
    blocks = t.split("\n\n")
    assert [b.split("\n")[0] for b in blocks] == [E["medicines"], E["avoid"], E["other"], E["red_flags"]]
    for b in blocks:                                                     # inside a section: no blank lines
        assert all(ln.strip() for ln in b.split("\n"))
        body = b.split("\n")[2:]
        assert all(ln.startswith("- ") or ln.startswith("  ") and not ln.startswith("   ") for ln in body)


def test_plan_text_english_patient_has_single_language():
    plan = dict(NE_REVIEW_PLAN, lang="en")
    t = careplan.plan_text(plan)
    assert not re.search(r"[ऀ-ॿ]", t)
    assert t.split("\n")[1].startswith("- ")                              # no second heading line
    assert "\n  " not in t


def test_plan_text_without_red_flags_keeps_the_emergency_line():
    t = careplan.plan_text({"lang": "ne", "medicines": [], "avoid": [], "advice": [], "follow_up": {},
                            "red_flags": [], "emergency": "999"})
    assert t.split("\n")[-1] == "- Call 999."


def test_plan_text_round_trips_through_the_plan_parser():
    from bayan.outputs import labels

    t = careplan.plan_text(NE_REVIEW_PLAN)
    secs = careplan.parse_text(t)
    L, E = labels("ne"), labels("en")
    assert [s["heading"] for s in secs] == [[E[k], L[k]] for k in ("medicines", "avoid", "other", "red_flags")]
    assert [len(s["items"]) for s in secs] == [1, 1, 2, 2]
    assert all(len(it) == 2 for s in secs for it in s["items"])           # English + its native line
    assert secs[2]["items"][1] == ["Come back in 3 days.", "3 दिनपछि फेरि आउनुहोस्।"]
    # the patient page rendered from the doctor's (unchanged) text: 4 sections, red headings, 2-line headings
    html = careplan._text_sections(t, "en")
    assert html.count("<section") == 4 and html.count("<li>") == 6
    assert html.count("class='h red'") == 2
    assert f"<span>{E['medicines']}</span><small>{L['medicines']}</small>" in html


def test_parser_handles_doctor_edits_and_old_format():
    edited = ("Your medicines\n- Paracetamol 1 g when needed\n  प्यारासिटामोल\n\n"
              "Rest at home\n\n\nCall 999 or come back now if\nयस्तो भए\n- Chest pain\n  छाती दुख्यो भने\n"
              "  छाती दुख्यो भने\n")
    secs = careplan.parse_text(edited)
    assert [s["heading"] for s in secs] == [["Your medicines"], ["Rest at home"],
                                            ["Call 999 or come back now if", "यस्तो भए"]]
    assert secs[2]["items"] == [["Chest pain", "छाती दुख्यो भने"]]        # repeated line dropped
    old = "Your medicines  ·  तपाईंका औषधिहरू\n- Paracetamol\n  प्यारासिटामोल"
    assert careplan.parse_text(old)[0]["heading"] == ["Your medicines  ·  तपाईंका औषधिहरू"]
    # an item before any heading still renders
    assert careplan.parse_text("- Drink water")[0] == {"heading": [], "items": [["Drink water"]]}


def test_tidy_text_cleans_model_output():
    raw = "عنوان  \n\n\n- بند   \n  सामग्री \n\n"
    assert careplan.tidy_text(raw) == "عنوان\n\n- بند\n  सामग्री"


def test_approved_edited_text_page_uses_new_parser():
    pid = careplan.create("ne", NE_REVIEW_PLAN)
    t = careplan.plan_text(NE_REVIEW_PLAN)
    careplan.set_text(pid, t, "", "en")
    careplan.approve(pid)
    code, body = careplan.page_html(pid)
    assert code == 200 and body.count("<section") == 4 and "<small>" in body
