"""Bayan AI · GPU voice worker.

Serves the speech models that no Inference Provider hosts:
  * ASR: ai4bharat/indic-conformer-600m-multilingual (22 Indic languages incl. Nepali)
  * ASR + role ID (doctor en/ar): openai/whisper-large-v3-turbo
  * TTS: ai4bharat/indic-parler-tts (21 languages incl. Nepali, Hindi, Urdu, Bengali, Malayalam)

API (call from the main Space with gradio_client + HF_TOKEN; this Space is private):
  /hear(audio_path, patient_lang)          -> {"role", "lang", "text", "engine", "lid", timings}
  /transcribe(audio_path, lang, decoding)  -> {"text", "lang", "seconds", "audio_seconds"}
  /speak(text, lang, description)          -> (wav, {"seconds", "audio_seconds", "rtf"})
  /speak_stream(text, lang, description)   -> generator of {"sr", "pcm" (b64 int16), ...}, then {"done": true, stats}
  /speak_stream_opts(text, lang, description, opts_json), /tts_probe(opts_json) -> latency experiments
  /benchmark()                             -> Nepali TTS -> ASR round-trip timings
  /langs()                                 -> ASR language codes
Fast HTTP API (Bearer token): POST /v1/hear, POST /v1/speak_stream (NDJSON), GET /v1/voices, GET /v1/ping.

Voice rule: a language is spoken only by an engine on that language's allow-list (PARLER_LANGS, supertonic.LANGS,
MMS tl/sw, Piper ka) and only when the text is in the language's script; otherwise HTTP 422 / gr.Error and no
audio. Never another language's voice.
"""

import base64
import importlib.util
import json
import os
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_T_BOOT = time.time()


def _log(msg: str) -> None:
    print(f"[boot +{time.time() - _T_BOOT:6.1f}s {time.strftime('%H:%M:%S')}] {msg}", flush=True)


# Must be set before huggingface_hub is imported. hf_transfer ships in the Spaces base image.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
if importlib.util.find_spec("hf_transfer") is not None:
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
_log(f"process start; hf_transfer={os.environ.get('HF_HUB_ENABLE_HF_TRANSFER', '0')}")

import torch  # import before onnxruntime so CUDA/cuDNN libs from the torch wheels are loaded
import numpy as np
import torchaudio
import gradio as gr
from huggingface_hub import constants as hf_constants, snapshot_download
from transformers import AutoModel, AutoTokenizer, WhisperForConditionalGeneration, WhisperProcessor
from parler_tts import ParlerTTSForConditionalGeneration, ParlerTTSStreamer
from speechbrain.inference.classifiers import EncoderClassifier

_log(f"imports done; torch {torch.__version__}, cuda={torch.cuda.is_available()}")

# TorchScript's GPU fuser fails to compile IndicConformer's complex-valued preprocessor
# ("default_program ... c10::complex" NVRTC errors), so run TorchScript unfused.
torch._C._jit_override_can_fuse_on_gpu(False)
torch._C._jit_set_texpr_fuser_enabled(False)
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

HF_TOKEN = os.environ.get("HF_TOKEN")
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
TTS_DTYPE = getattr(torch, os.environ.get("TTS_DTYPE", "bfloat16"))
# torch.compile + static cache is broken with parler-tts on transformers 4.46.1
# ("'StaticCache' object has no attribute 'max_batch_size'"), so it is off by default.
TTS_COMPILE = os.environ.get("TTS_COMPILE", "off")
TTS_COMPILE = "" if TTS_COMPILE.lower() in ("", "off", "0", "false") else TTS_COMPILE
DESC_MAX, PROMPT_MAX = 64, 192  # fixed padded lengths so the compiled graph is reused
ASR_SR = 16_000

CONFORMER_ID = "ai4bharat/indic-conformer-600m-multilingual"
PARLER_ID = "ai4bharat/indic-parler-tts"
WHISPER_ID = "openai/whisper-large-v3-turbo"
VOX_ID = "speechbrain/lang-id-voxlingua107-ecapa"
_TOK_FILES = ["*.json", "*.model", "*.txt"]
# Nothing is cached between container starts (no persistent storage), so every boot downloads ~8 GB.
# Fetch all repos in parallel (many small files in the conformer repo) before the loaders run;
# the loaders then hit the local cache.
_PREFETCH = {
    CONFORMER_ID: None,
    PARLER_ID: None,
    WHISPER_ID: ["*.json", "*.txt", "model.safetensors"],
    VOX_ID: None,
    "google/flan-t5-large": _TOK_FILES,  # tokenizer only (Parler's description encoder)
    "Supertone/supertonic-3": ["onnx/*", "voice_styles/*"],  # CPU voice for Korean (and A/B for Arabic)
    # Georgian ASR: Whisper is unusable for Georgian (FLEURS dev, 20 speakers: WER 110%, CER 83%); MMS-1B-all with
    # its Georgian adapter: WER 27%, CER 4.8%.
    "facebook/mms-1b-all": ["config.json", "preprocessor_config.json", "special_tokens_map.json", "tokenizer_config.json",
                            "vocab.json", "model.safetensors", "adapter.kat.safetensors"],
}


def _prefetch(repo: str, patterns):
    t = time.time()
    for attempt in range(2):
        try:
            snapshot_download(repo, allow_patterns=patterns, token=HF_TOKEN, max_workers=32)
            break
        except Exception as e:  # noqa: BLE001 - fall back to plain HTTP if hf_transfer misbehaves
            _log(f"prefetch {repo} failed ({type(e).__name__}: {e}); retrying without hf_transfer")
            hf_constants.HF_HUB_ENABLE_HF_TRANSFER = False
    _log(f"prefetched {repo} in {time.time() - t:.1f}s")


t0 = time.time()
_pool = ThreadPoolExecutor(max_workers=len(_PREFETCH))
_fetched = {repo: _pool.submit(_prefetch, repo, pat) for repo, pat in _PREFETCH.items()}


def _wait_fetch(*repos):
    """Block until these repos are prefetched; loading starts while others are still downloading."""
    for repo in repos:
        try:
            _fetched[repo].result()
        except Exception as e:  # noqa: BLE001 - the loader downloads whatever is missing
            _log(f"prefetch error for {repo}, continuing: {type(e).__name__}: {e}")


# ---------------------------------------------------------------- models
_wait_fetch(PARLER_ID, "google/flan-t5-large")
t = time.time()
tts = ParlerTTSForConditionalGeneration.from_pretrained(
    PARLER_ID, token=HF_TOKEN, torch_dtype=TTS_DTYPE,
    **({"attn_implementation": "eager"} if TTS_COMPILE else {}),  # explicit "sdpa" is rejected by its T5 encoder
).to(DEVICE)
tts_tok = AutoTokenizer.from_pretrained(PARLER_ID, token=HF_TOKEN)
desc_tok = AutoTokenizer.from_pretrained(tts.config.text_encoder._name_or_path, token=HF_TOKEN)
TTS_SR = tts.config.sampling_rate
_log(f"Parler-TTS loaded in {time.time() - t:.1f}s")
_wait_fetch(WHISPER_ID)
t = time.time()
w_proc = WhisperProcessor.from_pretrained(WHISPER_ID)
w_model = WhisperForConditionalGeneration.from_pretrained(
    WHISPER_ID, torch_dtype=torch.float16 if DEVICE.startswith("cuda") else torch.float32
).to(DEVICE)
W_DTYPE = w_model.dtype
_log(f"Whisper loaded in {time.time() - t:.1f}s")
_wait_fetch(VOX_ID)
t = time.time()
# Dedicated spoken-language ID (107 languages incl. Nepali); Whisper's Nepali LID proved unreliable.
lid_model = EncoderClassifier.from_hparams(
    source=VOX_ID, savedir="/tmp/voxlingua107",
    run_opts={"device": DEVICE},
)
VOX_INDEX = {lab.split(":")[0].strip(): idx for lab, idx in lid_model.hparams.label_encoder.lab2ind.items()}
_log(f"VoxLingua107 loaded in {time.time() - t:.1f}s")
_wait_fetch(CONFORMER_ID)
_log(f"all downloads done in {time.time() - t0:.1f}s")
_pool.shutdown(wait=False)
t = time.time()
asr = AutoModel.from_pretrained(CONFORMER_ID, trust_remote_code=True, token=HF_TOKEN)
_log(f"IndicConformer loaded in {time.time() - t:.1f}s")
# Patient languages transcribed with MMS-1B-all + a per-language adapter (ISO 639-3 code).
MMS_ASR_LANGS = {"ka": "kat"}
mms_asr = mms_proc = None
try:
    from transformers import AutoProcessor, Wav2Vec2ForCTC  # noqa: E402
    _wait_fetch("facebook/mms-1b-all")
    t = time.time()
    mms_proc = AutoProcessor.from_pretrained("facebook/mms-1b-all", target_lang="kat")
    mms_asr = Wav2Vec2ForCTC.from_pretrained(
        "facebook/mms-1b-all", target_lang="kat", ignore_mismatched_sizes=True,
        torch_dtype=torch.float16 if DEVICE.startswith("cuda") else torch.float32).to(DEVICE).eval()
    _log(f"MMS-1B-all ASR (kat) loaded in {time.time() - t:.1f}s")
except Exception as _e:  # noqa: BLE001 - boot anyway; Georgian falls back to Whisper
    MMS_ASR_LANGS = {}
    _log(f"MMS ASR failed: {type(_e).__name__}: {_e}")


@torch.inference_mode()
def _mms_text(wav16: torch.Tensor) -> str:
    inp = mms_proc(wav16.squeeze(0).numpy(), sampling_rate=ASR_SR, return_tensors="pt")
    ids = mms_asr(inp.input_values.to(DEVICE, mms_asr.dtype)).logits.argmax(-1)[0]
    return mms_proc.decode(ids).strip()
# Voices Indic Parler-TTS lacks: Arabic (doctor side), Filipino/Tagalog and Swahili (patient side).
# Meta MMS-TTS (VITS, ~36M params each, CC-BY-NC-4.0): fast and cheap; plain but clear voice.
from transformers import VitsModel  # noqa: E402
t = time.time()
MMS = {}
for _code, _repo in (("ar", "facebook/mms-tts-ara"), ("tl", "facebook/mms-tts-tgl"), ("sw", "facebook/mms-tts-swh")):
    try:
        _m = VitsModel.from_pretrained(_repo).to(DEVICE).eval()
        _m.speaking_rate = float(os.environ.get("MMS_RATE", "0.9"))  # a little slower than default: clearer
        MMS[_code] = (AutoTokenizer.from_pretrained(_repo), _m)
    except Exception as _e:  # noqa: BLE001 - boot anyway; the app falls back to text
        _log(f"MMS {_repo} failed: {type(_e).__name__}: {_e}")
_log(f"MMS-TTS loaded ({', '.join(MMS)}) in {time.time() - t:.1f}s")
# Supertonic 3 (ONNX, ~99M params) on CPU: ~0.7 s per sentence, never waits for the GPU lock.
ST = None
# Default voice per language: Indic Parler-TTS for Indic languages, MMS for Filipino/Swahili, Supertonic 3 for
# everything else it speaks (doctor English + Arabic, Korean, Japanese, European languages, Indonesian, Turkish,
# Vietnamese...). Arabic moved from MMS to Supertonic: drug names survive the ASR round trip better and its licence
# (OpenRAIL-M) allows commercial use, unlike MMS (CC-BY-NC). engine= still forces any engine for A/B.
ST_NOT_DEFAULT = {"hi"}

# Piper (rhasspy/piper-voices, ONNX VITS ~63 MB, CPU ~0.1 s per sentence) for languages none of the above speak:
# Georgian ("natia"). piper-tts pins the CPU-only onnxruntime wheel, which would replace onnxruntime-gpu (needed by
# IndicConformer), so it is installed here without dependencies and runs on onnxruntime-gpu's CPU provider.
PIPER_VOICES = {"ka": "ka/ka_GE/natia/medium/ka_GE-natia-medium"}
PIPER = {}
try:
    import subprocess, sys  # noqa: E401, E402
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "piper-tts==1.8.0", "pathvalidate==3.2.3"],
                   check=True, timeout=180)
    from huggingface_hub import hf_hub_download  # noqa: E402
    from piper import PiperVoice  # noqa: E402
    from piper.config import SynthesisConfig  # noqa: E402
    t = time.time()
    for _code, _stem in PIPER_VOICES.items():
        _onnx = hf_hub_download("rhasspy/piper-voices", _stem + ".onnx", token=HF_TOKEN)
        hf_hub_download("rhasspy/piper-voices", _stem + ".onnx.json", token=HF_TOKEN)
        PIPER[_code] = PiperVoice.load(_onnx)
    _log(f"Piper loaded ({', '.join(PIPER)}) in {time.time() - t:.1f}s")
except Exception as _e:  # noqa: BLE001 - boot anyway; Georgian falls back to text
    _log(f"Piper failed: {type(_e).__name__}: {_e}")
PIPER_RATE = float(os.environ.get("PIPER_LENGTH_SCALE", "1.1"))  # >1 = slower: calm, clear
ST_SPEED = float(os.environ.get("ST_SPEED", "0.9"))  # languages that use it by default; any of supertonic.LANGS on request (engine=)
try:
    from supertonic import LANGS as ST_LANGS, REPO as ST_REPO, Supertonic  # noqa: E402
    _wait_fetch(ST_REPO)
    t = time.time()
    ST = Supertonic(snapshot_download(ST_REPO, allow_patterns=["onnx/*", "voice_styles/*"], token=HF_TOKEN),
                    voice=os.environ.get("ST_VOICE", "F1"), threads=os.cpu_count() or 0)
    _log(f"Supertonic 3 loaded in {time.time() - t:.1f}s")
except Exception as _e:  # noqa: BLE001 - boot anyway; Korean falls back to text
    ST_LANGS = set()
    _log(f"Supertonic failed: {type(_e).__name__}: {_e}")
LOAD_SECONDS = round(time.time() - t0, 1)

DOCTOR_LANGS = ("en", "ar")
_W_TOK = w_proc.tokenizer
_W_UNK = _W_TOK.unk_token_id
_W_SOT = _W_TOK.convert_tokens_to_ids("<|startoftranscript|>")


def _whisper_lang_id(code: str):
    tid = _W_TOK.convert_tokens_to_ids(f"<|{code}|>")
    return None if tid in (None, _W_UNK) else tid

# Indic Parler-TTS speakers are trained per language: a speaker from another language (or an unnamed "A female
# speaker", which samples any of the 69 voices) drifts the accent towards that speaker's language. So every language
# with named speakers on the model card uses its own recommended speaker (female where the card has one).
# Card table: https://huggingface.co/ai4bharat/indic-parler-tts#🎯-using-a-specific-speaker (no Urdu, Konkani,
# Maithili, Santali or Sindhi speakers are named there: those keep the generic description).
PARLER_SPEAKERS = {  # every named speaker per language (card), recommended first
    "as": ["Sita", "Amit", "Poonam", "Rakesh"], "bn": ["Aditi", "Arjun", "Tapan", "Rashmi", "Arnav", "Riya"],
    "brx": ["Maya", "Bikram", "Kalpana"], "doi": ["Karan"],
    "en": ["Mary", "Thoma", "Swapna", "Dinesh", "Meera", "Jatin", "Aakash", "Sneha", "Kabir", "Tisha", "Chingkhei",
           "Thoiba", "Priya", "Tarun", "Gauri", "Nisha", "Raghav", "Kavya", "Ravi", "Vikas", "Riya"],
    "gu": ["Neha", "Yash"], "hi": ["Divya", "Rohit", "Aman", "Rani"], "kn": ["Anu", "Suresh", "Chetan", "Vidya"],
    "ml": ["Anjali", "Harish", "Anju"], "mni": ["Laishram", "Ranjit"],
    "mr": ["Sunita", "Sanjay", "Nikhil", "Radha", "Varun", "Isha"], "ne": ["Amrita"], "or": ["Debjani", "Manas"],
    "sa": ["Aryan"], "ta": ["Jaya", "Kavitha"], "te": ["Lalitha", "Prakash", "Kiran"],
}
_ALL_SPEAKERS = sorted({n for ns in PARLER_SPEAKERS.values() for n in ns}
                       | {"Bhanu", "Champa", "Divjot", "Gurpreet"}, key=len, reverse=True)  # + Chhattisgarhi, Punjabi
_SPEAKER_RE = re.compile(r"\b(" + "|".join(_ALL_SPEAKERS) + r")\b")
_UNNAMED_RE = re.compile(r"^\s*(?:a|the)\s+(?:(?:young|old|middle-aged)\s+)?(?:female|male|woman|man)?\s*(?:speaker|voice)\b",
                         re.I)
# Calm and slow suits patients.
_CLEAR = "The recording is of very high quality, with the speaker's voice sounding clear and very close up."
DEFAULT_DESCRIPTIONS = {
    lang: f"{names[0]} speaks at a slow, calm pace with a clear voice. {_CLEAR}" for lang, names in PARLER_SPEAKERS.items()
}
DEFAULT_DESCRIPTIONS["hi"] = f"Divya speaks at a slow, calm pace with a warm, clear voice. {_CLEAR}"
DEFAULT_DESCRIPTIONS["en"] = f"Mary delivers calm, clear speech at a moderate speed and pitch. {_CLEAR}"
GENERIC_DESCRIPTION = f"A female speaker delivers calm, clear speech at a slow pace and moderate pitch. {_CLEAR}"


def _describe(lang: str, description: str = "") -> str:
    """The Parler voice description for `lang`, always with a speaker of that language when the card names one.
    A caller's description keeps its style words; an unnamed speaker ("A female speaker…") becomes the language's
    speaker, and another language's speaker (e.g. "Divya" for Nepali) is replaced."""
    if not description:
        return DEFAULT_DESCRIPTIONS.get(lang, GENERIC_DESCRIPTION)
    own = PARLER_SPEAKERS.get(lang, [])
    default = own[0] if own else "A female speaker"
    description = _SPEAKER_RE.sub(lambda m: m.group(1) if m.group(1) in own else default, description)
    if own and not _SPEAKER_RE.search(description):
        description = _UNNAMED_RE.sub(default, description, count=1) if _UNNAMED_RE.match(description) \
            else f"{default}'s voice. {description}"
    return description


_EAGER_FORWARD = tts.forward
TTS_COMPILED = False
COMPILE_NOTE = "off"


def _tokenize_tts(text: str, description: str, padded: bool):
    if padded:
        d = desc_tok(description, return_tensors="pt", padding="max_length", max_length=DESC_MAX, truncation=True)
        p = tts_tok(text, return_tensors="pt", padding="max_length", max_length=PROMPT_MAX, truncation=True)
    else:
        d = desc_tok(description, return_tensors="pt")
        p = tts_tok(text, return_tensors="pt")
    return d.to(DEVICE), p.to(DEVICE)


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


_REPEAT_RE = re.compile(r"(.{1,6}?)\1{5,}", re.S)


def _degenerate(text: str) -> bool:
    """Whisper's classic failure: a syllable/word looping ("ماهوهوهو…"). Same zlib ratio test Whisper uses (2.4)."""
    if not text:
        return False
    import zlib  # noqa: PLC0415
    # One byte per character (low byte of the code point), NOT UTF-8: in Georgian, Devanagari, Bengali, Tamil,
    # Korean… two of every three UTF-8 bytes are the same script prefix, which pushed long, correct sentences over
    # 2.4 (real Georgian FLEURS sentences scored 2.2-2.44 and were dropped as "unclear"). Real loops still score >3.
    b = bytes(ord(c) & 0xFF for c in text)
    ratio = len(b) / max(1, len(zlib.compress(b)))
    return ratio > 2.4 or bool(_REPEAT_RE.search(text))


def _whisper_text(feats, lang: str, audio_seconds: float) -> str:
    out = w_model.generate(
        feats, language=lang, task="transcribe",
        max_new_tokens=int(min(220, 16 + 10 * audio_seconds)),  # ~10 tokens/s of speech is generous
        no_repeat_ngram_size=4,  # blocks the looping failure mode
    )
    return w_proc.batch_decode(out, skip_special_tokens=True)[0].strip()


def _asr_engine(patient_lang: str):
    """The ONE engine that transcribes this patient language (its own model / language mask), or None."""
    if patient_lang in MMS_ASR_LANGS:
        return "mms-1b-all"
    if patient_lang in asr.language_masks:
        return "indic-conformer-600m"
    if patient_lang and _whisper_lang_id(patient_lang) is not None:
        return "whisper-large-v3-turbo"
    return None


@torch.inference_mode()
def _hear_wave(wav: torch.Tensor, sr: int, patient_lang: str, doctor_lang: str = "", role_override: str = "") -> dict:
    """Decide doctor vs patient for one utterance, then transcribe it with the right model."""
    t_all = time.time()
    if not _asr_engine(patient_lang):
        raise ValueError(f"no speech recognition for {patient_lang!r}")
    wav16 = _to_mono16k(wav, sr)
    feats = w_proc(wav16.squeeze(0).numpy(), sampling_rate=ASR_SR, return_tensors="pt").input_features
    feats = feats.to(DEVICE, W_DTYPE)

    # 1) Restricted language ID with VoxLingua107: score only {en, ar, patient_lang}.
    t = time.time()
    # If the app tells us the doctor's language, only {doctor_lang, patient_lang} compete (no en/ar guessing).
    fixed_doc = doctor_lang if doctor_lang in DOCTOR_LANGS else ""
    doc_langs = (fixed_doc,) if fixed_doc else DOCTOR_LANGS
    cands = [c for c in (*doc_langs, patient_lang) if c in VOX_INDEX]
    out_prob = lid_model.classify_batch(wav16.to(DEVICE))[0][0]  # log-likelihoods over 107 languages
    probs = torch.softmax(out_prob[[VOX_INDEX[c] for c in cands]].float(), dim=-1).tolist()
    lid = dict(zip(cands, [round(p, 4) for p in probs]))
    lid_seconds = time.time() - t
    # Whisper's opinion, for diagnostics only.
    w_cands = [c for c in (*doc_langs, patient_lang) if _whisper_lang_id(c) is not None]
    w_logits = w_model(
        input_features=feats, decoder_input_ids=torch.tensor([[_W_SOT]], device=DEVICE)
    ).logits[0, -1]
    w_probs = torch.softmax(w_logits[[_whisper_lang_id(c) for c in w_cands]].float(), dim=-1).tolist()
    lid_whisper = dict(zip(w_cands, [round(p, 4) for p in w_probs]))
    # Doctor vs patient: VoxLingua107 (reliable for Nepali/Indic, where Whisper's LID is not).
    # English vs Arabic for the doctor: Whisper's LID (very reliable for en/ar; VoxLingua confused them).
    doc_p = sum(lid.get(c, 0.0) for c in doc_langs)
    detected_role = "doctor" if doc_p >= lid.get(patient_lang, 0.0) else "patient"
    # The app can tell us who is speaking (turn-based UI); detection is then only reported, as a safety check.
    role_forced = role_override in ("doctor", "patient")
    role = role_override if role_forced else detected_role
    doc_lang = fixed_doc or max(DOCTOR_LANGS, key=lambda c: lid_whisper.get(c, lid.get(c, 0.0)))

    # 2) Transcribe with the right engine.
    t = time.time()
    dur = wav16.shape[-1] / ASR_SR
    unclear = False
    if role == "doctor":
        lang, engine = doc_lang, "whisper-large-v3-turbo"
        text = _whisper_text(feats, lang, dur)
        if _degenerate(text):  # noise, or (auto mode) the wrong doctor language: retry once, else give up
            if fixed_doc:
                text, unclear = "", True
            else:
                other = [c for c in DOCTOR_LANGS if c != lang][0]
                alt = _whisper_text(feats, other, dur)
                if not _degenerate(alt):
                    lang, text = other, alt
                else:
                    text, unclear = "", True
    elif patient_lang in MMS_ASR_LANGS:
        lang, engine = patient_lang, "mms-1b-all"
        text = _mms_text(wav16)
        if _degenerate(text):
            text, unclear = "", True
    elif patient_lang in asr.language_masks:
        lang, engine = patient_lang, "indic-conformer-600m"
        text = asr(wav16, patient_lang, "ctc")
        if _degenerate(text):
            text, unclear = "", True
    else:
        lang, engine = patient_lang, "whisper-large-v3-turbo"
        text = _whisper_text(feats, lang, dur)
        if _degenerate(text):
            text, unclear = "", True
    asr_seconds = time.time() - t

    return {
        "role": role,
        "lang": lang,
        "text": text,
        "unclear": unclear,
        # Whisper's language token does not force the output language (Tagalog audio forced to "en" comes back as
        # Tagalog text labelled "en"): the same script/word check as the voices, as a hint for the app.
        "text_problem": script_problem(text, lang) if text else None,
        "role_forced": role_forced,
        "detected_role": detected_role,
        "engine": engine,
        "lid": lid,
        "lid_whisper": lid_whisper,
        "audio_seconds": round(wav16.shape[-1] / ASR_SR, 2),
        "lid_seconds": round(lid_seconds, 3),
        "asr_seconds": round(asr_seconds, 3),
        "seconds": round(time.time() - t_all, 3),
    }


def _load_and_delete(audio_path: str):
    """Load the uploaded utterance, then delete it: patient audio must not stay in Gradio's cache."""
    try:
        return torchaudio.load(audio_path)
    finally:
        try:
            os.unlink(audio_path)
        except OSError:
            pass


def hear(audio_path: str, patient_lang: str = "ne") -> dict:
    if not audio_path:
        raise gr.Error("No audio received.")
    wav, sr = _load_and_delete(audio_path)
    if not _asr_engine(patient_lang):
        raise gr.Error(f"no speech recognition for {patient_lang or '(no language)'}")
    return _hear_wave(wav, sr, patient_lang)


def transcribe(audio_path: str, lang: str = "ne", decoding: str = "ctc") -> dict:
    if not audio_path:
        raise gr.Error("No audio received.")
    wav, sr = _load_and_delete(audio_path)
    return _transcribe_wave(wav, sr, lang, decoding)


@torch.inference_mode()
def _speak_array(text: str, lang: str = "ne", description: str = ""):
    description = _describe(lang, description)
    fits = len(tts_tok(text).input_ids) <= PROMPT_MAX and len(desc_tok(description).input_ids) <= DESC_MAX
    use_compiled = TTS_COMPILED and fits
    tts.forward = _COMPILED_FORWARD if use_compiled else _EAGER_FORWARD
    tts.generation_config.cache_implementation = "static" if use_compiled else None
    d, p = _tokenize_tts(text, description, padded=use_compiled)
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
        "compiled": use_compiled,
    }
    return audio, stats


_COMPILED_FORWARD = _EAGER_FORWARD
if TTS_COMPILE and DEVICE.startswith("cuda"):
    try:
        t_c = time.time()
        _COMPILED_FORWARD = torch.compile(_EAGER_FORWARD, mode=TTS_COMPILE)
        TTS_COMPILED = True
        for _ in range(2 if TTS_COMPILE == "reduce-overhead" else 1):
            _speak_array("नमस्ते", "ne")
        COMPILE_NOTE = f"{TTS_COMPILE} (warm-up {time.time() - t_c:.0f}s)"
    except Exception as e:  # noqa: BLE001 - never fail boot because of compilation
        TTS_COMPILED, _COMPILED_FORWARD = False, _EAGER_FORWARD
        tts.forward = _EAGER_FORWARD
        tts.generation_config.cache_implementation = None
        COMPILE_NOTE = f"failed, eager fallback: {type(e).__name__}: {e}"[:300]
    print("TTS compile:", COMPILE_NOTE, flush=True)


# ---------------------------------------------------------------- streaming TTS
# Parler generates ~86 codec frames per second of audio, one decoding step each; on an L4 a step costs
# ~18 ms, i.e. ~1.5x slower than real time, and the cost is per-step overhead, not FLOPs. So:
#   * the text is cut into short segments (sentences; long ones at commas; a short first segment),
#   * ALL segments of a group are generated in ONE batched generate() (a step for 6 segments costs about
#     the same as a step for 1), and audio is streamed in segment order,
#   * playback starts once the buffered audio guarantees that no segment will run dry. With batching
#     that wait is set by the first (short) segment instead of the whole text.
K_CODEBOOKS = tts.decoder.num_codebooks
CODEBOOK_SIZE = tts.audio_encoder.config.codebook_size
FRAME_RATE = float(tts.audio_encoder.config.frame_rate)
CHARS_PER_SEC = {"ne": 11.0, "hi": 12.0, "ur": 12.0, "bn": 12.0, "ml": 10.0, "ta": 10.0, "te": 10.0}
STREAM_OPTS = {
    "max_batch": 8,         # segments generated together
    "first_steps": K_CODEBOOKS + 24,  # decoding steps before the very first chunk (~0.28 s of audio)
    "play_steps": int(FRAME_RATE * 0.5),  # later chunks: ~0.5 s
    "first_max": 45,        # first segment is cut at a comma if longer than this (chars)
    "max_len": 60,          # any segment is cut at commas if longer than this
    "safety": 1.05,         # multiplier on the estimated segment durations
    "margin": 0.15,         # extra seconds of buffer
}
_TAU = {}  # measured seconds per decoding step, by batch size (EMA across requests)
_TAU_DEFAULT = 0.020  # measured 16.7 ms (batch 1) to 19.9 ms (batch 8) on the L4
_SENT_SPLIT = re.compile(r"(?<=[।॥.!?؟])\s+")
_CLAUSE_SPLIT = re.compile(r"(?<=[,،;:])\s+")
_STOP = object()
# Each segment is generated separately, so without these the sentences run into each other ("rushing").
PAUSE_SENTENCE = float(os.environ.get("PAUSE_SENTENCE", "0.55"))  # after . ? ! ।
PAUSE_CLAUSE = float(os.environ.get("PAUSE_CLAUSE", "0.25"))      # after , ; : when a sentence was cut there


def _trim(audio: np.ndarray, sr: int, keep: float = 0.06) -> np.ndarray:
    """Cut leading/trailing silence (below -40 dBFS), keeping a short natural tail, so pauses are exactly ours."""
    fr = max(1, int(sr * 0.01))
    n = len(audio) // fr
    if n < 3:
        return audio
    rms = np.sqrt(np.mean(audio[: n * fr].reshape(n, fr) ** 2, axis=1) + 1e-12)
    loud = np.flatnonzero(rms > 0.01)
    if len(loud) == 0:
        return audio
    a = max(0, loud[0] * fr - int(keep * sr))
    b = min(len(audio), (loud[-1] + 1) * fr + int(keep * sr))
    return audio[a:b]


def _pause_after(seg: str) -> float:
    return PAUSE_SENTENCE if re.search(r"[।॥.!?؟]\W*$", seg.strip()) else PAUSE_CLAUSE


def _split_sentences(text: str) -> list:
    return [p.strip() for p in _SENT_SPLIT.split(text.strip()) if p.strip()]


def _segments(text: str, first_max: int = 45, max_len: int = 60) -> list:
    """Sentences; a sentence longer than the limit is cut at clause punctuation (never mid-clause)."""
    out = []
    for sent in _split_sentences(text):
        limit = first_max if not out else max_len
        clauses = [c.strip() for c in _CLAUSE_SPLIT.split(sent) if c.strip()]
        if len(sent) <= limit or len(clauses) == 1:
            out.append(sent)
            continue
        cur = ""
        for c in clauses:
            if cur and len(cur) + 1 + len(c) > limit and len(cur) >= 12:
                out.append(cur)
                limit = max_len
                cur = c
            else:
                cur = f"{cur} {c}".strip()
        if cur:
            if out and len(cur) < 12:
                out[-1] = f"{out[-1]} {cur}"
            else:
                out.append(cur)
    return out


class _BatchStreamer(ParlerTTSStreamer):
    """Streamer for a batch of B segments; emits ("audio", seg, np.ndarray, seg_end) in segment order."""

    def __init__(self, n: int, first_steps: int, play_steps: int):
        super().__init__(tts, device=DEVICE, play_steps=play_steps)
        self.n, self.first_steps = n, first_steps
        self.cur, self.emitted, self.last_decode = 0, [0] * n, 0
        self.q = queue.Queue()
        self.t_start, self.step_times = None, []

    def tau(self):
        st = self.step_times
        if len(st) < 8:
            return None
        return (st[-1] - st[1]) / (len(st) - 2)  # skip the prefill step

    def _decode(self, b: int) -> np.ndarray:
        return self.apply_delay_pattern_mask(self.token_cache[b * K_CODEBOOKS:(b + 1) * K_CODEBOOKS])

    def _pump(self, final: bool):
        steps = self.token_cache.shape[-1]
        while self.cur < self.n:
            b = self.cur
            col = self.token_cache[b * K_CODEBOOKS:(b + 1) * K_CODEBOOKS, -1]
            done = final or (steps > K_CODEBOOKS + 1 and bool((col >= CODEBOOK_SIZE).all()))
            if done:
                audio = self._decode(b)
                self.q.put(("audio", b, audio[self.emitted[b]:], True))
                self.emitted[b] = len(audio)
                self.cur += 1
                self.last_decode = 0  # decode the next segment's backlog right away
                continue
            need = self.first_steps if self.emitted[b] == 0 else self.play_steps
            if steps - self.last_decode >= need and steps > K_CODEBOOKS + 2:
                audio = self._decode(b)
                upto = len(audio) - self.stride
                if upto > self.emitted[b]:
                    self.q.put(("audio", b, audio[self.emitted[b]:upto], False))
                    self.emitted[b] = upto
                self.last_decode = steps
            break

    def put(self, value):
        self.step_times.append(time.time())
        if self.token_cache is None:
            self.token_cache = value
            return
        self.token_cache = torch.cat([self.token_cache, value[:, None]], dim=-1)
        self._pump(final=False)

    def end(self):
        if self.token_cache is not None:
            self._pump(final=True)


def _payload(audio: np.ndarray, **meta) -> dict:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    return {"sr": TTS_SR, "pcm": base64.b64encode(pcm).decode("ascii"),
            "audio_seconds": round(len(audio) / TTS_SR, 3), **meta}


def _est_seconds(seg: str, lang: str, o: dict) -> float:
    # Measured on Nepali: a segment carries ~0.6 s of lead/tail silence plus ~13 chars/s of speech
    # ("नमस्ते।" 0.78 s, 11 chars 1.43 s, 31 chars 2.8 s, 45 chars 3.4 s).
    return (0.6 + len(seg) / (1.2 * CHARS_PER_SEC.get(lang, 11.0))) * o["safety"]


def _stream_group(segs, lang, description, o, st):
    """Generate one batch of segments; yield ("audio", seg_idx, chunk, seg_end) once safe to play."""
    description = _describe(lang, description)
    B = len(segs)
    d = desc_tok([description] * B, return_tensors="pt", padding=True).to(DEVICE)
    p = tts_tok(list(segs), return_tensors="pt", padding=True).to(DEVICE)
    streamer = _BatchStreamer(B, o["first_steps"], o["play_steps"])
    err = []

    def _run():
        try:
            with torch.inference_mode():
                tts.generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                             prompt_input_ids=p.input_ids, prompt_attention_mask=p.attention_mask,
                             streamer=streamer)
        except Exception as e:  # noqa: BLE001 - surfaced in the consumer
            err.append(e)
        finally:
            streamer.q.put(_STOP)

    t_launch = time.time()
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    est = [_est_seconds(s, lang, o) for s in segs]
    before = np.concatenate([[0.0], np.cumsum(est)[:-1]])
    held, released, finished = [], False, False
    while not finished:
        try:
            item = streamer.q.get(timeout=0.03)
        except queue.Empty:
            item = None
        if item is _STOP:
            finished = True
        elif item is not None:
            held.append(item)
        if not held:
            continue
        if not released:
            tau = max(streamer.tau() or 0.0, _TAU.get(B, _TAU_DEFAULT))
            t_gen = streamer.step_times[0] if streamer.step_times else t_launch
            # Segment k ends generating at t_gen + (a_k*F + K)*tau and ends playing at P + S_k + a_k.
            need = max((a * FRAME_RATE + K_CODEBOOKS) * tau - s - a for a, s in zip(est, before))
            release_at = t_gen + need + o["margin"]
            released = finished or max(time.time(), st["play_end"]) >= release_at
        if released:
            # Merge what was held back (per segment): separate SSE messages can arrive ~0.3 s apart,
            # which would let a tiny first chunk run dry.
            merged = []
            for it in held:
                if merged and merged[-1][1] == it[1]:
                    merged[-1] = ("audio", it[1], np.concatenate([merged[-1][2], it[2]]), it[3])
                else:
                    merged.append(it)
            yield from merged
            held = []
    th.join()
    if err:
        raise err[0]
    tau = streamer.tau()
    if tau:
        _TAU[B] = tau if B not in _TAU else 0.5 * _TAU[B] + 0.5 * tau
    st["groups"].append({"segments": B, "tau_ms": round(1000 * (tau or 0), 2),
                         "steps": len(streamer.step_times)})


def _speak_stream(text: str, lang: str, description: str, opts: dict):
    o = {**STREAM_OPTS, **(opts or {})}
    t0 = time.time()
    segs = _segments(text, o["first_max"], o["max_len"])
    st = {"play_end": 0.0, "groups": []}
    first_at, n, generated, last_seg = None, 0, 0.0, None
    mb = max(int(o["max_batch"]), 1)
    for g in range(0, len(segs), mb):
        for _, b, chunk, seg_end in _stream_group(segs[g:g + mb], lang, description, o, st):
            if len(chunk) == 0:
                continue
            now = time.time()
            dur = len(chunk) / TTS_SR
            generated += dur
            st["play_end"] = max(st["play_end"], now) + dur
            n += 1
            seg = g + b
            meta = {"i": n, "t": round(now - t0, 3), "seg": seg, "seg_start": seg != last_seg}
            if first_at is None:
                first_at = now - t0
                meta["first"] = True
            last_seg = seg
            audio = np.asarray(chunk, dtype=np.float32)
            if seg_end and seg < len(segs) - 1:  # natural pause before the next sentence / clause
                gap = np.zeros(int(_pause_after(segs[seg]) * TTS_SR), dtype=np.float32)
                audio = np.concatenate([audio, gap])
                st["play_end"] += len(gap) / TTS_SR
                generated += len(gap) / TTS_SR
            yield _payload(audio, engine="indic-parler-tts", **meta)
    total = time.time() - t0
    yield {"done": True, "engine": "indic-parler-tts", "first_audio_seconds": round(first_at or total, 3), "total_seconds": round(total, 3),
           "audio_seconds": round(generated, 3), "rtf": round(total / max(generated, 1e-6), 3), "chunks": n,
           "segments": segs, "groups": st["groups"]}


def _legacy_stream(text: str, lang: str, description: str):
    """Previous implementation (one sentence at a time, batch 1); used only as a fallback."""
    description = _describe(lang, description)
    t0, n, generated = time.time(), 0, 0.0
    for sentence in _split_sentences(text):
        d, p = _tokenize_tts(sentence, description, padded=False)
        streamer = ParlerTTSStreamer(tts, device=DEVICE, play_steps=STREAM_OPTS["play_steps"])
        th = threading.Thread(target=lambda: tts.generate(
            input_ids=d.input_ids, attention_mask=d.attention_mask, prompt_input_ids=p.input_ids,
            prompt_attention_mask=p.attention_mask, streamer=streamer), daemon=True)
        th.start()
        for chunk in streamer:
            if chunk.shape[0] == 0:
                break
            generated += len(chunk) / TTS_SR
            n += 1
            yield _payload(np.asarray(chunk, dtype=np.float32), i=n, t=round(time.time() - t0, 3),
                           engine="indic-parler-tts")
        th.join()
    total = time.time() - t0
    yield {"done": True, "total_seconds": round(total, 3), "audio_seconds": round(generated, 3),
           "rtf": round(total / max(generated, 1e-6), 3), "chunks": n, "fallback": True, "engine": "indic-parler-tts"}


@torch.inference_mode()
def _mms_wave(text: str, lang: str) -> np.ndarray:
    tok, model = MMS[lang]
    inputs = tok(text, return_tensors="pt").to(DEVICE)
    torch.manual_seed(0)  # VITS samples noise: fixed seed = the same sentence always sounds the same
    return model(**inputs).waveform[0].float().cpu().numpy()


def _mms_stream(text: str, lang: str):
    sr = MMS[lang][1].config.sampling_rate
    t0, n, total = time.time(), 0, 0.0
    first = None
    sents = _split_sentences(text) or [text]
    for k, sent in enumerate(sents):
        audio = _trim(_mms_wave(sent, lang), sr)
        if k < len(sents) - 1:
            audio = np.concatenate([audio, np.zeros(int(_pause_after(sent) * sr), dtype=np.float32)])
        if first is None:
            first = time.time() - t0
        n += 1
        total += len(audio) / sr
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        yield {"sr": sr, "pcm": base64.b64encode(pcm).decode("ascii"), "audio_seconds": round(len(audio) / sr, 3),
               "i": n, "first": n == 1, "engine": "mms-tts"}
    yield {"done": True, "first_audio_seconds": round(first or 0, 3), "total_seconds": round(time.time() - t0, 3),
           "audio_seconds": round(total, 3), "chunks": n, "engine": "mms-tts"}


# ---------------------------------------------------------------- which voice may speak which language
# Rule: a language is voiced only by an engine that officially speaks it. No voice -> an error and silence (the app
# shows the text); never another language's voice. Each engine has an explicit allow-list:
#   Indic Parler-TTS: the 21 languages on its model card ("officially supported").
PARLER_LANGS = {"as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "mai", "ml", "mni", "mr", "ne", "or", "sa",
                "sat", "sd", "ta", "te", "ur"}
MMS_DEFAULT = {"tl", "sw"}  # MMS-TTS voices by default; its Arabic voice only when engine="mms" is asked for
ENGINES = ("parler", "supertonic", "mms", "piper")


def _can(engine: str, lang: str) -> bool:
    return {"parler": lang in PARLER_LANGS, "supertonic": ST is not None and lang in ST_LANGS,
            "mms": lang in MMS, "piper": lang in PIPER}.get(engine, False)


def _engine_for(lang: str, engine: str = ""):
    """The engine that voices `lang`, or None (-> HTTP 422 / gr.Error, no audio). A requested `engine` that cannot
    speak `lang` is None too: never silently swapped for another engine."""
    engine = (engine or "").strip().lower()
    if engine:
        return engine if _can(engine, lang) else None
    if lang in PIPER:
        return "piper"
    if lang in MMS_DEFAULT:
        return "mms" if lang in MMS else None
    if _can("supertonic", lang) and lang not in ST_NOT_DEFAULT:
        return "supertonic"
    if lang in PARLER_LANGS:  # incl. English if Supertonic failed to load: Parler's English voice, still English
        return "parler"
    return None


def voices() -> dict:
    """Default engine per voiced language (what the app may ask for), plus every engine's allow-list."""
    langs = PARLER_LANGS | set(ST_LANGS) | MMS_DEFAULT | set(PIPER)
    default = {c: e for c in sorted(langs) if (e := _engine_for(c))}
    return {"default": default,
            "engines": {e: sorted(c for c in langs | set(MMS) if _can(e, c)) for e in ENGINES}}


# Text/language guard: a translation that came back in another script (English text for a Nepali patient, Hindi
# text for a Bengali patient, Arabic for Urdu…) is never spoken. Unicode ranges only; cheap.
_SCRIPT_RANGES = {
    "latin": ((0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F), (0x1E00, 0x1EFF), (0x2C60, 0x2C7F), (0xA720, 0xA7FF),
              (0xFF21, 0xFF3A), (0xFF41, 0xFF5A)),
    "devanagari": ((0x900, 0x97F), (0xA8E0, 0xA8FF)), "bengali": ((0x980, 0x9FF),), "gurmukhi": ((0xA00, 0xA7F),),
    "gujarati": ((0xA80, 0xAFF),), "odia": ((0xB00, 0xB7F),), "tamil": ((0xB80, 0xBFF),),
    "telugu": ((0xC00, 0xC7F),), "kannada": ((0xC80, 0xCFF),), "malayalam": ((0xD00, 0xD7F),),
    "arabic": ((0x600, 0x6FF), (0x750, 0x77F), (0x8A0, 0x8FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)),
    "cyrillic": ((0x400, 0x52F), (0x1C80, 0x1C8F)), "greek": ((0x370, 0x3FF), (0x1F00, 0x1FFF)),
    "georgian": ((0x10A0, 0x10FF), (0x1C90, 0x1CBF), (0x2D00, 0x2D2F)),
    "hangul": ((0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xAC00, 0xD7FF)),
    "kana": ((0x3040, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F)),
    "han": ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)),
    "olchiki": ((0x1C50, 0x1C7F),), "meetei": ((0xABC0, 0xABFF),),
}
_LATIN_LANGS = {"en", "tl", "sw", "es", "fr", "pt", "id", "tr", "vi", "de", "it", "nl", "pl", "ro", "cs", "sk", "hu",
                "hr", "sl", "sv", "da", "fi", "et", "lv", "lt"}
LANG_SCRIPTS = {
    **{c: {"latin"} for c in _LATIN_LANGS},
    **{c: {"devanagari"} for c in ("ne", "hi", "mr", "sa", "kok", "mai", "doi", "brx")},
    "bn": {"bengali"}, "as": {"bengali"}, "mni": {"bengali", "meetei"}, "sat": {"olchiki", "devanagari"},
    "ar": {"arabic"}, "ur": {"arabic"}, "sd": {"arabic", "devanagari"},
    "gu": {"gujarati"}, "kn": {"kannada"}, "or": {"odia"}, "ta": {"tamil"}, "te": {"telugu"}, "ml": {"malayalam"},
    "pa": {"gurmukhi"}, "ko": {"hangul", "han"}, "ja": {"kana", "han"}, "ka": {"georgian"},
    "ru": {"cyrillic"}, "uk": {"cyrillic"}, "bg": {"cyrillic"}, "el": {"greek"},
}
_URDU_ONLY = set("ٹڈڑںےۓھہ")             # letters Arabic never uses
_URDU_OR_PERSIAN = _URDU_ONLY | set("یکگپچژ")  # Urdu text always has some of these (Arabic uses ي ك instead)


def _script_of(ch: str):
    import unicodedata  # noqa: PLC0415
    cat = unicodedata.category(ch)
    if not (cat[0] in "LM" or (cat == "Nd" and ord(ch) > 0x7F)):
        return None  # spaces, punctuation, ASCII digits, symbols: neutral
    o = ord(ch)
    for name, ranges in _SCRIPT_RANGES.items():
        if any(a <= o <= b for a, b in ranges):
            return name
    return "other"


# English words that no other Latin-script patient language uses as an ordinary word (so "for" (Danish), "do"
# (Portuguese), "doctor" (Spanish), "pain" (French), "may" (Tagalog), "is"/"in" (Dutch) are left out).
_EN_WORDS = {"the", "you", "your", "and", "have", "has", "take", "with", "this", "that", "please", "what", "does",
             "any", "there", "should", "would", "about", "after", "before", "times", "how", "when", "they", "been"}
# For English itself: a sentence of 6+ words without a single one of these is not English.
_EN_COMMON = _EN_WORDS | {"a", "i", "is", "in", "of", "to", "it", "my", "me", "for", "on", "at", "was", "be", "are",
                          "not", "no", "yes", "do", "he", "she", "we", "his", "her", "day", "days", "since", "pain",
                          "or", "if", "can", "will", "an", "so", "but", "from", "by", "as", "did", "am"}
# Everyday function words of the Latin-script patient languages whose MT output may be Taglish/mixed: any of them
# means the sentence is (also) in that language, so English loanwords alone don't silence it.
_MARKERS = {"tl": {"ang", "ng", "sa", "na", "po", "mga", "ito", "ay", "ka", "ko", "mo", "nang", "kayo", "ninyo", "siya",
                   "hindi", "opo", "araw", "gamot", "inyong", "niyo", "natin", "lang", "din", "rin"},
            "sw": {"na", "ya", "wa", "kwa", "ni", "za", "la", "hii", "je", "mara", "siku", "dawa", "una", "kila", "hapana",
                   "ndiyo", "sana", "yako", "wako", "baada", "kabla"}}
_UNITS = {"mg", "mcg", "ml", "kg", "iu", "mmol", "mmhg", "cm", "mm", "units", "unit", "tab", "tabs", "bd", "tds", "od"}
_JOINERS = re.compile(r"(?<=[^\W\d_])[-'’](?=[^\W\d_])")  # "co-amoxiclav", "don't": one word


def _script_runs(text: str) -> list:
    """Words as runs of consecutive characters in one script: [(script, run_text)]. Neutral characters (spaces,
    punctuation, ASCII digits) end a run. Latin dose units ("500 mg") and single Latin letters are ignored: every
    language writes them in Latin."""
    runs, cur, buf = [], None, []
    for ch in _JOINERS.sub("", text) + " ":
        s = _script_of(ch)
        if s != cur and buf:
            runs.append((cur, "".join(buf)))
            buf = []
        cur = s
        if s is not None:
            buf.append(ch)
    return [(s, w) for s, w in runs if not (s == "latin" and (len(w) < 2 or w.lower() in _UNITS))]


def script_problem(text: str, lang: str):
    """None when `text` is plausibly written in `lang`'s script, else a short reason. Works on words (script runs),
    not characters, so drug names in Latin inside a Nepali sentence ("Co-amoxiclav 625 mg, दिनमा ३ पटक") pass, while
    a sentence in the wrong script fails: > 40% of the words must be in the language's script (>= 50% for languages
    written in Latin, since every language borrows Latin drug names but not the reverse)."""
    want = LANG_SCRIPTS.get(lang)
    if want is None:
        return None  # no script on record: routing already restricts to voiced languages
    runs = _script_runs(text)
    if not runs:
        return None  # digits/punctuation/units only: the voice reads them in its own language
    own = sum(1 for s, _ in runs if s in want)
    if own / len(runs) < (0.5 if want == {"latin"} else 0.4):
        seen = {}
        for s, _ in runs:
            seen[s] = seen.get(s, 0) + 1
        return f"text is not in {lang} script (word scripts: {seen})"
    if want == {"latin"}:  # same script; an untranslated English sentence for a Filipino/Swahili/... voice, or vice versa
        words = [w.lower() for s, w in runs if s == "latin"]
        hits = sum(w in _EN_WORDS for w in words)
        if (lang != "en" and hits >= 3 and hits >= 0.25 * len(words)
                and not any(w in _MARKERS.get(lang, ()) for w in words)):
            return f"text looks like English, not {lang}"
        if lang == "en" and len(words) >= 6 and not any(w in _EN_COMMON for w in words):
            return "text does not look like English"
    if lang in ("ar", "ur"):  # same script; tell them apart by the letters only one of them uses
        arabic = [c for c in text if _script_of(c) == "arabic"]
        if lang == "ar" and sum(c in _URDU_ONLY for c in arabic) >= 2:
            return "text looks like Urdu, not Arabic"
        if lang == "ur" and len(arabic) >= 15 and not any(c in _URDU_OR_PERSIAN for c in arabic):
            return "text looks like Arabic, not Urdu"
    return None


class NoVoice(Exception):
    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason  # "lang" (no voice for this language / engine) or "script" (text in another script)


def _check_voice(text: str, lang: str, engine: str = "") -> str:
    """The engine to use, or NoVoice. Run before ANY audio is produced."""
    eng = _engine_for(lang, engine)
    if eng is None:
        msg = f"no voice for {lang or '(no language)'}" + (f" with engine {engine}" if engine else "")
        raise NoVoice(msg, "lang")
    problem = script_problem(text, lang)
    if problem:
        raise NoVoice(problem, "script")
    return eng


def _piper_wave(text: str, lang: str) -> np.ndarray:
    v = PIPER[lang]
    chunks = list(v.synthesize(text, syn_config=SynthesisConfig(length_scale=PIPER_RATE)))
    return np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32) if chunks else np.zeros(1, np.float32)


def _piper_stream(text: str, lang: str):
    sr = PIPER[lang].config.sample_rate
    t0, n, total, first = time.time(), 0, 0.0, None
    sents = _split_sentences(text) or [text]
    for k, sent in enumerate(sents):
        audio = _trim(_piper_wave(sent, lang), sr)
        if k < len(sents) - 1:
            audio = np.concatenate([audio, np.zeros(int(_pause_after(sent) * sr), dtype=np.float32)])
        first = first if first is not None else time.time() - t0
        n += 1
        total += len(audio) / sr
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        yield {"sr": sr, "pcm": base64.b64encode(pcm).decode("ascii"), "audio_seconds": round(len(audio) / sr, 3),
               "i": n, "first": n == 1, "engine": "piper"}
    yield {"done": True, "first_audio_seconds": round(first or 0, 3), "total_seconds": round(time.time() - t0, 3),
           "audio_seconds": round(total, 3), "chunks": n, "engine": "piper"}


def _st_stream(text: str, lang: str):
    t0, n, total, first = time.time(), 0, 0.0, None
    sents = _split_sentences(text) or [text]
    for k, sent in enumerate(sents):
        audio = _trim(ST.synth(sent, lang, steps=8, speed=ST_SPEED), ST.sr)
        if k < len(sents) - 1:
            audio = np.concatenate([audio, np.zeros(int(_pause_after(sent) * ST.sr), dtype=np.float32)])
        first = first if first is not None else time.time() - t0
        n += 1
        total += len(audio) / ST.sr
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        yield {"sr": ST.sr, "pcm": base64.b64encode(pcm).decode("ascii"), "audio_seconds": round(len(audio) / ST.sr, 3),
               "i": n, "first": n == 1, "engine": "supertonic-3"}
    yield {"done": True, "first_audio_seconds": round(first or 0, 3), "total_seconds": round(time.time() - t0, 3),
           "audio_seconds": round(total, 3), "chunks": n, "engine": "supertonic-3"}


def _voice_or_gr_error(text: str, lang: str, engine: str = "") -> str:
    if not text or not text.strip():
        raise gr.Error("No text received.")
    try:
        return _check_voice(text, lang, engine)
    except NoVoice as e:
        raise gr.Error(str(e)) from None


def speak_stream(text: str, lang: str = "ne", description: str = "", engine: str = ""):
    """Yield {"sr", "pcm" (base64 int16 LE mono), ...} chunks; the last item has "done": true.
    A language without a voice of its own, or text in another script, raises before any audio (gr.Error)."""
    eng = _voice_or_gr_error(text, lang, engine)
    if eng == "piper":
        yield from _piper_stream(text, lang)
        return
    if eng == "supertonic":
        yield from _st_stream(text, lang)
        return
    if eng == "mms":
        yield from _mms_stream(text, lang)
        return
    started = False
    try:
        for item in _speak_stream(text, lang, description, {}):
            started = True
            yield item
    except Exception as e:  # noqa: BLE001 - keep the demo talking
        if started:
            raise
        # Same engine, same language, same speaker description: only the batching differs.
        print(f"batched stream failed, falling back to unbatched Parler ({lang}): {type(e).__name__}: {e}", flush=True)
        yield from _legacy_stream(text, lang, description)


def speak_stream_opts(text: str, lang: str = "ne", description: str = "", opts_json: str = "{}"):
    """Same as /speak_stream with tunable STREAM_OPTS (JSON), for latency experiments (Parler only)."""
    _voice_or_gr_error(text, lang, "parler")
    yield from _speak_stream(text, lang, description, json.loads(opts_json or "{}"))


@torch.inference_mode()
def tts_probe(opts_json: str = "{}") -> dict:
    """Seconds per decoding step vs batch size, plus an ASR round trip of every batched segment."""
    o = json.loads(opts_json or "{}")
    sizes = o.get("sizes", [1, 2, 4, 8])
    texts = o.get("texts") or _split_sentences(BENCH_SENTENCE_NE) + [BENCH_SENTENCE_NE_Q]
    out = {"tau_ms_by_batch": {}, "segments": []}
    for B in sizes:
        segs = [texts[i % len(texts)] for i in range(B)]
        st = {"play_end": 0.0, "groups": []}
        audio = {}
        for _, b, chunk, _end in _stream_group(segs, "ne", "", {**STREAM_OPTS, "margin": 0.0}, st):
            audio.setdefault(b, []).append(chunk)
        out["tau_ms_by_batch"][str(B)] = st["groups"][0]
        if B == max(sizes):
            for b, seg in enumerate(segs):
                wav = torch.from_numpy(np.concatenate(audio.get(b, [np.zeros(1, np.float32)]))).unsqueeze(0)
                r = _transcribe_wave(wav, TTS_SR, "ne")
                out["segments"].append({"text": seg, "asr": r["text"], "audio_seconds": r["audio_seconds"]})
    return out


def speak(text: str, lang: str = "ne", description: str = ""):
    eng = _voice_or_gr_error(text, lang)
    if eng == "piper":
        audio = np.concatenate([_piper_wave(s_, lang) for s_ in (_split_sentences(text) or [text])])
        return (PIPER[lang].config.sample_rate, audio), {"engine": "piper"}
    if eng == "supertonic":
        audio = np.concatenate([ST.synth(s_, lang, speed=ST_SPEED) for s_ in (_split_sentences(text) or [text])])
        return (ST.sr, audio), {"engine": "supertonic-3"}
    if eng == "mms":
        audio = np.concatenate([_mms_wave(s_, lang) for s_ in (_split_sentences(text) or [text])])
        return (MMS[lang][1].config.sampling_rate, audio), {"engine": "mms-tts"}
    audio, stats = _speak_array(text, lang, description)
    return (TTS_SR, audio), stats


BENCH_SENTENCE_NE = "नमस्ते। म बयान हुँ। तपाईंको डाक्टरले भनेको कुरा म नेपालीमा भन्छु।"
# "Hello. I am Bayan. I will say what your doctor says in Nepali." (machine draft; verify with a native speaker)


BENCH_SENTENCE_EN = "Do you have any allergies to medicines?"
BENCH_SENTENCE_NE_Q = "तपाईंलाई कुनै औषधिसँग एलर्जी छ?"


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
        "tts_compile": COMPILE_NOTE,
        "model_load_seconds": LOAD_SECONDS,
        "nepali": {"input_text": BENCH_SENTENCE_NE, "tts": tts_ne, "hear": hear_ne},
        "english": {"input_text": BENCH_SENTENCE_EN, "tts": tts_en, "hear": hear_en},
        "nepali_stream": [x for x in speak_stream(BENCH_SENTENCE_NE, "ne") if x.get("done")][0],
    }


def langs() -> list:
    return sorted(asr.language_masks.keys())


# Warm up CUDA kernels / allocator so the first real request is not slow (also primes _TAU).
t = time.time()
try:
    for _ in _speak_stream("नमस्ते। धन्यवाद।", "ne", "", {}):
        pass
    _log(f"TTS warm-up done in {time.time() - t:.1f}s; tau_ms={ {k: round(v * 1000, 2) for k, v in _TAU.items()} }")
except Exception as e:  # noqa: BLE001 - never fail boot because of the warm-up
    _log(f"TTS warm-up failed: {type(e).__name__}: {e}")
_log(f"ready to serve (models {LOAD_SECONDS}s)")

# ---------------------------------------------------------------- UI / API
# delete_cache: synthesised speech and any other cached files are removed every 10 min once 10 min old.
with gr.Blocks(title="Bayan voice worker", delete_cache=(600, 600)) as demo:
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
    with gr.Tab("Speak (streaming)"):
        ss_text = gr.Textbox(label="Text", value=BENCH_SENTENCE_NE)
        ss_lang = gr.Textbox(label="Language code", value="ne")
        ss_desc = gr.Textbox(label="Voice description (optional)")
        ss_btn = gr.Button("Stream")
        ss_out = gr.JSON(label="Chunks (base64 PCM) / final stats")
        ss_btn.click(speak_stream, [ss_text, ss_lang, ss_desc], ss_out, api_name="speak_stream")
    with gr.Tab("Debug"):
        x_text = gr.Textbox(label="Text", value=BENCH_SENTENCE_NE)
        x_lang = gr.Textbox(label="Language code", value="ne")
        x_desc = gr.Textbox(label="Voice description (optional)")
        x_opts = gr.Textbox(label="Stream options (JSON)", value="{}")
        x_btn = gr.Button("Stream with options")
        x_out = gr.JSON()
        x_btn.click(speak_stream_opts, [x_text, x_lang, x_desc, x_opts], x_out, api_name="speak_stream_opts")
        pr_btn = gr.Button("TTS probe (step time vs batch size)")
        pr_out = gr.JSON()
        pr_btn.click(tts_probe, [x_opts], pr_out, api_name="tts_probe")
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

# ---------------------------------------------------------------- fast HTTP API (no Gradio queue / upload / SSE)
# Measured from the main app: /hear via gradio_client took ~2.8 s for 0.1 s of GPU work, and /speak_stream added
# ~1-1.5 s before the first chunk. These plain routes skip the upload + queue + event-stream round trips.
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

GPU_LOCK = threading.Lock()
fast = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@fast.post("/v1/hear")
async def v1_hear(request: Request, sr: int = 48000, lang: str = "", doctor: str = "", role: str = ""):
    """Body: raw mono int16 little-endian PCM at `sr` Hz. Returns the same dict as /hear.
    `lang` (the patient's language) is required: no default language is ever guessed."""
    body = await request.body()
    if not body:
        return JSONResponse({"error": "empty audio"}, status_code=400)
    if not _asr_engine(lang):
        return JSONResponse({"error": f"no speech recognition for {lang or '(no language)'}"}, status_code=422)
    if doctor and doctor not in DOCTOR_LANGS:
        return JSONResponse({"error": f"doctor language must be one of {DOCTOR_LANGS}"}, status_code=422)
    pcm = np.frombuffer(body, dtype="<i2").astype(np.float32) / 32768.0
    wav = torch.from_numpy(pcm).unsqueeze(0)

    def run():
        with GPU_LOCK:
            return _hear_wave(wav, sr, lang, doctor, role)

    import anyio  # noqa: PLC0415 - shipped with FastAPI
    return JSONResponse(await anyio.to_thread.run_sync(run))


@fast.post("/v1/speak_stream")
async def v1_speak_stream(request: Request):
    """Body: {"text", "lang", "description", "engine"?}. Streams NDJSON: the same chunk dicts as /speak_stream.
    HTTP 422 {"error", "reason": "lang" | "script"} and no audio when `lang` has no voice of its own (or the requested
    engine cannot speak it), or when the text is not written in `lang`'s script."""
    req = await request.json()
    text, lang, desc = (req.get("text") or "").strip(), (req.get("lang") or "").strip(), req.get("description") or ""
    engine = req.get("engine") or ""
    if not text:
        return JSONResponse({"error": "empty text"}, status_code=400)
    try:
        eng = _check_voice(text, lang, engine)
    except NoVoice as e:
        print(f"[speak] refused lang={lang!r} engine={engine!r}: {e} | {text[:60]!r}", flush=True)
        return JSONResponse({"error": str(e), "reason": e.reason, "lang": lang}, status_code=422)

    def gen():
        if eng in ("supertonic", "piper"):  # CPU: no need to wait for the GPU
            for item in speak_stream(text, lang, desc, engine):
                yield json.dumps(item) + "\n"
            return
        with GPU_LOCK:
            for item in speak_stream(text, lang, desc, engine):
                yield json.dumps(item) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


@fast.get("/v1/ping")
def v1_ping():
    return {"ok": True}


@fast.get("/v1/voices")
def v1_voices():
    """Which engine voices which language (the app's WORKER_TTS_LANGS must match "default")."""
    return voices()


app = gr.mount_gradio_app(fast, demo, path="/")

if __name__ == "__main__":
    import uvicorn  # noqa: PLC0415
    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="warning")
