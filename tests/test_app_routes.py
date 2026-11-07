"""The real FastAPI app (app.py, SPACE_ID unset): plan page and token-keyed file routes. Skipped if the app cannot be
built here (it needs gradio / fastrtc and the cached Silero VAD model)."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def client():
    try:
        import app as bayan_app
        from fastapi.testclient import TestClient
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"app not importable here: {e}")
    return TestClient(bayan_app.app)


def test_file_route_rejects_unknown_tokens_and_paths(client, tmp_path):
    from bayan import careplan

    for url in ("/files/" + "A" * 22 + "/care_plan.pdf", "/files/short/care_plan.pdf",
                "/files/..%2F..%2Fetc/passwd", "/plan/unknown"):
        r = client.get(url)
        assert r.status_code == 404, url
        if "%2F" not in url:      # a path that does not even match the route 404s in the Gradio mount
            assert r.headers.get("cache-control") == "no-store"
    (tmp_path / "care_plan.pdf").write_bytes(b"%PDF-1.4 test")
    (tmp_path / "note.md").write_text("private")
    tok = "T" * 22
    careplan.register_files(tok, tmp_path, ["care_plan.pdf"])
    r = client.get(f"/files/{tok}/care_plan.pdf")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 test" and r.headers["content-type"] == "application/pdf"
    assert client.get(f"/files/{tok}/note.md").status_code == 404
    assert client.get(f"/files/{tok}/doctor_report.pdf").status_code == 404
    careplan.forget_files([tok])
    assert client.get(f"/files/{tok}/care_plan.pdf").status_code == 404


def test_plan_page_route_serves_an_approved_structured_plan(client):
    from bayan import careplan

    plan = {"lang": "en", "medicines": [{"name": "Paracetamol", "title_en": "Paracetamol 1 g",
                                         "note_en": "Take 1 g only when needed.", "prn": True}],
            "avoid": [{"en": "Penicillin medicines. You are allergic."}], "advice": [],
            "red_flags": [{"en": "Your chest pain comes back."}], "emergency": "999"}
    pid = careplan.create("en", plan)
    assert "almost ready" in client.get(f"/plan/{pid}").text
    careplan.approve(pid)
    r = client.get(f"/plan/{pid}")
    assert r.status_code == 200 and r.headers["x-robots-tag"] == "noindex"
    for needle in ("Your medicines", "Paracetamol 1 g", "Do not take", "Call 999 or come back now if"):
        assert needle in r.text


# ------------------------------------------------------------------ talk-loop state across visits (no network, no LLM)
import html as _html
import json as _json
import re as _re


class _FastTime:
    def __getattr__(self, name):
        import time as _t
        return getattr(_t, name)

    @staticmethod
    def sleep(_s):
        return None


@pytest.fixture
def app_mod(client, monkeypatch):
    import app as bayan_app
    from bayan import consult, talk
    from bayan.brain import llm

    def no_llm(*_a, **_k):
        raise RuntimeError("LLM down in this test")
    llm.set_backend(no_llm)
    monkeypatch.setattr(bayan_app, "time", _FastTime())
    monkeypatch.setattr(consult, "time", _FastTime())
    monkeypatch.setattr(bayan_app, "worker_up", lambda: False)
    monkeypatch.setattr(talk, "speak_chunks", lambda *a, **k: iter(()))
    yield bayan_app
    llm.set_backend(None)


def _state(out):
    raw = _re.search(r'data-s="([^"]*)"', out).group(1)
    return _json.loads(_html.unescape(raw))


def _act(app_mod, sid, **p):
    p.setdefault("n", __import__("time").time_ns())
    return list(app_mod.on_act(_json.dumps(p), "", sid, None))


def test_start_never_guesses_the_patient_language(app_mod):
    from bayan import consult
    sid = consult.new_sid()
    outs = _act(app_mod, sid, act="start", lang="xx", doc="en")
    s = consult.SESS[sid]
    assert s.screen == "start" and s.error == "err_lang" and not s.pending
    assert _state(outs[-1][0])["screen"] == "start"


def test_english_consent_fallback_is_shown_not_spoken(app_mod, monkeypatch):
    from bayan import consult, talk
    said = []
    monkeypatch.setattr(talk, "speak_chunks", lambda text, lang, *a, **k: said.append((text, lang)) or iter(()))
    monkeypatch.delitem(consult._CONSENT, "hi", raising=False)
    sid = consult.new_sid()
    outs = _act(app_mod, sid, act="start", lang="hi", doc="en")
    s = consult.SESS[sid]
    assert s.screen == "consent" and s.consent_native == consult.CONSENT_EN
    assert not said and not s.pending                                     # never read out in a Hindi voice
    assert s.notice["text"] == consult.ui.t("en", "voice_unavailable")
    assert all(o[1] == {"__type__": "update"} for o in outs)              # no audio went to the page


def test_home_mid_speech_stops_the_old_visit_and_never_repaints_it(app_mod, monkeypatch):
    from bayan import consult, talk
    import numpy as np
    sid = consult.new_sid()
    holder = {}

    def tts(text, lang, *a, **k):
        yield 16000, np.full(16000, 0.2, np.float32)
        consult.reset(holder["s"])                                        # Home while the clip is streaming
        yield 16000, np.full(16000, 0.2, np.float32)
    monkeypatch.setattr(talk, "speak_chunks", tts)
    s = consult.SESS[sid]
    holder["s"] = s
    outs = _act(app_mod, sid, act="start", lang="ne", doc="en")
    fresh = consult.SESS[sid]
    assert fresh is not s
    audio = [o[1] for o in outs if isinstance(o[1], str) and o[1]]
    assert len(audio) == 1 and audio[0].count("class='bz-au'") == 1 and f"data-c='{s.cid}'" in audio[0]
    after = [o for o in outs[outs.index(next(o for o in outs if o[1] == audio[0])) + 1:]]
    for state, voice in after:                                            # after Home: the fresh visit or nothing
        assert not (isinstance(voice, str) and voice)
        if isinstance(state, str):
            assert _state(state)["cid"] == fresh.cid
    seqs = [_state(o[0])["seq"] for o in outs if isinstance(o[0], str)]
    assert seqs == sorted(seqs)


def test_demo_cannot_leak_into_the_visit_that_replaces_it(app_mod):
    from bayan import consult
    sid = consult.new_sid()
    s = consult.SESS[sid]
    gen = app_mod.on_act(_json.dumps({"act": "demo", "n": 1}), "", sid, None)
    next(gen)
    assert s.demo and s.lang == "ne" and s.screen == "consent"
    _act(app_mod, sid, act="consent_yes")                                 # the demo answers its own consent
    assert s.screen == "consent"
    _act(app_mod, sid, act="home", lang="en")                             # Home, then a real visit in Hindi
    fresh = consult.SESS[sid]
    fresh_outs = _act(app_mod, sid, act="start", lang="hi", doc="en")
    assert fresh.lang == "hi" and not fresh.demo
    rest = list(gen)                                                      # the old demo winds down
    for state, voice in rest:
        assert not (isinstance(voice, str) and voice)
        assert not isinstance(state, str) or _state(state)["cid"] == fresh.cid
    assert fresh.lang == "hi" and not fresh.demo and all(p.lang == "hi" for p in fresh.pending)
    assert fresh_outs
