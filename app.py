"""Bayan AI · HF Space entry point.

Ambient interpretation with FastRTC: no push-to-talk. Silero VAD finds the end of each utterance;
bayan.consult hears, translates, checks for held prescribing alerts and speaks. The UI is one
static stage (bayan/ui.py) driven by JSON views pushed from Python.

Run: python app.py  (FastAPI + Gradio on 0.0.0.0:7860; GET /plan/<id> serves the patient's plan)
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time

import gradio as gr
import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastrtc import AdditionalOutputs, AlgoOptions, ReplyOnPause, SileroVadOptions, WebRTC, get_current_context

from bayan import careplan, consult, talk, ui
from bayan.consult import UI, Speech

ON_SPACES = bool(os.environ.get("SPACE_ID"))
ACCESS_CODE = os.environ.get("BAYAN_ACCESS_CODE", "" if ON_SPACES else "local")
TURN_KEYS = bool(os.environ.get("CLOUDFLARE_TURN_KEY_ID") and os.environ.get("CLOUDFLARE_TURN_KEY_API_TOKEN"))
RTC_CONFIG, SERVER_RTC_CONFIG = None, None

if ON_SPACES and TURN_KEYS:
    # Our own Cloudflare TURN key. hf_token="" forces the Cloudflare-key path: FastRTC otherwise
    # prefers HF's shared relay (turn.fastrtc.org), whose TLS certificate expired on 2026-10-05.
    from fastrtc import get_cloudflare_turn_credentials, get_cloudflare_turn_credentials_async

    async def RTC_CONFIG():  # noqa: N802 - called per browser connection
        return await get_cloudflare_turn_credentials_async(hf_token="")

    try:
        SERVER_RTC_CONFIG = get_cloudflare_turn_credentials(hf_token="", ttl=86_400)  # Cloudflare rejected 360_000
    except Exception as e:  # noqa: BLE001 - boot anyway and say why audio may not connect
        RTC_CONFIG = None
        print(f"TURN unavailable: {e}", flush=True)


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


# ------------------------------------------------------------------ live audio turn (FastRTC handler)
def _out(sess, ev):
    if ev == UI:
        return AdditionalOutputs(consult.render(sess))
    return ev  # (sample_rate, int16 pcm)


def turn(audio, *args):
    sess = consult.find(args)
    if sess is None:  # not past the access gate: ignore
        return
    if hasattr(audio, "audio"):  # WebRTCData wrapper
        audio = audio.audio
    sr, arr = audio
    arr = np.asarray(arr).reshape(-1)
    sess.webrtc_id = get_current_context().webrtc_id
    sess.busy = True
    try:
        if arr.size >= int(0.3 * sr) and sess.screen == "live" and not sess.demo:
            for ev in consult.process_audio(sess, sr, arr):
                yield _out(sess, ev)
        while sess.screen in ("consent", "live"):
            sp = consult.pop_pending(sess)
            if sp is None:
                break
            for ev in consult.speak_live(sess, sp):
                yield _out(sess, ev)
    except Exception as e:  # noqa: BLE001 - never kill the stream on one bad turn
        print(f"[turn] {type(e).__name__}: {e}", flush=True)
        sess.error = "Bayan could not process that. Please say it again."
        yield AdditionalOutputs(consult.render(sess))
    finally:
        sess.busy = False


def kick(sess):
    """Run the stream handler now (speaks queued speech). Retried once: a trigger that lands while
    a turn is finishing is cleared by ReplyOnPause.reset()."""
    def _t():
        h = mic.handlers.get(sess.webrtc_id) if sess.webrtc_id else None
        if h is not None and hasattr(h, "trigger_response") and sess.pending and not sess.busy:
            h.trigger_response()
    _t()
    threading.Timer(1.5, _t).start()
    threading.Timer(4.0, _t).start()


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


def _queue_consent(sess):
    if sess.screen == "consent" and sess.consent_native and not sess.consent_queued and sess.webrtc_id and not sess.demo:
        sess.consent_queued = True
        sess.pending.append(Speech(sess.consent_native, sess.lang, "patient", False, consult.CONSENT_EN, kind="consent"))
        kick(sess)


def on_act(payload, webrtc_id, sid, request: gr.Request):
    sess = consult.get(sid)
    if not payload or sess is None:
        yield gr.skip(), gr.skip()
        return
    try:
        p = json.loads(payload)
    except json.JSONDecodeError:
        yield gr.skip(), gr.skip()
        return
    act = p.get("act", "")
    skip = gr.skip()

    def R():
        return consult.render(consult.SESS.get(sess.sid, sess))

    if act == "start" and sess.screen == "start":
        sess.lang = p.get("lang") if p.get("lang") in consult.LANGS else "ne"
        sess.screen, sess.started_at, sess.error, sess.demo = "consent", time.time(), "", False
        sess.consent_native = consult._CONSENT.get(sess.lang, "")
        yield R(), skip
        if not sess.consent_native:
            try:
                sess.consent_native = consult.consent_text(sess.lang)
            except Exception as e:  # noqa: BLE001
                print(f"[consent] {e}", flush=True)
                sess.consent_native = consult.CONSENT_EN
            yield R(), skip
        _queue_consent(sess)
    elif act == "connected":
        if isinstance(webrtc_id, str) and webrtc_id:
            sess.webrtc_id = webrtc_id
        elif not sess.webrtc_id:  # fallback: the one live connection no other tab has claimed
            claimed = {s.webrtc_id for s in consult.SESS.values() if s is not sess}
            free = [k for k in list(mic.connections) if k not in claimed]
            if len(free) == 1:
                sess.webrtc_id = free[0]
        print(f"[connected] sid={sess.sid[:6]} webrtc={(sess.webrtc_id or '')[:8]}", flush=True)
        sess.error = ""
        _queue_consent(sess)
        yield R(), skip
    elif act == "mic_failed" and sess.screen in ("consent", "live") and not sess.demo:
        sess.error = "Microphone not connected. Allow the microphone and start again."
        yield R(), skip
    elif act == "consent_yes" and sess.screen == "consent":
        sess.screen, sess.live, sess.tint, sess.error = "live", "idle", "n", ""
        sess.pending.clear()
        yield R(), skip
    elif act in ("consent_no", "new"):
        consult.reset(sess)
        yield R(), skip
    elif act == "end" and sess.screen in ("consent", "live"):
        sess.stop_mic += 1
        for _ in consult.end_visit(sess, _base_url(request)):
            yield R(), skip
    elif act == "approve" and sess.screen == "review":
        for _ in consult.approve(sess, p.get("text", "")):
            yield R(), skip
    elif act == "ask" and sess.screen == "live" and not sess.demo:
        if consult.ask_suggestion(sess, p.get("id", "")):
            yield R(), skip
            kick(sess)
    elif act == "held_else" and sess.held:
        consult.held_else(sess)
        yield R(), skip
    elif act == "held_anyway" and sess.held and not sess.demo:
        consult.held_anyway(sess)
        yield R(), skip
        kick(sess)
    elif act in ("again", "slower") and sess.screen == "live" and not sess.demo:
        consult.again(sess, slow=act == "slower")
        kick(sess)
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
        return consult.SESS.get(s.sid) is s

    def R():
        return consult.render(s)

    def say(sp):
        for ev in consult.speak_demo(s, sp, voice):
            if ev == UI:
                yield R(), gr.skip()
            else:
                yield gr.skip(), ev[1]

    def speak_pending():
        while alive() and s.screen == "live":
            sp = consult.pop_pending(s)
            if sp is None:
                break
            yield from say(sp)

    s.demo, s.lang, s.screen, s.started_at = True, "ne", "consent", time.time()
    s.consent_native = consult.consent_text("ne")
    yield R(), gr.skip()
    time.sleep(1.0)
    yield from say(Speech(s.consent_native, "ne", "patient", False, consult.CONSENT_EN, kind="consent"))
    time.sleep(1.2)
    if not alive() or s.screen != "consent":
        return
    s.screen, s.live, s.tint = "live", "idle", "n"
    yield R(), gr.skip()
    time.sleep(1.5)
    try:
        for role, text in consult.DEMO_SCRIPT:
            if not alive() or s.screen != "live":
                return
            if role in ("doctor", "patient"):
                for _ in consult.process_text(s, role, text, "en" if role == "doctor" else "ne"):
                    yield R(), gr.skip()
                time.sleep(2.2 if role == "doctor" else 3.2)
                if s.live == "held":
                    continue
                yield from speak_pending()
            elif role == "ask":
                time.sleep(1.0)
                s.open_notes += 1
                yield R(), gr.skip()
                time.sleep(4.0)
                sug = next((x for x in s.suggestions if x["status"] == "open"), None)
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
        s.error = "The demo hit a problem. Please try again."
        yield R(), gr.skip()


# ------------------------------------------------------------------ access gate
def on_gate(payload, _sid=None):
    nothing = (gr.skip(),) * 5
    try:
        p = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return nothing
    if p.get("act") != "unlock":
        return nothing
    code = (p.get("code") or "").strip()
    ok = bool(ACCESS_CODE) and hmac.compare_digest(code.encode(), ACCESS_CODE.encode())
    if not ok:
        time.sleep(0.8)  # slow down guessing
        return gr.skip(), gr.skip(), gr.skip(), gr.skip(), ui.gate_html(error=True)
    sid = consult.new_sid()
    return gr.update(visible=False), gr.update(visible=True), sid, consult.render(consult.SESS[sid]), gr.skip()


# ------------------------------------------------------------------ UI
THEME = gr.themes.Base(font=["Instrument Sans", "system-ui", "sans-serif"]).set(
    body_background_fill="#FBFCFC", body_background_fill_dark="#FBFCFC",
    body_text_color="#173430", body_text_color_dark="#173430",
)

with gr.Blocks(title="Bayan", head=ui.HEAD, theme=THEME, fill_width=True, analytics_enabled=False) as demo:
    sid_box = gr.Textbox(visible=False)
    act_box = gr.Textbox(visible=False)
    wid_box = gr.Textbox(visible=False)
    with gr.Column(visible=True) as gate_col:
        gate = gr.HTML(ui.gate_html(), padding=False)
    with gr.Column(visible=False) as app_col:  # WebRTC is not on the page until the gate is passed
        stage = gr.HTML(ui.STAGE_HTML, padding=False)
        state_html = gr.HTML("", elem_id="bayan-state", padding=False)
        mic = WebRTC(
            elem_id="mic", show_label=False, mode="send-receive", modality="audio",
            rtc_configuration=RTC_CONFIG, server_rtc_configuration=SERVER_RTC_CONFIG, full_screen=False,
            button_labels={"start": "Bayan start", "stop": "Bayan stop", "waiting": "Bayan connecting"},
        )
        demo_audio = gr.Audio(type="numpy", autoplay=True, elem_id="demo-audio", show_label=False,
                              interactive=False, streaming=False)

    gate.click(on_gate, inputs=[act_box, sid_box], outputs=[gate_col, app_col, sid_box, state_html, gate],
               js="(a, s) => [window.__bayanAct || '', s]", show_progress="hidden", concurrency_limit=None,
               trigger_mode="multiple")
    # Don't pass the WebRTC component as an input: before it connects its value is None and fastrtc's
    # preprocess raises "'NoneType' object has no attribute 'root'". on_act maps the connection itself.
    stage.click(on_act, inputs=[act_box, wid_box, sid_box], outputs=[state_html, demo_audio],
                js="(a, w, s) => [window.__bayanAct || '', '', s]", show_progress="hidden", concurrency_limit=None,
                trigger_mode="multiple")

    mic.stream(
        ReplyOnPause(
            turn,
            can_interrupt=False,  # don't listen to our own voice while speaking
            algo_options=AlgoOptions(audio_chunk_duration=0.6, started_talking_threshold=0.2, speech_threshold=0.1),
            model_options=SileroVadOptions(threshold=0.5, min_silence_duration_ms=600),
        ),
        inputs=[mic, sid_box],
        outputs=[mic],
        time_limit=3600,
        concurrency_limit=6,  # FastRTC default is ONE connection server-wide
    )

    async def pump(webrtc_id):
        """Long-lived: forwards every AdditionalOutputs from the handler to the stage.
        (on_additional_outputs(queue=False) stops updating after a few turns in this version pair.)"""
        if hasattr(webrtc_id, "webrtc_id"):
            webrtc_id = webrtc_id.webrtc_id
        if not webrtc_id:
            return
        async for out in mic.output_stream(webrtc_id):
            yield out.args[0]

    mic.state_change(pump, inputs=[mic], outputs=[state_html], queue=True, concurrency_limit=None,
                     show_progress="hidden", trigger_mode="once")


# ------------------------------------------------------------------ FastAPI: patient plan page + Gradio
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/plan/{pid}")
def plan_page(pid: str):
    code, body = careplan.page_html(pid)
    return HTMLResponse(body, status_code=code, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"})


app = gr.mount_gradio_app(app, demo, path="", ssr_mode=False, show_api=False)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
