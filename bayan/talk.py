"""Bayan AI · talk loop (foreground).

One utterance:  audio ─► voice worker /hear (who spoke? + ASR)
                      ─► gpt-oss-120b (translate + drugs with intent / allergies / tests, JSON schema)
                      ─► bayan.brain prescription gate (rule engine, in bayan.consult)
                      ─► bayan.brain coherence check (doctor plans / diagnoses / claims: one fast gpt-oss call)
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
# Exactly the languages the worker voices (its GET /v1/voices "default" table; voice_worker/app.py _engine_for), each
# only with a voice of that language: Indic Parler-TTS for the 21 languages on its card (ne hi ur bn ml ta te…),
# MMS-TTS for tl / sw, Piper for ka, Supertonic 3 for en + ar (the doctor's voices), ko, ja and the European languages.
# Anything else is never sent: silence, and the text stays on screen. The worker re-checks (HTTP 422, no audio) and also
# refuses text that is not in the language's script. Chunks carry their own sample rate (Parler 44.1 kHz, MMS 16 kHz).
_PARLER_LANGS = {"as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "mai", "ml", "mni", "mr", "ne", "or", "sa",
                 "sat", "sd", "ta", "te", "ur"}
_SUPERTONIC_LANGS = {"en", "ko", "ja", "ar", "bg", "cs", "da", "de", "el", "es", "et", "fi", "fr", "hi", "hr", "hu",
                     "id", "it", "lt", "lv", "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "vi"}
WORKER_TTS_LANGS = _PARLER_LANGS | _SUPERTONIC_LANGS | {"tl", "sw", "ka"}


class NoVoice(RuntimeError):
    """The worker will not voice this text: `reason` "lang" (no voice of that language) or "script" (the text is not
    written in that language's script, e.g. an untranslated English sentence for a Nepali patient). Show the text."""

    def __init__(self, message: str, reason: str = "lang", lang: str = ""):
        super().__init__(message)
        self.reason, self.lang = reason, lang


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
    """Who is speaking + transcript: raw PCM to the worker's /v1/hear (~0.3 s round trip). The worker transcribes
    with the model of the forced role's language only (doctor: Whisper with language=doctor_lang; patient: the
    patient language's own model). No Gradio fallback: its /hear takes neither the doctor's language nor the forced
    role, so it could transcribe with the wrong language. Worker down/rebooting -> the exception (the app says so)."""
    a = np.asarray(audio).reshape(-1)
    if a.dtype != np.int16:
        a = (np.clip(a.astype(np.float32), -1, 1) * 32767).astype(np.int16)
    try:
        r = http().post("/v1/hear", params={"sr": int(sr), "lang": patient_lang, "doctor": doctor_lang, **({"role": role} if role else {})}, content=a.astype("<i2").tobytes(),
                        headers={"Content-Type": "application/octet-stream"})
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[hear fast] {type(e).__name__}: {e}", flush=True)
        raise


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
     name: the GENERIC (INN) name, never a brand and never an ordinary English word that sounds like it. Brands:
     Augmentin -> co-amoxiclav (amoxicillin-clavulanate), Amoxil -> amoxicillin, Brufen/Advil/Nurofen -> ibuprofen,
     Panadol/Adol/Tylenol/Calpol/Biogesic -> paracetamol, Voltaren/Cataflam -> diclofenac, Bactrim/Septrin ->
     co-trimoxazole, Ventolin -> salbutamol, Zithromax -> azithromycin, Rocephin -> ceftriaxone, Flagyl ->
     metronidazole, Keflex -> cephalexin, Lasix -> furosemide, Glucophage -> metformin, Tramal -> tramadol.
     An unfamiliar brand: write it as said, lowercase.
     intent "prescribe": the doctor gives, starts, continues or proposes it now ("take paracetamol 1 g", "I'll give you amoxicillin");
     "stop": the doctor withdraws, stops or rules it out ("no amoxicillin", "stop the ibuprofen", "let's not use amoxicillin");
     "mention": anything else (a question about it, a patient naming it, a past medicine, an allergy).
     dose_mg: the dose in mg (1 g -> 1000; a bare number after the drug name, "amoxicillin 500", is mg).
     frequency_per_day: "three times a day" -> 3, "twice daily" -> 2, "every 8 hours" -> 3. Clinical abbreviations:
     OD/QD/nocte/mane -> 1, BD/BID -> 2, TDS/TID -> 3, QDS/QID -> 4, q4h -> 6, q6h -> 4, q8h -> 3, q12h -> 2;
     "as needed, up to 4 times a day" -> 4. One medicine with a regular dose PLUS an extra or as-needed dose
     ("100 mg QDS plus 100 mg at night if needed") is ONE item: dose_mg the single dose, frequency_per_day the
     regular plus the maximum extra doses (4 + 1 = 5), dose as said.
     Leave out dose_mg, frequency_per_day or dose when they were not said; never guess.
  "allergies": allergies or bad reactions to medicines the speaker reports: [{"substance": "<lowercase drug or class>", "reaction": "<as said>"}],
  "tests": tests or investigations the doctor orders or reports today, as short English names: ["ECG", "troponin blood test"],
  "statement": what the speaker's utterance does; when it does several things, the FIRST of these that applies to
     any part of it (a finding followed by a question is "claim", a plan followed by a question is "plan"):
     "plan": gives or changes a treatment, medicine, test, referral, advice or follow-up;
     "diagnosis": says what the problem is or what caused it;
     "claim": states a clinical fact about the patient (a finding, measurement or test result, "you have a fever");
     "question": only asks something;
     "other": greeting, thanks, acknowledgement, small talk, anything else. Always "other" for the patient.
Use [] for drugs, allergies and tests when there are none."""

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
        "statement": {"type": "string", "enum": ["plan", "diagnosis", "claim", "question", "other"]},
    },
    "required": ["translation", "english", "drugs", "allergies", "tests", "statement"],
}
INTENTS = ("prescribe", "stop", "mention")
STATEMENTS = ("plan", "diagnosis", "claim", "question", "other")


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
    frequency_per_day), "allergies", "tests", "statement" (plan | diagnosis | claim | question | other; always
    "other" for the patient)}. `context` = a few earlier transcript lines (English);
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
    try:   # brands / mangled names -> generics the rules know ("augmented" for "Augmentin 625")
        from bayan.brain.vocab import repair_drug_items
        repair_drug_items(data["drugs"], [text, data["english"]])
    except Exception as e:  # noqa: BLE001 - the talk loop must never break on the safety net
        print(f"[translate] drug-name repair failed: {type(e).__name__}: {e}", flush=True)
    data["allergies"] = [a for a in data["allergies"] if isinstance(a, dict) and str(a.get("substance") or "").strip()]
    st = str(data.get("statement") or "").strip().lower()   # what the doctor's sentence does (coherence check routing)
    data["statement"] = st if role == "doctor" and st in STATEMENTS else "other"
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
    """Stream speech in `lang` from the worker's /v1/speak_stream (NDJSON, ~0.5 s chunks). One engine per request,
    always a voice of `lang`. HTTP 422 (no voice for `lang`, or the text is not in its script) -> NoVoice before any
    audio. No fallback to any other API or voice: on any failure the caller shows the text and stays silent."""
    with http().stream("POST", "/v1/speak_stream", json={"text": text, "lang": lang, "description": description}) as r:
        if r.status_code == 422:
            r.read()
            try:
                err = r.json()
            except ValueError:
                err = {"error": r.text[:200]}
            print(f"[speak] no voice: lang={lang} {err.get('error')} | {text[:60]!r}", flush=True)
            raise NoVoice(str(err.get("error") or f"no voice for {lang}"), str(err.get("reason") or "lang"), lang)
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            out = json.loads(line)
            if out.get("done") or not out.get("pcm"):
                continue
            yield out["sr"], np.frombuffer(base64.b64decode(out["pcm"]), dtype="<i2").astype(np.float32) / 32767.0


def speak_chunks(text: str, lang: str, description: str = ""):
    """Yield (sample_rate, float32 array) chunks in `lang`'s own voice; nothing when `lang` has no voice.
    Raises NoVoice (no audio was produced) when the worker refuses the text, e.g. it is not in `lang`'s script."""
    if text and text.strip() and lang in WORKER_TTS_LANGS:
        yield from _stream_worker_tts(text, lang, description)


def speak(text: str, lang: str, description: str = ""):
    """Return (sample_rate, float32 mono array), or None when `lang` has no voice. Same voice and checks as
    speak_chunks (one fast-API stream, collected); NoVoice when the text is not in `lang`'s script."""
    if not text.strip() or lang not in WORKER_TTS_LANGS:
        return None
    try:
        chunks = list(speak_chunks(text, lang, description))
    except NoVoice as e:
        if e.reason == "lang":
            return None
        raise
    if not chunks:
        return None
    sr = chunks[0][0]
    return sr, np.concatenate([c for r, c in chunks if r == sr])
