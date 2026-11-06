"""Bayan AI — HF Space entry point (talk loop MVP).

Ambient interpretation with FastRTC: no push-to-talk. Silero VAD detects the end of each
utterance; bayan.talk.run_turn hears, translates, checks for held prescribing alerts and speaks.
"""

import os

import gradio as gr
import numpy as np
from fastrtc import AdditionalOutputs, AlgoOptions, ReplyOnPause, SileroVadOptions, WebRTC, get_current_context

from bayan import talk

ON_SPACES = bool(os.environ.get("SPACE_ID"))
if ON_SPACES:
    from fastrtc import get_cloudflare_turn_credentials, get_cloudflare_turn_credentials_async

    RTC_CONFIG = get_cloudflare_turn_credentials_async
    SERVER_RTC_CONFIG = get_cloudflare_turn_credentials(ttl=360_000)
else:
    RTC_CONFIG, SERVER_RTC_CONFIG = None, None

PATIENT_LANGS = [
    ("Nepali · नेपाली", "ne"),
    ("Hindi · हिन्दी", "hi"),
    ("Urdu · اردو", "ur"),
    ("Bengali · বাংলা", "bn"),
    ("Malayalam · മലയാളം", "ml"),
    ("Filipino · Tagalog (text only for now)", "tl"),
]

HEADER = """
# بيان · Bayan AI
**Ambient medical interpreter & safety net.** Pick the patient's language, press the mic once and just talk.
The doctor may speak English (Arabic text-only for now); Bayan works out who is speaking from the language.
<sub>Decision support for licensed clinicians only · not a medical device · synthetic demo consultations only.</sub>
"""


def turn(audio: tuple[int, np.ndarray], patient_lang: str):
    sr, arr = audio
    key = get_current_context().webrtc_id
    sess = talk.session_for(key, patient_lang or "ne")
    try:
        for event in talk.run_turn(sess, sr, arr):
            if event[0] == "ui":
                yield AdditionalOutputs(event[1], event[2])
            else:
                _, out_sr, out = event
                pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16).reshape(1, -1)
                yield (out_sr, pcm)
    except Exception as e:  # noqa: BLE001 - never kill the stream on one bad turn
        sess.history.append({"role": "assistant", "content": f"⚠️ *Bayan could not process that turn: {e}*"})
        yield AdditionalOutputs(list(sess.history), talk.render_alerts(sess.alerts))


with gr.Blocks(title="Bayan AI") as demo:
    gr.Markdown(HEADER)
    with gr.Row():
        lang = gr.Dropdown(PATIENT_LANGS, value="ne", label="Patient language", scale=2)
        wake = gr.Button("Wake voice worker", scale=1)
        status = gr.Markdown("")
    with gr.Row():
        with gr.Column(scale=3):
            transcript = gr.Chatbot(type="messages", label="Live transcript", height=520)
        with gr.Column(scale=2):
            gr.Markdown("### 🔕 Silent alerts (doctor only)")
            alerts = gr.Markdown(talk.render_alerts([]))
    mic = WebRTC(
        label="Bayan is listening",
        mode="send-receive",
        modality="audio",
        rtc_configuration=RTC_CONFIG,
        server_rtc_configuration=SERVER_RTC_CONFIG,
        full_screen=False,
    )
    mic.stream(
        ReplyOnPause(
            turn,
            can_interrupt=False,  # don't listen to our own voice while speaking
            algo_options=AlgoOptions(audio_chunk_duration=0.6, started_talking_threshold=0.2, speech_threshold=0.1),
            model_options=SileroVadOptions(threshold=0.5, min_silence_duration_ms=600),
        ),
        inputs=[mic, lang],
        outputs=[mic],
        time_limit=1800,
    )
    mic.on_additional_outputs(lambda h, a: (h, a), outputs=[transcript, alerts], queue=False, show_progress="hidden")
    wake.click(talk.wake_worker, None, status)

if __name__ == "__main__":
    demo.launch()
