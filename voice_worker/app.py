"""Bayan AI · GPU voice worker.

Serves the speech models that no Inference Provider hosts:
  * ASR: ai4bharat/indic-conformer-600m-multilingual (22 Indic languages incl. Nepali)
  * ASR + role ID (doctor en/ar): openai/whisper-large-v3-turbo
  * TTS: ai4bharat/indic-parler-tts (21 languages incl. Nepali, Hindi, Urdu, Bengali, Malayalam)

API (call from the main Space with gradio_client + HF_TOKEN; this Space is private):
  /hear(audio_path, patient_lang)          -> {"role", "lang", "text", "engine", "lid", timings}
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
from transformers import AutoModel, AutoTokenizer, WhisperForConditionalGeneration, WhisperProcessor
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
WHISPER_ID = "openai/whisper-large-v3-turbo"
w_proc = WhisperProcessor.from_pretrained(WHISPER_ID)
w_model = WhisperForConditionalGeneration.from_pretrained(
    WHISPER_ID, torch_dtype=torch.float16 if DEVICE.startswith("cuda") else torch.float32
).to(DEVICE)
W_DTYPE = w_model.dtype
LOAD_SECONDS = round(time.time() - t0, 1)

DOCTOR_LANGS = ("en", "ar")
_W_TOK = w_proc.tokenizer
_W_UNK = _W_TOK.unk_token_id
_W_SOT = _W_TOK.convert_tokens_to_ids("<|startoftranscript|>")


def _whisper_lang_id(code: str):
    tid = _W_TOK.convert_tokens_to_ids(f"<|{code}|>")
    return None if tid in (None, _W_UNK) else tid

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


def _to_mono16k(wav: torch.Tensor, sr: int) -> torch.Tensor:
    wav = torch.mean(wav, dim=0, keepdim=True) if wav.dim() == 2 else wav.unsqueeze(0)
    return torchaudio.functional.resample(wav, sr, ASR_SR) if sr != ASR_SR else wav


@torch.inference_mode()
def _hear_wave(wav: torch.Tensor, sr: int, patient_lang: str) -> dict:
    """Decide doctor vs patient for one utterance, then transcribe it with the right model."""
    t_all = time.time()
    wav16 = _to_mono16k(wav, sr)
    feats = w_proc(wav16.squeeze(0).numpy(), sampling_rate=ASR_SR, return_tensors="pt").input_features
    feats = feats.to(DEVICE, W_DTYPE)

    # 1) Restricted language ID: score only {en, ar, patient_lang} with one decoder step.
    t = time.time()
    cands = [c for c in (*DOCTOR_LANGS, patient_lang) if _whisper_lang_id(c) is not None]
    ids = [_whisper_lang_id(c) for c in cands]
    logits = w_model(
        input_features=feats, decoder_input_ids=torch.tensor([[_W_SOT]], device=DEVICE)
    ).logits[0, -1]
    probs = torch.softmax(logits[ids].float(), dim=-1).tolist()
    lid = dict(zip(cands, [round(p, 4) for p in probs]))
    lid_seconds = time.time() - t
    top = max(lid, key=lid.get)
    role = "doctor" if top in DOCTOR_LANGS else "patient"

    # 2) Transcribe with the right engine.
    t = time.time()
    if role == "doctor":
        lang, engine = top, "whisper-large-v3-turbo"
        out = w_model.generate(feats, language=lang, task="transcribe", max_new_tokens=220)
        text = w_proc.batch_decode(out, skip_special_tokens=True)[0].strip()
    elif patient_lang in asr.language_masks:
        lang, engine = patient_lang, "indic-conformer-600m"
        text = asr(wav16, patient_lang, "ctc")
    else:
        lang, engine = patient_lang, "whisper-large-v3-turbo"
        out = w_model.generate(feats, language=lang, task="transcribe", max_new_tokens=220)
        text = w_proc.batch_decode(out, skip_special_tokens=True)[0].strip()
    asr_seconds = time.time() - t

    return {
        "role": role,
        "lang": lang,
        "text": text,
        "engine": engine,
        "lid": lid,
        "audio_seconds": round(wav16.shape[-1] / ASR_SR, 2),
        "lid_seconds": round(lid_seconds, 3),
        "asr_seconds": round(asr_seconds, 3),
        "seconds": round(time.time() - t_all, 3),
    }


def hear(audio_path: str, patient_lang: str = "ne") -> dict:
    if not audio_path:
        raise gr.Error("No audio received.")
    wav, sr = torchaudio.load(audio_path)
    return _hear_wave(wav, sr, patient_lang)


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


BENCH_SENTENCE_EN = "Do you have any allergies to medicines?"


def benchmark() -> dict:
    """Nepali TTS -> /hear (expect patient) and English TTS -> /hear (expect doctor)."""
    audio_ne, tts_ne = _speak_array(BENCH_SENTENCE_NE, "ne")
    hear_ne = _hear_wave(torch.from_numpy(audio_ne).unsqueeze(0), TTS_SR, "ne")
    audio_en, tts_en = _speak_array(BENCH_SENTENCE_EN, "en")
    hear_en = _hear_wave(torch.from_numpy(audio_en).unsqueeze(0), TTS_SR, "ne")
    return {
        "device": DEVICE,
        "gpu": torch.cuda.get_device_name(0) if DEVICE.startswith("cuda") else None,
        "tts_dtype": str(TTS_DTYPE),
        "model_load_seconds": LOAD_SECONDS,
        "nepali": {"input_text": BENCH_SENTENCE_NE, "tts": tts_ne, "hear": hear_ne},
        "english": {"input_text": BENCH_SENTENCE_EN, "tts": tts_en, "hear": hear_en},
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
    with gr.Tab("Hear (role + ASR)"):
        h_audio = gr.Audio(label="Utterance", type="filepath", sources=["upload", "microphone"])
        h_lang = gr.Textbox(label="Patient language (dropdown value)", value="ne")
        h_btn = gr.Button("Hear")
        h_out = gr.JSON()
        h_btn.click(hear, [h_audio, h_lang], h_out, api_name="hear")
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
