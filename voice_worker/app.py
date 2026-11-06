"""Bayan AI · GPU voice worker.

Serves the speech models that no Inference Provider hosts:
  * ASR: ai4bharat/indic-conformer-600m-multilingual (22 Indic languages incl. Nepali)
  * TTS: ai4bharat/indic-parler-tts (21 languages incl. Nepali, Hindi, Urdu, Bengali, Malayalam)

API (call from the main Space with gradio_client + HF_TOKEN; this Space is private):
  /transcribe(audio_path, lang, decoding)  -> {"text", "lang", "seconds", "audio_seconds"}
  /speak(text, lang, description)          -> (wav, {"seconds", "audio_seconds", "rtf"})
  /benchmark()                             -> Nepali TTS -> ASR round-trip timings
  /langs()                                 -> ASR language codes
"""

import os
import time

import torch  # import before onnxruntime so CUDA/cuDNN libs from the torch wheels are loaded
import numpy as np
import torchaudio
import gradio as gr
from transformers import AutoModel, AutoTokenizer
from parler_tts import ParlerTTSForConditionalGeneration

HF_TOKEN = os.environ.get("HF_TOKEN")
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
TTS_DTYPE = getattr(torch, os.environ.get("TTS_DTYPE", "float32"))
ASR_SR = 16_000

# ---------------------------------------------------------------- models
t0 = time.time()
asr = AutoModel.from_pretrained(
    "ai4bharat/indic-conformer-600m-multilingual", trust_remote_code=True, token=HF_TOKEN
)
tts = ParlerTTSForConditionalGeneration.from_pretrained(
    "ai4bharat/indic-parler-tts", token=HF_TOKEN, torch_dtype=TTS_DTYPE
).to(DEVICE)
tts_tok = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts", token=HF_TOKEN)
desc_tok = AutoTokenizer.from_pretrained(tts.config.text_encoder._name_or_path, token=HF_TOKEN)
TTS_SR = tts.config.sampling_rate
LOAD_SECONDS = round(time.time() - t0, 1)

# Named speakers from the Indic Parler-TTS card; calm and slow suits patients.
_CLEAR = "The recording is of very high quality, with the speaker's voice sounding clear and very close up."
DEFAULT_DESCRIPTIONS = {
    "ne": f"Amrita speaks at a slow, calm pace with a clear voice. {_CLEAR}",
    "hi": f"Divya speaks at a slow, calm pace with a warm, clear voice. {_CLEAR}",
    "en": f"A female speaker delivers calm, clear speech at a moderate speed and pitch. {_CLEAR}",
}
GENERIC_DESCRIPTION = f"A female speaker delivers calm, clear speech at a slow pace and moderate pitch. {_CLEAR}"


def _sync():
    if DEVICE.startswith("cuda"):
        torch.cuda.synchronize()


# ---------------------------------------------------------------- core functions
def _transcribe_wave(wav: torch.Tensor, sr: int, lang: str, decoding: str = "ctc") -> dict:
    wav = torch.mean(wav, dim=0, keepdim=True) if wav.dim() == 2 else wav.unsqueeze(0)
    if sr != ASR_SR:
        wav = torchaudio.functional.resample(wav, sr, ASR_SR)
    t = time.time()
    text = asr(wav, lang, decoding)
    return {
        "text": text,
        "lang": lang,
        "seconds": round(time.time() - t, 3),
        "audio_seconds": round(wav.shape[-1] / ASR_SR, 2),
    }


def transcribe(audio_path: str, lang: str = "ne", decoding: str = "ctc") -> dict:
    if not audio_path:
        raise gr.Error("No audio received.")
    wav, sr = torchaudio.load(audio_path)
    return _transcribe_wave(wav, sr, lang, decoding)


@torch.inference_mode()
def _speak_array(text: str, lang: str = "ne", description: str = ""):
    description = description or DEFAULT_DESCRIPTIONS.get(lang, GENERIC_DESCRIPTION)
    d = desc_tok(description, return_tensors="pt").to(DEVICE)
    p = tts_tok(text, return_tensors="pt").to(DEVICE)
    _sync()
    t = time.time()
    out = tts.generate(
        input_ids=d.input_ids,
        attention_mask=d.attention_mask,
        prompt_input_ids=p.input_ids,
        prompt_attention_mask=p.attention_mask,
    )
    _sync()
    seconds = time.time() - t
    audio = out.to(torch.float32).cpu().numpy().squeeze()
    audio_seconds = len(audio) / TTS_SR
    stats = {
        "seconds": round(seconds, 3),
        "audio_seconds": round(audio_seconds, 2),
        "rtf": round(seconds / max(audio_seconds, 1e-6), 3),  # < 1.0 = faster than real time
        "chars": len(text),
    }
    return audio, stats


def speak(text: str, lang: str = "ne", description: str = ""):
    if not text or not text.strip():
        raise gr.Error("No text received.")
    audio, stats = _speak_array(text, lang, description)
    return (TTS_SR, audio), stats


BENCH_SENTENCE_NE = "नमस्ते। म बयान हुँ। तपाईंको डाक्टरले भनेको कुरा म नेपालीमा भन्छु।"
# "Hello. I am Bayan. I will say what your doctor says in Nepali." (machine draft; verify with a native speaker)


def benchmark() -> dict:
    """Nepali TTS -> ASR round trip; the first call after boot includes CUDA warm-up."""
    audio, tts_stats = _speak_array(BENCH_SENTENCE_NE, "ne")
    asr_stats = _transcribe_wave(torch.from_numpy(audio).unsqueeze(0), TTS_SR, "ne", "ctc")
    return {
        "device": DEVICE,
        "gpu": torch.cuda.get_device_name(0) if DEVICE.startswith("cuda") else None,
        "tts_dtype": str(TTS_DTYPE),
        "model_load_seconds": LOAD_SECONDS,
        "input_text": BENCH_SENTENCE_NE,
        "tts": tts_stats,
        "asr": asr_stats,
        "round_trip_seconds": round(tts_stats["seconds"] + asr_stats["seconds"], 3),
    }


def langs() -> list:
    return sorted(asr.language_masks.keys())


# ---------------------------------------------------------------- UI / API
with gr.Blocks(title="Bayan voice worker") as demo:
    gr.Markdown(
        "# Bayan AI · GPU voice worker\n"
        "Private API backend for the Bayan AI Space: IndicConformer (ASR) and Indic Parler-TTS (TTS)."
    )
    with gr.Tab("Benchmark"):
        b_btn = gr.Button("Run Nepali TTS → ASR round trip")
        b_out = gr.JSON()
        b_btn.click(benchmark, None, b_out, api_name="benchmark")
    with gr.Tab("Speak (TTS)"):
        s_text = gr.Textbox(label="Text", value=BENCH_SENTENCE_NE)
        s_lang = gr.Textbox(label="Language code", value="ne")
        s_desc = gr.Textbox(label="Voice description (optional)")
        s_btn = gr.Button("Speak")
        s_audio = gr.Audio(label="Audio", type="numpy")
        s_stats = gr.JSON()
        s_btn.click(speak, [s_text, s_lang, s_desc], [s_audio, s_stats], api_name="speak")
    with gr.Tab("Transcribe (ASR)"):
        a_audio = gr.Audio(label="Audio", type="filepath", sources=["upload", "microphone"])
        a_lang = gr.Textbox(label="Language code", value="ne")
        a_dec = gr.Radio(["ctc", "rnnt"], value="ctc", label="Decoding")
        a_btn = gr.Button("Transcribe")
        a_out = gr.JSON()
        a_btn.click(transcribe, [a_audio, a_lang, a_dec], a_out, api_name="transcribe")
    with gr.Tab("Languages"):
        l_btn = gr.Button("List ASR language codes")
        l_out = gr.JSON()
        l_btn.click(langs, None, l_out, api_name="langs")

demo.queue(default_concurrency_limit=1)  # one GPU job at a time

if __name__ == "__main__":
    demo.launch()
