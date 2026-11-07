"""Idiom index (deterministic matching) and presenting-complaint checklists."""

from __future__ import annotations

import pytest

from bayan.brain.checklist import QUESTION_TOPICS, checklist
from bayan.brain.idioms import IdiomIndex
from bayan.brain.merge import merge_delta
from bayan.brain.rules import RuleEngine
from bayan.brain.state import Consultation, empty_state


@pytest.fixture(scope="module")
def ix() -> IdiomIndex:
    return IdiomIndex()


def hit_ids(hits):
    return [h["id"] for h in hits]


# ============================================================================ idioms
def test_golden_path_nepali_sentence_matches_npi_005(ix):
    hits = ix.match("मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ", "My chest is burning like gastric", lang="ne")
    assert hit_ids(hits) == ["npi-005"]
    h = hits[0]
    assert set(h) >= {"id", "matched", "red_flag_tags", "entry"}
    assert h["red_flag_tags"] == ["acs", "gi_bleed"] and h["entry"]["romanized"] == "gyastrik"
    assert h["matched"] == "ग्यास्ट्रिक"
    assert hit_ids(ix.match("मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ")) == ["npi-005"]   # no lang, no English


@pytest.mark.parametrize("text,lang,expected", [
    ("gyastrik", "ne", ["npi-005"]),
    ("gastric", "ne", ["npi-005"]),
    ("Gastric", "npi", ["npi-005"]),
    ("gastric", "bn", ["ben-007"]),
    ("mero chati gyastrikle jasto polyo", "ne", ["npi-005"]),
    ("kabag", None, ["tgl-002"]),
    ("kabag", "tl", ["tgl-002"]),
    ("Kinakabagan po ako", "tl", ["tgl-002"]),
    ("Pasma po ang kamay ko, nanginginig.", "tl", ["tgl-001"]),
    ("gas trouble", "ml", ["mal-001"]),
    ("Mero man bhaari chha", "ne", ["npi-002"]),
    ("मलाई टेन्सन छ", "ne", ["mul-001"]),
    ("दिल घबरा रहा है", "hi", ["hin-001"]),
    ("قلبي مقبوض", "ar", ["ara-001"]),
])
def test_matches(ix, text, lang, expected):
    assert hit_ids(ix.match(text, "", lang)) == expected


def test_english_rendering_loanword_respects_patient_language(ix):
    assert hit_ids(ix.match("...", "My chest is burning like gastric", "ne")) == ["npi-005"]
    assert hit_ids(ix.match("...", "My chest is burning like gastric", "bn")) == ["ben-007"]
    assert hit_ids(ix.match("...", "I get tension at work", "hi")) == ["mul-001"]
    # a Tagalog patient's English rendering "gas pain" must not pull in the Hindi 'gas' idiom
    hits = ix.match("May kabag po ako, masakit ang tiyan, tsaka nahihilo.", "I have gas pain, my stomach hurts, and I feel dizzy.", "tl")
    assert "tgl-002" in hit_ids(hits) and "hin-004" not in hit_ids(hits)
    assert set(hit_ids(ix.match("মাথা গরম, শরীর দুর্বল", "My head is hot, my body is weak.", "bn"))) == {"ben-003", "ben-005"}


@pytest.mark.parametrize("sentence", [
    "I work outside on a building site",
    "my throat has hurt for three days",
    "I work outside on a building site. Once, after a penicillin injection, my body swelled up. And my throat has hurt for three days.",
    "What brings you in today?",
    "It's probably a throat infection. You can go home.",
    "I have a mass in my belly and an initial test was normal",
    "My stomach hurts and I feel tired",
    "The pain is in my chest and spreads to my arm",
    "I feel hot and weak after work",
    "Take paracetamol, one gram, up to three times a day.",
])
@pytest.mark.parametrize("lang", [None, "ne", "tl", "en"])
def test_ordinary_sentences_do_not_match(ix, sentence, lang):
    assert ix.match(sentence, sentence, lang) == []


def test_english_utterance_only_matches_loanwords_of_the_patient_language(ix):
    for s in ("Mass casualty incident at the site", "I init the system", "There is a gas leak in the kitchen"):
        for lang in ("tl", "ar", "ne", "bn", "en"):
            assert ix.match(s, s, lang) == [], (s, lang)
    assert ix.match("The tension in my shoulders is bad", "", "en") == []
    assert hit_ids(ix.match("I have tension", "I have tension", "ne")) == ["mul-001"]


def test_no_duplicates_best_first_and_lookup(ix):
    hits = ix.match("gyastrik gastric gyastrikle", "gastric", None)
    ids = hit_ids(hits)
    assert len(ids) == len(set(ids)) and ids[0] == "npi-005"
    assert ix.lookup("gyastrik", "ne")["id"] == "npi-005"
    assert ix.lookup("kabag")["id"] == "tgl-002"
    assert ix.lookup("npi-002")["id"] == "npi-002"
    assert ix.lookup("the weather is nice") is None
    assert ix.get("tgl-002")["literal_en"].startswith("gas pain")
    assert ix.get("nope") is None


def test_every_entry_matches_its_own_native_or_romanized_form(ix):
    for e in ix.entries:
        lang = e["iso639_3"]
        native = e["native"].split(" / ")[0].split(" (")[0]
        assert e["id"] in hit_ids(ix.match(native, "", lang)), (e["id"], native)


# ============================================================================ checklist
def _chest_state():
    c = Consultation()
    c.set_scenario_time(1.0)
    t = c.add_turn("patient", "ne", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ", english="My chest is burning like gastric")
    merge_delta(c, {"symptoms": [{"code": "chest_burning", "evidence": [{"utt": t.id}]}]})
    return c


def test_checklist_empty_and_topics():
    assert checklist(empty_state()) == []
    assert {"pain_radiation", "exertional_pattern", "sweating_breathlessness"} <= set(QUESTION_TOPICS)
    assert len(QUESTION_TOPICS) == len(set(QUESTION_TOPICS))


def test_chest_pain_checklist_open_to_done():
    c = _chest_state()
    rows = checklist(c.state, 1.0)
    by = {r["id"]: r for r in rows}
    assert {"ecg_12lead", "troponin", "bp", "ask_pain_radiation", "ask_exertional_pattern",
            "ask_sweating_breathlessness"} <= set(by)
    assert all(r["group"] == "chest_pain" and r["status"] == "open" and r["closed_by"] is None for r in rows)
    assert set(rows[0]) >= {"id", "group", "label", "status", "closed_by"}
    assert by["ask_pain_radiation"]["ask_en"] and by["ecg_12lead"]["overdue"] is False
    assert checklist(c.state, 12.0)[0]["overdue"] is True

    # ECG ordered closes the ECG item (and only it)
    c.set_scenario_time(13.0)
    d = c.add_turn("doctor", "en", "We'll do a heart tracing (ECG) and a troponin.")
    merge_delta(c, {"investigations": [{"code": "ecg_12lead", "status": "ordered", "evidence": [{"utt": d.id}]}]})
    by = {r["id"]: r for r in checklist(c.state, 13.0)}
    assert by["ecg_12lead"]["status"] == "done" and "ecg_12lead ordered" in by["ecg_12lead"]["closed_by"]
    assert d.id in by["ecg_12lead"]["closed_by"]
    assert by["troponin"]["status"] == "open" and by["bp"]["status"] == "open"

    merge_delta(c, {"investigations": [{"code": "troponin_hs", "status": "ordered"}],
                    "vitals": {"bp": "128/82"},
                    "questions_asked": ["pain_radiation", "exertional_pattern", "sweating"]})
    by = {r["id"]: r for r in checklist(c.state, 14.0)}
    assert all(r["status"] == "done" for r in by.values()), by
    assert by["bp"]["closed_by"] == "BP 128/82"


def test_asked_item_closes_when_answer_already_volunteered():
    c = _chest_state()
    merge_delta(c, {"symptoms": [{"code": "jaw_arm_pain", "first_mention_min": 2.0}]})
    by = {r["id"]: r for r in checklist(c.state)}
    assert by["ask_pain_radiation"]["status"] == "done" and "jaw_arm_pain" in by["ask_pain_radiation"]["closed_by"]


def test_checklist_items_track_the_rules():
    """When every chest-pain checklist item is done, no WORK-CHEST rule fires (and vice versa for ECG)."""
    engine = RuleEngine()
    c = _chest_state()
    merge_delta(c, {"idiom_hits": [{"id": "npi-005", "utt": "u001", "t_min": 1.0}], "disposition": "discharge"})
    assert {f["rule_id"] for f in engine.evaluate(c.state, 12)} == {"WORK-CHEST-01", "WORK-CHEST-02", "WORK-CHEST-03", "WORK-CHEST-04"}
    merge_delta(c, {"investigations": ["ecg_12lead", "troponin"]})
    by = {r["id"]: r for r in checklist(c.state)}
    assert by["ecg_12lead"]["status"] == by["troponin"]["status"] == "done"
    assert engine.evaluate(c.state, 12) == []


def test_heat_and_other_groups_and_unique_ids():
    st = empty_state()
    merge_delta(st, {"patient": {"heat_exposure": True, "sex": "female", "age_years": 30},
                     "symptoms": ["confusion", "syncope", "dizziness"]})
    rows = checklist(st)
    groups = {r["group"] for r in rows}
    assert {"heat_illness", "pregnancy_check", "syncope"} <= groups and "chest_pain" not in groups
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert {"temp_core", "active_cooling", "ck", "creatinine", "electrolytes", "pregnancy_test", "ecg_12lead"} <= set(ids)
    merge_delta(st, {"investigations": [{"code": "temp_rectal", "status": "resulted"}], "interventions": ["active_cooling"],
                     "patient": {"pregnant": False}})
    by = {r["id"]: r for r in checklist(st)}
    assert by["temp_core"]["status"] == by["active_cooling"]["status"] == by["pregnancy_test"]["status"] == "done"
    assert by["ck"]["status"] == "open"
    # suicidality idiom opens the suicide-risk group
    st2 = empty_state()
    merge_delta(st2, {"idiom_hits": [{"id": "ara-007", "red_flag_tags": ["suicidality"], "utt": "u3", "t_min": 2}]})
    assert {r["id"] for r in checklist(st2)} == {"suicide_risk_assessment", "ask_suicidal_thoughts"}
