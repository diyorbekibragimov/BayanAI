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
    "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर फुलेर आयो।": {
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



def _to_patient(s):
    """Speech queued for the patient. (The patient's own words are also read to the doctor: to="doctor".)"""
    return [p.kind for p in s.pending if p.to == "patient"]

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
    _say(s, "patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर फुलेर आयो।")
    assert s.brain.state["allergies"][0]["substance"] == "penicillin"
    _say(s, "doctor", "Actually, no amoxicillin.")
    assert s.held is None and s.live == "doctor"
    assert _to_patient(s) == ["turn"]                        # spoken to the patient
    assert [(p.to, p.lang) for p in s.pending if p.to == "doctor"] == [("doctor", "en")]  # the patient's words, to the doctor
    assert not any(c["severity"] == "critical" for c in s.brain.cards.all_cards())


def test_penicillin_allergy_holds_amoxicillin_and_say_something_else_discards_it():
    s = _new()
    _say(s, "patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर फुलेर आयो।")
    _say(s, "doctor", "Amoxicillin 500 three times a day, and you can go home.")
    h = s.held
    assert s.live == "held" and h["rule"] == "ALG-PEN-01" and h["drug"] == "amoxicillin"
    assert h["headline"] == "The patient reported a penicillin allergy. Amoxicillin is a penicillin."
    assert "penicillin injection" in h["pq"] and h["dq"].startswith("Amoxicillin 500")
    v = _view(s)
    assert {k: v["held"][k] for k in ("headline", "pq", "drug", "rule")} == {k: h[k] for k in ("headline", "pq", "drug", "rule")}
    assert not _to_patient(s)                                # nothing spoken to the patient
    turn = s.brain.turn_by_id(h["utt"])
    assert turn.held and any(m["drug"] == "amoxicillin" for m in s.brain.state["prescribed_meds"])
    consult.held_else(s)
    assert s.held is None and s.live == "idle" and not _to_patient(s)
    assert turn.kind == "system" and turn.held               # discarded: never interpreted, never extracted
    assert not any(m["drug"] == "amoxicillin" for m in s.brain.state["prescribed_meds"])
    card = s.brain.cards.get(h["cards"][0])
    assert card["status"] == "resolved"
    assert any(a["action"] == "acknowledge" and "said something else" in (a["reason"] or "") for a in s.brain.audit)


def test_speak_it_anyway_is_an_audited_override():
    s = _new()
    _say(s, "patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर फुलेर आयो।")
    _say(s, "doctor", "Amoxicillin 500 three times a day, and you can go home.")
    h = s.held
    consult.held_anyway(s)
    assert s.held is None and _to_patient(s) == ["override"]
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
    assert _to_patient(s) == ["ask"]
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
    token = r["patient_pdf"].split("/files/")[1].split("/")[0]   # links are absolute (phones open them)
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
    dtoken = r["doctor_pdf"].split("/files/")[1].split("/")[0]
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


# ------------------------------------------------------------------ voice state: one consultation, the right listener
import numpy as np  # noqa: E402


def _tone(lang: str, seconds: float = 1.0, sr: int = 16000) -> np.ndarray:
    """A clip that says which language produced it (amplitude per language): cross-serving shows up at once."""
    amp = {"ne": 0.1, "hi": 0.2, "sw": 0.3, "tl": 0.4, "id": 0.5, "en": 0.6, "ar": 0.7}.get(lang, 0.05)
    return np.full(int(seconds * sr), amp, dtype=np.float32)


@pytest.fixture
def tts(monkeypatch):
    """talk.speak_chunks stand-in that records every synthesis call."""
    calls = []

    def fake(text, lang, description=""):
        calls.append((text, lang))
        yield 16000, _tone(lang, max(0.8, len(text) / 12))
    monkeypatch.setattr(talk, "speak_chunks", fake)
    with consult._CLIPS_LOCK:
        consult._CLIPS.clear()
    yield calls
    with consult._CLIPS_LOCK:
        consult._CLIPS.clear()


def _items(html: str) -> list[dict]:
    return [dict(re.findall(r"data-(\w+)='([^']*)'", m)) for m in re.findall(r"<i class='bz-au'([^>]*)>", html or "")]


def _speak(s, sp):
    """Run speak_clip; returns the last audio html it sent (None if it never spoke)."""
    last = None
    for ev in consult.speak_clip(s, sp):
        if ev != consult.UI and ev[1]:
            last = ev[1]
    return last


def _pcm_amp(item: dict) -> float:
    import base64
    return float(np.frombuffer(base64.b64decode(item["p"]), dtype="<i2")[0]) / 32767


def test_clip_cache_never_serves_another_language_or_visit(tts):
    s = _new()
    s.lang = "sw"
    same = "Habari daktari ni mzuri sana leo"        # identical Latin text for two Latin-script patients
    sp = consult.Speech(same, "sw", "patient", True, kind="turn", cid=s.cid)
    a = _items(_speak(s, sp))
    assert a and all(it["c"] == s.cid for it in a) and abs(_pcm_amp(a[0]) - 0.3) < 1e-3
    s2 = _new()
    s2.lang = "id"
    b = _items(_speak(s2, consult.Speech(same, "id", "patient", True, kind="turn", cid=s2.cid)))
    assert abs(_pcm_amp(b[0]) - 0.5) < 1e-3 and b[0]["c"] == s2.cid   # its own synthesis, its own voice
    assert tts == [(same, "sw"), (same, "id")]
    _speak(s, consult.Speech(same, "sw", "patient", True, kind="again", cid=s.cid))   # Say it again: from the cache
    assert len(tts) == 2
    consult.reset(s)                                                    # a dropped visit's clips are gone
    assert not any(k[0] == s.cid for k in consult._CLIPS)
    assert any(k[0] == s2.cid for k in consult._CLIPS)


def test_clip_cache_refuses_garbage_and_anything_streamed_across_a_worker_failure(monkeypatch, tts):
    key = ("scope", "नमस्ते, तपाईंलाई कस्तो छ? आज धेरै राम्रो दिन हो।", "ne")
    # too short for the text, or silent: never stored
    for pcm in (np.full(1600, 3000, np.int16), np.zeros(40000, np.int16)):
        assert not consult._clip_put((*key, consult._voice_id()), 16000, pcm, key[1], "ne")
    assert consult._clip_put((*key, consult._voice_id()), 16000, np.full(40000, 3000, np.int16), key[1], "ne")
    # the worker fails mid-stream: the cache is cleared, the partial clip is not stored
    def broken(text, lang, description=""):
        yield 16000, _tone(lang)
        raise RuntimeError("worker rebooting")
    monkeypatch.setattr(talk, "speak_chunks", broken)
    with pytest.raises(RuntimeError):
        list(consult.voice_chunks("Some words to say here", "ne", "x"))
    assert not consult._CLIPS
    # a stream that was running while another one failed is never stored either
    def slow_ok(text, lang, description=""):
        yield 16000, _tone(lang, 3.0)
        consult.voice_failed()
    monkeypatch.setattr(talk, "speak_chunks", slow_ok)
    assert len(list(consult.voice_chunks("नमस्ते", "ne", "x"))) == 1 and not consult._CLIPS
    # a refusal (no voice / wrong script) is not a worker failure: the cache survives
    if hasattr(talk, "NoVoice"):
        consult._clip_put((*key, consult._voice_id()), 16000, np.full(40000, 3000, np.int16), key[1], "ne")
        def refuse(text, lang, description=""):
            raise talk.NoVoice("not in script", "script", lang)
            yield  # noqa: unreachable - a generator
        monkeypatch.setattr(talk, "speak_chunks", refuse)
        with pytest.raises(talk.NoVoice):
            list(consult.voice_chunks("hello", "ne", "x"))
        assert len(consult._CLIPS) == 1


def test_clip_cache_is_bounded(monkeypatch, tts):
    monkeypatch.setattr(consult, "CLIP_MAX", 3)
    for i in range(6):
        assert consult._clip_put(("s", f"t{i}", "ne", consult._voice_id()), 16000, np.full(16000, 3000, np.int16), "x", "ne")
    assert [k[1] for k in consult._CLIPS] == ["t3", "t4", "t5"]
    monkeypatch.setattr(consult, "CLIP_MAX_BYTES", 40000)
    consult._clip_put(("s", "big", "ne", consult._voice_id()), 16000, np.full(16000, 3000, np.int16), "x", "ne")
    assert sum(v[1].nbytes for v in consult._CLIPS.values()) <= 40000


def test_speak_clip_only_speaks_the_current_visit_in_the_listeners_language(tts):
    s = _new()
    s.doc_lang = "ar"
    ok = consult.Speech("के तपाईंलाई दुख्छ?", "ne", "patient", True, kind="turn", cid=s.cid)
    assert _speak(s, consult.Speech(ok.text, "ne", "patient", True, kind="turn", cid="other")) is None   # another visit
    assert _speak(s, consult.Speech(ok.text, "ne", "patient", True, kind="turn")) is None                # unstamped
    assert _speak(s, consult.Speech("Does it hurt?", "en", "doctor", False, kind="turn", cid=s.cid)) is None  # doctor is ar
    assert _speak(s, consult.Speech(ok.text, "hi", "patient", True, kind="turn", cid=s.cid)) is None     # patient is ne
    assert not tts
    fresh = consult.reset(s)
    assert _speak(s, ok) is None and not tts                                   # Home / No: the old visit is silent
    assert fresh.cid != s.cid and fresh.lang == "ne" and not fresh.pending


def test_dropped_visit_never_records_or_queues_a_late_reply(monkeypatch):
    s = _new()
    real = talk.translate

    def translate_then_home(*a, **k):
        consult.reset(s)                          # the doctor pressed Home while the LLM was translating
        return real(*a, **k)
    monkeypatch.setattr(talk, "translate", translate_then_home)
    n = len(s.brain.turns)
    _say(s, "doctor", "Do you have any allergies to medicines?")
    assert not s.pending and len(s.brain.turns) == n
    fresh = consult.SESS[s.sid]
    assert fresh is not s and not fresh.pending and not fresh.brain.turns


def test_render_of_a_dropped_visit_shows_the_current_one_and_seq_never_goes_back():
    s = _new()
    s.lang = "ne"
    v1 = _view(s)
    fresh = consult.reset(s)
    fresh.lang = "hi"
    v2 = _view(s)                                  # a generator of the old visit renders: the page sees the new one
    assert v2["cid"] == fresh.cid != v1["cid"] and v2["screen"] == "start" and v2["seq"] > v1["seq"]
    assert f'data-c="{fresh.cid}"' in consult.render(s)
    assert _view(fresh)["seq"] > v2["seq"]


def test_wrong_language_text_is_shown_never_spoken():
    assert consult.speakable("के तपाईंलाई दुख्छ?", "ne") and consult.speakable("هل يؤلمك؟", "ar")
    assert consult.speakable("Paracetamol 1 g मात्र खानुहोस्।", "ne")       # a drug name inside the sentence is fine
    assert not consult.speakable("Does it hurt?", "ne")                       # untranslated English, Nepali voice
    assert not consult.speakable("Does it hurt?", "ar")                       # English text, Arabic doctor voice
    assert not consult.speakable("के तपाईंलाई दुख्छ?", "sw")                   # Nepali text, Swahili voice
    assert not consult.speakable("Do you have any pain today?", "sw", source="Do you have any pain today?")  # echo
    assert not consult.speakable("500 mg", "ne") and not consult.speakable("", "en")
    s = _new()
    assert not consult.queue_speech(s, consult.Speech("Does it hurt?", "ne", "patient"))
    assert not consult.queue_speech(s, consult.Speech("के दुख्छ?", "ne", "doctor"))     # the doctor hears en, not ne
    assert consult.queue_speech(s, consult.Speech("के दुख्छ?", "ne", "patient")) and s.pending[-1].cid == s.cid


def test_untranslated_doctor_sentence_is_not_spoken_to_the_patient(monkeypatch):
    s = _new()
    monkeypatch.setattr(talk, "translate", lambda text, *a, **k: {"translation": text, "english": text, "drugs": [],
                                                                    "allergies": [], "tests": []})
    _say(s, "doctor", "Please lie down on the bed for me.")
    assert not s.pending and s.notice["text"] == consult.ui.t("en", "voice_unavailable")
    assert s.next_speaker == "patient"           # the visit goes on, in text


def test_patient_reply_reaches_an_arabic_doctor_only_in_arabic(monkeypatch):
    s = _new()
    s.doc_lang = "ar"
    monkeypatch.setattr(talk, "translate", lambda *a, **k: {"translation": "", "english": "My chest hurts.",
                                                            "drugs": [], "allergies": [], "tests": []})
    _say(s, "patient", "मेरो छाती दुख्छ।")
    assert not s.pending                         # no Arabic translation: the English line is never read in Arabic
    monkeypatch.setattr(talk, "translate", lambda *a, **k: {"translation": "صدري يؤلمني.", "english": "My chest hurts.",
                                                            "drugs": [], "allergies": [], "tests": []})
    _say(s, "patient", "मेरो छाती दुख्छ।")
    assert [(p.to, p.lang, p.text) for p in s.pending] == [("doctor", "ar", "صدري يؤلمني.")]


def test_consent_fallback_is_not_spoken_or_cached(monkeypatch):
    monkeypatch.setattr(talk, "translate", lambda *a, **k: {"translation": consult.CONSENT_EN})   # an echo
    monkeypatch.delitem(consult._CONSENT, "te", raising=False)
    assert consult.consent_text("te") == consult.CONSENT_EN and "te" not in consult._CONSENT
    s = _new()
    s.lang = "te"
    assert not consult.queue_speech(s, consult.Speech(consult.CONSENT_EN, "te", "patient", False, kind="consent"),
                                    source=consult.CONSENT_EN)


def _heard(role, detected=None, lid=None, text="Do you have any allergies to medicines?", lang="en", seconds=3.0):
    return {"role": role, "detected_role": detected or role, "lid": lid or {}, "text": text, "lang": lang,
            "role_forced": True, "audio_seconds": seconds}


def test_short_clip_needs_near_certainty_before_questioning_the_speaker(monkeypatch):
    # 1-2 s answers fooled VoxLingua at ~0.95 live; under 2 s the prompt needs >= 0.99
    s = _new()
    arr = np.zeros(16000, np.int16)
    monkeypatch.setattr(talk, "hear", lambda *a, **k: _heard("doctor", "patient", {"ne": 0.95, "en": 0.05}, seconds=1.4))
    list(consult.process_audio(s, 16000, arr, "doctor"))
    assert s.live != "confirm"
    s2 = _new()
    monkeypatch.setattr(talk, "hear", lambda *a, **k: _heard("doctor", "patient", {"ne": 0.995, "en": 0.005}, seconds=1.4))
    list(consult.process_audio(s2, 16000, arr, "doctor"))
    assert s2.live == "confirm"


def test_speaker_choice_is_kept_unless_the_worker_is_very_sure(monkeypatch):
    s = _new()
    arr = np.zeros(16000, np.int16)
    # low-confidence disagreement: translated as the doctor chose (doctor -> patient)
    monkeypatch.setattr(talk, "hear", lambda *a, **k: _heard("doctor", "patient", {"ne": 0.6, "en": 0.4}))
    list(consult.process_audio(s, 16000, arr, "doctor"))
    assert s.confirm is None and [p.to for p in s.pending] == ["patient"]
    s.pending.clear()
    # a confident disagreement asks first and says nothing
    monkeypatch.setattr(talk, "hear", lambda *a, **k: _heard("doctor", "patient", {"ne": 0.97, "en": 0.03}))
    list(consult.process_audio(s, 16000, arr, "doctor"))
    assert s.confirm and s.live == "confirm" and not s.pending
    s.confirm = s.confirm_pcm = None
    s.live = "idle"
    # an 'unclear' / unknown detected role never asks and never flips the direction
    monkeypatch.setattr(talk, "hear", lambda *a, **k: _heard("doctor", "unclear", {"en": 0.99}))
    list(consult.process_audio(s, 16000, arr, "doctor"))
    assert s.confirm is None and [p.to for p in s.pending] == ["patient"]
    s.pending.clear()
    # the worker did not honour the forced role (its text is in the other side's language): nothing is translated
    monkeypatch.setattr(talk, "hear", lambda *a, **k: _heard("patient", "patient", {"ne": 0.5}, "मलाई दुख्छ", "ne"))
    n = len(s.brain.turns)
    list(consult.process_audio(s, 16000, arr, "doctor"))
    assert not s.pending and len(s.brain.turns) == n and s.notice["text"] == consult.ui.t("en", "not_caught")
    # no role at all and no choice: never guessed
    monkeypatch.setattr(talk, "hear", lambda *a, **k: {"text": "hello there", "lid": {}})
    list(consult.process_audio(s, 16000, arr, ""))
    assert not s.pending and len(s.brain.turns) == n


def test_confirm_with_an_unknown_role_does_nothing():
    s = _new()
    s.confirm = {"selected": "doctor", "detected": "unclear", "engine_role": "doctor", "text": "x", "lang": "en"}
    s.confirm_pcm = (16000, np.zeros(10, np.int16))
    n = len(s.brain.turns)
    list(consult.resolve_confirm(s, True))
    assert not s.pending and len(s.brain.turns) == n and not s.processing


def test_slower_replays_the_cached_clip_marked_for_the_page_no_new_synthesis(monkeypatch, tts):
    s = _new()
    text = "पहिलो वाक्य। दोस्रो वाक्य।"
    # a clip with one sentence gap (0.5 s of zeros) between two voiced parts
    clip = np.concatenate([np.full(8000, 0.2, np.float32), np.zeros(8000, np.float32), np.full(8000, 0.2, np.float32)])
    calls = []

    def fake(t, lang, description=""):
        calls.append((t, lang, description))
        yield 16000, clip
    monkeypatch.setattr(talk, "speak_chunks", fake)
    first = _items(_speak(s, consult.Speech(text, "ne", "patient", True, kind="turn", cid=s.cid)))
    assert "rate" not in first[0] and first[-1]["end"] == "1"
    consult.again(s, slow=True)
    sp = consult.pop_pending(s)
    assert sp.slow and sp.cid == s.cid
    slow = _items(_speak(s, sp))
    assert len(calls) == 1 and calls[0][2] == ""            # Slower is not a new TTS call (and no ignored "slow" hint)
    end = slow[-1]
    assert all(it["rate"] == str(consult.SLOW_RATE) for it in slow) and all(it["c"] == s.cid for it in slow)
    assert end["gaps"] == "12000" and float(end["gapx"]) == consult.SLOW_GAP_EXTRA_S
    assert abs(float(end["dur"]) - (24000 / 16000 / consult.SLOW_RATE + consult.SLOW_GAP_EXTRA_S)) < 1e-3
    assert consult.sentence_gaps(np.zeros(100, np.int16), 16000) == []      # leading/trailing silence is no gap
