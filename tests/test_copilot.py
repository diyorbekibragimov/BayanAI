"""Copilot think loop, prescription gate, agent guardrails and fallbacks: offline (fake LLM + fake smolagents model).

GOLDEN_TURNS / golden_backend / golden_agent_factory are reused by scripts/smoke_copilot.py for an offline demo.
"""

from __future__ import annotations

import json
import time

import pytest

from bayan.brain import agentkit, copilot, extract, llm
from bayan.brain.state import Consultation

# ------------------------------------------------------------------ golden path (docs/02 §8, docs/09 §2.2)
GOLDEN_TURNS = [
    # (t_min, role, lang, text, english, talk-loop drugs JSON)
    (1.0, "doctor", "en", "Hello, I'm Dr Sara. What brings you in today?", "", []),
    (1.2, "patient", "ne", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ। खाना खाएपछि सुरु भयो, अनि रिँगटा लागेको छ।",
     "My chest is burning, like gyastrik (gastric). It started after lunch, and I feel dizzy.", []),
    (2.0, "doctor", "en", "Do you work outdoors? Are you allergic to any medicine?", "", []),
    (2.3, "patient", "ne", "हो, म बाहिर साइटमा काम गर्छु। एक पटक पेनिसिलिनको सुई लगाउँदा मेरो जिउ सुन्निएको थियो। "
     "अनि तीन दिनदेखि घाँटी दुखेको छ।",
     "Yes, I work outside on a site. Once, after a penicillin injection, my body swelled up. And my throat has "
     "hurt for three days.", []),
    ("tick", 11.5),
    (12.0, "doctor", "en", "It's probably just gastric, and a throat infection. I'll give you amoxicillin five "
     "hundred milligrams three times a day for your throat, and you can go home.", "",
     [{"name": "amoxicillin", "dose_mg": 500, "frequency_per_day": 3, "intent": "prescribe"}]),
    ("ack", 12.5),
    (13.0, "doctor", "en", "Actually, no amoxicillin. Your throat looks viral. Before you go, we'll check your blood "
     "pressure, do a heart tracing, and a blood test for the heart called troponin.", "",
     [{"name": "amoxicillin", "dose_mg": None, "frequency_per_day": None, "intent": "stop"}]),
    (75.0, "doctor", "en", "Your blood pressure is one twenty-eight over eighty-two, your heart tracing is normal, "
     "and the troponin test is normal.", "", []),
    (76.0, "doctor", "en", "Take paracetamol, one gram, up to three times a day, for your throat. Drink plenty of "
     "water and rest out of the sun for two days. If the chest pain comes back, spreads to your arm or jaw, you feel "
     "faint or sweaty, or you vomit blood or pass black stools, call 999 or come straight back.", "",
     [{"name": "paracetamol", "dose_mg": 1000, "frequency_per_day": 3, "intent": "prescribe"}]),
    (77.0, "patient", "ne", "हुन्छ, धन्यवाद डाक्टर।", "Okay, thank you, doctor.", []),
]


def _new_section(messages) -> list[tuple[str, str]]:
    user = messages[-1]["content"]
    sec = user.split("NEW TURNS (extract from these):", 1)[1].split("\n\nquestion topics:", 1)[0]
    return [(ln.split()[0], ln.lower()) for ln in sec.strip().splitlines() if ln.strip()]


def golden_backend(messages, schema, max_tokens) -> str:
    """Scripted extractor: the delta a correct gpt-oss extraction returns for each golden-path turn."""
    out: dict = {}

    def ev(utt, q):
        return [{"utt": utt, "quote": q}]

    for utt, low in _new_section(messages):
        if "chest is burning" in low:
            out.setdefault("symptoms", []).extend([
                {"code": "chest_burning", "onset": "after lunch", "evidence": ev(utt, "My chest is burning, like gyastrik")},
                {"code": "dizziness", "evidence": ev(utt, "I feel dizzy")}])
        if "allergic to any medicine" in low:
            out["questions_asked"] = [{"topic": "allergies"}, {"topic": "work_heat_exposure"}]
        if "penicillin injection" in low:
            out["allergies"] = [{"substance": "penicillin", "reaction": "body swelling", "severity": "severe",
                                 "evidence": ev(utt, "after a penicillin injection, my body swelled up")}]
            out["patient"] = {"heat_exposure": True, "evidence": ev(utt, "I work outside on a site")}
            out.setdefault("symptoms", []).append({"code": "sore_throat", "onset": "3 days",
                                                   "evidence": ev(utt, "my throat has hurt for three days")})
        if "i'll give you amoxicillin" in low:
            out["prescribed_meds"] = [{"drug": "amoxicillin", "dose_mg": 500, "frequency_per_day": 3,
                                       "indication": "throat infection",
                                       "evidence": ev(utt, "I'll give you amoxicillin five hundred milligrams three times a day")}]
            out["disposition"] = {"type": "discharge", "evidence": ev(utt, "you can go home")}
        if "actually, no amoxicillin" in low:
            out["remove"] = {"prescribed_meds": ["amoxicillin"]}
            out["investigations"] = [
                {"code": "ecg_12lead", "status": "ordered", "evidence": ev(utt, "do a heart tracing")},
                {"code": "troponin", "status": "ordered", "evidence": ev(utt, "a blood test for the heart called troponin")}]
        if "blood pressure is one twenty-eight" in low:
            out["vitals"] = {"bp_sys": 128, "bp_dia": 82, "evidence": ev(utt, "one twenty-eight over eighty-two")}
            out["investigations"] = [
                {"code": "ecg_12lead", "status": "resulted", "result": "normal", "evidence": ev(utt, "heart tracing is normal")},
                {"code": "troponin", "status": "resulted", "result": "normal", "evidence": ev(utt, "troponin test is normal")}]
        if "take paracetamol" in low:
            out["prescribed_meds"] = [{"drug": "paracetamol", "dose_mg": 1000, "amount": 1, "unit": "g",
                                       "frequency_per_day": 3, "as_needed": True, "max_per_day": 3,
                                       "as_needed_for": "throat pain",
                                       "evidence": ev(utt, "Take paracetamol, one gram, up to three times a day")}]
        # medication-instruction sentences (care plan): what a correct extraction returns
        if "one capsule three times a day after food" in low:
            out["prescribed_meds"] = [{"drug": "amoxicillin", "dose_mg": 500, "dose_raw": "500 milligrams",
                                       "form": "capsules", "amount": "one", "unit": "capsule", "frequency_per_day": 3,
                                       "food": "after meals", "duration_days": 5,
                                       "evidence": ev(utt, "one capsule three times a day after food for five days")}]
        if "two sprays in each nostril" in low:
            out["prescribed_meds"] = [{"drug": "nasal spray", "form": "nose spray", "amount": "two", "unit": "sprays",
                                       "site": "each nostril", "times": ["when you wake up"], "frequency_per_day": 1,
                                       "duration_text": "one month",
                                       "evidence": ev(utt, "two sprays in each nostril every morning when you wake up")}]
        if "omeprazole 20 mg every morning before breakfast" in low:
            out["prescribed_meds"] = [{"drug": "omeprazole", "dose_mg": 20, "times": ["morning"],
                                       "food": "before breakfast", "duration_days": 14,
                                       "evidence": ev(utt, "Omeprazole 20 mg every morning before breakfast")}]
        if "take the amoxicillin after food" in low:
            out["prescribed_meds"] = [{"drug": "amoxicillin", "food": "after_food",
                                       "instructions": ["finish the whole course"],
                                       "evidence": ev(utt, "take the amoxicillin after food")}]
        if "i'll give you amoxicillin 500 three times a day." in low:
            out["prescribed_meds"] = [{"drug": "amoxicillin", "dose_mg": 500, "frequency_per_day": 3,
                                       "evidence": ev(utt, "I'll give you amoxicillin 500 three times a day")}]
    return json.dumps(out)


def _task_text(messages) -> str:
    parts = []
    for m in messages:
        c = getattr(m, "content", None) if not isinstance(m, dict) else m.get("content")
        if isinstance(c, list):
            parts.extend(str(x.get("text", "")) for x in c if isinstance(x, dict))
        elif c:
            parts.append(str(c))
    return "\n".join(parts)


def _golden_step(messages):
    """Fake gpt-oss: one final_answer call. Proposes the radiation/sweating question once the gyastrik idiom and the
    chest-pain checklist are in the task, unless such a card is already open."""
    task = _task_text(messages)
    utt = next((ln.split()[1] for ln in task.splitlines() if ln.startswith("* ") and "PATIENT" in ln), None)
    grounding_line = next((ln for ln in task.splitlines() if ln.startswith("VALID GROUNDING IDS:")), "")
    open_line = next((ln for ln in task.splitlines() if ln.startswith("OPEN CARDS:")), "")
    if utt and "ask_pain_radiation" in grounding_line and "spread" not in open_line.lower():
        return [("final_answer", {"cards": [{
            "kind": "ask", "title": "Ask about radiation and sweating",
            "body": "'gyastrik' chest burning can mask cardiac pain; radiation and sweating not asked yet.",
            "evidence": [utt], "grounding": "ask_pain_radiation",
            "ask_text": "Does the burning spread to your arm, jaw or back, and do you sweat with it?",
            "severity": "caution"}]})]
    return [("final_answer", {"cards": []})]


def golden_agent_factory():
    return agentkit.scripted_model([_golden_step])


def play(consult, turns=GOLDEN_TURNS, after_turn=None):
    """Replay the golden path as text turns through the talk-loop hooks + think_now (synchronous)."""
    for step in turns:
        if step[0] == "tick":
            consult.set_scenario_time(step[1])
            copilot.tick(consult)
            continue
        if step[0] == "ack":
            consult.set_scenario_time(step[1])
            for c in consult.cards.open_cards():
                if c["source"] == "rules" and c["severity"] == "critical":
                    consult.cards.act(c["id"], "acknowledge", user="doctor")
            continue
        t, role, lang, text, english, drugs = step
        consult.set_scenario_time(t)
        turn = consult.add_turn(role, lang, text, english=english or text)
        held = []
        if role == "doctor" and drugs:
            held = copilot.prescription_gate(consult, drugs, turn.english, turn.id)
            turn.held = bool(held)
        summary = copilot.think_now(consult)
        if after_turn:
            after_turn(turn, held, summary)
    return consult


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("BAYAN_AGENT", "on")
    llm.set_backend(golden_backend)
    agentkit.set_model_factory(golden_agent_factory)
    yield
    llm.set_backend(None)
    agentkit.set_model_factory(None)


def _consult():
    c = Consultation(patient_lang="ne")
    copilot.attach(c)
    return c


def _rule_card(c, rule_id):
    return next((x for x in c.cards.all_cards() if x["source"] == "rules" and rule_id in x["rule_ids"]), None)


# ------------------------------------------------------------------ golden path
def test_golden_path_cards():
    c = _consult()
    seen = {}

    def after(turn, held, summary):
        chest = _rule_card(c, "WORK-CHEST-04") or _rule_card(c, "WORK-CHEST-02")
        seen[turn.id] = {"held": held, "chest": dict(chest) if chest else None, "summary": summary}

    play(c, after_turn=after)
    # P1 (u002): idiom card npi-005 + caution chest-pain workup card + agent ask card
    idiom = next(x for x in c.cards.all_cards() if x["kind"] == "idiom")
    assert idiom["grounding"] == "npi-005" and idiom["source"] == "lexicon" and idiom["severity"] == "caution"
    assert "Cardiac ischaemia" in idiom["body"] and idiom["source_urls"]
    assert seen["u002"]["chest"]["severity"] == "caution"
    assert seen["u002"]["chest"]["title"] == "Chest-pain workup"
    asks = [x for x in c.cards.all_cards() if x["kind"] == "ask"]
    assert any(("spread" in x["ask_text"].lower() or "sweat" in x["ask_text"].lower()) for x in asks)
    assert all(x["source"] in ("agent", "fallback") for x in asks)
    # D3 (u005): ALG-PEN-01 held + chest card critical with 4 rule hits
    d3 = seen["u005"]
    assert [h["rule_id"] for h in d3["held"]] == ["ALG-PEN-01"]
    assert d3["chest"]["severity"] == "critical"
    assert sorted(d3["chest"]["rule_ids"]) == ["WORK-CHEST-01", "WORK-CHEST-02", "WORK-CHEST-03", "WORK-CHEST-04"]
    pen = _rule_card(c, "ALG-PEN-01")
    assert pen["severity"] == "critical" and pen["kind"] == "safety" and pen["source"] == "rules"
    assert any(e["utt"] == "u004" for e in pen["evidence"])        # the allergy quote
    # D4 (u006): amoxicillin withdrawn (no hold), ECG + troponin ordered -> everything resolves
    assert seen["u006"]["held"] == []
    assert pen["status"] == "resolved" and _rule_card(c, "WORK-CHEST-02")["status"] == "resolved"
    # D6: paracetamol 1 g x3 -> no DOSE-PARA rule
    assert not [x for x in c.cards.open_cards() if x["source"] == "rules"]
    assert not any(r.startswith("DOSE-PARA") for s in seen.values() for r in s["summary"]["fired"])
    assert [m["drug"] for m in c.state["prescribed_meds"]] == ["paracetamol"]
    assert "amoxicillin" in [m["drug"] for m in c.state["stopped_meds"]]
    # P3 is a courtesy turn: no extraction call, no agent run
    assert seen["u009"]["summary"]["agent_skipped"] == "nothing new"
    assert seen["u009"]["summary"]["extract_tokens"] == [0, 0] and seen["u009"]["summary"]["agent"] is None
    # audit + trace + metrics
    acts = [(a["action"], a["rule_id"]) for a in c.audit if a["action"] == "acknowledge"]
    assert len(acts) == 2
    texts = [t["text"] for t in c.trace if t["kind"] == "tool"]
    assert any(t.startswith("lookup_idiom(") and "npi-005" in t for t in texts)
    assert any(t.startswith("update_state → ") and "+chest_burning" in t for t in texts)
    assert any(t.startswith("check_safety_rules → ") and "WORK-CHEST-04" in t for t in texts)
    assert any(t.startswith("final_answer(") for t in texts)
    metrics = c.outputs["metrics"]
    assert len(metrics) == len([s for s in GOLDEN_TURNS if s[0] not in ("tick", "ack")])
    assert all({"latency_s", "input_tokens", "output_tokens", "cost_usd", "agent_steps"} <= set(m) for m in metrics)
    assert max(m["agent_steps"] for m in metrics) == 1        # one LLM step per agent run


def test_doctor_dismissed_card_does_not_return():
    c = _consult()
    play(c, GOLDEN_TURNS[:2])
    ask = next(x for x in c.cards.open_cards() if x["kind"] == "ask")
    c.cards.act(ask["id"], "dismiss", user="doctor")
    # the agent proposes the very same card again on the next clinical turn -> rejected, never reopened
    agentkit.set_model_factory(lambda: agentkit.scripted_model([[("final_answer", {"cards": [{
        "kind": "ask", "title": ask["title"], "body": "again", "evidence": ["u002"], "grounding": ask["grounding"],
        "ask_text": ask["ask_text"]}]})]]))
    c.set_scenario_time(1.5)
    c.add_turn("patient", "ne", "दुख्छ", english="It hurts a lot when I carry bricks.")
    copilot.think_now(c)
    same = [x for x in c.cards.all_cards() if x["kind"] == "ask" and x["ask_text"] == ask["ask_text"]]
    assert len(same) == 1 and same[0]["status"] == "dismissed"
    assert any(a["action"] == "rejected" and "dismissed" in (a["reason"] or "") for a in c.audit)


def test_agent_critical_attempt_rejected_then_fallback():
    agentkit.set_model_factory(lambda: agentkit.scripted_model([[("final_answer", {"cards": [{
        "kind": "missed", "title": "Possible ACS", "body": "x", "evidence": ["u002"], "grounding": "npi-005",
        "severity": "critical"}]})]]))
    c = _consult()
    play(c, GOLDEN_TURNS[:2])
    assert not [x for x in c.cards.all_cards() if x["source"] == "agent"]
    rej = [a for a in c.audit if a["action"] == "rejected"]
    assert rej and "rule engine" in rej[0]["reason"]
    assert all(x["severity"] != "critical" for x in c.cards.all_cards() if x["source"] != "rules")
    fb = [x for x in c.cards.all_cards() if x["source"] == "fallback"]
    assert 1 <= len(fb) <= 2 and all(x["kind"] == "ask" for x in fb)


def test_agent_exception_falls_back():
    agentkit.set_model_factory(lambda: agentkit.scripted_model([RuntimeError("provider 503")]))
    c = _consult()
    play(c, GOLDEN_TURNS[:2])
    fb = [x for x in c.cards.all_cards() if x["source"] == "fallback"]
    assert 1 <= len(fb) <= 2
    assert any("sweat" in x["ask_text"].lower() or "spread" in x["ask_text"].lower() for x in fb)
    assert {x["grounding"] for x in fb} <= {"npi-005", "ask_pain_radiation", "ask_exertional_pattern",
                                            "ask_sweating_breathlessness"}
    assert any(t["kind"] == "error" and "copilot failed" in t["text"] for t in c.trace)
    # rule + idiom cards are unaffected by the agent failure
    assert _rule_card(c, "WORK-CHEST-04")["severity"] == "caution"
    assert any(x["kind"] == "idiom" for x in c.cards.all_cards())


def test_agent_timeout_falls_back_and_late_cards_are_ignored(monkeypatch):
    monkeypatch.setattr(copilot, "AGENT_TIMEOUT_S", 0.3)
    agentkit.set_model_factory(lambda: agentkit.scripted_model([[("final_answer", {"cards": [{
        "kind": "ask", "title": "Late question", "body": "x", "evidence": ["u002"], "grounding": "npi-005",
        "ask_text": "Is it late?"}]})]], delay_s=0.8))
    c = _consult()
    t0 = time.time()
    play(c, GOLDEN_TURNS[:2])
    assert time.time() - t0 < 2.0
    assert [x for x in c.cards.all_cards() if x["source"] == "fallback"]
    time.sleep(1.0)                                      # the late final_answer runs now: must be a no-op
    assert not [x for x in c.cards.all_cards() if x["source"] == "agent"]
    assert any("timed out" in t["text"] for t in c.trace)


def test_agent_off_uses_fallback_only(monkeypatch):
    monkeypatch.setenv("BAYAN_AGENT", "off")
    calls = []
    agentkit.set_model_factory(lambda: calls.append(1) or golden_agent_factory())
    c = _consult()
    play(c, GOLDEN_TURNS[:2])
    assert not calls
    assert [x for x in c.cards.all_cards() if x["source"] == "fallback"]


# ------------------------------------------------------------------ prescription gate
def _with_allergy():
    c = _consult()
    c.set_scenario_time(2.0)
    t = c.add_turn("patient", "ne", "पेनिसिलिन", english="After a penicillin injection my body swelled up.")
    copilot.record_allergies(c, [{"substance": "penicillin", "reaction": "body swelling"}], t.english, t.id)
    assert c.state["allergies"][0]["substance"] == "penicillin"
    return c


def test_gate_prescribe_holds():
    c = _with_allergy()
    c.set_scenario_time(9.0)
    t = c.add_turn("doctor", "en", "I'll give you amoxicillin 500 three times a day")
    held = copilot.prescription_gate(c, [{"name": "amoxicillin", "dose_mg": 500, "frequency_per_day": 3,
                                          "intent": "prescribe"}], t.text, t.id)
    assert [h["rule_id"] for h in held] == ["ALG-PEN-01"] and held[0]["severity"] == "critical"
    card = _rule_card(c, "ALG-PEN-01")
    assert card and card["status"] == "open" and card["severity"] == "critical"
    assert {e["utt"] for e in card["evidence"]} >= {"u001", "u002"}
    # the background extractor sees the same turn later: still one card
    copilot.think_now(c)
    assert len([x for x in c.cards.all_cards() if "ALG-PEN-01" in x["rule_ids"]]) == 1
    # a timer tick must not resolve it
    copilot.tick(c)
    assert _rule_card(c, "ALG-PEN-01")["status"] == "open"


def test_gate_stop_does_not_hold_and_resolves():
    c = _with_allergy()
    t = c.add_turn("doctor", "en", "I'll give you amoxicillin 500 three times a day")
    assert copilot.prescription_gate(c, [{"name": "amoxicillin", "dose_mg": 500, "frequency_per_day": 3,
                                          "intent": "prescribe"}], t.text, t.id)
    t2 = c.add_turn("doctor", "en", "Actually, no amoxicillin.")
    assert copilot.prescription_gate(c, [{"name": "amoxicillin", "intent": "stop"}], t2.text, t2.id) == []
    assert c.state["prescribed_meds"] == []
    assert _rule_card(c, "ALG-PEN-01")["status"] == "resolved"


def test_gate_mention_does_not_hold():
    c = _with_allergy()
    t = c.add_turn("doctor", "en", "Any reaction to penicillin before?")
    assert copilot.prescription_gate(c, [{"name": "penicillin", "intent": "mention"}], t.text, t.id) == []
    assert c.state["prescribed_meds"] == []
    assert _rule_card(c, "ALG-PEN-01") is None


def test_gate_never_raises():
    c = _consult()
    assert copilot.prescription_gate(c, [{"name": "amoxicillin"}, "junk", None], "q", "u999") == []


# ------------------------------------------------------------------ background scheduling
def test_on_turn_is_non_blocking_and_debounced(monkeypatch):
    monkeypatch.setattr(copilot, "DEBOUNCE_S", 0.1)

    def slow_backend(messages, schema, max_tokens):
        time.sleep(0.5)
        return golden_backend(messages, schema, max_tokens)

    llm.set_backend(slow_backend)
    c = _consult()
    for step in GOLDEN_TURNS[:2]:
        t, role, lang, text, english, _ = step
        c.set_scenario_time(t)
        turn = c.add_turn(role, lang, text, english=english or text)
        t0 = time.perf_counter()
        copilot.on_turn(c, turn)
        assert time.perf_counter() - t0 < 0.05
    # a turn arriving mid-run marks the run dirty -> exactly one rerun picks it up
    time.sleep(0.25)
    c.set_scenario_time(2.0)
    t0 = time.perf_counter()
    copilot.on_turn(c, c.add_turn("doctor", "en", "Do you work outdoors? Are you allergic to any medicine?"))
    assert time.perf_counter() - t0 < 0.05
    assert copilot.idle(c, 10)
    runs = c._copilot.runs
    assert 1 <= len(runs) <= 2
    assert c.agent_seen == 3
    assert sum(len(r["new_turns"]) for r in runs) == 3
    assert any(x["kind"] == "idiom" for x in c.cards.all_cards())


def test_think_loop_swallows_errors():
    def broken(messages, schema, max_tokens):
        raise RuntimeError("all providers down")

    llm.set_backend(broken)
    c = _consult()
    play(c, GOLDEN_TURNS[:2])
    assert any(t["kind"] == "error" and "update_state failed" in t["text"] for t in c.trace)
    # deterministic idiom + rules still ran
    assert _rule_card(c, "WORK-CHEST-04") is not None


def test_ask_card_returns_question():
    c = _consult()
    play(c, GOLDEN_TURNS[:2])
    ask = next(x for x in c.cards.open_cards() if x["kind"] == "ask")
    q = copilot.ask_card(c, ask["id"])
    assert q == ask["ask_text"]
    assert c.cards.get(ask["id"])["status"] == "accepted"
    assert copilot.ask_card(c, "c999") is None


# ------------------------------------------------------------------ extraction
def test_extract_uses_schema_and_compact_context():
    seen = {}

    def spy(messages, schema, max_tokens):
        seen["schema"], seen["max_tokens"], seen["user"] = schema, max_tokens, messages[-1]["content"]
        return golden_backend(messages, schema, max_tokens)

    llm.set_backend(spy)
    c = _consult()
    for i in range(8):
        c.add_turn("doctor", "en", f"Filler question number {i}?", t_min=i * 0.1)
    t = c.add_turn("patient", "ne", "x", english="My chest is burning, like gyastrik (gastric). I feel dizzy.")
    delta = extract.extract_delta(c, [t])
    assert seen["schema"] is extract.EXTRACT_SCHEMA and seen["max_tokens"] == extract.EXTRACT_MAX_TOKENS
    sym_enum = extract.EXTRACT_SCHEMA["properties"]["symptoms"]["items"]["properties"]["code"]["enum"]
    assert "chest_burning" in sym_enum and "sore_throat" in sym_enum
    assert "pain_radiation" in extract.EXTRACT_SCHEMA["properties"]["questions_asked"]["items"]["properties"]["topic"]["enum"]
    assert "Filler question number 3" in seen["user"] and "Filler question number 2" not in seen["user"]
    assert [s["code"] for s in delta["symptoms"]] == ["chest_burning", "dizziness"]
    assert delta["symptoms"][0]["evidence"][0]["utt"] == t.id
    assert delta["symptoms"][0]["first_mention_min"] == t.t_min


def test_clean_delta_never_guesses_and_respects_intent():
    c = _consult()
    t = c.add_turn("doctor", "en", "Actually, no amoxicillin. Paracetamol instead.", t_min=5.0)
    raw = {"prescribed_meds": [{"drug": "Amoxicillin", "dose_mg": None, "evidence": [{"utt": "u404", "quote": "x"}]},
                               {"drug": "paracetamol", "dose_mg": "1 g", "frequency_per_day": "3",
                                "evidence": [{"utt": t.id, "quote": "Paracetamol instead"}]}],
           "remove": {"prescribed_meds": ["amoxicillin"]},
           "patient": {"pregnant": "unknown", "age_years": None, "heat_exposure": True},
           "vitals": {"bp_sys": None, "hr": "96"},
           "disposition": {"type": None},
           "allergies": [{"substance": "Penicillin", "reaction": None, "severity": "weird"}]}
    d = extract.clean_delta(raw, c, [t])
    assert d["remove"] == {"prescribed_meds": ["amoxicillin"]}
    assert [m["drug"] for m in d["prescribed_meds"]] == ["paracetamol"]
    assert d["patient"] == {"heat_exposure": True}
    assert d["vitals"]["hr"] == 96 and "bp_sys" not in d["vitals"]
    assert "disposition" not in d
    assert d["allergies"][0]["severity"] == "unknown" and d["allergies"][0]["reaction"] is None
    assert d["prescribed_meds"][0]["evidence"][0]["utt"] == t.id


# ------------------------------------------------------------------ agent tool tolerance / single-step design
def _chest_consult():
    agentkit.set_model_factory(lambda: agentkit.scripted_model([[("final_answer", {"cards": []})]]))
    c = _consult()
    play(c, GOLDEN_TURNS[:2])          # gyastrik + chest burning: WORK-CHEST-04 fires, checklist open
    return c


def _run_agent_with(c, script):
    agentkit.set_model_factory(lambda: agentkit.scripted_model(script))
    c.set_scenario_time(1.6)
    c.add_turn("patient", "ne", "काम गर्दा बढ्छ", english="It gets worse when I carry things at work.")
    return copilot.think_now(c)


def test_reference_card_set_and_rule_coverage():
    """The card set measured live on Cerebras (gpt-oss-120b, medium): two asks + "ECG not performed"."""
    c = _chest_consult()
    s = _run_agent_with(c, [[("final_answer", {"cards": [
        {"kind": "ask", "title": "Ask about radiation", "body": "b", "evidence": ["u002"],
         "grounding": "ask_pain_radiation", "ask_text": "Does the burning spread to your arm, jaw or back?"},
        {"kind": "ask", "title": "Ask about exertion", "body": "b", "evidence": ["u003"],
         "grounding": "ask_exertional_pattern", "ask_text": "Does it get worse with activity and ease with rest?"},
        {"kind": "missed", "title": "ECG not performed", "body": "b", "evidence": ["u002"],
         "grounding": "ecg_12lead", "severity": "caution"}]})]])
    agent_cards = [x for x in c.cards.all_cards() if x["source"] == "agent"]
    assert sorted(x["grounding"] for x in agent_cards) == ["ask_exertional_pattern", "ask_pain_radiation"]
    assert all(x["severity"] == "info" for x in agent_cards)          # ask default severity
    assert s["agent"]["steps"] == 1 and s["agent"]["ok"]
    line = [t["text"] for t in c.trace if t["text"].startswith("final_answer(")][-1]
    assert "covered" in line or "duplicate" in line                   # ECG card deduped against WORK-CHEST-04


def test_final_answer_fixable_error_gets_one_retry():
    c = _chest_consult()
    s = _run_agent_with(c, [
        [("final_answer", {"cards": [
            {"title": "Ask about sweating", "evidence": ["u002"], "grounding": "ask_sweating_breathlessness",
             "ask_text": "Do you sweat or feel short of breath when it comes?"},          # kind missing: inferred
            {"kind": "missed", "title": "BP not recorded", "evidence": ["u002"], "grounding": "BP check"}]})],
        [("final_answer", {"cards": [
            {"kind": "missed", "title": "BP not recorded", "evidence": ["u002"], "grounding": "bp"}]})],
    ])
    groundings = sorted(x["grounding"] for x in c.cards.all_cards() if x["source"] == "agent")
    assert groundings == ["ask_sweating_breathlessness", "bp"]
    assert s["agent"]["steps"] == 2 and s["agent"]["ok"] and not s["fallback"]
    assert any("Fix and call final_answer again" in t["text"] for t in c.trace if t["kind"] == "agent")


def test_final_answer_tolerates_stringified_and_missing_cards():
    c = _chest_consult()
    s = _run_agent_with(c, [[("final_answer", {})]])
    assert s["agent"]["ok"] and s["agent"]["steps"] == 1
    res = copilot.post_cards(c, json.dumps([{"kind": "observation", "title": "Dose stated twice", "body": "500 vs 50",
                                             "evidence": "u002", "grounding": "u002"}]))
    assert res[0].startswith("c")


def test_agent_prompt_is_compact_and_lists_valid_ids():
    seen = []

    def factory():
        m = agentkit.scripted_model([[("final_answer", {"cards": []})]])
        seen.append(m)
        return m

    agentkit.set_model_factory(factory)
    c = _consult()
    play(c, GOLDEN_TURNS[:2])
    msgs = seen[-1].seen_messages[0]
    system = _task_text(msgs[:1])
    assert "Here are a few examples using notional tools" not in system
    assert "Critical alerts come only from the deterministic rule engine" in system
    assert 300 < len(system.split()) < 1500
    task = _task_text(msgs[1:])
    vline = next(ln for ln in task.splitlines() if ln.startswith("VALID GROUNDING IDS:"))
    assert "ask_pain_radiation" in vline and "npi-005" in vline and "WORK-CHEST-04" in vline
    assert "ecg_12lead" not in vline                      # covered by WORK-CHEST-04
    assert "(covered by WORK-CHEST-04)" in task


def test_yes_answer_to_a_question_is_not_trivial():
    c = _consult()
    c.add_turn("doctor", "en", "Does it spread to your arm?")
    yes = c.add_turn("patient", "ne", "हो", english="Yes.")
    bye = c.add_turn("patient", "ne", "धन्यवाद", english="Okay, thank you, doctor.")
    assert not copilot.is_trivial(yes, c)
    assert copilot.is_trivial(bye, c)


def test_keyword_fallback_when_extractor_down():
    def broken(messages, schema, max_tokens):
        raise RuntimeError("all providers down")

    llm.set_backend(broken)
    c = _consult()
    play(c, GOLDEN_TURNS[:2])
    assert [s["code"] for s in c.state["symptoms"]] == ["chest_burning"]
    assert any("keyword fallback" in t["text"] for t in c.trace)


def test_real_model_config_offline(monkeypatch):
    """InferenceClientModel wiring (no network): Cerebras, reasoning effort + max_tokens reach every completion."""
    import threading

    from smolagents.models import ChatMessage, MessageRole

    agentkit.set_model_factory(None)
    monkeypatch.setenv("HF_TOKEN", "hf_fake_for_test")
    model = agentkit.make_model()
    assert model.client_kwargs["provider"] == agentkit.AGENT_PROVIDER == "cerebras"
    assert model.model_id == "openai/gpt-oss-120b"
    c = _consult()
    tools = copilot.build_tools(c, threading.Event())
    kw = model._prepare_completion_kwargs(
        messages=[ChatMessage(role=MessageRole.USER, content=[{"type": "text", "text": "x"}])],
        tools_to_call_from=tools, stop_sequences=["Observation:"])
    assert kw["max_tokens"] == agentkit.AGENT_MAX_TOKENS == 6000
    assert kw["extra_body"] == {"reasoning_effort": "medium"} and kw["temperature"] == 0
    assert kw["tool_choice"] == "required"
    fa = next(t["function"] for t in kw["tools"] if t["function"]["name"] == "final_answer")
    assert fa["parameters"]["properties"]["cards"]["type"] == "array"
    assert fa["parameters"]["properties"]["cards"]["items"]["properties"]["kind"]["enum"] == ["ask", "missed", "observation"]
    assert sorted(t["function"]["name"] for t in kw["tools"]) == [
        "check_safety_rules", "final_answer", "lookup_drug", "lookup_idiom"]


def test_agent_missed_card_resolves_when_checklist_item_done():
    """Live smoke test regression: 'Troponin not ordered' stayed open after the doctor ordered troponin."""
    c = _consult()
    posted = {}

    def after(turn, _held, _summary):
        if turn.role == "patient" and "cid" not in posted:
            posted["cid"] = c.cards.post("missed", "Troponin not ordered", "No troponin yet.", [turn.id],
                                         "troponin", source="agent", t_min=c.now_min())

    play(c, after_turn=after)
    card = c.cards.get(posted["cid"])
    assert card is not None and card["status"] == "resolved"


# ------------------------------------------------------------------ cost: question batching + cheaper extraction host
def _outcome(c):
    s = c.state
    return {
        "symptoms": sorted(x["code"] for x in s["symptoms"]),
        "allergies": sorted((a["substance"], a.get("severity")) for a in s["allergies"]),
        "prescribed": sorted(m["drug"] for m in s["prescribed_meds"]),
        "investigations": sorted((i["code"], i["status"]) for i in s["investigations"]),
        "vitals": {k: v for k, v in s["vitals"].items() if k in ("bp_sys", "bp_dia")},
        "disposition": (s.get("disposition") or {}).get("type"),
        "questions": sorted(q if isinstance(q, str) else q.get("topic") for q in s["questions_asked"]),
        "rule_cards": sorted((x["grounding"], x["status"], x["severity"]) for x in c.cards.all_cards()
                             if x["source"] == "rules"),
        "idiom_cards": sorted(x["grounding"] for x in c.cards.all_cards() if x["kind"] == "idiom"),
    }


def test_question_batching_saves_calls_with_identical_outcome(monkeypatch):
    def run(defer: bool):
        monkeypatch.setattr(copilot, "DEFER_QUESTIONS", defer)
        calls = []

        def counting(messages, schema, max_tokens):
            calls.append(_new_section(messages))
            return golden_backend(messages, schema, max_tokens)

        llm.set_backend(counting)
        c = play(_consult())
        copilot.flush(c)
        return calls, _outcome(c)

    calls_off, out_off = run(False)
    calls_on, out_on = run(True)
    assert len(calls_on) == len(calls_off) - 2          # the two plain questions ride along with their answers
    assert out_on == out_off                            # same facts, same alerts, same idiom card
    assert any(len(batch) == 2 and batch[0][1].find("allergic") >= 0 for batch in calls_on)


@pytest.mark.parametrize("text,deferrable", [
    ("Does it spread to your arm, jaw or back?", True),
    ("Are you allergic to any medicine?", True),
    ("We'll do an ECG now, okay?", False),                  # an order
    ("Shall I give you amoxicillin?", False),               # a medicine
    ("Is your blood pressure usually high?", False),        # a measurement word
    ("Did it start 2 hours ago?", False),                   # a number
    ("You can go home now.", False),                        # not a question
])
def test_is_deferrable(text, deferrable):
    c = _consult()
    t = c.add_turn("doctor", "en", text, english=text, t_min=1.0)
    assert copilot.is_deferrable(t) is deferrable
    p = c.add_turn("patient", "ne", "हो", english="Does it spread?", t_min=1.1)
    assert copilot.is_deferrable(p) is False                # patient turns are never deferred


def test_unanswered_question_is_extracted_on_flush():
    calls = []
    llm.set_backend(lambda m, s, n: (calls.append(1), golden_backend(m, s, n))[1])
    c = _consult()
    c.set_scenario_time(2.0)
    c.add_turn("doctor", "en", "Do you work outdoors? Are you allergic to any medicine?")
    copilot.think_now(c)
    assert calls == [] and "allergies" not in str(c.state["questions_asked"])
    copilot.flush(c)
    assert calls == [1] and "allergies" in str(c.state["questions_asked"])


def test_extraction_runs_on_groq_with_cerebras_fallback(monkeypatch):
    seen = {}

    def fake_chat_json(system, user, schema=None, **kw):
        seen.update(kw)
        return {}

    monkeypatch.setattr(extract.llm, "chat_json", fake_chat_json)
    c = _consult()
    t = c.add_turn("patient", "ne", "x", english="My chest burns.", t_min=1.0)
    extract.extract_delta(c, [t])
    assert seen["provider"] == "groq" and seen["fallback"] == "cerebras" and seen["reasoning"] == "medium"


def test_llm_provider_fallback_and_cost_metering(monkeypatch):
    llm.set_backend(None)
    tried = []

    class _Resp:
        def __init__(self):
            self.usage = type("U", (), {"prompt_tokens": 1000, "completion_tokens": 100})()
            self.choices = [type("C", (), {"message": type("M", (), {"content": '{"ok": true}'})()})()]

    class _Client:
        def __init__(self, prov):
            self.prov, self.chat, self.completions = prov, self, self

        def create(self, **_kw):
            tried.append(self.prov)
            if self.prov == "groq":
                raise RuntimeError("groq down")
            return _Resp()

    monkeypatch.setattr(llm, "_client", lambda prov: _Client(prov))
    before = llm.USAGE["cost_usd"]
    assert llm.chat_json("s", "u", schema={"type": "object"}, provider="groq", fallback="cerebras") == {"ok": True}
    assert tried[0] == "groq" and tried[-1] == "cerebras"
    assert abs(llm.USAGE["cost_usd"] - before - llm.cost_usd("cerebras", 1000, 100)) < 1e-12
    assert llm.cost_usd("groq", 1_000_000, 0) < llm.cost_usd("cerebras", 1_000_000, 0)


# ------------------------------------------------------------------ medication instructions (care plan fields)
def _say(c, text, t):
    c.set_scenario_time(t)
    c.add_turn("doctor", "en", text)
    copilot.think_now(c)
    return c


def _med(c, drug):
    items = [m for m in c.state["prescribed_meds"] if m["drug"] == drug]
    assert len(items) == 1, items
    return items[0]


def test_golden_paracetamol_is_as_needed():
    c = _consult()
    play(c)
    para = _med(c, "paracetamol")
    assert para["as_needed"] is True and para["max_per_day"] == 3 and para["as_needed_for"] == "throat pain"
    assert para["dose_mg"] == 1000 and para["daily_dose_mg"] == 3000
    assert "times" not in para                       # only a frequency was said: the renderer maps it to slots


def test_capsule_after_food_for_five_days():
    c = _say(_consult(), "Amoxicillin 500 milligrams, one capsule three times a day after food for five days.", 3.0)
    amox = _med(c, "amoxicillin")
    assert (amox["form"], amox["amount"], amox["unit"]) == ("capsule", 1, "capsule")
    assert amox["frequency_per_day"] == 3 and amox["food"] == "after_food" and amox["duration_days"] == 5
    assert amox["dose_mg"] == 500 and amox["daily_dose_mg"] == 1500 and "penicillin" in amox["class"]


def test_nasal_spray_on_waking_for_a_month():
    c = _say(_consult(), "Use the nasal spray, two sprays in each nostril every morning when you wake up, "
                         "for one month.", 3.0)
    spray = _med(c, "nasal spray")
    assert spray["form"] == "nasal_spray" and (spray["amount"], spray["unit"]) == (2, "spray")
    assert spray["site"] == "each nostril" and spray["times"] == ["on_waking"]
    assert spray.get("duration_days") == 30 or spray.get("duration_text") == "one month"


def test_omeprazole_before_breakfast_two_weeks():
    c = _say(_consult(), "Omeprazole 20 mg every morning before breakfast for two weeks.", 3.0)
    ome = _med(c, "omeprazole")
    assert ome["times"] == ["morning"] and ome["food"] == "before_food" and ome["duration_days"] == 14
    assert ome["frequency_per_day"] == 1                 # derived from the one stated time


def test_follow_up_detail_merges_into_same_item():
    c = _consult()
    _say(c, "I'll give you amoxicillin 500 three times a day.", 3.0)
    first = _med(c, "amoxicillin")
    assert "food" not in first
    _say(c, "Take the amoxicillin after food, and finish the whole course.", 3.5)
    amox = _med(c, "amoxicillin")                       # still exactly one item
    assert amox["food"] == "after_food" and amox["dose_mg"] == 500 and amox["frequency_per_day"] == 3
    assert amox["instructions"] == ["finish the whole course"]
    assert {e["utt"] for e in amox["evidence"]} == {"u001", "u002"}


def test_med_detail_normalisation_synonyms():
    from bayan.brain.merge import normalise_med, normalise_med_details
    d = normalise_med_details({"form": "nose spray", "food": "after meals", "times": ["at night", "with breakfast"],
                               "amount": "2 puffs", "as_needed": "prn", "instructions": "Shake well.",
                               "interval_hours": "8"})
    assert d["form"] == "nasal_spray" and d["food"] == "after_food" and d["times"] == ["morning", "bedtime"]
    assert (d["amount"], d["unit"]) == (2, "puff") and d["as_needed"] is True
    assert d["instructions"] == ["Shake well"] and d["interval_hours"] == 8
    assert normalise_med_details({"form": "syrup", "amount": 1, "unit": "teaspoon"}) == \
        {"form": "liquid", "amount": 5, "unit": "ml"}
    assert normalise_med_details({"form": "drops", "site": "both eyes"})["form"] == "eye_drops"
    assert normalise_med_details({"times": "whenever", "food": "unknown", "site": None}) == {}
    m = normalise_med({"drug": "ibuprofen", "amount": 400, "unit": "mg", "interval_hours": 8})
    assert m["dose_mg"] == 400 and m["frequency_per_day"] == 3 and m["daily_dose_mg"] == 1200
    m = normalise_med({"drug": "paracetamol", "amount": "one", "unit": "gram"})
    assert m["dose_mg"] == 1000


def test_med_details_keep_intent_logic():
    c = _consult()
    copilot._dep("merge")(c, {"prescribed_meds": [{"drug": "ibuprofen", "intent": "mention", "food": "after_food"}]})
    assert c.state["prescribed_meds"] == []
    t = c.add_turn("doctor", "en", "Omeprazole 20 mg every morning before food")
    delta = extract.clean_delta({"prescribed_meds": [{"drug": "Omeprazole", "dose_mg": 20, "times": ["morning"],
                                                      "food": "before_food", "site": None, "instructions": []}]},
                                c, [t])
    item = delta["prescribed_meds"][0]
    assert item["times"] == ["morning"] and item["food"] == "before_food"
    assert "site" not in item and "instructions" not in item
    props = extract.EXTRACT_SCHEMA["properties"]["prescribed_meds"]["items"]["properties"]
    assert props["food"]["enum"] == ["before_food", "with_food", "after_food", "empty_stomach"]
    assert props["times"]["items"]["enum"] == ["on_waking", "morning", "midday", "evening", "bedtime"]
    assert "times" in extract.SYSTEM and "on_waking" in extract.SYSTEM


# ------------------------------------------------------------------ simulation-suite regressions (fix1)
def test_gate_repairs_a_mangled_brand_and_holds():
    # alg-01: the translator's drug name was "augmented" for "Augmentin 625"
    c = _with_allergy()
    t = c.add_turn("doctor", "en", "Okay. I'll give you Augmentin 625, one tablet three times a day for five days.")
    held = copilot.prescription_gate(c, [{"name": "augmented", "dose_mg": 625, "frequency_per_day": 3,
                                          "intent": "prescribe"}], t.text, t.id)
    assert [(h["rule_id"], h["key"]) for h in held] == [("ALG-PEN-01", "ALG-PEN-01|co-amoxiclav")]
    assert {m["drug"] for m in c.state["prescribed_meds"]} == {"co-amoxiclav"}


def test_gate_parses_qds_and_sums_scheduled_plus_prn():
    c = _consult()
    t = c.add_turn("doctor", "en", "For the kidney stone pain, tramadol 100 mg QDS, plus another 100 mg at night if "
                                   "the pain wakes you.")
    # the model under-counted QDS as once a day; the dose as said carries the abbreviation
    held = copilot.prescription_gate(c, [
        {"name": "tramadol", "intent": "prescribe", "dose_mg": 100, "frequency_per_day": 1, "dose": "100 mg QDS"},
        {"name": "tramadol", "intent": "prescribe", "dose_mg": 100, "frequency_per_day": 1, "dose": "100 mg at night"}],
        t.text, t.id)
    assert any(h["rule_id"] == "DOSE-TRAM-01" and h["severity"] == "critical" for h in held)
    assert c.state["prescribed_meds"][0]["daily_dose_mg"] == 500


def test_brain_route_defaults_and_override(monkeypatch):
    # unset: the caller's own provider / fallback (extraction stays on Groq -> Cerebras); translation untouched
    monkeypatch.setattr(llm, "BRAIN_MODEL", "")
    monkeypatch.setattr(llm, "BRAIN_PROVIDER", "")
    assert llm.brain_route("groq", "cerebras") == {"provider": "groq", "fallback": "cerebras"}
    assert llm.brain_route() == {}
    monkeypatch.setitem(llm.MODEL_PRICES, "example/brain-model", {"deepinfra": (0.09, 0.18)})
    monkeypatch.setattr(llm, "BRAIN_MODEL", "example/brain-model")
    monkeypatch.setattr(llm, "BRAIN_PROVIDER", "deepinfra")
    assert llm.brain_route("groq", "cerebras") == {"model": "example/brain-model", "provider": "deepinfra",
                                                   "fallback": "deepinfra"}
    # priced with the brain model's own provider prices; gpt-oss keeps its table
    assert llm.price("example/brain-model", "deepinfra") == (0.09, 0.18)
    assert abs(llm.cost_usd("deepinfra", 1_000_000, 1_000_000, "example/brain-model") - 0.27) < 1e-9
    assert llm.cost_usd("cerebras", 1000, 100) == llm.cost_usd("cerebras", 1000, 100, "openai/gpt-oss-120b")
    # reasoning_effort only for gpt-oss
    assert llm.reasoning_body("example/brain-model", "medium") == {}
    assert llm.reasoning_body("openai/gpt-oss-120b", "low") == {"reasoning_effort": "low"}


def test_chat_json_sends_the_brain_model_and_prices_it(monkeypatch):
    sent = []

    class _Usage:
        prompt_tokens, completion_tokens = 1_000_000, 0

    class _Resp:
        usage = _Usage()
        choices = [type("C", (), {"message": type("M", (), {"content": '{"ok": true}'})()})()]

    class _Client:
        def __init__(self, prov):
            self.prov, self.chat, self.completions = prov, self, self

        def create(self, **kw):
            sent.append((self.prov, kw.get("model"), (kw.get("response_format") or {}).get("type"),
                         "extra_body" in kw))
            return _Resp()

    llm.set_backend(None)
    monkeypatch.setattr(llm, "_client", lambda prov: _Client(prov))
    before = llm.USAGE["cost_usd"]
    monkeypatch.setitem(llm.MODEL_PRICES, "example/brain-model", {"deepinfra": (0.09, 0.18)})
    out = llm.chat_json("s", "u", schema={"type": "object"}, model="example/brain-model",
                        provider="deepinfra", fallback="deepinfra")
    assert out == {"ok": True}
    assert sent == [("deepinfra", "example/brain-model", "json_schema", False)]
    assert abs(llm.USAGE["cost_usd"] - before - 0.09) < 1e-9
    # a pair listed without structured output goes straight to json_object
    sent.clear()
    llm.chat_json("s", "u", schema={"type": "object"}, model="openai/gpt-oss-120b", provider="deepinfra",
                  fallback="deepinfra")
    assert sent[0][2] == "json_object"
    # the default call (live translation) is unchanged: gpt-oss with reasoning_effort
    sent.clear()
    llm.chat_json("s", "u", schema={"type": "object"}, provider="cerebras")
    assert sent[0] == ("cerebras", llm.LLM_MODEL, "json_schema", True)
