"""Bayan AI · talk loop (foreground).

One utterance:  audio ─► voice worker /hear (who spoke? + ASR)
                      ─► gpt-oss-120b (translate + extract drugs / allergies, JSON)
                      ─► deterministic held-turn check (allergy vs drug class)
                      ─► TTS in the listener's language (worker /speak or Kokoro)
"""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

HF_TOKEN = os.environ.get("HF_TOKEN")
WORKER_SPACE = os.environ.get("BAYAN_WORKER", "dullgrey/team-qh-129-bayan-voice")
LLM_MODEL = os.environ.get("BAYAN_LLM", "openai/gpt-oss-120b")
LLM_PROVIDER = os.environ.get("BAYAN_LLM_PROVIDER", "cerebras")
DOCTOR_TTS_MODEL = "hexgrad/Kokoro-82M"

LANG_NAMES = {
    "en": "English", "ar": "Arabic", "ne": "Nepali", "hi": "Hindi", "ur": "Urdu",
    "bn": "Bengali", "ml": "Malayalam", "tl": "Filipino (Tagalog)", "ta": "Tamil", "te": "Telugu",
}
# Patient languages Indic Parler-TTS can speak (worker /speak). Others: text only for now.
WORKER_TTS_LANGS = {"ne", "hi", "ur", "bn", "ml", "ta", "te"}

# ------------------------------------------------------------------ safety data (held-turn check)
_RULES = json.loads((Path(__file__).resolve().parent.parent / "data" / "safety_rules.json").read_text())
DRUG_CLASSES: dict[str, list[str]] = _RULES["meta"]["drug_classes"]
BRAND_ALIASES = {k.lower(): v for k, v in _RULES["meta"].get("brand_aliases_examples", {}).items()}
ALG_PEN_01 = next(r for r in _RULES["rules"] if r["id"] == "ALG-PEN-01")


def normalise_drug(name: str) -> str:
    n = (name or "").strip().lower()
    return BRAND_ALIASES.get(n, n)


def classes_of(substance: str) -> set[str]:
    """Classes a drug or allergen belongs to; a class name maps to itself."""
    s = normalise_drug(substance)
    out = {c for c, members in DRUG_CLASSES.items() if s in members}
    if s in DRUG_CLASSES:
        out.add(s)
    if s.endswith("s") and s[:-1] in DRUG_CLASSES:  # "penicillins"
        out.add(s[:-1])
    return out


# ------------------------------------------------------------------ session state
@dataclass
class Session:
    patient_lang: str = "ne"
    doctor_lang: str = "en"
    allergies: list[dict] = field(default_factory=list)  # {"substance", "reaction", "quote"}
    history: list[dict] = field(default_factory=list)    # gr.Chatbot(type="messages") rows
    alerts: list[dict] = field(default_factory=list)


SESSIONS: dict[str, Session] = {}


def session_for(key: str, patient_lang: str) -> Session:
    s = SESSIONS.get(key)
    if s is None or s.patient_lang != patient_lang:
        s = SESSIONS[key] = Session(patient_lang=patient_lang)
    return s


# ------------------------------------------------------------------ clients (lazy)
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


def wake_worker() -> str:
    t = time.time()
    try:
        langs = worker().predict(api_name="/langs")
        return f"✅ Voice worker ready ({time.time() - t:.1f}s) · ASR languages: {len(langs)}"
    except Exception as e:  # noqa: BLE001
        return f"⚠️ Voice worker not ready: {e}"


_llm = None


def llm():
    global _llm
    if _llm is None:
        from huggingface_hub import InferenceClient
        _llm = InferenceClient(provider=LLM_PROVIDER, api_key=HF_TOKEN)
    return _llm


_tts_client = None


def tts_client():
    global _tts_client
    if _tts_client is None:
        from huggingface_hub import InferenceClient
        _tts_client = InferenceClient(provider="auto", api_key=HF_TOKEN)
    return _tts_client


# ------------------------------------------------------------------ pipeline steps
def hear(sr: int, audio: np.ndarray, patient_lang: str) -> dict:
    from gradio_client import handle_file
    audio = np.asarray(audio).reshape(-1)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, audio, sr)
        path = f.name
    try:
        return worker().predict(handle_file(path), patient_lang, api_name="/hear")
    finally:
        os.unlink(path)


TRANSLATE_SYSTEM = """You are Bayan, a professional medical interpreter in a clinic in Qatar.
Translate the speaker's words faithfully: never add, omit, soften or explain anything. Keep every number,
dose, unit, frequency and drug name exact. Use simple, respectful, everyday wording that a patient with
little schooling understands. Write the translation in the target language's native script.

Return ONLY a JSON object with these keys:
  "translation": the utterance in the TARGET language,
  "english": a literal English rendering of what the speaker said,
  "drugs": medicines the speaker prescribes, proposes or names: [{"name": "<generic name, lowercase>", "dose": "<as said or null>"}],
  "allergies": allergies or bad reactions to medicines the speaker reports: [{"substance": "<lowercase drug or class>", "reaction": "<as said or null>"}]
Use [] when there are none. Reasoning: low"""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}


def translate(text: str, role: str, src: str, tgt: str) -> dict:
    user = (
        f"Speaker: {'doctor' if role == 'doctor' else 'patient'}\n"
        f"Source language: {LANG_NAMES.get(src, src)}\nTarget language: {LANG_NAMES.get(tgt, tgt)}\n"
        f"Utterance: {text}"
    )
    kwargs = dict(
        model=LLM_MODEL,
        messages=[{"role": "system", "content": TRANSLATE_SYSTEM}, {"role": "user", "content": user}],
        temperature=0,
        max_tokens=700,
    )
    try:
        out = llm().chat.completions.create(**kwargs, extra_body={"reasoning_effort": "low"})
    except Exception:  # noqa: BLE001 - provider may reject the extra field; retry plain
        out = llm().chat.completions.create(**kwargs)
    data = _parse_json(out.choices[0].message.content)
    data.setdefault("translation", "")
    data.setdefault("english", text if src == "en" else "")
    data.setdefault("drugs", [])
    data.setdefault("allergies", [])
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


def speak_chunks(text: str, lang: str):
    """Yield (sample_rate, float32 array) per sentence; yields nothing if no voice for this language yet."""
    if lang not in WORKER_TTS_LANGS and lang != "en":
        return
    for sentence in split_sentences(text):
        voiced = speak(sentence, lang)
        if voiced is not None:
            yield voiced


def speak(text: str, lang: str):
    """Return (sample_rate, float32 mono array) or None if no voice for this language yet."""
    if not text.strip():
        return None
    if lang in WORKER_TTS_LANGS:
        wav_path, _stats = worker().predict(text, lang, "", api_name="/speak")
        audio, sr = sf.read(wav_path, dtype="float32")
        return sr, audio
    if lang == "en":
        raw = tts_client().text_to_speech(text, model=DOCTOR_TTS_MODEL)
        audio, sr = sf.read(io.BytesIO(raw), dtype="float32")
        return sr, audio
    return None  # e.g. Arabic doctor voice, Tagalog patient voice: on the roadmap


def held_turn_alerts(sess: Session, drugs: list[dict], quote: str) -> list[dict]:
    """ALG-PEN-01-style check: a mentioned drug shares a class with a reported allergy."""
    alerts = []
    for d in drugs:
        drug = normalise_drug(d.get("name", ""))
        d_classes = classes_of(drug)
        for a in sess.allergies:
            shared = d_classes & classes_of(a["substance"])
            if shared:
                alerts.append({
                    "rule": ALG_PEN_01["id"] if "penicillin" in shared else "ALG-CLASS",
                    "severity": "critical",
                    "message": f"{a['substance'].title()} allergy reported (“{a['quote']}”). "
                               f"{drug} is a {', '.join(sorted(shared))}.",
                    "sources": ALG_PEN_01["source_urls"] if "penicillin" in shared else [],
                    "quote": quote,
                })
    return alerts


# ------------------------------------------------------------------ rendering
def _fmt(seconds: float) -> str:
    return f"{seconds:.1f}s"


def render_row(role: str, lang: str, said: str, english: str, translation: str, timings: dict, held: bool) -> dict:
    who = "🩺 Doctor" if role == "doctor" else "🧑 Patient"
    lines = [f"**{who}** · {LANG_NAMES.get(lang, lang)}", said]
    if role == "patient" and english:
        lines.append(f"> **English:** {english}")
    if role == "doctor":
        lines.append(f"> **→ {LANG_NAMES.get(timings.get('tgt', ''), '')}:** {translation}"
                     + ("  \n> ⏸️ *Held: not spoken to the patient until the doctor reviews the alert.*" if held else ""))
    t = " · ".join(f"{k} {_fmt(v)}" for k, v in timings.items() if isinstance(v, (int, float)))
    lines.append(f"<sub>{t}</sub>")
    return {"role": "user" if role == "doctor" else "assistant", "content": "\n\n".join(lines)}


def render_alerts(alerts: list[dict]) -> str:
    if not alerts:
        return "🔕 *No alerts. Alerts appear here silently and are never spoken aloud.*"
    out = []
    for a in reversed(alerts):
        icon = {"critical": "🔴", "caution": "🟠"}.get(a["severity"], "⚪")
        src = " · ".join(f"[source]({u})" for u in a.get("sources", [])[:2])
        out.append(f"{icon} **{a['severity'].upper()} · {a['rule']}**  \n{a['message']}  \n"
                   f"<sub>Doctor said: “{a['quote']}” {src}</sub>")
    return "\n\n---\n\n".join(out)


# ------------------------------------------------------------------ one turn
def run_turn(sess: Session, sr: int, audio: np.ndarray):
    """Generator of events: ("ui", history, alerts_md) and ("audio", sr, array)."""
    t0 = time.time()
    heard = hear(sr, audio, sess.patient_lang)
    t_hear = time.time() - t0
    text = (heard.get("text") or "").strip()
    if not text:
        return
    role = heard["role"]
    if role == "doctor":
        src, tgt = heard["lang"], sess.patient_lang
        sess.doctor_lang = src
    else:
        src, tgt = sess.patient_lang, sess.doctor_lang

    t1 = time.time()
    tr = translate(text, role, src, tgt)
    t_tr = time.time() - t1

    if role == "patient":
        for a in tr["allergies"]:
            if a.get("substance"):
                sess.allergies.append({"substance": a["substance"], "reaction": a.get("reaction"),
                                       "quote": tr.get("english") or text})
    new_alerts = held_turn_alerts(sess, tr["drugs"], tr.get("english") or text) if role == "doctor" else []
    sess.alerts.extend(new_alerts)
    held = bool(new_alerts)

    timings = {"hear": t_hear, "translate": t_tr, "tgt": tgt}
    row = render_row(role, src, text, tr.get("english", ""), tr["translation"], timings, held)
    sess.history.append(row)
    yield ("ui", list(sess.history), render_alerts(sess.alerts))

    if held:
        return
    t2 = time.time()
    first = True
    for out_sr, out in speak_chunks(tr["translation"], tgt):
        if first:  # time to first audio is the number that matters for conversation
            timings["first_audio"] = time.time() - t0
            first = False
        yield ("audio", out_sr, out)
    if first:
        return  # no voice for this language yet (text only)
    timings["speak_total"] = time.time() - t2
    sess.history[-1] = render_row(role, src, text, tr.get("english", ""), tr["translation"], timings, held)
    yield ("ui", list(sess.history), render_alerts(sess.alerts))
