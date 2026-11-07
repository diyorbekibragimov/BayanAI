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


@torch.inference_mode()
def _hear_wave(wav: torch.Tensor, sr: int, patient_lang: str) -> dict:
    """Decide doctor vs patient for one utterance, then transcribe it with the right model."""
    t_all = time.time()
    wav16 = _to_mono16k(wav, sr)
    feats = w_proc(wav16.squeeze(0).numpy(), sampling_rate=ASR_SR, return_tensors="pt").input_features
    feats = feats.to(DEVICE, W_DTYPE)

    # 1) Restricted language ID with VoxLingua107: score only {en, ar, patient_lang}.
    t = time.time()
    cands = [c for c in (*DOCTOR_LANGS, patient_lang) if c in VOX_INDEX]
    out_prob = lid_model.classify_batch(wav16.to(DEVICE))[0][0]  # log-likelihoods over 107 languages
    probs = torch.softmax(out_prob[[VOX_INDEX[c] for c in cands]].float(), dim=-1).tolist()
    lid = dict(zip(cands, [round(p, 4) for p in probs]))
    lid_seconds = time.time() - t
    # Whisper's opinion, for diagnostics only.
    w_cands = [c for c in (*DOCTOR_LANGS, patient_lang) if _whisper_lang_id(c) is not None]
    w_logits = w_model(
        input_features=feats, decoder_input_ids=torch.tensor([[_W_SOT]], device=DEVICE)
    ).logits[0, -1]
    w_probs = torch.softmax(w_logits[[_whisper_lang_id(c) for c in w_cands]].float(), dim=-1).tolist()
    lid_whisper = dict(zip(w_cands, [round(p, 4) for p in w_probs]))
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
    return _hear_wave(wav, sr, patient_lang)


def transcribe(audio_path: str, lang: str = "ne", decoding: str = "ctc") -> dict:
    if not audio_path:
        raise gr.Error("No audio received.")
    wav, sr = _load_and_delete(audio_path)
    return _transcribe_wave(wav, sr, lang, decoding)


@torch.inference_mode()
def _speak_array(text: str, lang: str = "ne", description: str = ""):
    description = description or DEFAULT_DESCRIPTIONS.get(lang, GENERIC_DESCRIPTION)
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
    description = description or DEFAULT_DESCRIPTIONS.get(lang, GENERIC_DESCRIPTION)
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
            yield _payload(np.asarray(chunk, dtype=np.float32), **meta)
    total = time.time() - t0
    yield {"done": True, "first_audio_seconds": round(first_at or total, 3), "total_seconds": round(total, 3),
           "audio_seconds": round(generated, 3), "rtf": round(total / max(generated, 1e-6), 3), "chunks": n,
           "segments": segs, "groups": st["groups"]}


def _legacy_stream(text: str, lang: str, description: str):
    """Previous implementation (one sentence at a time, batch 1); used only as a fallback."""
    description = description or DEFAULT_DESCRIPTIONS.get(lang, GENERIC_DESCRIPTION)
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
            yield _payload(np.asarray(chunk, dtype=np.float32), i=n, t=round(time.time() - t0, 3))
        th.join()
    total = time.time() - t0
    yield {"done": True, "total_seconds": round(total, 3), "audio_seconds": round(generated, 3),
           "rtf": round(total / max(generated, 1e-6), 3), "chunks": n, "fallback": True}


def speak_stream(text: str, lang: str = "ne", description: str = ""):
    """Yield {"sr", "pcm" (base64 int16 LE mono), ...} chunks; the last item has "done": true."""
    if not text or not text.strip():
        raise gr.Error("No text received.")
    started = False
    try:
        for item in _speak_stream(text, lang, description, {}):
            started = True
            yield item
    except Exception as e:  # noqa: BLE001 - keep the demo talking
        if started:
            raise
        print(f"batched stream failed, falling back: {type(e).__name__}: {e}", flush=True)
        yield from _legacy_stream(text, lang, description)


def speak_stream_opts(text: str, lang: str = "ne", description: str = "", opts_json: str = "{}"):
    """Same as /speak_stream with tunable STREAM_OPTS (JSON), for latency experiments."""
    if not text or not text.strip():
        raise gr.Error("No text received.")
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
    if not text or not text.strip():
        raise gr.Error("No text received.")
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

if __name__ == "__main__":
    demo.launch()
