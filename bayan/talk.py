"""Bayan AI · talk loop (foreground).

One utterance:  audio ─► voice worker /hear (who spoke? + ASR)
                      ─► gpt-oss-120b (translate + drugs with intent / allergies / tests, JSON schema)
                      ─► bayan.brain prescription gate (rule engine, in bayan.consult)
                      ─► TTS in the listener's language (worker /speak_stream: patient and doctor voices)
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import threading

import numpy as np
import soundfile as sf

from bayan.brain import llm
from bayan.langs import MORE

HF_TOKEN = os.environ.get("HF_TOKEN")
WORKER_SPACE = os.environ.get("BAYAN_WORKER", "dullgrey/team-qh-129-bayan-voice")
WORKER_URL = os.environ.get("BAYAN_WORKER_URL", "https://" + WORKER_SPACE.replace("/", "-").replace("_", "-").lower() + ".hf.space")
LLM_PROVIDER = os.environ.get("BAYAN_LLM_PROVIDER", "cerebras")

LANG_NAMES = {
    "en": "English", "ar": "Arabic", "ne": "Nepali", "hi": "Hindi", "ur": "Urdu",
    "bn": "Bengali", "ml": "Malayalam", "tl": "Filipino (Tagalog)", "ta": "Tamil", "te": "Telugu",
    "sw": "Swahili", "ko": "Korean",
    **{code: v["en"] for code, v in MORE.items()},
}
# Voices on the worker: Indic Parler-TTS (ne hi ur bn ml ta te), MMS-TTS (tl Filipino, sw Swahili, ar Arabic for the
# doctor) and Supertonic (ko). Chunks carry their own sample rate (Parler 44.1 kHz, MMS 16 kHz).
# The doctor hears the patient too: English and Arabic doctor voices (Supertonic on the worker's CPU).
WORKER_TTS_LANGS = {"ne", "hi", "ur", "bn", "ml", "ta", "te", "tl", "sw", "ko", "ar", "en", *MORE}


# ------------------------------------------------------------------ clients (lazy)
_http = None
_http_lock = threading.Lock()


def http():
    """Shared keep-alive HTTPS client for the worker's fast /v1 API (skips Gradio upload + queue + SSE)."""
    global _http
    with _http_lock:
        if _http is None:
            import httpx
            _http = httpx.Client(base_url=WORKER_URL, headers={"Authorization": f"Bearer {HF_TOKEN}"},
                                 timeout=httpx.Timeout(30.0, connect=10.0),
                                 limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=120))
        return _http



_worker = None
_worker_lock = threading.Lock()


def worker():
    """gradio_client for the private GPU voice worker (wakes it if asleep)."""
    global _worker
    with _worker_lock:
        if _worker is None:
            from gradio_client import Client
            _worker = Client(WORKER_SPACE, hf_token=HF_TOKEN, verbose=False)
        return _worker


# ------------------------------------------------------------------ pipeline steps
def hear(sr: int, audio: np.ndarray, patient_lang: str, doctor_lang: str = "en", role: str = "") -> dict:
    """Who is speaking + transcript. Fast path: raw PCM to the worker's /v1/hear (~0.3 s round trip
    instead of ~2.8 s through gradio_client). Falls back to the Gradio API only when the fast API is missing (404/405);
    a worker that is down or rebooting fails fast instead of hanging in gradio_client."""
    a = np.asarray(audio).reshape(-1)
    if a.dtype != np.int16:
        a = (np.clip(a.astype(np.float32), -1, 1) * 32767).astype(np.int16)
    try:
        r = http().post("/v1/hear", params={"sr": int(sr), "lang": patient_lang, "doctor": doctor_lang, **({"role": role} if role else {})}, content=a.astype("<i2").tobytes(),
                        headers={"Content-Type": "application/octet-stream"})
        if r.status_code not in (404, 405):
            r.raise_for_status()
            return r.json()
        print(f"[hear fast] HTTP {r.status_code}: no /v1 API on the worker; using the Gradio API", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[hear fast] {type(e).__name__}: {e}", flush=True)
        raise
    from gradio_client import handle_file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, a, sr)
        path = f.name
    try:
        return worker().predict(handle_file(path), patient_lang, api_name="/hear")
    finally:
        os.unlink(path)


TRANSLATE_SYSTEM = """You are Bayan, a professional medical interpreter in a clinic in Qatar.
Translate the speaker's words faithfully: never add, omit, soften or explain anything. Keep every number,
dose, unit, frequency and drug name exact. Use simple, respectful, everyday wording that a patient with
little schooling understands. Write the translation in the target language's native script.
Earlier turns, when given, are context only (pronouns, short answers such as "yes"): translate only the utterance.

Return ONLY a JSON object with these keys:
  "translation": the utterance in the TARGET language,
  "english": a literal English rendering of what the speaker said,
  "drugs": every medicine the speaker names: [{"name": "<generic name, lowercase>", "intent": "prescribe" | "stop" | "mention",
           "dose_mg": <number>, "frequency_per_day": <number>, "dose": "<dose as said>"}]
     intent "prescribe": the doctor gives, starts, continues or proposes it now ("take paracetamol 1 g", "I'll give you amoxicillin");
     "stop": the doctor withdraws, stops or rules it out ("no amoxicillin", "stop the ibuprofen", "let's not use amoxicillin");
     "mention": anything else (a question about it, a patient naming it, a past medicine, an allergy).
     dose_mg: the dose in mg (1 g -> 1000; a bare number after the drug name, "amoxicillin 500", is mg).
     frequency_per_day: "three times a day" -> 3, "twice daily" -> 2, "every 8 hours" -> 3.
     Leave out dose_mg, frequency_per_day or dose when they were not said; never guess.
  "allergies": allergies or bad reactions to medicines the speaker reports: [{"substance": "<lowercase drug or class>", "reaction": "<as said>"}],
  "tests": tests or investigations the doctor orders or reports today, as short English names: ["ECG", "troponin blood test"]
Use [] when there are none."""

# Without a schema gpt-oss sometimes answers with fenced or invalid JSON (measured live).
TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "translation": {"type": "string"},
        "english": {"type": "string"},
        "drugs": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "intent": {"type": "string", "enum": ["prescribe", "stop", "mention"]},
            "dose_mg": {"type": "number"},
            "frequency_per_day": {"type": "number"},
            "dose": {"type": "string"}}, "required": ["name", "intent"]}},
        "allergies": {"type": "array", "items": {"type": "object", "properties": {
            "substance": {"type": "string"}, "reaction": {"type": "string"}}, "required": ["substance"]}},
        "tests": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["translation", "english", "drugs", "allergies", "tests"],
}
INTENTS = ("prescribe", "stop", "mention")


def _clean_drugs(items) -> list[dict]:
    out = []
    for d in items if isinstance(items, list) else []:
        if not isinstance(d, dict) or not str(d.get("name") or "").strip():
            continue
        d = dict(d)
        d["name"] = str(d["name"]).strip().lower()
        intent = str(d.get("intent") or "").strip().lower()
        d["intent"] = intent if intent in INTENTS else "prescribe"   # unknown intent: holding is the safe default
        out.append(d)
    return out


def translate(text: str, role: str, src: str, tgt: str, context: list[str] | None = None, hint: str = "") -> dict:
    """One schema'd gpt-oss-120b call: {"translation", "english", "drugs" (with intent / dose_mg /
    frequency_per_day), "allergies", "tests"}. `context` = a few earlier transcript lines (English);
    `hint` = a note for the interpreter (e.g. a cultural idiom to keep as said)."""
    ctx = "\n".join(c for c in (context or []) if c)
    user = (
        (f"Earlier turns (context only):\n{ctx}\n\n" if ctx else "")
        + f"Speaker: {'doctor' if role == 'doctor' else 'patient'}\n"
        f"Source language: {LANG_NAMES.get(src, src)}\nTarget language: {LANG_NAMES.get(tgt, tgt)}\n"
        + (f"Note for the interpreter: {hint}\n" if hint else "")
        + f"Utterance: {text}"
    )
    data = llm.chat_json(TRANSLATE_SYSTEM, user, schema=TRANSLATE_SCHEMA, max_tokens=700, reasoning="low",
                         provider=LLM_PROVIDER)
    data.setdefault("translation", "")
    data.setdefault("english", text if src == "en" else "")
    for k in ("drugs", "allergies", "tests"):
        if not isinstance(data.get(k), list):
            data[k] = []
    data["translation"] = str(data.get("translation") or "")
    data["english"] = str(data.get("english") or "")
    data["drugs"] = _clean_drugs(data["drugs"])
    data["allergies"] = [a for a in data["allergies"] if isinstance(a, dict) and str(a.get("substance") or "").strip()]
    return data


_SENT_SPLIT = re.compile(r"(?<=[।.!?؟])\s+")


def split_sentences(text: str, max_chars: int = 160) -> list[str]:
    """Short chunks so the first one can play while the next is synthesised."""
    out = []
    for part in _SENT_SPLIT.split(text.strip()):
        part = part.strip()
        while len(part) > max_chars:  # very long sentence: cut at the last comma/space
            cut = max(part.rfind(",", 0, max_chars), part.rfind(" ", 0, max_chars))
            cut = cut if cut > 20 else max_chars
            out.append(part[:cut].strip())
            part = part[cut:].strip(" ,")
        if part:
            out.append(part)
    return out


def _stream_worker_tts(text: str, lang: str, description: str = ""):
    """Stream patient-language speech from the worker: ~0.5 s chunks, generated continuously
    across sentences, with a start buffer sized so playback never overtakes generation.
    Fast path: NDJSON stream from /v1/speak_stream; falls back to the Gradio API if it fails before any audio."""
    import base64
    started = False
    try:
        with http().stream("POST", "/v1/speak_stream", json={"text": text, "lang": lang, "description": description}) as r:
            if r.status_code in (404, 405):
                raise LookupError(f"no /v1 API on the worker (HTTP {r.status_code})")
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                out = json.loads(line)
                if out.get("done") or not out.get("pcm"):
                    continue
                started = True
                yield out["sr"], np.frombuffer(base64.b64decode(out["pcm"]), dtype="<i2").astype(np.float32) / 32767.0
        return
    except Exception as e:  # noqa: BLE001
        if started or not isinstance(e, LookupError):
            raise  # mid-stream, or the worker is down/rebooting: fail fast (text-only), never hang in gradio_client
        print(f"[speak fast] {type(e).__name__}: {e}; falling back to Gradio API", flush=True)
    job = worker().submit(text, lang, description, api_name="/speak_stream")
    for out in job:
        if not isinstance(out, dict) or out.get("done") or not out.get("pcm"):
            continue
        pcm = np.frombuffer(base64.b64decode(out["pcm"]), dtype="<i2").astype(np.float32) / 32767.0
        yield out["sr"], pcm


def speak_chunks(text: str, lang: str, description: str = ""):
    """Yield (sample_rate, float32 array) chunks; yields nothing if no voice for this language yet."""
    if lang in WORKER_TTS_LANGS:
        yield from _stream_worker_tts(text, lang, description)


def speak(text: str, lang: str, description: str = ""):
    """Return (sample_rate, float32 mono array) or None if no voice for this language yet."""
    if not text.strip():
        return None
    if lang in WORKER_TTS_LANGS:
        wav_path, _stats = worker().predict(text, lang, description, api_name="/speak")
        audio, sr = sf.read(wav_path, dtype="float32")
        return sr, audio
    return None
