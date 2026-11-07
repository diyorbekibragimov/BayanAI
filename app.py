"""Bayan AI · HF Space entry point.

Tap-to-talk interpretation: the doctor taps the pearl (or presses Space), someone speaks, they tap
again. The browser sends that one utterance as 16 kHz PCM; bayan.consult works out who spoke (voice
worker), translates, runs the rule engine's prescription gate (held sentences) and streams the reply to the
page's WebAudio player. The clinical brain (bayan.brain: rules, idiom lexicon, smolagents copilot, wrap-up agent)
runs beside the talk loop; its cards reach the stage through a 1 s poll (gr.Timer -> consult.poll_render).
The UI is one static stage (bayan/ui.py, bayan/web/) driven by JSON views from Python.

Run: python app.py  (FastAPI + Gradio on 0.0.0.0:7860; GET /plan/<id> serves the patient's plan,
GET /files/<token>/<name> the PDFs of one consultation)
"""

from __future__ import annotations

import base64
import json
import os
import time

import gradio as gr
import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

from bayan import careplan, consult, talk, ui
from bayan.brain import llm as brain_llm
from bayan.consult import UI, Speech
from bayan.outputs import retention

MAX_SECONDS = 60
SR = 16000


# ------------------------------------------------------------------ voice worker status (demo uses it)
_WK = {"t": 0.0, "up": False}


def worker_up() -> bool:
    if time.time() - _WK["t"] < 20:
        return _WK["up"]
    up = False
    try:
        from huggingface_hub import HfApi
        up = HfApi(token=talk.HF_TOKEN).space_info(talk.WORKER_SPACE).runtime.stage == "RUNNING"
    except Exception as e:  # noqa: BLE001
        print(f"worker status: {e}", flush=True)
    _WK.update(t=time.time(), up=up)
    return up


# ------------------------------------------------------------------ speech out (one clip at a time)
def drain(sess, voice_on: bool = True):
    """Speak everything queued for this visit, one clip after another. Only one generator speaks at a
    time; anything queued meanwhile (Say it again, Slower) is picked up by the one already speaking."""
    with sess.lock:
        if sess.busy:
            return
        sess.busy = True
    try:
        while consult.alive(sess) and sess.screen in ("consent", "live"):
            sp = consult.pop_pending(sess)
            if sp is None:
                break
            sess.processing = sess.processing or sp.kind != "consent"
            yield consult.render(sess), gr.skip()
            for ev in consult.speak_clip(sess, sp, voice_on):
                if ev == UI:
                    yield consult.render(sess), gr.skip()
                else:
                    yield consult.render(sess), (ev[1] if ev[1] is not None else gr.skip())
            if not consult.alive(sess) or sess.screen not in ("consent", "live"):
                break
    finally:
        with sess.lock:
            sess.busy = False
            sess.processing = False
    yield consult.render(sess), gr.skip()


def _queue_consent(sess) -> None:
    """The consent line, spoken only if it really is in the patient's language (an English fallback is shown only)."""
    sp = Speech(sess.consent_native, sess.lang, "patient", False, consult.CONSENT_EN, kind="consent")
    if not consult.queue_speech(sess, sp, source=consult.CONSENT_EN):
        consult.notify(sess, "voice_unavailable")


def _wait_idle(sess, timeout: float = 5.0) -> bool:
    """A recording that started during the post-speech pause arrives while that pause is ending."""
    t0 = time.time()
    while sess.busy and time.time() - t0 < timeout:
        time.sleep(0.05)
    return not sess.busy


def decode_pcm(p: dict) -> np.ndarray | None:
    try:
        a = np.frombuffer(base64.b64decode(p.get("pcm") or ""), dtype="<i2")
    except Exception:  # noqa: BLE001
        return None
    return a[: MAX_SECONDS * SR] if a.size else None


# ------------------------------------------------------------------ actions from the stage
def _base_url(request: gr.Request | None) -> str:
    host = os.environ.get("SPACE_HOST")
    if host:
        return f"https://{host}"
    try:
        h = request.headers
        return f"{h.get('x-forwarded-proto', 'http')}://{h.get('x-forwarded-host') or h.get('host')}"
    except Exception:  # noqa: BLE001
        return "http://127.0.0.1:7860"


def on_act(payload, _wid, sid, request: gr.Request):
    sess = consult.get(sid)
    skip = gr.skip()
    if not payload or sess is None:
        yield skip, skip
        return
    try:
        p = json.loads(payload)
    except json.JSONDecodeError:
        yield skip, skip
        return
    act = p.get("act", "")
    if act not in ("lang", "") and p.get("n") is not None:  # one action, one effect (never process a payload twice)
        if p.get("n") == sess.last_n and act == sess.last_act:
            yield skip, skip
            return
        sess.last_n, sess.last_act = p.get("n"), act

    def R():
        return consult.render(consult.SESS.get(sess.sid, sess))

    if act == "start" and sess.screen == "start":
        if p.get("lang") not in consult.LANGS:  # never guess the patient's language (no silent Nepali default)
            sess.error = "err_lang"
            yield R(), skip
            return
        sess.lang = p["lang"]
        if p.get("doc") in ("en", "ar"):
            sess.doc_lang = p["doc"]
        sess.screen, sess.started_at, sess.error, sess.demo = "consent", time.time(), "", False
        consult.begin(sess)  # a fresh brain consultation on the visit clock (doctor's language set above)
        sess.consent_native = consult._CONSENT.get(sess.lang, "")
        yield R(), skip
        if not sess.consent_native:
            try:
                sess.consent_native = consult.consent_text(sess.lang)
            except Exception as e:  # noqa: BLE001
                print(f"[consent] {e}", flush=True)
                sess.consent_native = consult.CONSENT_EN
            yield R(), skip
        if not consult.alive(sess) or sess.screen != "consent":
            return
        _queue_consent(sess)
        yield from drain(sess)
    elif act == "settle_skip":  # a tap or key during the 3 s pause after Bayan spoke: move on now
        sess.settle_cancel = True
        yield skip, skip
    elif act == "audio":
        sess.audio_ack = p.get("n")  # the page unlocks the pearl only once it sees this id (never on unrelated renders)
        ok = (sess.screen == "live" and not sess.demo and not sess.held and not sess.confirm and not sess.hearing
              and _wait_idle(sess))
        pcm = decode_pcm(p) if ok else None
        if not ok:
            if sess.screen == "live" and not sess.demo and not sess.held and not sess.confirm:
                consult.notify(sess, consult.NOT_CAUGHT)  # dropped (still speaking / another turn running): say again
            yield R(), skip
            return
        if pcm is None or pcm.size < int(0.4 * SR):
            consult.notify(sess, consult.NOT_CAUGHT)
            yield R(), skip
            return
        print(f"[audio] sid={sess.sid[:6]} {pcm.size / SR:.1f}s", flush=True)
        sess.processing, sess.error, sess.hearing = True, "", True
        yield R(), skip
        try:
            for _ in consult.process_audio(sess, SR, pcm, p.get("speaker", "")):
                yield R(), skip
        except Exception as e:  # noqa: BLE001
            print(f"[audio] {type(e).__name__}: {e}", flush=True)
            sess.error = "err_process"
        finally:
            sess.hearing = False
        if not consult.alive(sess):  # Home / No pressed while this turn was heard: its reply goes nowhere
            yield R(), skip
            return
        sess.processing = bool(sess.pending)
        yield R(), skip
        yield from drain(sess)
    elif act in ("confirm_other", "confirm_keep") and sess.confirm and not sess.busy:
        try:
            for _ in consult.resolve_confirm(sess, act == "confirm_other"):
                yield R(), skip
        except Exception as e:  # noqa: BLE001
            print(f"[confirm] {type(e).__name__}: {e}", flush=True)
            sess.error = "err_process"
        sess.processing = bool(sess.pending)
        yield R(), skip
        yield from drain(sess)
    elif act == "doclang" and sess.screen == "start":
        if p.get("id") in ("en", "ar"):
            sess.doc_lang = p["id"]
        yield R(), skip
    elif act == "home":  # the wordmark: drop the visit, keep the doctor's language (set on the fresh one only, so
        fresh = consult.reset(sess)  # nothing still running for the old visit ever sees a different listener language)
        if p.get("lang") in ("en", "ar"):
            fresh.doc_lang = p["lang"]
        yield R(), ""
    elif act == "consent_yes" and sess.screen == "consent" and not sess.demo:  # the demo answers for itself
        sess.screen, sess.live, sess.tint, sess.error = "live", "idle", "n", ""
        sess.pending.clear()
        consult.record_consent(sess)
        consult.set_turn(sess, "doctor")  # the doctor speaks first
        yield R(), skip
    elif act in ("consent_no", "new"):
        consult.reset(sess)
        yield R(), ""
    elif act == "end" and sess.screen in ("consent", "live"):
        sess.stop_mic += 1
        for _ in consult.end_visit(sess, _base_url(request)):
            yield R(), skip
    elif act == "approve" and sess.screen == "review":
        for _ in consult.approve(sess, p.get("text", ""), None, force=bool(p.get("force"))):
            yield R(), skip
    elif act == "ask" and sess.screen == "live" and not sess.demo and not sess.busy:
        sess.processing = True
        yield R(), skip
        try:
            consult.ask_suggestion(sess, p.get("id", ""))
        except Exception as e:  # noqa: BLE001
            print(f"[ask] {type(e).__name__}: {e}", flush=True)
            sess.error = "err_ask"
        yield from drain(sess)
    elif act == "held_else" and sess.held:
        consult.held_else(sess)
        yield R(), skip
    elif act == "held_anyway" and sess.held and not sess.demo:
        consult.held_anyway(sess)
        yield R(), skip
        yield from drain(sess)
    elif act in ("again", "slower") and sess.screen == "live" and not sess.demo:
        consult.again(sess, slow=act == "slower")
        yield from drain(sess)
    elif act == "demo" and sess.screen == "start":
        yield from run_demo(sess)
    else:
        yield skip, skip


# ------------------------------------------------------------------ demo mode (no microphone)
def run_demo(sess):
    """Golden path from the prototype with text turns: real LLM translation, real worker TTS if it is running."""
    voice = worker_up()
    print(f"[demo] start, voice={'on' if voice else 'off'}", flush=True)
    s = sess

    def alive():
        return consult.alive(s)

    def R():  # a dropped demo never repaints the page (the real visit that replaced it owns the stage)
        return consult.render(s) if alive() else gr.skip()

    def say(sp):
        for ev in consult.speak_clip(s, sp, voice):
            if ev == UI:
                yield R(), gr.skip()
            else:
                yield R(), (ev[1] if ev[1] is not None else gr.skip())

    def speak_pending(screen="live"):
        while alive() and s.screen == screen:
            sp = consult.pop_pending(s)
            if sp is None:
                break
            yield from say(sp)

    def pause(seconds):  # sleep, but show copilot cards the moment they arrive
        for _ in consult.wait(s, seconds):
            yield R(), gr.skip()

    s.demo, s.lang, s.screen, s.started_at = True, "ne", "consent", time.time()
    consult.begin(s)
    s.consent_native = consult.consent_text("ne")
    yield R(), gr.skip()
    time.sleep(1.0)
    if not alive():
        return
    _queue_consent(s)
    yield from speak_pending("consent")
    time.sleep(1.2)
    if not alive() or s.screen != "consent":
        return
    s.screen, s.live, s.tint = "live", "idle", "n"
    consult.record_consent(s)
    yield R(), gr.skip()
    time.sleep(1.5)
    try:
        for role, text in consult.DEMO_SCRIPT:
            if not alive() or s.screen != "live":
                return
            if role in ("doctor", "patient"):
                for _ in consult.process_text(s, role, text, "en" if role == "doctor" else s.lang):
                    yield R(), gr.skip()
                if not alive():
                    return
                yield from pause(2.2 if role == "doctor" else 3.2)
                if s.live == "held":
                    continue
                yield from speak_pending()
            elif role == "ask":
                time.sleep(1.0)
                s.open_notes += 1
                yield R(), gr.skip()
                yield from pause(4.0)
                sug = next((x for x in consult.refresh(s) if x["status"] == "open"), None)
                if sug and alive() and s.screen == "live":
                    consult.ask_suggestion(s, sug["id"])
                    yield R(), gr.skip()
                    time.sleep(1.5)
                    yield from speak_pending()
                time.sleep(1.5)
            elif role == "held_else":
                if s.live == "held":
                    time.sleep(5.0)
                    consult.held_else(s)
                    yield R(), gr.skip()
                time.sleep(1.2)
            elif role == "end":
                time.sleep(2.0)
                if alive() and s.screen == "live":
                    for _ in consult.end_visit(s, _base_url(None)):
                        yield R(), gr.skip()
    except Exception as e:  # noqa: BLE001
        print(f"[demo] {type(e).__name__}: {e}", flush=True)
        s.error = "err_demo"
        yield R(), gr.skip()


# ------------------------------------------------------------------ warm-up (first calls are 2-4 s slower)
def _warm_up():
    import threading as _th

    def ping(name, fn):
        try:
            t0 = time.time(); fn(); print(f"[warm] {name} {time.time() - t0:.2f}s", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[warm] {name} failed: {type(e).__name__}: {e}", flush=True)

    def run():
        # Keep the GPU worker warm only while the app is in use (a session touched in the last 15 min). No LLM
        # keep-alive: it cost a paid request every 50 s around the clock for ~2 s saved on the first call after idle.
        while True:
            recent = any(time.time() - getattr(x, "touched", 0) < 900 for x in list(consult.SESS.values()))
            if recent:
                ping("worker", lambda: talk.http().get("/v1/ping", timeout=60))
            time.sleep(50)

    _th.Thread(target=run, daemon=True).start()


_warm_up()


# ------------------------------------------------------------------ session start (no access gate)
def on_load():
    sid = consult.new_sid()
    return sid, consult.render(consult.SESS[sid])


# ------------------------------------------------------------------ UI
THEME = gr.themes.Base(font=["Instrument Sans", "system-ui", "sans-serif"]).set(
    body_background_fill="#FBFCFC", body_background_fill_dark="#FBFCFC",
    body_text_color="#173430", body_text_color_dark="#173430",
)

with gr.Blocks(title="Bayan", head=ui.HEAD, theme=THEME, fill_width=True, analytics_enabled=False) as demo:
    sid_box = gr.Textbox(visible=False)
    act_box = gr.Textbox(visible=False)
    wid_box = gr.Textbox(visible=False)
    with gr.Column(visible=True) as app_col:
        stage = gr.HTML(ui.STAGE_HTML, padding=False)
        state_html = gr.HTML("", elem_id="bayan-state", padding=False)
        # Bayan's voice: TTS chunks as base64 PCM, appended per chunk; the page plays them gaplessly with
        # WebAudio. (gr.Audio(streaming=True) transcodes every chunk with ffmpeg; this has no gaps or extra hop.)
        voice_html = gr.HTML("", elem_id="bayan-voice", padding=False)

    demo.load(on_load, inputs=None, outputs=[sid_box, state_html], show_progress="hidden")

    # Copilot cards arrive from the background think run (and timer rules re-fire): poll once a second while the
    # visit is live and push a fresh view only when the brain's cards (or their Arabic translations) changed.
    cards_timer = gr.Timer(1.0)

    def poll_cards(sid):
        html = consult.poll_render(consult.SESS.get(sid) if isinstance(sid, str) else None)
        return html if html is not None else gr.skip()

    cards_timer.tick(poll_cards, inputs=[sid_box], outputs=[state_html], show_progress="hidden",
                     concurrency_limit=None, trigger_mode="always_last")
    stage.click(on_act, inputs=[act_box, wid_box, sid_box], outputs=[state_html, voice_html],
                js=ui.STAGE_INPUTS_JS, show_progress="hidden", concurrency_limit=None,
                trigger_mode="multiple")


# ------------------------------------------------------------------ FastAPI: patient plan page + Gradio
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


PRIVATE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"}


@app.get("/plan/{pid}")
def plan_page(pid: str):
    code, body = careplan.page_html(pid)
    return HTMLResponse(body, status_code=code, headers=PRIVATE)


@app.get("/files/{token}/{name}")
def files(token: str, name: str):
    """A consultation's PDFs (and care-plan audio) by unguessable token; only whitelisted names, no paths.
    inline + filename: iOS Safari and Android Chrome open the PDF viewer (with save/share)."""
    got = careplan.open_file(token, name)
    if got is None:
        return HTMLResponse("Not found", status_code=404, headers=PRIVATE)
    data, media = got
    return Response(data, media_type=media, headers={**PRIVATE, "Content-Disposition": f'inline; filename="{name}"'})


retention.start_sweeper()  # deletes consultation folders older than 24 h, even if a session never ends


app = gr.mount_gradio_app(app, demo, path="", ssr_mode=False, show_api=False)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
