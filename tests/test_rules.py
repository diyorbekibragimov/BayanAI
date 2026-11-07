"""Rule engine, validator (merge) and vocab: golden path, docs/05 worked examples, prescription gate."""

from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path

import pytest

from bayan.brain import vocab
from bayan.brain.idioms import IdiomIndex
from bayan.brain.merge import merge_delta, normalise_med
from bayan.brain.rules import RuleEngine
from bayan.brain.state import Consultation, empty_state

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "safety_rules.json"


@pytest.fixture(scope="module")
def engine() -> RuleEngine:
    return RuleEngine()


@pytest.fixture(scope="module")
def index() -> IdiomIndex:
    return IdiomIndex()


def ids(fired) -> set[str]:
    return {f["rule_id"] for f in fired}


def ev(turn, quote=None):
    return [{"utt": turn.id, "quote": quote or turn.english or turn.text}]


def idiom_delta(index, turn, lang):
    hits = index.match(turn.text, turn.english, lang)
    return {"idiom_hits": [{"id": h["id"], "red_flag_tags": h["red_flag_tags"], "utt": turn.id,
                            "t_min": turn.t_min, "matched": h["matched"]} for h in hits]}


# ============================================================================ golden path (docs/02 §8)
class GoldenPath:
    """Builds the consultation of docs/02 §8 step by step through merge_delta (scenario minutes)."""

    def __init__(self, index):
        self.c = Consultation(patient_lang="ne")
        self.index = index

    def step2(self):  # t = 1 (21:01)
        c = self.c
        c.set_scenario_time(1.0)
        c.add_turn("doctor", "en", "What brings you in today?")
        p = c.add_turn("patient", "ne", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ। खाना खाएपछि सुरु भयो, र मलाई रिंगटा लाग्छ।",
                       english="My chest is burning like gyastrik (gastric). It started after lunch, and I feel dizzy.")
        merge_delta(c, {"symptoms": [
            {"code": "chest_burning", "severity": "moderate", "onset": "after lunch",
             "evidence": ev(p, "My chest is burning like gyastrik (gastric)")},
            {"code": "dizziness", "evidence": ev(p, "I feel dizzy")}]})
        merge_delta(c, idiom_delta(self.index, p, "ne"))

    def step3(self):  # t = 2 (21:02)
        c = self.c
        c.set_scenario_time(2.0)
        c.add_turn("doctor", "ar", "ما هو عملك؟ هل عندك حساسية من أي دواء؟", english="What is your work? Are you allergic to any medicine?")
        p = c.add_turn("patient", "ne", "म बाहिर निर्माण साइटमा काम गर्छु। एकपटक पेनिसिलिनको सुई लगाएपछि मेरो शरीर सुन्नियो। अनि मेरो घाँटी तीन दिनदेखि दुखेको छ।",
                       english="I work outside on a building site. Once, after a penicillin injection, my body swelled up. "
                               "And my throat has hurt for three days.")
        self.idioms_step3 = idiom_delta(self.index, p, "ne")["idiom_hits"]
        merge_delta(c, {
            "allergies": [{"substance": "penicillin", "class": "penicillin", "reaction": "body swelling",
                           "severity": "severe", "confidence": 0.8,
                           "evidence": ev(p, "Once, after a penicillin injection, my body swelled up")}],
            "patient": {"heat_exposure": True, "sex": "male", "age_years": 29},
            "symptoms": [{"code": "sore_throat", "onset": "3 days",
                          "evidence": ev(p, "my throat has hurt for three days")}],
            "questions_asked": ["allergies"],
        })

    def step4(self):  # t = 12 (21:12)
        c = self.c
        c.set_scenario_time(12.0)
        d = c.add_turn("doctor", "en", "It's probably just gastric, and a throat infection. I'll give you amoxicillin "
                                       "500 mg three times a day for your throat, and you can go home.")
        self.step4_turn = d
        return merge_delta(c, {
            "prescribed_meds": [{"drug": "amoxicillin", "dose_mg": 500, "unit_raw": "mg", "dose_raw": "500 mg",
                                 "frequency_per_day": 3, "route": "oral", "indication": "sore throat",
                                 "evidence": ev(d, "I'll give you amoxicillin 500 mg three times a day")}],
            "disposition": {"type": "discharge", "evidence": ev(d, "you can go home")},
        })

    def step5(self):  # t = 13 (21:13)
        c = self.c
        c.set_scenario_time(13.0)
        d = c.add_turn("doctor", "en", "Actually, no amoxicillin. Your throat looks viral. Before you go, we'll check "
                                       "your blood pressure, do a heart tracing (ECG), and a blood test for the heart called troponin.")
        return merge_delta(c, {
            "remove": {"prescribed_meds": [{"drug": "amoxicillin", "evidence": ev(d, "Actually, no amoxicillin")}]},
            "investigations": [{"code": "ecg_12lead", "status": "ordered", "evidence": ev(d, "do a heart tracing (ECG)")},
                               {"code": "troponin_hs", "status": "ordered",
                                "evidence": ev(d, "a blood test for the heart called troponin")}],
        })

    def step6(self):  # t = 75 (22:15)
        c = self.c
        c.set_scenario_time(75.0)
        r = c.add_turn("doctor", "en", "Your blood pressure is 128 over 82, your heart tracing is normal, and the troponin test is normal.")
        merge_delta(c, {
            "vitals": {"bp_sys": 128, "bp_dia": 82, "evidence": ev(r, "Your blood pressure is 128 over 82")},
            "investigations": [{"code": "ecg_12lead", "status": "resulted", "result": "normal", "evidence": ev(r, "your heart tracing is normal")},
                               {"code": "troponin_hs", "status": "resulted", "result": "normal", "evidence": ev(r, "the troponin test is normal")}],
        })
        plan = c.add_turn("doctor", "en", "Take paracetamol, one gram, up to three times a day, for your throat. Drink plenty of "
                                          "water and rest out of the sun for two days. If the chest pain comes back, spreads to your "
                                          "arm or jaw, you feel faint or sweaty, or you vomit blood or pass black stools, call 999 or come straight back.")
        self.plan_turn = plan
        return merge_delta(c, {
            "prescribed_meds": [{"drug": "Panadol", "dose_mg": 1, "unit_raw": "g", "dose_raw": "one gram",
                                 "frequency_per_day": "up to three times a day", "route": "oral", "indication": "sore throat",
                                 "evidence": ev(plan, "Take paracetamol, one gram, up to three times a day")}],
            "disposition": {"type": "discharge", "evidence": ev(plan, "come straight back")},
        })


def test_golden_path_expected_rule_outcome(engine, index):
    g = GoldenPath(index)
    c = g.c

    # Step 2: idiom + chest burning -> WORK-CHEST-04 only
    g.step2()
    assert [h["id"] for h in c.state["idiom_hits"]] == ["npi-005"]
    assert c.state["idiom_hits"][0]["red_flag_tags"] == ["acs", "gi_bleed"]
    assert {s["code"] for s in c.state["symptoms"]} == {"chest_burning", "dizziness"}
    assert c.state["symptoms"][0]["first_mention_min"] == 1.0
    fired = engine.evaluate(c.state, c.now_min())
    assert ids(fired) == {"WORK-CHEST-04"}
    f04 = fired[0]
    assert f04["severity"] == "caution" and f04["group"] == "chest_pain_workup"
    assert "gyastrik" in f04["message"]

    # Step 3: allergy recorded, heat exposure, sore throat -> nothing new (allergy alone triggers nothing)
    g.step3()
    assert g.idioms_step3 == []          # "I work outside on a building site ..." matches no idiom
    allergy = c.state["allergies"][0]
    assert allergy["substance"] == "penicillin" and allergy["class"] == ["penicillin"]
    assert allergy["severity"] == "severe" and allergy["reaction"] == "body swelling"
    assert c.state["patient"]["heat_exposure"] is True
    assert ids(engine.evaluate(c.state, 2.0)) == {"WORK-CHEST-04"}

    # Timer tick just after 21:11 (>10 min since first mention at 21:01) -> + WORK-CHEST-01.
    # NOTE: at exactly t=11.0 the elapsed time is 10.0 and the rule is `gt 10`; see test_timer_boundary.
    assert ids(engine.evaluate(c.state, 11.0 + 1 / 60)) == {"WORK-CHEST-04", "WORK-CHEST-01"}

    # Step 4: the prescription gate sees ALG-PEN-01 before the sentence is spoken
    gate = engine.check_prescription(c.state, [{"name": "amoxicillin", "dose_mg": 500, "frequency_per_day": 3,
                                                "intent": "prescribe"}], 12.0)
    assert [f["rule_id"] for f in gate] == ["ALG-PEN-01"] and gate[0]["severity"] == "critical"
    events = g.step4()
    assert events == {"state_change", "on_prescribe", "on_disposition"}
    fired = {f["rule_id"]: f for f in engine.evaluate(c.state, 12.0)}
    assert set(fired) == {"WORK-CHEST-04", "WORK-CHEST-01", "ALG-PEN-01", "WORK-CHEST-02", "WORK-CHEST-03"}
    pen = fired["ALG-PEN-01"]
    assert pen["severity"] == "critical" and pen["group"] is None and pen["key"] == "ALG-PEN-01|amoxicillin"
    assert "my body swelled up" in pen["message"] and "02:00" in pen["message"]
    assert pen["message"].endswith("Amoxicillin is a penicillin.")
    assert [e["utt"] for e in pen["evidence"]] == ["u004", g.step4_turn.id]
    assert fired["WORK-CHEST-02"]["severity"] == "critical" and fired["WORK-CHEST-03"]["severity"] == "critical"
    chest_card = [f for f in fired.values() if f["group"] == "chest_pain_workup"]
    assert len(chest_card) == 4                       # two cards, five rule hits
    assert max(f["severity"] for f in chest_card) == "critical"
    assert "11 min ago" in fired["WORK-CHEST-01"]["message"]

    # Step 5: amoxicillin withdrawn, ECG + troponin ordered -> nothing fires
    events = g.step5()
    assert "state_change" in events and "on_prescribe" not in events
    assert c.state["prescribed_meds"] == []
    assert [s["drug"] for s in c.state["stopped_meds"]] == ["amoxicillin"]
    assert ids(engine.evaluate(c.state, 13.0)) == set()

    # Step 6: results + paracetamol 1 g x3 (3 g/day) -> still nothing, in particular no DOSE-PARA-*
    events = g.step6()
    para = c.state["prescribed_meds"][0]
    assert para["drug"] == "paracetamol" and para["dose_mg"] == 1000 and para["frequency_per_day"] == 3
    assert para["daily_dose_mg"] == 3000
    assert "on_prescribe" in events and "on_disposition" not in events   # disposition unchanged
    assert c.state["vitals"]["bp_sys"] == 128 and c.state["vitals"]["bp_dia"] == 82
    assert {i["code"]: i["status"] for i in c.state["investigations"]} == {"ecg_12lead": "resulted",
                                                                           "troponin_hs": "resulted"}
    fired = engine.evaluate(c.state, 75.0)
    assert ids(fired) == set()
    assert engine.check_prescription(c.state, [para], 75.0) == []
    # sanity: the same plan at "four times a day" with suspected heat illness WOULD hit DOSE-PARA-04 (build note 2)
    risky = copy.deepcopy(c.state)
    risky["patient"]["heat_illness_suspected"] = True
    hit = engine.check_prescription(risky, [{"name": "paracetamol", "dose_mg": 1000, "frequency_per_day": 4}], 75.0)
    assert "DOSE-PARA-04" in ids(hit)


def test_timer_boundary(engine, index):
    """WORK-CHEST-01 is `elapsed_min_since.first_match gt 10`: at exactly 10.0 minutes it does not fire yet.
    The docs/02 §8 table shows it at 21:11 for a first mention at 21:01, i.e. the replay timer tick must land
    strictly after the 10-minute mark (e.g. t_scenario 11.1)."""
    g = GoldenPath(index)
    g.step2()
    g.step3()
    assert ids(engine.evaluate(g.c.state, 11.0)) == {"WORK-CHEST-04"}
    assert ids(engine.evaluate(g.c.state, 11.01)) == {"WORK-CHEST-04", "WORK-CHEST-01"}
    assert "WORK-CHEST-01" not in ids(engine.evaluate(g.c.state, 5.0))


def test_first_match_counts_from_earliest_chest_group_symptom(engine):
    st = empty_state()
    merge_delta(st, {"symptoms": [{"code": "chest_pain", "first_mention_min": 6.0, "evidence": [{"utt": "u9", "t_min": 6.0, "quote": "pain"}]},
                                  {"code": "chest_burning", "first_mention_min": 1.0, "evidence": [{"utt": "u2", "t_min": 1.0, "quote": "burns"}]}]})
    assert "WORK-CHEST-01" in ids(engine.evaluate(st, 11.5))       # 10.5 min since chest_burning
    f = next(f for f in engine.evaluate(st, 11.5) if f["rule_id"] == "WORK-CHEST-01")
    assert "burns" in f["message"] and "10 min ago" in f["message"]


# ============================================================================ docs/05 §3 worked examples
def test_worked_example_2_kabag_pasma_ibuprofen_ct(engine, index):
    c = Consultation(patient_lang="tl")
    c.set_scenario_time(0.08)
    merge_delta(c, {"investigations": [{"code": "ecg_12lead", "status": "resulted", "evidence": [{"utt": "triage", "t_min": 0.08, "quote": "12-lead ECG at triage"}]}],
                    "patient": {"sex": "female", "age_years": 29}})
    c.set_scenario_time(0.5)
    p = c.add_turn("patient", "tl", "May kabag po ako, masakit ang tiyan, tsaka nahihilo.",
                   english="I have gas pain, my stomach hurts, and I feel dizzy.")
    d = idiom_delta(index, p, "tl")
    assert "tgl-002" in [h["id"] for h in d["idiom_hits"]]
    merge_delta(c, d)
    merge_delta(c, {"symptoms": [{"code": "abdominal_pain", "evidence": ev(p, "masakit ang tiyan")},
                                 {"code": "dizziness", "evidence": ev(p, "nahihilo")}]})
    assert "WORK-CHEST-04" not in ids(engine.evaluate(c.state, 0.5))   # ECG exists (and no chest symptom)
    c.set_scenario_time(1.83)
    p2 = c.add_turn("patient", "tl", "Pasma po ang kamay ko, nanginginig.", english="My hands have pasma; they tremble.")
    d2 = idiom_delta(index, p2, "tl")
    assert [h["id"] for h in d2["idiom_hits"]] == ["tgl-001"]
    merge_delta(c, d2)
    # (the doc's table is silent here, but WORK-PREG-01 already holds as caution: woman 29, dizziness, unknown status)
    assert ids(engine.evaluate(c.state, 1.83)) == {"WORK-PREG-01"}

    c.set_scenario_time(4.17)
    dr = c.add_turn("doctor", "en", "Ibuprofen 800 four times a day, and let's get a CT abdomen.")
    merge_delta(c, {"prescribed_meds": [{"drug": "Brufen", "dose_mg": 800, "frequency_per_day": 4, "route": "oral",
                                         "evidence": ev(dr, "Ibuprofen 800 four times a day")}],
                    "investigations": [{"code": "ct_abdomen", "status": "ordered", "evidence": ev(dr, "let's get a CT abdomen")}]})
    fired = {f["rule_id"]: f for f in engine.evaluate(c.state, 4.17)}
    assert set(fired) == {"DOSE-IBU-01", "WORK-PREG-01"}           # documented alert list
    assert fired["DOSE-IBU-01"]["severity"] == "caution" and "3200 mg/day" in fired["DOSE-IBU-01"]["message"]
    assert fired["WORK-PREG-01"]["severity"] == "critical" and fired["WORK-PREG-01"]["escalated"] is True

    # 04:30 follow-up: >= 20 weeks -> PREG-NSAID-01 caution; >= 30 weeks -> critical
    st = copy.deepcopy(c.state)
    merge_delta(st, {"patient": {"pregnant": True, "gestation_weeks": 24}})
    f = {x["rule_id"]: x for x in engine.evaluate(st, 5.0)}
    assert f["PREG-NSAID-01"]["severity"] == "caution" and "WORK-PREG-01" not in f
    merge_delta(st, {"patient": {"gestation_weeks": 31}})
    f = {x["rule_id"]: x for x in engine.evaluate(st, 5.0)}
    assert f["PREG-NSAID-01"]["severity"] == "critical" and "31 weeks" in f["PREG-NSAID-01"]["message"]


def test_worked_example_3_matha_gorom_heat(engine, index):
    c = Consultation(patient_lang="bn")
    c.set_scenario_time(0.33)
    col = c.add_turn("patient", "bn", "দুপুরে কাজ করার পর থেকে ও উল্টাপাল্টা কথা বলছে, বমি করেছে",
                     english="Since working at midday he's been talking nonsense and vomited.")
    merge_delta(c, {"symptoms": [{"code": "confusion", "evidence": ev(col, "he's been talking nonsense")},
                                 {"code": "vomiting_in_heat", "evidence": ev(col, "vomited")}],
                    "patient": {"heat_exposure": True, "sex": "male", "age_years": 31}})
    c.set_scenario_time(0.75)
    p = c.add_turn("patient", "bn", "মাথা গরম, শরীর দুর্বল", english="My head is hot, my body is weak.")
    d = idiom_delta(index, p, "bn")
    assert {h["id"] for h in d["idiom_hits"]} == {"ben-003", "ben-005"}
    merge_delta(c, d)
    c.set_scenario_time(0.77)
    merge_delta(c, {"vitals": {"temp_c": 39.4, "temp_site": "tympanic"}, "patient": {"heat_stroke_suspected": True}})
    fired = {f["rule_id"]: f for f in engine.evaluate(c.state, 0.77)}
    assert set(fired) == {"WORK-HEAT-01", "WORK-HEAT-02"}
    assert all(f["severity"] == "critical" and f["group"] == "heat_illness" for f in fired.values())
    assert "confusion" in fired["WORK-HEAT-01"]["message"]

    c.set_scenario_time(3.0)
    dr = c.add_turn("doctor", "en", "Dehydration. Paracetamol 1 g four times a day, ibuprofen 400 three times a day, oral fluids, home.")
    merge_delta(c, {
        "current_meds": [{"drug": "lisinopril", "dose_mg": 10, "frequency_per_day": 1, "evidence": [{"utt": "u000", "t_min": 0.0, "quote": "own medicines"}]},
                         {"drug": "hydrochlorothiazide", "dose_mg": 25, "frequency_per_day": 1}],
        "prescribed_meds": [{"drug": "paracetamol", "dose_raw": "1 g", "frequency_per_day": 4, "evidence": ev(dr, "Paracetamol 1 g four times a day")},
                            {"drug": "ibuprofen", "dose_mg": 400, "frequency_per_day": 3, "evidence": ev(dr, "ibuprofen 400 three times a day")}],
        "patient": {"dehydration": "moderate", "heat_illness_suspected": True},
        "disposition": {"type": "home", "evidence": ev(dr, "home")},
    })
    fired = {f["rule_id"]: f for f in engine.evaluate(c.state, 3.0)}
    assert set(fired) == {"WORK-HEAT-01", "WORK-HEAT-02", "WORK-HEAT-04", "DOSE-PARA-04", "DDI-AKI-01",
                          "HEAT-MED-01", "WORK-HEAT-03"}
    assert fired["WORK-HEAT-04"]["severity"] == "info"
    assert fired["DOSE-PARA-04"]["severity"] == "caution" and "4000 mg/day" in fired["DOSE-PARA-04"]["message"]
    assert fired["DDI-AKI-01"]["severity"] == "critical" and fired["DDI-AKI-01"]["escalated"] is True
    assert fired["HEAT-MED-01"]["severity"] == "caution" and fired["WORK-HEAT-03"]["severity"] == "caution"


# ============================================================================ prescription gate
def _allergy_state(severity="moderate", substance="penicillin"):
    st = empty_state()
    merge_delta(st, {"allergies": [{"substance": substance, "reaction": "rash", "severity": severity,
                                    "evidence": [{"utt": "u002", "t_min": 1.2, "quote": "penicillin gave me a rash"}]}]})
    return st


def test_check_prescription_amoxicillin_penicillin_allergy(engine):
    st = _allergy_state()
    before = copy.deepcopy(st)
    fired = engine.check_prescription(st, [{"name": "Amoxicillin 500mg", "dose_mg": 500, "frequency_per_day": 3,
                                            "intent": "prescribe"}], 10.8)
    assert ids(fired) == {"ALG-PEN-01"}
    assert fired[0]["severity"] == "critical" and fired[0]["key"] == "ALG-PEN-01|amoxicillin"
    assert "penicillin gave me a rash" in fired[0]["message"]
    assert st == before                                     # not mutated


def test_check_prescription_cephalexin_escalates_with_severe_allergy(engine):
    for sev in ("severe", "anaphylaxis"):
        fired = {f["rule_id"]: f for f in engine.check_prescription(_allergy_state(sev), [{"name": "cefalexin", "dose_mg": 500, "frequency_per_day": 4}], 5)}
        assert set(fired) == {"ALG-PEN-02"}
        assert fired["ALG-PEN-02"]["severity"] == "critical" and fired["ALG-PEN-02"]["escalated"] is True
    mild = {f["rule_id"]: f for f in engine.check_prescription(_allergy_state("mild"), [{"name": "Keflex", "dose_mg": 500, "frequency_per_day": 4}], 5)}
    assert set(mild) == {"ALG-PEN-02"} and mild["ALG-PEN-02"]["severity"] == "caution"
    # a dissimilar cephalosporin in a non-severe allergy: info only (ALG-PEN-04)
    info = engine.check_prescription(_allergy_state("mild"), [{"name": "ceftriaxone", "dose_mg": 1000, "frequency_per_day": 1, "route": "iv"}], 5)
    assert [(f["rule_id"], f["severity"]) for f in info] == [("ALG-PEN-04", "info")]


def test_check_prescription_brand_augmentin_is_co_amoxiclav(engine):
    fired = engine.check_prescription(_allergy_state(), [{"name": "Augmentin", "dose_mg": 625, "frequency_per_day": 3, "intent": "prescribe"}], 5)
    assert ids(fired) == {"ALG-PEN-01"}
    assert fired[0]["key"] == "ALG-PEN-01|co-amoxiclav" and "Co-amoxiclav is a penicillin." in fired[0]["message"]


def test_check_prescription_only_reports_rules_involving_the_candidate(engine):
    st = empty_state()
    merge_delta(st, {"current_meds": [{"drug": "warfarin", "dose_mg": 5, "frequency_per_day": 1}],
                     "prescribed_meds": [{"drug": "ibuprofen", "dose_mg": 400, "frequency_per_day": 3}]})
    assert "DDI-WARF-01" in ids(engine.evaluate(st, 1))
    assert engine.check_prescription(st, [{"name": "paracetamol", "dose_mg": 1000, "frequency_per_day": 3}], 1) == []
    nsaid = engine.check_prescription(empty_state() | {"current_meds": st["current_meds"]}, [{"name": "Voltaren", "dose_mg": 50, "frequency_per_day": 3}], 1)
    assert ids(nsaid) == {"DDI-WARF-01"} and "Warfarin with diclofenac" in nsaid[0]["message"]
    # talk-loop intents: only "prescribe" counts
    assert engine.check_prescription(_allergy_state(), [{"name": "amoxicillin", "intent": "mention"},
                                                        {"name": "amoxicillin", "intent": "stop"}], 1) == []


# ============================================================================ engine semantics
def test_engine_loads_all_rules_and_every_node_is_evaluable(engine):
    assert len(engine.rules) == 81
    assert engine.unevaluable == []


def test_missing_data_is_false_except_none_in(engine):
    st = empty_state()
    assert engine.evaluate(st, 100.0) == []
    # heat exposure unknown -> WORK-HEAT-01 cannot fire even with confusion and no core temperature
    merge_delta(st, {"symptoms": ["confusion"]})
    assert "WORK-HEAT-01" not in ids(engine.evaluate(st, 1))
    merge_delta(st, {"patient": {"heat_exposure": "yes"}})
    assert "WORK-HEAT-01" in ids(engine.evaluate(st, 1))
    # no weight -> DOSE-PARA-03 (mg/kg) cannot fire
    para = engine.check_prescription(empty_state(), [{"name": "paracetamol", "dose_mg": 1000, "frequency_per_day": 4}], 1)
    assert "DOSE-PARA-03" not in ids(para)
    st2 = empty_state()
    merge_delta(st2, {"patient": {"weight_kg": 40}})
    para = {f["rule_id"]: f for f in engine.check_prescription(st2, [{"name": "paracetamol", "dose_mg": 1000, "frequency_per_day": 4}], 1)}
    assert "DOSE-PARA-03" in para and "100 mg/kg/day" in para["DOSE-PARA-03"]["message"]


def test_class_list_and_dotted_facts_and_escalation(engine):
    st = empty_state()
    merge_delta(st, {"allergies": [{"substance": "ibuprofen", "reaction": "wheeze", "severity": "moderate"}]})
    assert st["allergies"][0]["class"] == ["nsaid_cox1", "nsaid"]
    fired = engine.check_prescription(st, [{"name": "naproxen", "dose_mg": 250, "frequency_per_day": 2}], 1)
    assert ids(fired) == {"ALG-NSAID-01"}
    # disposition.type (dotted global fact) + escalate_to_critical_if with a plain fact
    st = empty_state()
    merge_delta(st, {"symptoms": ["syncope"]})
    f = next(x for x in engine.evaluate(st, 1) if x["rule_id"] == "WORK-TLOC-01")
    assert f["severity"] == "caution"
    merge_delta(st, {"disposition": "discharge"})
    f = next(x for x in engine.evaluate(st, 1) if x["rule_id"] == "WORK-TLOC-01")
    assert f["severity"] == "critical" and f["escalated"]
    # low-dose aspirin is excluded from PREG-NSAID-01 (drug neq aspirin_low_dose); ibuprofen is not
    st = empty_state()
    merge_delta(st, {"patient": {"pregnant": True, "gestation_weeks": 22}})
    assert "PREG-NSAID-01" not in ids(engine.check_prescription(st, [{"name": "aspirin", "dose_mg": 75, "frequency_per_day": 1}], 1))
    assert "PREG-NSAID-01" in ids(engine.check_prescription(st, [{"name": "ibuprofen", "dose_mg": 400, "frequency_per_day": 3}], 1))


def test_derived_dose_facts(engine):
    fired = ids(engine.check_prescription(empty_state(), [{"name": "levothyroxine", "dose_mg": 100, "frequency_per_day": 1}], 1))
    assert "DOSE-LEVO-01" in fired                                 # 100 mg = 100000 mcg: unit error
    assert engine.check_prescription(empty_state(), [{"name": "levothyroxine", "dose_raw": "100 micrograms", "frequency_per_day": 1}], 1) == []
    assert "DOSE-COAMOX-01" in ids(engine.check_prescription(empty_state(), [{"name": "co-amoxiclav", "dose_raw": "500/125 mg", "frequency_per_day": 4}], 1))
    assert "DOSE-COAMOX-01" not in ids(engine.check_prescription(empty_state(), [{"name": "Augmentin", "dose_mg": 625, "frequency_per_day": 3}], 1))
    adr = engine.check_prescription(empty_state(), [{"name": "epinephrine", "dose_raw": "1 mg/mL 1 mg", "route": "intravenous"}], 1)
    assert ids(adr) == {"DOSE-ADR-01"}
    assert "DOSE-SALB-01" in ids(engine.check_prescription(empty_state(), [{"name": "Ventolin", "puffs": 2, "frequency_per_day": "every 2 hours"}], 1))


def test_evaluate_is_fast(engine, index):
    g = GoldenPath(index)
    g.step2(); g.step3(); g.step4()
    engine.evaluate(g.c.state, 12.0)
    runs = []
    for _ in range(30):
        t = time.perf_counter()
        engine.evaluate(g.c.state, 12.0)
        runs.append(time.perf_counter() - t)
    runs.sort()
    assert runs[len(runs) // 2] < 0.005          # median < 5 ms for 81 rules


# ---------------------------------------------------------------------------- synthetic firing of every rule
_GLOBAL = ("patient.", "vitals.", "disposition.", "elapsed_min_since.")


def _sat(op, value):
    return {"eq": lambda: value, "in": lambda: value[0], "contains_any": lambda: [value[0]], "gt": lambda: value + 1,
            "gte": lambda: value, "lt": lambda: value - 1, "lte": lambda: value, "neq": lambda: "zz_other",
            "not_in": lambda: "zz_other", "exists": lambda: "present"}[op]()


def _set_global(state, fact, op, value):
    if fact.startswith("elapsed_min_since") or op == "not_exists":
        return
    root, key = fact.split(".", 1)
    if root == "disposition":
        state["disposition"]["type"] = _sat(op, value)
    else:
        state[root][key] = _sat(op, value)


def _fill_where(node, item, state):
    if node is None:
        return
    if "all" in node:
        for ch in node["all"]:
            _fill_where(ch, item, state)
    elif "any" in node:
        _fill_where(node["any"][0], item, state)
    elif "fact" in node:
        f, op, v = node["fact"], node["op"], node.get("value")
        if f.startswith(_GLOBAL):
            _set_global(state, f, op, v)
        elif op == "not_exists":
            item.pop(f, None)
        else:
            val = _sat(op, v)
            item[f] = (val if isinstance(val, list) else [val]) if f == "class" else val


def _satisfy(node, state, n):
    if "all" in node:
        for ch in node["all"]:
            _satisfy(ch, state, n)
    elif "any" in node:
        _satisfy(node["any"][0], state, n)
    elif "exists_in" in node:
        coll = node["exists_in"]
        n[0] += 1
        item = {"evidence": [{"utt": f"u{n[0]:03d}", "t_min": 0.0, "quote": f"synthetic quote {n[0]}"}]}
        if coll == "symptoms":
            item["first_mention_min"] = 0.0
        if coll.endswith("meds"):
            item.update({"drug": "zz_drug", "class": [], "dose_mg": None, "frequency_per_day": None})
        if coll == "idiom_hits":
            item.update({"id": "npi-005", "utt": f"u{n[0]:03d}", "t_min": 0.0, "matched": "gyastrik"})
        _fill_where(node.get("where"), item, state)
        state["prescribed_meds" if coll == "all_meds" else coll].append(item)
    elif "fact" in node:
        _set_global(state, node["fact"], node["op"], node.get("value"))


def _synthetic_state(rule):
    st = empty_state()
    _satisfy(rule["trigger"], st, [0])
    return st


@pytest.mark.parametrize("rule_id", [r["id"] for r in json.loads(RULES_PATH.read_text(encoding="utf-8"))["rules"]])
def test_every_rule_fires_with_a_synthetic_state_and_renders_cleanly(engine, rule_id):
    rule = engine.by_id[rule_id]
    st = _synthetic_state(rule)
    fired = {f["rule_id"]: f for f in engine.evaluate(st, 30.0)}
    assert rule_id in fired, f"{rule_id} did not fire on a state built to satisfy it"
    f = fired[rule_id]
    assert "{" not in f["message"] and "}" not in f["message"] and "None" not in f["message"]
    assert set(f) >= {"rule_id", "family", "severity", "message", "rationale", "source_urls", "fire_on",
                      "verification", "evidence", "group", "key"}
    assert f["severity"] in ("info", "caution", "critical") and f["key"].startswith(rule_id)
    assert f["group"] == ("chest_pain_workup" if rule_id.startswith("WORK-CHEST") else f["group"])
    if any(isinstance(v, list) and v for v in st.values()):
        assert f["evidence"], "matched items' evidence must be attached"


def test_message_placeholders_in_file_are_all_supported(engine):
    """Every {placeholder} used anywhere in message_en renders to a value (rule fired on synthetic state)."""
    seen = set()
    for r in engine.rules:
        seen |= set(re.findall(r"\{([^}]*)\}", r["message_en"]))
    assert {"allergy.evidence", "rx.drug", "symptom.evidence", "idiom.romanized", "elapsed"} <= seen
    for r in engine.rules:
        f = next(x for x in engine.evaluate(_synthetic_state(r), 30.0) if x["rule_id"] == r["id"])
        assert not re.search(r"[{}]", f["message"])


# ============================================================================ WORK-CHEST-04 data fix
def test_work_chest_04_requires_chest_symptom(engine):
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rule = next(r for r in raw["rules"] if r["id"] == "WORK-CHEST-04")
    assert rule.get("change_note")
    st = empty_state()
    merge_delta(st, {"idiom_hits": [{"id": "tgl-002", "utt": "u001", "t_min": 0.5, "matched": "kabag"}],
                     "symptoms": [{"code": "abdominal_pain", "first_mention_min": 0.5}]})
    assert "WORK-CHEST-04" not in ids(engine.evaluate(st, 1))          # kabag + stomach ache: no ACS alert
    merge_delta(st, {"symptoms": [{"code": "chest_pressure", "first_mention_min": 0.8}]})
    f = next(x for x in engine.evaluate(st, 1) if x["rule_id"] == "WORK-CHEST-04")
    assert "kabag" in f["message"] and f["key"] == "WORK-CHEST-04|tgl-002"
    merge_delta(st, {"investigations": ["ecg"]})
    assert "WORK-CHEST-04" not in ids(engine.evaluate(st, 1))
    # the JSON keeps its formatting: 2-space indent, CRLF, non-ASCII unescaped
    text = RULES_PATH.read_bytes()
    assert text == json.dumps(raw, indent=2, ensure_ascii=False).replace("\n", "\r\n").encode("utf-8")


# ============================================================================ merge semantics
def test_merge_drug_normalisation_units_and_daily_dose():
    st = empty_state()
    merge_delta(st, {"prescribed_meds": [{"drug": "Panadol", "dose_raw": "1 g", "frequency_per_day": 3},
                                         {"drug": "AUGMENTIN", "dose_mg": 625, "frequency_per_day": "tds"},
                                         {"drug": "levothyroxine sodium", "dose_mg": 100, "unit_raw": "mcg", "frequency_per_day": 1}],
                     "current_meds": [{"drug": "Lisinopril 10 mg tablet", "dose_mg": 10, "frequency_per_day": "once daily"}]})
    meds = {m["drug"]: m for m in st["prescribed_meds"]}
    assert set(meds) == {"paracetamol", "co-amoxiclav", "levothyroxine"}
    assert meds["paracetamol"]["dose_mg"] == 1000 and meds["paracetamol"]["daily_dose_mg"] == 3000
    assert meds["co-amoxiclav"]["class"] == ["penicillin"] and meds["co-amoxiclav"]["daily_dose_mg"] == 1875
    assert meds["co-amoxiclav"]["daily_clavulanate_mg"] == 375
    assert meds["levothyroxine"]["dose_mcg"] == 100 and meds["levothyroxine"]["dose_mg"] == 0.1
    lis = st["current_meds"][0]
    assert lis["drug"] == "lisinopril" and set(lis["class"]) == {"acei", "teratogen"} and lis["daily_dose_mg"] == 10
    # ambiguous unit -> dose unknown rather than guessed
    st2 = empty_state()
    merge_delta(st2, {"prescribed_meds": [{"drug": "amoxicillin", "dose": 500, "frequency_per_day": 3}]})
    assert st2["prescribed_meds"][0]["dose_mg"] is None and st2["prescribed_meds"][0]["daily_dose_mg"] is None


def test_merge_first_mention_earliest_wins_and_dedupe():
    c = Consultation()
    c.set_scenario_time(5.0)
    t = c.add_turn("patient", "ne", "छाती दुख्छ", english="chest hurts")
    merge_delta(c, {"symptoms": [{"code": "chest_pain", "evidence": [{"utt": t.id}]}]})
    s = c.state["symptoms"][0]
    assert s["first_mention_min"] == 5.0 and s["evidence"][0]["quote"] == "छाती दुख्छ" and s["evidence"][0]["t_min"] == 5.0
    merge_delta(c, {"symptoms": [{"code": "chest_pain", "first_mention_t": "00:03:00", "evidence": [{"utt": "u000", "t_min": 3.0, "quote": "earlier"}]}]})
    merge_delta(c, {"symptoms": [{"code": "chest_pain", "first_mention_min": 7.0}]})
    assert len(c.state["symptoms"]) == 1
    assert c.state["symptoms"][0]["first_mention_min"] == 3.0
    assert len(c.state["symptoms"][0]["evidence"]) == 2
    # same allergy twice: one item, evidence merged, known severity never overwritten by unknown
    merge_delta(c, {"allergies": [{"substance": "Penicillins", "reaction": "body swelling", "severity": "severe", "evidence": [{"utt": "u1", "quote": "a"}]}]})
    merge_delta(c, {"allergies": [{"substance": "penicillin", "reaction": None, "severity": "unknown", "evidence": [{"utt": "u2", "quote": "b"}]}]})
    assert len(c.state["allergies"]) == 1
    a = c.state["allergies"][0]
    assert a["severity"] == "severe" and a["reaction"] == "body swelling" and len(a["evidence"]) == 2


def test_merge_never_overwrites_known_with_unknown_and_versioning():
    c = Consultation()
    v0 = c.state_version
    ev = merge_delta(c, {"patient": {"age_years": 29, "pregnant": False, "sex": "F"}, "vitals": {"bp": "128/82", "hr": "96"}})
    assert ev == {"state_change"} and c.state_version == v0 + 1
    assert c.state["patient"]["sex"] == "female" and c.state["vitals"] == {"bp_sys": 128, "bp_dia": 82, "hr": 96}
    ev = merge_delta(c, {"patient": {"age_years": None, "pregnant": "unknown", "sex": "unknown"}, "vitals": {"hr": None}})
    assert ev == set() and c.state_version == v0 + 1
    assert c.state["patient"]["age_years"] == 29 and c.state["patient"]["pregnant"] is False
    assert merge_delta(c, {}) == set()


def test_merge_remove_and_events():
    c = Consultation()
    assert merge_delta(c, {"prescribed_meds": [{"drug": "amoxicillin", "dose_mg": 500, "frequency_per_day": 3}]}) == {"state_change", "on_prescribe"}
    # repeating the same prescription changes nothing
    assert merge_delta(c, {"prescribed_meds": [{"drug": "Amoxil", "dose_mg": 500, "frequency_per_day": 3}]}) == set()
    # a new dose is a material change
    assert "on_prescribe" in merge_delta(c, {"prescribed_meds": [{"drug": "amoxicillin", "dose_mg": 1000, "frequency_per_day": 3}]})
    assert c.state["prescribed_meds"][0]["daily_dose_mg"] == 3000
    # "mention" intent is not a prescription
    assert merge_delta(c, {"prescribed_meds": [{"drug": "ibuprofen", "intent": "mention"}]}) == set()
    ev = merge_delta(c, {"remove": {"prescribed_meds": ["Amoxicillin"]}})
    assert ev == {"state_change"} and c.state["prescribed_meds"] == []
    assert [s["drug"] for s in c.state["stopped_meds"]] == ["amoxicillin"]
    merge_delta(c, {"prescribed_meds": [{"drug": "amoxicillin", "dose_mg": 500, "frequency_per_day": 3}]})
    assert c.state["stopped_meds"] == []                      # re-prescribed
    assert merge_delta(c, {"disposition": {"type": "discharge"}}) == {"state_change", "on_disposition"}
    assert merge_delta(c, {"disposition": {"type": "home"}}) == set()       # same disposition
    assert merge_delta(c, {"disposition": {"type": None}}) == set()         # null never clears it
    assert merge_delta(c, {"disposition": "admit"}) == {"state_change", "on_disposition"}
    # investigation status upgrades, never downgrades
    merge_delta(c, {"investigations": [{"code": "ECG", "status": "resulted", "result": "normal"}]})
    merge_delta(c, {"investigations": [{"code": "ecg_12lead", "status": "ordered"}]})
    assert c.state["investigations"] == [{"code": "ecg_12lead", "status": "resulted", "result": "normal", "evidence": []}]
    # idiom hits deduped by id
    merge_delta(c, {"idiom_hits": [{"id": "npi-005", "utt": "u1", "t_min": 1.0}, {"id": "npi-005", "utt": "u9", "t_min": 9.0}]})
    assert len(c.state["idiom_hits"]) == 1 and c.state["idiom_hits"][0]["t_min"] == 1.0


def test_normalise_med_talk_loop_shape():
    m = normalise_med({"name": "Brufen", "dose_mg": 400, "frequency_per_day": 3, "intent": "prescribe"})
    assert m["drug"] == "ibuprofen" and m["daily_dose_mg"] == 1200 and "nsaid_cox1" in m["class"]


# ============================================================================ vocab
def _harvest(node, coll, out):
    if isinstance(node, list):
        for n in node:
            _harvest(n, coll, out)
    elif isinstance(node, dict):
        q = node.get("exists_in") or node.get("none_in")
        if q:
            _harvest(node.get("where"), q, out)
        for k in ("all", "any", "none"):
            _harvest(node.get(k), coll, out)
        if node.get("fact") == "code":
            out.setdefault(coll, set()).update(node["value"] if isinstance(node["value"], list) else [node["value"]])


def test_vocab_codes_cover_every_rule_code():
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    out: dict[str, set] = {}
    for r in raw["rules"]:
        _harvest(r["trigger"], None, out)
        _harvest(r.get("escalate_to_critical_if"), None, out)
    c = vocab.codes()
    assert set(c) == {"symptoms", "investigations", "interventions", "assessments", "disposition", "idiom_tags"}
    for coll, codes in out.items():
        assert codes <= set(c[coll]), coll
    assert {"chest_burning", "dizziness", "sore_throat"} <= set(c["symptoms"])
    assert {"ecg_12lead", "troponin", "troponin_hs"} <= set(c["investigations"])
    assert set(c["disposition"]) == {"discharge", "admit", "refer", "observe"}
    assert {"acs", "suicidality", "gi_bleed"} <= set(c["idiom_tags"])


def test_vocab_drug_normalisation():
    brands = json.loads(RULES_PATH.read_text(encoding="utf-8"))["meta"]["brand_aliases_examples"]
    for brand, inn in brands.items():
        if not brand.startswith("_"):
            assert vocab.normalise_drug(brand) == inn and vocab.normalise_drug(brand.upper()) == inn
    assert vocab.normalise_drug("acetaminophen") == "paracetamol"
    assert vocab.normalise_drug("Amoxicillin 500 mg capsules") == "amoxicillin"
    assert vocab.normalise_drug("metformin hydrochloride") == "metformin"
    assert vocab.classes_of("penicillins") == ["penicillin"]
    assert vocab.classes_of("cefalexin") == ["cephalosporin_aminopenicillin_like_R1"]
    assert vocab.classes_of("co-amoxiclav") == ["penicillin"]
    assert vocab.classes_of("sulfa") == ["sulfonamide_antibiotic"]
