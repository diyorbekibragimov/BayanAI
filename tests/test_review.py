"""General clinical review: running case summary, transcript-quoted concerns (no predefined-id cage), the curator's
attention budget, and the consent record. Offline: fake extractor (llm.set_backend) + scripted smolagents model."""

from __future__ import annotations

import json

import pytest

from bayan import copilot as ui_copilot
from bayan.brain import agentkit, copilot, curator, extract, llm, merge
from bayan.brain.cards import quote_in_turn
from bayan.brain.state import Consultation

# The user's live failure (Russian patient, English doctor), as the talk loop records it.
NASAL = [
    ("patient", "ru", "У меня болит попа.", "My butt hurts."),
    ("patient", "ru", "Я сидел на холодной плитке, застудил попу.", "I sat on cold tiles and chilled my butt."),
    ("patient", "ru", "Мне холодно в сердце, кажется, у меня нет настроения.",
     "I feel cold in my heart, I think I have no mood."),
    ("doctor", "en", "I think it should be your nose. I'm gonna give you nasal sprays every day for the next three "
                     "weeks after lunch and after dinner.", ""),
    ("patient", "ru", "Зачем мне это? Мне нужно использовать его в попу?",
     "Why do I need this? Am I supposed to use it in my butt?"),
    ("doctor", "en", "You are not cold, you are very hot and have a really high temperature.", ""),
]


def _case_backend(messages, schema, max_tokens) -> str:
    """Fake extractor: the case delta a correct extraction returns for the NASAL turns."""
    user = messages[-1]["content"]
    new = user.split("NEW TURNS (extract from these):", 1)[1].split("\n\nquestion topics:", 1)[0]
    case: dict = {}
    for line in new.strip().splitlines():
        utt, low = line.split()[0], line.lower()

        def ev(q):
            return [{"utt": utt, "quote": q}]
        if "my butt hurts" in low:
            case["chief_complaint"] = {"text": "pain in the buttocks", "evidence": ev("My butt hurts")}
        if "cold tiles" in low:
            case.setdefault("history", []).append({"text": "sat on cold tiles before it started", "present": True,
                                                   "evidence": ev("I sat on cold tiles")})
        if "no mood" in low:
            case["patient_affect"] = [{"text": "feels cold in the heart, low mood", "evidence": ev("no mood")}]
        if "nasal sprays" in low:
            case["working_diagnosis"] = [{"text": "problem is in the nose", "evidence": ev("it should be your nose")}]
            case["plan"] = [{"type": "medicine", "text": "nasal spray daily after lunch and dinner for three weeks",
                             "evidence": ev("nasal sprays every day")}]
        if "in my butt" in low:
            case["patient_understanding"] = [{"text": "asks if the spray goes in the buttocks",
                                              "evidence": ev("use it in my butt")}]
        if "high temperature" in low:
            case["exam_claims"] = [{"text": "says the patient has a very high temperature",
                                    "evidence": ev("really high temperature")}]
    return json.dumps({"case": case} if case else {})


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("BAYAN_AGENT", "on")
    llm.set_backend(_case_backend)
    agentkit.set_model_factory(lambda: agentkit.scripted_model([[("final_answer", {"cards": []})]]))
    yield
    llm.set_backend(None)
    agentkit.set_model_factory(None)


def _consult(lang="ru"):
    c = Consultation(patient_lang=lang)
    copilot.attach(c)
    return c


def _say(c, role, lang, text, english="", t=None):
    c.set_scenario_time(t if t is not None else (len(c.turns) + 1) * 0.5)
    turn = c.add_turn(role, lang, text, english=english or text)
    return turn, copilot.think_now(c)


def _agent(*steps):
    agentkit.set_model_factory(lambda: agentkit.scripted_model(list(steps)))


def _concern(**kw):
    base = {"kind": "observation", "dimension": "plan", "severity": "caution", "confidence": 0.85,
            "title": "Nasal spray does not fit buttock pain",
            "body": "The complaint is buttock pain after sitting on cold tiles; a nasal spray treats neither."}
    base.update(kw)
    return base


# ------------------------------------------------------------------ the cage must not come back
def test_transcript_quoted_concern_outside_checklist_is_shown_and_unquoted_is_rejected():
    """No rule, idiom or checklist item covers "nasal spray for buttock pain". A concern that quotes the transcript is
    accepted and shown; the same concern without a quote, or with an invented one, is rejected and never shown."""
    c = _consult()
    for role, lang, text, en in NASAL[:3]:
        _say(c, role, lang, text, en)
    assert copilot._checklist(c) == [] or all("nose" not in str(i).lower() for i in copilot._checklist(c))
    # unquoted (bare utterance ids) and invented quote: rejected, nothing on screen
    _agent([("final_answer", {"cards": [_concern(evidence=["u001", "u004"])]})],
           [("final_answer", {"cards": [_concern(evidence=[{"utt": "u004", "quote": "spray it in your bottom"}])]})])
    _, s = _say(c, *NASAL[3])
    assert not [x for x in c.cards.all_cards() if x["source"] == "agent"]
    assert all(r.startswith("rejected") for r in s["curation"])
    reasons = [a["reason"] for a in c.audit if a["action"] == "rejected"]
    assert any("no quote" in r for r in reasons) and any("not found in the transcript" in r for r in reasons)
    # quoted (no ref id at all): accepted, shown, grounded in the review dimension
    _agent([("final_answer", {"cards": [_concern(evidence=[{"utt": "u001", "quote": "My butt hurts"},
                                                           {"utt": "u004", "quote": "nasal sprays every day"}])]})])
    _, s = _say(c, *NASAL[4])
    shown = [x for x in c.cards.all_cards() if x["source"] == "agent"]
    assert len(shown) == 1 and shown[0]["status"] == "open" and s["curation"] == [shown[0]["id"]]
    assert shown[0]["grounding"] == "plan" and shown[0]["dimension"] == "plan"
    assert [e["quote"] for e in shown[0]["evidence"]] == ["My butt hurts", "nasal sprays every day"]
    assert {"kind": "observation", "text": "Nasal spray does not fit buttock pain", "id": shown[0]["id"]} \
        in ui_copilot.notes(c)


def test_quote_check_is_normalised_but_real():
    t = Consultation().add_turn("patient", "ru", "Мне нужно использовать его в попу?",
                                english="Am I supposed to use it in my butt?")
    assert quote_in_turn(t, "am i supposed to use it in my butt")
    assert quote_in_turn(t, "“Am I supposed to use it… in my butt?”")
    assert quote_in_turn(t, "использовать его в попу")              # the words as said
    assert not quote_in_turn(t, "use it in my nose")
    assert not quote_in_turn(t, "my bu")                             # whole words only
    assert not quote_in_turn(t, "")


def test_agent_sees_case_summary_and_runs_on_substantive_doctor_turns():
    seen = []

    def factory():
        m = agentkit.scripted_model([[("final_answer", {"cards": []})]])
        seen.append(m)
        return m

    agentkit.set_model_factory(factory)
    c = _consult()
    for role, lang, text, en in NASAL:
        _say(c, role, lang, text, en)
    case = c.state["case"]
    assert case["chief_complaint"]["text"] == "pain in the buttocks"
    assert case["plan"][0]["type"] == "medicine" and "nasal spray" in case["plan"][0]["text"]
    assert case["exam_claims"] and case["patient_understanding"] and case["patient_affect"]
    assert case["working_diagnosis"][0]["evidence"][0]["utt"] == "u004"
    assert len(seen) == len(NASAL)                       # every substantive turn, doctor statements included
    task = "\n".join(str(getattr(m, "content", m)) for m in seen[-1].seen_messages[0][1:])
    assert "Chief complaint: pain in the buttocks (u001)" in task
    assert "Plan: medicine: nasal spray daily after lunch and dinner for three weeks (u004)" in task
    assert "Findings the doctor states: says the patient has a very high temperature (u006)" in task
    diff = [t["text"] for t in c.trace if t["text"].startswith("update_state →")]
    assert any("plan: nasal spray" in d for d in diff) and any("affect: feels cold" in d for d in diff)


def test_courtesy_turns_and_waiting_questions_do_not_run_the_review():
    runs = []
    agentkit.set_model_factory(lambda: runs.append(1) or agentkit.scripted_model([[("final_answer", {"cards": []})]]))
    c = _consult()
    _say(c, "doctor", "en", "Does it hurt when you sit?")             # waits for the answer
    _say(c, "patient", "ru", "Спасибо, доктор.", "Okay, thank you, doctor.")
    assert runs == []
    _say(c, "patient", "ru", "Да, очень.", "Yes, a lot.")             # the answer: reviewed with the question
    assert runs == [1]


def test_case_merge_dedupes_and_tracks_changes():
    c = _consult()
    t1 = c.add_turn("patient", "ru", "x", english="My butt hurts.", t_min=1.0)
    t2 = c.add_turn("patient", "ru", "y", english="It is worse when I sit.", t_min=2.0)
    ev1, ev2 = [{"utt": t1.id, "quote": "My butt hurts"}], [{"utt": t2.id, "quote": "worse when I sit"}]
    assert merge.merge_delta(c, {"case": {"chief_complaint": {"text": "buttock pain", "evidence": ev1},
                                          "history": [{"text": "worse when sitting", "present": True,
                                                       "evidence": ev2}]}})
    assert not merge.merge_delta(c, {"case": {"history": [{"text": "Worse when sitting.", "present": True,
                                                           "evidence": ev2}]}})     # same item: no change
    merge.merge_delta(c, {"case": {"history": [{"text": "worse when sitting", "present": False, "evidence": ev1}]}})
    hx = c.state["case"]["history"]
    assert len(hx) == 1 and hx[0]["present"] is False and len(hx[0]["evidence"]) == 2
    merge.merge_delta(c, {"case": {"chief_complaint": {"text": "low mood", "evidence": ev2}}})
    assert c.state["case"]["chief_complaint"]["text"] == "low mood"
    assert c.state["case"]["history"][-1]["text"] == "earlier complaint: buttock pain"
    txt = extract.case_text(c.state)
    assert txt.splitlines()[0] == "Chief complaint: low mood (u002)" and "- worse when sitting (u002, u001)" in txt


def test_clean_case_keeps_unknown_shapes_out():
    c = _consult()
    t = c.add_turn("doctor", "en", "Nasal spray twice a day.", t_min=1.0)
    d = extract.clean_delta({"case": {"plan": [{"type": "weird", "text": "nasal spray twice a day",
                                                "evidence": [{"utt": "u999", "quote": "x"}]}, {"text": ""}],
                                      "patient_affect": ["very worried"], "chief_complaint": None}}, c, [t])
    assert d["case"]["plan"] == [{"text": "nasal spray twice a day", "type": "advice",
                                  "evidence": [{"utt": t.id, "t_min": 1.0, "quote": "Nasal spray twice a day."}]}]
    assert d["case"]["patient_affect"][0]["text"] == "very worried"
    assert "chief_complaint" not in d["case"]


# ------------------------------------------------------------------ curator: the attention budget
def _turns(c, n):
    for i in range(n):
        c.add_turn("patient" if i % 2 else "doctor", "en", f"Sentence number {i} about knee pain and swelling.",
                   t_min=float(i))


def _cand(utt, title, kind="observation", dim="plan", conf=0.8, sev="caution", ask=None):
    return {"kind": kind, "dimension": dim, "title": title, "body": title, "severity": sev, "confidence": conf,
            "evidence": [{"utt": utt, "quote": "knee pain"}], "ask_text": ask}


def test_curator_one_new_card_per_turn_threshold_and_merge():
    c = _consult()
    _turns(c, 4)
    res = curator.offer(c, [_cand("u004", "Painkiller dose missing", conf=0.7),
                            _cand("u004", "Swelling not examined", dim="safety", conf=0.9),
                            _cand("u004", "Minor wording issue", dim="communication", conf=0.3, sev="info"),
                            _cand("u004", "Knee not examined at all", dim="safety", conf=0.6)])
    assert res[1].startswith("c") and res[0].startswith("held back: one new card per turn")
    assert res[2].startswith("held back: score 0.30 < 0.40")      # communication weighs as caution: 1.0 x 0.3
    assert res[3] == f"duplicate (merged into {res[1]})"          # same theme as the card just posted
    assert c.cards.get(res[1])["body"] == "Swelling not examined Also: Knee not examined at all."
    assert {e["utt"] for e in c.cards.get(res[1])["evidence"]} == {"u004"}
    # same dimension + overlapping evidence: merged into the card on screen, its second point kept in the body
    res = curator.offer(c, [_cand("u004", "Knee swelling never looked at", dim="safety", conf=0.95)])
    assert res == [f"duplicate (merged into {c.cards.open_cards()[0]['id']})"]
    card = c.cards.open_cards()[0]
    assert card["body"].endswith("Also: Knee swelling never looked at.") and card["confidence"] == 0.95
    assert len([x for x in c.cards.all_cards() if x["source"] == "agent"]) == 1


def test_curator_exactly_one_ask_next_replaced_not_stacked():
    c = _consult()
    _turns(c, 2)
    a = curator.offer(c, [_cand("u002", "Ask about injury", "ask", "history", 0.8, "info",
                                "Did you fall or twist your knee?")])[0]
    assert a.startswith("c")
    _turns(c, 4)                                           # the conversation moves on: the old question decays
    b = curator.offer(c, [_cand("u006", "Ask about fever", "ask", "safety", 0.9, "caution",
                                "Do you have a fever or chills?")])[0]
    assert b.startswith("c")
    asks = [x for x in c.cards.all_cards() if x["kind"] == "ask"]
    assert [x["status"] for x in asks] == ["resolved", "open"]
    assert [s["text"] for s in ui_copilot.suggest(c) if s["status"] == "open"] == ["Do you have a fever or chills?"]
    # a weaker question does not displace the open one
    r = curator.offer(c, [_cand("u006", "Ask about job", "ask", "history", 0.75, "info", "What work do you do?")])[0]
    assert r.startswith("held back: score 0.45 < 0.62")          # two questions shown, none used: 0.4 x 1.25^2


def test_curator_visible_budget_dismissed_theme_and_resolution():
    c = _consult()
    for i, (title, dim) in enumerate([("Painkiller dose missing", "plan"), ("Swelling not examined", "safety"),
                                      ("Fever claim not measured", "consistency"),
                                      ("Patient unsure how to rest", "communication"),
                                      ("Antibiotic without a reason", "plan")]):
        _turns(c, 1)
        uid = c.turns[-1].id
        curator.offer(c, [_cand(uid, title, dim=dim)])
    agent_open = [x for x in c.cards.open_cards() if x["source"] == "agent"]
    assert len(agent_open) == curator.MAX_VISIBLE == 4
    assert "Painkiller dose missing" not in [x["title"] for x in agent_open]       # the oldest was retired
    # the doctor dismisses a card: its theme stays suppressed for the visit
    victim = next(x for x in agent_open if x["title"] == "Fever claim not measured")
    c.cards.act(victim["id"], "dismiss", user="doctor")
    _turns(c, 1)
    r = curator.offer(c, [_cand(c.turns[-1].id, "Fever claimed but not measured", dim="consistency")])[0]
    assert r.startswith("rejected: the doctor dismissed a similar card")
    # the reviewer reports a card as addressed: it resolves
    cid = next(x["id"] for x in c.cards.open_cards() if x["title"] == "Swelling not examined")
    curator.offer(c, [], addressed=[cid])
    assert c.cards.get(cid)["status"] == "resolved"


def test_doctor_asking_the_same_thing_resolves_the_ask_next():
    c = _consult()
    _turns(c, 2)
    cid = curator.offer(c, [_cand("u002", "Ask about fever", "ask", "safety", 0.9, "caution",
                                  "Have you had a fever or chills?")])[0]
    t = c.add_turn("doctor", "en", "Does your knee hurt more at night?", t_min=3.0)
    assert curator.resolve_asked(c, [t]) == []                   # another topic
    t = c.add_turn("doctor", "en", "Any fever at home?", t_min=3.5)
    assert curator.resolve_asked(c, [t]) == [cid]
    assert c.cards.get(cid)["status"] == "resolved"


def test_agent_addressed_ids_resolve_cards_through_final_answer():
    c = _consult()
    for role, lang, text, en in NASAL[:4]:
        _say(c, role, lang, text, en)
    cid = c.cards.post("observation", "Nasal spray does not fit", "b", [{"utt": "u004"}], "plan", source="agent")
    _agent([("final_answer", {"cards": [], "addressed": [cid]})])
    _say(c, "doctor", "en", "Sorry, I meant a cream for the buttock, not a nose spray.")
    assert c.cards.get(cid)["status"] == "resolved"


def test_agent_never_critical_and_rules_unaffected():
    c = _consult("ne")
    _agent([("final_answer", {"cards": [_concern(severity="critical",
                                                 evidence=[{"utt": "u001", "quote": "My butt hurts"}])]})])
    _say(c, *NASAL[0])
    assert not [x for x in c.cards.all_cards() if x["source"] == "agent"]
    assert any("rule engine" in (a["reason"] or "") for a in c.audit if a["action"] == "rejected")


# ------------------------------------------------------------------ consent: one source of truth
def test_consent_record_is_the_sentence_shown_and_spoken(monkeypatch, tmp_path):
    from bayan import consult, ui
    from bayan.brain import wrapup
    monkeypatch.setenv("BAYAN_OUTPUT_ROOT", str(tmp_path))
    assert consult.CONSENT_EN == ui.t("en", "consent_doc")        # the doctor's screen shows ui "consent_doc"
    assert "not stored" in consult.CONSENT_EN
    sid = consult.new_sid()
    s = consult.SESS[sid]
    s.lang, s.screen = "ne", "live"
    consult.begin(s)
    s.consent_native = consult.consent_text("ne")
    assert "भण्डारण गरिँदैन" in s.consent_native                 # Nepali says "not stored" too
    consult.record_consent(s)
    t = s.brain.turns[0]
    assert t.text == s.consent_native and t.english == f"Consent: {consult.CONSENT_EN}"
    assert s.brain.outputs["consent"]["en"] == consult.CONSENT_EN
    assert wrapup._consent(s.brain) == "Agreed"           # one word in the PDF panel; the sentence is in the transcript
    v = consult.view(s)
    assert v["consent"]["en"] == consult.CONSENT_EN
    consult.SESS.pop(sid, None)


# ------------------------------------------------------------------ refinements from the first live run
def test_asks_are_suggestions_and_different_questions_do_not_merge():
    c = _consult()
    _turns(c, 2)
    a = curator.offer(c, [_cand("u002", "Ask about injury", "ask", "safety", 0.95, "caution",
                                "Did you fall or twist your knee?")])[0]
    assert c.cards.get(a)["severity"] == "info"                     # a question is never a warning
    _turns(c, 3)
    b = curator.offer(c, [_cand("u005", "Ask about swallowing", "ask", "safety", 0.95, "info",
                                "Do you have trouble swallowing?")])[0]
    assert b.startswith("c") and c.cards.get(a)["status"] == "resolved"   # replaced, not merged into the first


def test_second_point_of_the_same_review_becomes_an_also_line():
    c = _consult()
    _turns(c, 4)
    res = curator.offer(c, [_cand("u004", "Antibiotic likely unnecessary", conf=0.9),
                            _cand("u004", "No antibiotic name or dose", conf=0.8)])
    assert res[0].startswith("c") and res[1] == f"duplicate (merged into {res[0]})"
    assert c.cards.get(res[0])["body"].endswith("Also: No antibiotic name or dose.")
    # in a LATER review, a different point about the same words is its own card (if the budget allows)
    _turns(c, 1)
    r = curator.offer(c, [_cand("u004", "Course length is too long", conf=0.9)])[0]
    assert r.startswith("c")


def test_dimension_written_into_kind_is_repaired():
    c = _consult()
    for role, lang, text, en in NASAL[:5]:
        _say(c, role, lang, text, en)
    res = copilot.post_cards(c, [{"kind": "communication", "title": "Patient unsure where to use the spray",
                                  "body": "b", "severity": "caution", "confidence": 0.9,
                                  "evidence": [{"utt": "u005", "quote": "use it in my butt"}]}])
    card = c.cards.get(res[0])
    assert card["kind"] == "observation" and card["dimension"] == "communication"


def test_swahili_patients_match_swahili_idioms_and_wrapup_tags_have_plain_labels():
    from bayan.brain import idioms, wrapup
    assert idioms._LANG["sw"] == "swh"
    tags = {t for e in idioms.IdiomIndex().entries for t in e.get("red_flag_tags") or []}
    assert {"suicidality", "sepsis_infection", "ectopic_pregnancy", "metabolic"} <= tags
    for t in tags:
        assert t in wrapup._TAG_TEXT and t in wrapup._TAG_PLAIN, t


def test_same_dimension_is_not_a_checklist_id_for_card_dedupe():
    """Live-run bug: the dimension (now the grounding of quoted concerns) was treated like a checklist id, so a
    second, different "plan" concern came back "duplicate" from CardStore and never showed."""
    c = _consult()
    _turns(c, 3)
    a = c.cards.post("missed", "No antibiotic name or dose", "b", [{"utt": "u003"}], "plan", source="agent")
    b = c.cards.post("missed", "Antibiotic not indicated", "b", [{"utt": "u003"}], "plan", source="agent")
    assert a.startswith("c") and b.startswith("c")


def test_same_concern_restated_under_another_dimension_is_merged():
    """Live run: 'Nose vs butt pain mismatch' (consistency) was followed by 'Nasal spray for butt pain' (plan)."""
    c = _consult()
    for role, lang, text, en in NASAL[:4]:
        c.add_turn(role, lang, text, english=en or text)
    ev = [{"utt": "u001", "quote": "My butt hurts"}, {"utt": "u004", "quote": "it should be your nose"}]
    a = curator.offer(c, [{"kind": "observation", "dimension": "consistency", "title": "Nose vs butt pain mismatch",
                           "body": "The doctor attributes the butt pain to the nose.", "severity": "caution",
                           "confidence": 0.9, "evidence": ev}])[0]
    c.add_turn("patient", "ru", "x", english="Why do I need this? Am I supposed to use it in my butt?")
    r = curator.offer(c, [{"kind": "observation", "dimension": "plan", "title": "Nasal spray for butt pain",
                           "body": "The nasal spray does not address the butt pain.", "severity": "caution",
                           "confidence": 0.85, "evidence": ev}])[0]
    assert r == f"duplicate (merged into {a})"


# ------------------------------------------------------------------ round 2: original words, required case fields, recency floor
def test_prompts_label_the_original_words_and_the_rendering():
    seen = []

    def factory():
        m = agentkit.scripted_model([[("final_answer", {"cards": []})]])
        seen.append(m)
        return m

    agentkit.set_model_factory(factory)
    prompts = []
    llm.set_backend(lambda m, s, n: (prompts.append(m[-1]["content"]), _case_backend(m, s, n))[1])
    c = _consult()
    _say(c, *NASAL[2])
    line = "u001 [00:30] PATIENT said (ru): Мне холодно в сердце, кажется, у меня нет настроения. | EN rendering: " \
           "I feel cold in my heart, I think I have no mood."
    assert line in prompts[-1]
    task = "\n".join(str(getattr(m, "content", m)) for m in seen[-1].seen_messages[0][1:])
    assert line in task
    system = str(getattr(seen[-1].seen_messages[0][0], "content", ""))
    assert "Judge the ORIGINAL meaning" in system


def test_case_understanding_and_affect_are_required_and_none_is_dropped():
    sch = extract.EXTRACT_SCHEMA
    assert "case" in sch["required"] and list(sch["properties"])[0] == "case"
    assert set(sch["properties"]["case"]["required"]) == {"patient_understanding", "patient_affect", "exam_claims"}
    assert list(sch["properties"]["case"]["properties"])[:3] == ["patient_affect", "patient_understanding",
                                                                 "exam_claims"]
    c = _consult()
    t = c.add_turn("patient", "ru", "Хорошо.", english="Okay.", t_min=1.0)
    d = extract.clean_delta({"case": {"patient_affect": [{"text": "None observed."}],
                                      "patient_understanding": []}}, c, [t])
    assert "case" not in d


def test_unaddressed_concern_keeps_a_recency_floor_but_questions_decay():
    c = _consult()
    _turns(c, 6)                      # the quoted turn u001 is 5 turns old: 0.8**5 = 0.33
    concern = _cand("u001", "Hopelessness never explored", dim="communication", conf=0.7)
    ask = _cand("u001", "Ask about bladder control", "ask", "safety", 0.9, "info", "Can you control your bladder?")
    s1, p1 = curator.score(c, concern, [])
    s2, p2 = curator.score(c, ask, [])
    assert p1["recency"] == 0.6 and s1 == pytest.approx(0.42) and s1 >= curator.THRESHOLD
    assert p2["recency"] == pytest.approx(0.33, abs=0.01) and s2 < curator.THRESHOLD



# ------------------------------------------------------------------ round 3: question budget, dimension weight
def test_unused_questions_raise_the_bar_and_a_used_one_resets_it():
    c = _consult()
    _turns(c, 2)
    q1 = curator.offer(c, [_cand("u002", "Ask about injury", "ask", "safety", 0.9, "info", "Did you fall?")])[0]
    assert curator.ask_threshold(c.cards.all_cards()) == pytest.approx(0.5)       # 1 shown, not used
    _turns(c, 1)
    q2 = curator.offer(c, [_cand("u003", "Ask about fever", "ask", "safety", 0.9, "info", "Any fever?")])[0]
    assert q2.startswith("c") and c.cards.get(q1)["status"] == "resolved"        # superseded = not used
    assert curator.ask_threshold(c.cards.all_cards()) == pytest.approx(0.625)
    _turns(c, 1)
    r = curator.offer(c, [_cand("u004", "Ask about work", "ask", "history", 0.95, "info", "What work do you do?")])[0]
    assert r.startswith("held back: score 0.57 < 0.62")
    # a safety / communication question is exempt from the raised bar (it still has to beat the open Ask-next)
    r = curator.offer(c, [_cand("u004", "Ask about mood", "ask", "communication", 0.95, "info",
                                "How has your mood been?")])[0]
    assert r.startswith("c") and c.cards.get(q2)["status"] == "resolved"
    q2 = r
    t = c.add_turn("doctor", "en", "How has your mood been lately?", t_min=9.0)    # the doctor uses it
    assert curator.resolve_asked(c, [t]) == [q2]
    assert curator.ask_threshold(c.cards.all_cards()) == pytest.approx(curator.THRESHOLD)


def test_safety_and_communication_concerns_weigh_as_caution_questions_do_not():
    c = _consult()
    _turns(c, 2)
    mood = _cand("u002", "Low mood not addressed", dim="communication", conf=0.8, sev="info")
    hist = _cand("u002", "Occupation not asked", dim="history", conf=0.8, sev="info")
    q = _cand("u002", "Ask about mood", "ask", "communication", 0.8, "info", "How is your mood?")
    assert curator.score(c, mood, [])[0] == pytest.approx(0.8)
    assert curator.score(c, hist, [])[0] == pytest.approx(0.48)
    assert curator.score(c, q, [])[0] == pytest.approx(0.48)
