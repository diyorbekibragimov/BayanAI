"""Coherence hold, offline (fake LLM): a doctor's plan / diagnosis / clinical claim that does not add up is held on the
existing held screen before the patient hears it; questions and small talk are never checked; a failed or slow check
never blocks the sentence."""

from __future__ import annotations

import html
import json
import re
import time

import pytest

from bayan import consult, talk
from bayan.brain import agentkit, coherence, llm, wrapup
from bayan.brain import copilot as brain

CHECK_SYSTEM = "You are a senior clinician standing beside a doctor"

# patient (Nepali, as said) -> English rendering; doctor (English) -> statement label
PATIENT = {
    "मेरो चाक दुखेको छ।": "My bottom hurts.",
    "म चिसो टायलमा बसेँ, अहिले जाडो लाग्छ।": "I sat on cold tiles, now I feel cold.",
}
DOCTOR = {
    "Any allergies to medicines?": "question",
    "Hello, nice to see you.": "other",
    "You are very hot and have a really high temperature.": "claim",
    "Your temperature is really high, you are burning up.": "claim",
    "It is a muscle strain from the cold floor.": "diagnosis",
    "Amoxicillin 500 three times a day.": "plan",
}
AMOX = {"name": "amoxicillin", "intent": "prescribe", "dose_mg": 500, "frequency_per_day": 3, "dose": "500"}

HOLD = {"hold": True, "reason": "No temperature was taken, and the patient said they feel cold",
        "kind": "contradiction", "confidence": 0.93,
        "evidence": [{"utt": "u002", "quote": "now I feel cold"}, {"utt": "u003", "quote": "really high temperature"}]}


class Fake:
    """llm.set_backend() fake routed by system prompt; the coherence reply is set per test."""

    def __init__(self):
        self.check = {"hold": False, "reason": "", "kind": "other", "confidence": 0.1, "evidence": []}
        self.calls: list[str] = []          # coherence prompts seen
        self.delay = 0.0
        self.error = False

    def __call__(self, messages, schema, max_tokens):
        system, user = messages[0]["content"], messages[-1]["content"]
        if system.startswith("You are Bayan, a professional medical interpreter"):
            utt = user.rsplit("Utterance: ", 1)[1].strip()
            if utt in PATIENT:
                return json.dumps({"translation": PATIENT[utt], "english": PATIENT[utt], "drugs": [], "allergies": [],
                                   "tests": [], "statement": "claim"})       # patient turns are forced to "other"
            if "पेनिसिलिन" in utt:
                en = "Penicillin made my body swell."
                return json.dumps({"translation": en, "english": en, "drugs": [{"name": "penicillin", "intent": "mention"}],
                                   "allergies": [{"substance": "penicillin", "reaction": "swelling"}], "tests": [],
                                   "statement": "other"})
            return json.dumps({"translation": "नेपाली अनुवाद: डाक्टरको वाक्य", "english": utt,
                               "drugs": [AMOX] if utt.startswith("Amoxicillin") else [], "allergies": [], "tests": [],
                               "statement": DOCTOR.get(utt, "other")}, ensure_ascii=False)
        if system.startswith(CHECK_SYSTEM):
            assert schema is coherence.SCHEMA and max_tokens <= 600
            self.calls.append(user)
            if self.delay:
                time.sleep(self.delay)
            if self.error:
                raise RuntimeError("provider down")
            return json.dumps(self.check)
        if system.startswith("Translate each English string into formal Modern Standard Arabic"):
            return json.dumps({"ar": ["ع: " + x for x in json.loads(user)]}, ensure_ascii=False)
        return "{}"


class _FastTime:
    def __getattr__(self, name):
        return getattr(time, name)

    @staticmethod
    def sleep(_s):
        return None


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setenv("BAYAN_OUTPUT_ROOT", str(tmp_path / "out"))
    monkeypatch.setenv("BAYAN_AGENT", "off")
    monkeypatch.setattr(brain, "DEBOUNCE_S", 0.01)
    monkeypatch.setattr(consult, "time", _FastTime())
    monkeypatch.setattr(talk, "speak", lambda *a, **k: None)
    monkeypatch.setattr(talk, "speak_chunks", lambda *a, **k: iter(()))
    f = Fake()
    llm.set_backend(f)
    agentkit.set_model_factory(None)
    yield f
    llm.set_backend(None)


def _new(doc_lang="en"):
    s = consult.SESS[consult.new_sid()]
    s.lang, s.doc_lang, s.screen, s.started_at = "ne", doc_lang, "live", time.time()
    consult.begin(s)
    return s


def _say(s, role, text):
    return list(consult.process_text(s, role, text, s.doc_lang if role == "doctor" else "ne"))


def _to_patient(s):
    return [p.kind for p in s.pending if p.to == "patient"]


def _view(s) -> dict:
    raw = re.search(r'data-s="([^"]*)"', consult.render(s)).group(1)
    return json.loads(html.unescape(raw))


def _history(s):
    _say(s, "patient", "मेरो चाक दुखेको छ।")
    _say(s, "patient", "म चिसो टायलमा बसेँ, अहिले जाडो लाग्छ।")
    s.pending.clear()


# ------------------------------------------------------------------ routing
def test_translate_returns_the_statement_and_patients_are_always_other(fake):
    assert "statement" in talk.TRANSLATE_SCHEMA["required"]
    assert talk.translate("You are very hot and have a really high temperature.", "doctor", "en", "ne")["statement"] == "claim"
    assert talk.translate("मेरो चाक दुखेको छ।", "patient", "ne", "en")["statement"] == "other"
    llm.set_backend(lambda *a: json.dumps({"translation": "x", "english": "y", "statement": "Lecture"}))
    assert talk.translate("x", "doctor", "en", "ne")["statement"] == "other"      # unknown / missing -> never checked


def test_questions_small_talk_and_patient_turns_are_never_checked(fake):
    s = _new()
    fake.check = HOLD
    _history(s)
    _say(s, "doctor", "Any allergies to medicines?")
    assert s.held is None and _to_patient(s) == ["turn"]
    _say(s, "doctor", "Hello, nice to see you.")
    assert s.held is None and fake.calls == []


# ------------------------------------------------------------------ hold / no hold
def test_confident_hold_shows_the_held_screen_with_reason_and_quotes(fake):
    s = _new()
    _history(s)
    fake.check = HOLD
    _say(s, "doctor", "You are very hot and have a really high temperature.")
    h = s.held
    assert s.live == "held" and h["rule"] == coherence.RULE_ID and h["kind"] == "contradiction"
    assert h["headline"] == "No temperature was taken, and the patient said they feel cold."
    assert h["pq"] == "now I feel cold"                                   # the patient's own words
    assert h["dq"] == "You are very hot and have a really high temperature."
    assert not _to_patient(s)                                             # nothing said to the patient
    assert s.brain.turn_by_id(h["utt"]).held
    assert {k: _view(s)["held"][k] for k in ("headline", "pq", "dq")} == {k: h[k] for k in ("headline", "pq", "dq")}
    # the prompt carries the case, the patient's original words + English, and the sentence under check
    p = fake.calls[0]
    assert "CASE SUMMARY" in p and "चिसो टायलमा" in p and "I feel cold" in p
    assert "DOCTOR'S SENTENCE TO CHECK (claim)" in p and "really high temperature" in p
    # the concern is a caution card (agent), hidden from the notes while the held screen shows it
    card = s.brain.cards.get(h["cards"][0])
    assert (card["source"], card["kind"], card["severity"], card["dimension"]) == ("agent", "observation", "caution",
                                                                                  "consistency")
    assert [e["utt"] for e in card["evidence"]] == ["u002", "u003"]
    assert not any(n["text"] == card["title"] for n in _view(s)["notes"])
    assert any("Paused, not said" in n["text"] for n in s.notes)


def test_below_threshold_is_spoken_normally(fake):
    s = _new()
    _history(s)
    fake.check = dict(HOLD, confidence=coherence.HOLD_MIN - 0.05)
    _say(s, "doctor", "You are very hot and have a really high temperature.")
    assert s.held is None and s.live == "doctor" and _to_patient(s) == ["turn"]
    assert not [c for c in s.brain.cards.all_cards() if c.get("coherence")]
    assert len(fake.calls) == 1


def test_not_hold_is_spoken(fake):
    s = _new()
    _history(s)
    _say(s, "doctor", "It is a muscle strain from the cold floor.")
    assert len(fake.calls) == 1 and s.held is None and _to_patient(s) == ["turn"]


@pytest.mark.parametrize("mode", ["error", "timeout", "bad json"])
def test_failed_or_slow_check_speaks_the_sentence(fake, monkeypatch, mode):
    s = _new()
    _history(s)
    fake.check = HOLD
    if mode == "error":
        fake.error = True
    elif mode == "timeout":
        monkeypatch.setattr(coherence, "TIMEOUT_S", 0.05)
        fake.delay = 0.5
    else:
        fake.check = {"nonsense": 1}
    t0 = time.time()
    _say(s, "doctor", "You are very hot and have a really high temperature.")
    assert time.time() - t0 < 0.45                                        # never waits past the timeout
    assert s.held is None and _to_patient(s) == ["turn"]
    assert any("coherence check" in t["text"] for t in s.brain.trace if t["kind"] == "error")


def test_prescription_gate_hold_wins_and_skips_the_check(fake):
    s = _new()
    _say(s, "patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर फुलेर आयो।")
    fake.check = HOLD
    _say(s, "doctor", "Amoxicillin 500 three times a day.")
    assert s.held["rule"] == "ALG-PEN-01" and fake.calls == []


def test_invented_quotes_are_dropped(fake):
    s = _new()
    _history(s)
    fake.check = dict(HOLD, evidence=[{"utt": "u002", "quote": "I have no fever at all"}])
    _say(s, "doctor", "You are very hot and have a really high temperature.")
    h = s.held
    assert h["pq"] == ""                                                  # no invented patient words on screen
    card = s.brain.cards.get(h["cards"][0])
    assert [e["utt"] for e in card["evidence"]] == [h["utt"]]             # the held sentence itself


# ------------------------------------------------------------------ the doctor's choice
def test_say_something_else_withdraws_and_the_concern_is_recorded(fake):
    s = _new()
    _history(s)
    fake.check = HOLD
    _say(s, "doctor", "You are very hot and have a really high temperature.")
    h = s.held
    consult.held_else(s)
    assert s.held is None and s.live == "idle" and not _to_patient(s)
    turn = s.brain.turn_by_id(h["utt"])
    assert turn.kind == "system" and turn.held                            # never interpreted, never extracted
    card = s.brain.cards.get(h["cards"][0])
    assert card["status"] == "acknowledged"
    assert any(n["text"] == card["title"] for n in _view(s)["notes"])     # now in "Noted in this visit"
    row = next(r for r in wrapup.copilot_concerns(s.brain) if r["id"] == card["id"])
    assert row["status"] == "acknowledged" and "said something else" in row["reason"]


def test_speak_it_anyway_overrides_and_the_same_issue_is_not_held_again(fake):
    s = _new()
    _history(s)
    fake.check = HOLD
    _say(s, "doctor", "You are very hot and have a really high temperature.")
    h = s.held
    consult.held_anyway(s)
    assert s.held is None and _to_patient(s) == ["override"]
    assert not s.brain.turn_by_id(h["utt"]).held
    card = s.brain.cards.get(h["cards"][0])
    assert card["status"] == "overridden"
    assert any(n["kind"] == "override" and n["text"] == "Said anyway after the pause" for n in s.notes)
    row = next(r for r in wrapup.copilot_concerns(s.brain) if r["id"] == card["id"])
    assert row["status"] == "overridden" and row["severity"] == "caution"
    # the doctor insists: the same point (reworded) is not held again, and the prompt says it was overridden
    s.pending.clear()
    fake.check = dict(HOLD, reason="The patient said they feel cold; no temperature was measured")
    _say(s, "doctor", "Your temperature is really high, you are burning up.")
    assert "ALREADY SAID ANYWAY" in fake.calls[-1] and HOLD["reason"] in fake.calls[-1]
    assert s.held is None and _to_patient(s) == ["turn"]
    # a different issue still holds
    s.pending.clear()
    fake.check = {"hold": True, "reason": "Muscle strain does not explain the high temperature you stated",
                  "kind": "plan_mismatch", "confidence": 0.9, "evidence": []}
    _say(s, "doctor", "It is a muscle strain from the cold floor.")
    assert s.held and s.held["kind"] == "plan_mismatch"


def test_arabic_doctor_gets_the_headline_in_arabic(fake):
    s = _new("ar")
    _history(s)
    fake.check = HOLD
    _say(s, "doctor", "You are very hot and have a really high temperature.")
    h = s.held
    assert h["headline"] == "ع: No temperature was taken, and the patient said they feel cold."
    assert h["pq"] == s.shown["u002"]                                     # the patient's words as the doctor saw them
