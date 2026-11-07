"""UI shell x brain integration, offline: the stage's consult flow over bayan.brain (fake LLM, no TTS, no network).

DEMO_TR / demo_backend script the talk-loop translation JSON, the extractor and the care-plan writer for the
teammate's no-mic DEMO_SCRIPT; scripts reuse them for an offline end-to-end run of app.run_demo.
"""

from __future__ import annotations

import json
import re

import pytest

from bayan import careplan, consult, talk
from bayan import copilot as ui_copilot
from bayan.brain import agentkit, llm
from bayan.brain import copilot as brain

AMOX = {"name": "amoxicillin", "intent": "prescribe", "dose_mg": 500, "frequency_per_day": 3, "dose": "500"}
QUESTION = "Is there sweating, breathlessness, nausea, or pain going to the arm, jaw, neck or back?"

# utterance -> talk-loop translation JSON (what gpt-oss returns with TRANSLATE_SCHEMA)
DEMO_TR = {
    "Do you have any allergies to medicines?": {
        "translation": "के तपाईंलाई कुनै औषधिको एलर्जी छ?", "drugs": [], "allergies": [], "tests": []},
    "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर सुन्नियो।": {
        "translation": "Once, when I had a penicillin injection, my body swelled up.",
        "english": "Once, when I had a penicillin injection, my body swelled up.",
        "drugs": [{"name": "penicillin", "intent": "mention"}],
        "allergies": [{"substance": "penicillin", "reaction": "body swelling"}], "tests": []},
    "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ, काम गर्दा झन् बढ्छ।": {
        "translation": "My chest burns like gastric, and it gets worse when I work.",
        "english": "My chest burns like gastric, and it gets worse when I work.",
        "drugs": [], "allergies": [], "tests": []},
    QUESTION: {"translation": "के पसिना आउँछ, सास फेर्न गाह्रो हुन्छ, वाकवाकी लाग्छ, वा दुखाइ पाखुरा, बङ्गारा, घाँटी वा "
                              "ढाडसम्म जान्छ?", "drugs": [], "allergies": [], "tests": []},
    "Amoxicillin 500 three times a day, and you can go home.": {
        "translation": "एमोक्सिसिलिन ५०० दिनमा तीन पटक, अनि तपाईं घर जान सक्नुहुन्छ।", "drugs": [AMOX],
        "allergies": [], "tests": []},
    "Let’s not use amoxicillin. Take paracetamol 1 g up to three times a day. We will also check your heart with an "
    "ECG and a blood test.": {
        "translation": "एमोक्सिसिलिन नचलाऔं। प्यारासिटामोल 1 g दिनमा तीन पटकसम्म खानुहोस्। हामी ECG र रगत जाँचले तपाईंको "
                       "मुटु पनि जाँच्नेछौं।",
        "drugs": [{"name": "amoxicillin", "intent": "stop"},
                  {"name": "paracetamol", "intent": "prescribe", "dose_mg": 1000, "frequency_per_day": 3,
                   "dose": "1 g"}],
        "allergies": [], "tests": ["ECG", "blood test"]},
    "Actually, no amoxicillin.": {
        "translation": "वास्तवमा, एमोक्सिसिलिन होइन।", "drugs": [{"name": "amoxicillin", "intent": "stop"}],
        "allergies": [], "tests": []},
}


def _translate_reply(user: str) -> dict:
    utt = user.rsplit("Utterance: ", 1)[1].strip()
    out = dict(DEMO_TR.get(utt) or {"translation": f"[ne] {utt}", "drugs": [], "allergies": [], "tests": []})
    out.setdefault("english", utt)
    return out


def _extract_reply(user: str) -> dict:
    new = user.split("NEW TURNS (extract from these):", 1)[1].split("\n\nquestion topics:", 1)[0]
    out: dict = {}
    for line in new.strip().splitlines():
        utt, low = line.split()[0], line.lower()
        ev = [{"utt": utt, "quote": line.split(": ", 1)[-1][:120]}]
        if "chest burns" in low:
            out.setdefault("symptoms", []).append({"code": "chest_burning", "evidence": ev})
        if "check your heart with an ecg" in low:
            out["investigations"] = [{"code": "ecg_12lead", "status": "ordered", "evidence": ev}]
    return out


def _plan_reply(user: str) -> dict:
    asked = json.loads(user).get("translate", {})
    return {"translations": [{"key": k, "native": f"नेपाली: {en}"} for k, en in asked.items()],
            "red_flags": [{"en": "Your chest pain comes back or spreads to your arm or jaw.",
                           "native": "छातीको दुखाइ फेरि आयो वा पाखुरा वा बङ्गारासम्म फैलियो भने।"}],
            "advice": [], "follow_up": {"en": "", "native": ""}}


def demo_backend(messages, schema, max_tokens) -> str:
    """llm.set_backend() fake: routes by system prompt (talk-loop translation, extraction, care plan)."""
    system, user = messages[0]["content"], messages[-1]["content"]
    if system.startswith("You are Bayan, a professional medical interpreter"):
        assert schema is talk.TRANSLATE_SCHEMA
        return json.dumps(_translate_reply(user), ensure_ascii=False)
    if system.startswith("You extract clinical facts"):
        return json.dumps(_extract_reply(user), ensure_ascii=False)
    if system.startswith(("CLINIC NOTE WRITER", "SOAP NOTE WRITER", "CHUNK SUMMARISER")):
        return "{}"       # the note falls back to the deterministic structured-record note
    return json.dumps(_plan_reply(user), ensure_ascii=False)


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    monkeypatch.setenv("BAYAN_OUTPUT_ROOT", str(tmp_path / "out"))
    monkeypatch.setattr(brain, "DEBOUNCE_S", 0.01)
    monkeypatch.setattr(consult, "time", _FastTime())
    monkeypatch.setattr(talk, "speak", lambda *a, **k: None)
    monkeypatch.setattr(talk, "speak_chunks", lambda *a, **k: iter(()))
    llm.set_backend(demo_backend)
    agentkit.set_model_factory(None)
    yield
    llm.set_backend(None)


class _FastTime:
    """consult's clock without the UX pauses (time.sleep is a no-op; time.time is real)."""

    def __getattr__(self, name):
        import time as _t
        return getattr(_t, name)

    @staticmethod
    def sleep(_s):
        return None


def _new():
    sid = consult.new_sid()
    s = consult.SESS[sid]
    s.lang, s.screen, s.started_at = "ne", "live", __import__("time").time()
    consult.begin(s)
    return s


def _say(s, role, text):
    return list(consult.process_text(s, role, text, "en" if role == "doctor" else "ne"))


def _view(s) -> dict:
    html = consult.render(s)
    raw = re.search(r'data-s="([^"]*)"', html).group(1)
    return json.loads(__import__("html").unescape(raw))


# ------------------------------------------------------------------ talk loop -> prescription gate
def test_translate_uses_schema_context_and_normalises_intent():
    seen = {}

    def fn(messages, schema, max_tokens):
        seen.update(schema=schema, user=messages[-1]["content"])
        return json.dumps({"translation": "x", "english": "y", "drugs": [{"name": " Amoxicillin "},
                                                                         {"name": "x", "intent": "STOP"}],
                           "allergies": [{"reaction": "rash"}], "tests": "ECG"})
    llm.set_backend(fn)
    tr = talk.translate("Amoxicillin.", "doctor", "en", "ne", context=["Patient: I am allergic to penicillin."])
    assert seen["schema"] is talk.TRANSLATE_SCHEMA and "I am allergic to penicillin" in seen["user"]
    assert tr["drugs"] == [{"name": "amoxicillin", "intent": "prescribe"}, {"name": "x", "intent": "stop"}]
    assert tr["allergies"] == [] and tr["tests"] == []


def test_actually_no_amoxicillin_is_not_held():
    s = _new()
    _say(s, "patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर सुन्नियो।")
    assert s.brain.state["allergies"][0]["substance"] == "penicillin"
    _say(s, "doctor", "Actually, no amoxicillin.")
    assert s.held is None and s.live == "doctor"
    assert [p.kind for p in s.pending] == ["turn"]          # spoken to the patient
    assert not any(c["severity"] == "critical" for c in s.brain.cards.all_cards())


def test_penicillin_allergy_holds_amoxicillin_and_say_something_else_discards_it():
    s = _new()
    _say(s, "patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर सुन्नियो।")
    _say(s, "doctor", "Amoxicillin 500 three times a day, and you can go home.")
    h = s.held
    assert s.live == "held" and h["rule"] == "ALG-PEN-01" and h["drug"] == "amoxicillin"
    assert h["headline"] == "The patient reported a penicillin allergy. Amoxicillin is a penicillin."
    assert "penicillin injection" in h["pq"] and h["dq"].startswith("Amoxicillin 500")
    v = _view(s)
    assert {k: v["held"][k] for k in ("headline", "pq", "drug", "rule")} == {k: h[k] for k in ("headline", "pq", "drug", "rule")}
    assert not s.pending                                     # nothing spoken
    turn = s.brain.turn_by_id(h["utt"])
    assert turn.held and any(m["drug"] == "amoxicillin" for m in s.brain.state["prescribed_meds"])
    consult.held_else(s)
    assert s.held is None and s.live == "idle" and not s.pending
    assert turn.kind == "system" and turn.held               # discarded: never interpreted, never extracted
    assert not any(m["drug"] == "amoxicillin" for m in s.brain.state["prescribed_meds"])
    card = s.brain.cards.get(h["cards"][0])
    assert card["status"] == "resolved"
    assert any(a["action"] == "acknowledge" and "said something else" in (a["reason"] or "") for a in s.brain.audit)


def test_speak_it_anyway_is_an_audited_override():
    s = _new()
    _say(s, "patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर सुन्नियो।")
    _say(s, "doctor", "Amoxicillin 500 three times a day, and you can go home.")
    h = s.held
    consult.held_anyway(s)
    assert s.held is None and [p.kind for p in s.pending] == ["override"]
    assert s.brain.cards.get(h["cards"][0])["status"] == "overridden"
    assert any(a["action"] == "override" and a["reason"] == "spoken anyway by clinician" for a in s.brain.audit)
    assert not s.brain.turn_by_id(h["utt"]).held             # it was interpreted after all
    assert any(n["kind"] == "override" for n in s.notes)


# ------------------------------------------------------------------ cards -> suggestions / notes
def test_idiom_turn_gives_explanation_and_red_flag_first_suggestion_from_cards():
    s = _new()
    _say(s, "patient", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ, काम गर्दा झन् बढ्छ।")
    v = _view(s)
    assert v["patient"]["idiom"] == "ग्यास्ट्रिक"
    assert v["patient"]["note"].startswith("Gyastrik usually means") and "acute coronary syndrome" in v["patient"]["note"]
    assert [x["text"] for x in v["suggestions"]] == [QUESTION] and v["badge"] == 1
    sug = v["suggestions"][0]
    card = s.brain.cards.get(sug["id"])
    assert card["kind"] == "ask" and card["grounding"] == "npi-005"
    assert consult.ask_suggestion(s, sug["id"])
    assert s.brain.cards.get(sug["id"])["status"] == "accepted"
    t = s.brain.turns[-1]
    assert (t.role, t.kind, t.text) == ("bayan", "ask", QUESTION) and t.translation
    assert [p.kind for p in s.pending] == ["ask"]
    assert _view(s)["badge"] == 0 and not consult.ask_suggestion(s, sug["id"])   # asked once


def test_cards_map_to_notes_and_poll_render_picks_up_async_cards():
    s = _new()
    _say(s, "patient", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ, काम गर्दा झन् बढ्छ।")
    consult.render(s)
    assert consult.poll_render(s) is None                    # nothing new
    utt = s.brain.turns[-1].id
    cid = s.brain.cards.post("observation", "Patient works outdoors in the heat", "why", [{"utt": utt}], utt,
                             severity="caution", source="agent")
    assert cid.startswith("c")
    html = consult.poll_render(s)                            # a card arrived in the background: re-render
    assert html is not None and "Patient works outdoors in the heat" in __import__("html").unescape(html)
    assert consult.poll_render(s) is None
    notes = ui_copilot.notes(s.brain)
    assert {"kind": "observation", "text": "Patient works outdoors in the heat", "id": cid} in notes
    s.brain.cards.act(cid, "dismiss")
    assert not any(n.get("id") == cid for n in ui_copilot.notes(s.brain))
    # a background think run (extraction -> rules -> fallback cards) never blocks and lands as cards
    assert brain.idle(s.brain, 10)
    assert s.brain.state["symptoms"][0]["code"] == "chest_burning"


# ------------------------------------------------------------------ end of visit -> review -> plan page / PDFs
def _golden_visit():
    s = _new()
    consult.record_consent(s)
    for role, text in consult.DEMO_SCRIPT:
        if role in ("doctor", "patient"):
            _say(s, role, text)
            s.pending.clear()
        elif role == "ask":
            sug = next(x for x in consult.refresh(s) if x["status"] == "open")
            assert consult.ask_suggestion(s, sug["id"])
        elif role == "held_else":
            assert s.held and s.held["rule"] == "ALG-PEN-01"
            consult.held_else(s)
    return s


def test_end_visit_produces_pdfs_and_plan_page_from_the_structured_plan():
    s = _golden_visit()
    steps = []
    for _ in consult.end_visit(s, "http://testserver"):
        steps.append([st["state"] for st in s.steps])
    assert s.screen == "review" and steps[-1] == ["done", "done", "done"]
    out = s.brain.outputs
    for k in ("doctor_pdf", "patient_pdf"):
        with open(out[k], "rb") as f:
            assert f.read(5) == b"%PDF-"
    plan = out["care_plan"]
    assert [m["drug"] for m in plan["medicines"]] == ["paracetamol"]   # amoxicillin was held and withdrawn
    assert any("penicillin" in a["en"].lower() for a in plan["avoid"])
    r = _view(s)["review"]
    assert "Paracetamol" in r["plan_en"] and "Do not take" in r["plan_en"] and "नेपाली:" in r["plan_en"]
    assert r["note"].startswith("#") and r["doctor_pdf"].endswith("/doctor_report.pdf")
    assert r["patient_pdf"].endswith("/care_plan.pdf") and r["qr"].startswith("<svg")
    assert not any(w.startswith("Audio not available") for w in r["warnings"])
    pid = r["plan_id"]
    code, body = careplan.page_html(pid)
    assert code == 200 and "almost ready" in body                       # not before approval
    token = r["patient_pdf"].split("/")[2]
    assert careplan.open_file(token, "care_plan.pdf")[0][:5] == b"%PDF-"
    assert careplan.open_file(token, "doctor_report.pdf") is None       # the patient token cannot reach it

    edited = r["note"] + "\n\n## Clinician addendum\n\n- Reviewed with the patient."
    list(consult.approve(s, r["plan_en"], edited))
    assert s.screen == "sent" and out["approved_at"] and out["note_md"] == edited
    code, body = careplan.page_html(pid)
    assert code == 200
    for needle in ("Your medicines", "Do not take", "Call 999 or come back now if", "नेपाली: Paracetamol",
                   f"/files/{token}/care_plan.pdf"):
        assert needle in body, needle
    assert "almost ready" not in body and "<script" not in body

    # session reset erases the consultation (folder, doctor token); the approved patient PDF stays with the plan
    dtoken = r["doctor_pdf"].split("/")[2]
    folder = __import__("pathlib").Path(out["out_dir"])
    consult.reset(s)
    assert not folder.exists() and careplan.open_file(dtoken, "doctor_report.pdf") is None
    assert careplan.open_file(token, "care_plan.pdf")[0][:5] == b"%PDF-"
    assert careplan.page_html(pid)[0] == 200


def test_plan_page_unknown_and_schedule_table(monkeypatch):
    assert careplan.page_html("nope")[0] == 404
    plan = {"lang": "ne", "medicines": [{"name": "Amlodipine", "name_native": "एम्लोडिपिन", "title_en": "Amlodipine 5 mg",
                                         "note_en": "Take 1 tablet every morning.", "slots": ["breakfast"],
                                         "dose_amount_en": "1 tablet", "prn": False}],
            "avoid": [], "advice": [{"en": "Rest.", "native": "आराम गर्नुहोस्।"}], "red_flags": [], "emergency": "999"}
    pid = careplan.create("ne", plan)
    careplan.approve(pid)
    body = careplan.page_html(pid)[1]
    assert "दैनिक तालिका" in body and "<table" in body and "Download PDF" not in body
    monkeypatch.setenv("BAYAN_PDF_SCHEDULE_TABLE", "off")
    assert "<table" not in careplan.page_html(pid)[1]


def test_file_tokens_reject_unknown_and_unsafe_names(tmp_path):
    (tmp_path / "care_plan.pdf").write_bytes(b"%PDF-1.4 x")
    (tmp_path / "secret.txt").write_text("no")
    tok = "A" * 22
    careplan.register_files(tok, tmp_path, ["care_plan.pdf", "secret.txt", "../x"])
    assert careplan.open_file(tok, "care_plan.pdf") == (b"%PDF-1.4 x", "application/pdf")
    for t, n in ((tok, "secret.txt"), (tok, "../care_plan.pdf"), ("B" * 22, "care_plan.pdf"), ("short", "care_plan.pdf"),
                 (tok, "doctor_report.pdf")):
        assert careplan.open_file(t, n) is None
    with pytest.raises(ValueError):
        careplan.register_files("../../etc", tmp_path, ["care_plan.pdf"])
    careplan.forget_files([tok])
    assert careplan.open_file(tok, "care_plan.pdf") is None
