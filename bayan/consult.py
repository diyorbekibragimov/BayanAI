"""Bayan consultation state machine (one Consult per browser tab, keyed by an unguessable sid).

The UI is a static stage (bayan/ui.py) driven by a JSON view rendered here. Every pipeline step
mutates the Consult and yields UI; speech goes out through the live WebRTC stream (live mode)
or a hidden audio player (demo mode).
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field

import numpy as np

from . import careplan, copilot, talk

UI = "ui"  # sentinel event: re-render the stage

DOCTOR_VOICE = os.environ.get("BAYAN_DOCTOR_VOICE", "0") == "1"  # speak the patient's English to the doctor (Kokoro)

LANGS = {
    "ne": {"name": "Nepali", "native": "नेपाली"},
    "hi": {"name": "Hindi", "native": "हिन्दी"},
    "ur": {"name": "Urdu", "native": "اردو"},
    "bn": {"name": "Bengali", "native": "বাংলা"},
    "ml": {"name": "Malayalam", "native": "മലയാളം"},
    "tl": {"name": "Filipino", "native": "Filipino"},
}
CHARS_PER_SEC = {"ne": 11.0, "hi": 12.0, "ur": 12.0, "bn": 12.0, "ml": 10.0, "tl": 13.0, "en": 14.0}
SLOW_DESCRIPTION = ("A female speaker speaks very slowly and calmly, pausing a little between words, with a very "
                    "clear voice. The recording is very clear with no background noise.")

CONSENT_EN = ("Hello, I am Bayan. I translate between you and the doctor. "
              "Do you consent to your voice being processed and stored?")
_CONSENT = {"ne": "नमस्ते। म बयान हुँ। म तपाईं र डाक्टरको कुरा अनुवाद गर्छु। के तपाईं आफ्नो आवाज प्रशोधन र भण्डारण गर्न सहमति दिनुहुन्छ?"}
_CONSENT_LOCK = threading.Lock()

END_RE = re.compile(r"\bend\W+(?:the\W+|this\W+)?(?:consultation|consult|visit|session)\b", re.I)

INK, BLUE, GREEN, AMBER = "#173430", "#1F6FB2", "#0E8A6F", "#C2410C"


def consent_text(lang: str) -> str:
    """Spoken consent in the patient's language; translated once with the LLM, then cached."""
    with _CONSENT_LOCK:
        if lang in _CONSENT:
            return _CONSENT[lang]
    out = talk.translate(CONSENT_EN, "doctor", "en", lang).get("translation", "").strip()
    if out:
        with _CONSENT_LOCK:
            _CONSENT[lang] = out
    return out or CONSENT_EN


@dataclass
class Speech:
    text: str
    lang: str
    to: str = "patient"          # patient | doctor
    caption: bool = True         # caption mode while speaking (patient-facing doctor speech)
    en: str = ""                 # English shown under the caption
    slow: bool = False
    kind: str = "turn"           # turn | consent | ask | override | again


@dataclass
class Consult:
    sid: str
    lang: str = "ne"
    screen: str = "start"        # start | consent | live | wrap | review | sent
    live: str = "idle"           # idle | doctor | patient | held | caption
    tint: str = "n"
    speaking: bool = False
    started_at: float | None = None
    webrtc_id: str | None = None
    demo: bool = False
    consent_native: str = ""
    consent_spoken: bool = False
    consent_queued: bool = False
    talk: talk.Session = field(default_factory=talk.Session)
    turns: list = field(default_factory=list)
    doctor_view: dict = field(default_factory=lambda: {"en": "", "native": "", "pending": False})
    patient_view: dict = field(default_factory=lambda: {"native": "", "en": "", "idiom": None, "note": "", "pending": False})
    caption: dict = field(default_factory=dict)
    held: dict | None = None
    notes: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    last_speech: Speech | None = None
    busy: bool = False
    error: str = ""
    steps: list = field(default_factory=list)
    review: dict = field(default_factory=dict)
    open_notes: int = 0
    close_notes: int = 0
    auto_end: int = 0
    stop_mic: int = 0
    seq: int = 0
    touched: float = field(default_factory=time.time)
    lock: threading.RLock = field(default_factory=threading.RLock)


SESS: dict[str, Consult] = {}


def new_sid() -> str:
    sid = uuid.uuid4().hex
    SESS[sid] = Consult(sid=sid)
    _gc()
    return sid


def get(sid) -> Consult | None:
    s = SESS.get(sid) if isinstance(sid, str) else None
    if s:
        s.touched = time.time()
    return s


def find(args) -> Consult | None:
    for a in args:
        if isinstance(a, str) and a in SESS:
            return get(a)
    return None


def reset(sess: Consult) -> Consult:
    fresh = Consult(sid=sess.sid, lang=sess.lang, seq=sess.seq + 1)
    SESS[sess.sid] = fresh
    return fresh


def _gc():
    cutoff = time.time() - 8 * 3600
    for k in [k for k, v in SESS.items() if v.touched < cutoff]:
        SESS.pop(k, None)


# ------------------------------------------------------------------ view
def status(s: Consult) -> list:
    name = LANGS.get(s.lang, {}).get("name", s.lang)
    if s.screen == "start":
        return ["Ready", "", INK]
    if s.screen == "consent":
        return ["Speaking to the patient", "Asking for consent", GREEN]
    if s.screen == "wrap":
        return ["Writing it up", "This takes a few seconds.", INK]
    if s.live == "held":
        return ["Sentence held", "", AMBER]
    if s.live in ("doctor", "patient") and s.tint == "n" and not s.speaking:
        return ["Listening", f"English and {name}", INK]
    if s.live == "doctor":
        return ["Speaking to the patient" if s.speaking else "Listening to you", name if s.speaking else "English",
                GREEN if s.speaking else BLUE]
    if s.live == "patient":
        if s.speaking:
            return ["Speaking to you", "English", BLUE]
        return ["Listening to the patient", name, GREEN]
    return ["Listening", f"English and {name}", INK]


def view(s: Consult) -> dict:
    s.seq += 1
    st = status(s)
    if s.error:
        st = [st[0], s.error, st[2]]
    open_sugs = [x for x in s.suggestions if x["status"] == "open"]
    v = {
        "seq": s.seq, "screen": s.screen, "live": s.live, "tint": s.tint, "lang": s.lang,
        "langName": LANGS.get(s.lang, {}).get("name", s.lang),
        "elapsed": round(time.time() - s.started_at, 1) if s.started_at else 0,
        "listen": s.screen == "live" and s.live in ("idle", "doctor", "patient") and not s.speaking,
        "speak": s.speaking, "status": st, "demo": s.demo,
        "consent": {"native": s.consent_native, "en": CONSENT_EN},
        "doctor": s.doctor_view, "patient": s.patient_view, "caption": s.caption, "held": s.held,
        "notes": s.notes, "suggestions": open_sugs, "badge": len(open_sugs),
        "toast": s.error if s.screen in ("start", "wrap", "review", "sent") else "",
        "steps": s.steps, "openNotes": s.open_notes, "closeNotes": s.close_notes, "autoEnd": s.auto_end, "stopMic": s.stop_mic,
    }
    if s.review:
        v["review"] = {k: s.review.get(k) for k in ("plan_id", "plan_en", "qr", "warnings", "sending")}
    return v


def render(s: Consult) -> str:
    with s.lock:
        data = json.dumps(view(s), ensure_ascii=False)
    return f"<div class='bz-s' data-s=\"{html.escape(data, quote=True)}\"></div>"


# ------------------------------------------------------------------ notes
def add_note(s: Consult, kind: str, text: str):
    if text and not any(n["text"].lower() == text.lower() for n in s.notes):
        s.notes.append({"kind": kind, "text": text})


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def held_reason(s: Consult, drugs: list[dict]) -> dict | None:
    """Allergy vs drug class (ALG-PEN-01 style). Returns the first conflict, structured for the UI."""
    for d in drugs:
        drug = talk.normalise_drug(d.get("name", ""))
        if not drug:
            continue
        d_cls = talk.classes_of(drug)
        for a in s.talk.allergies:
            shared = d_cls & talk.classes_of(a["substance"])
            if shared:
                cls = "penicillin" if "penicillin" in shared else sorted(shared)[0]
                sub = a["substance"].lower()
                head = f"The patient reported {_article(sub)} {sub} allergy."
                head += " This is the same medicine." if drug == sub else f" {drug[:1].upper()}{drug[1:]} is {_article(cls)} {cls}."
                return {"headline": head, "pq": a.get("quote", ""), "drug": drug,
                        "rule": talk.ALG_PEN_01["id"] if cls == "penicillin" else "ALG-CLASS"}
    return None


# ------------------------------------------------------------------ one turn
def process_audio(s: Consult, sr: int, arr: np.ndarray):
    try:
        heard = talk.hear(sr, arr, s.lang)
    except Exception as e:  # noqa: BLE001
        print(f"[hear] {type(e).__name__}: {e}", flush=True)
        s.error = "Voice service is offline or starting. Please try again in a minute."
        yield UI
        return
    text = (heard.get("text") or "").strip()
    if not text:
        return
    role = heard.get("role", "patient")
    src = heard.get("lang") or ("en" if role == "doctor" else s.lang)
    yield from process_text(s, role, text, src)


def process_text(s: Consult, role: str, text: str, src: str | None = None):
    """Translate one utterance, update the stage, and queue what Bayan should say."""
    s.error = ""
    if role == "doctor":
        src = src or "en"
        s.talk.doctor_lang = src
        if END_RE.search(text):
            s.auto_end += 1
            yield UI
            return
        with s.lock:
            s.held = None
            s.live, s.tint = "doctor", "d"
            s.doctor_view = {"en": text, "native": "", "pending": True}
        yield UI
        try:
            tr = talk.translate(text, "doctor", src, s.lang)
        except Exception as e:  # noqa: BLE001
            print(f"[translate] {type(e).__name__}: {e}", flush=True)
            s.error, s.doctor_view["pending"] = "Could not translate that. Please say it again.", False
            yield UI
            return
        english = text if src == "en" else (tr.get("english") or text)
        turn = {"role": "doctor", "said": text, "english": english, "translation": tr["translation"], "held": False}
        s.turns.append(turn)
        tests = [t for t in tr.get("tests", []) if isinstance(t, str) and t.strip()]
        reason = held_reason(s, tr.get("drugs", []))
        with s.lock:
            s.doctor_view = {"en": text, "native": tr["translation"], "pending": False}
            if tests:
                add_note(s, "test", f"{_join(tests)[:1].upper()}{_join(tests)[1:]} ordered")
            if reason:
                turn["held"] = True
                s.held = {**reason, "dq": english, "translation": tr["translation"]}
                s.live, s.tint = "held", "h"
                add_note(s, "held", f"{reason['drug'][:1].upper()}{reason['drug'][1:]} held back")
            else:
                for d in tr.get("drugs", []):
                    name = (d.get("name") or "").strip()
                    if name:
                        add_note(s, "drug", f"{name[:1].upper()}{name[1:]}" + (f" {d['dose']}" if d.get("dose") else ""))
        yield UI
        if not reason and tr["translation"].strip():
            s.pending.append(Speech(tr["translation"], s.lang, "patient", True, english, kind="turn"))
        return

    # patient
    with s.lock:
        s.held = None
        s.live, s.tint = "patient", "p"
        s.patient_view = {"native": text, "en": "", "idiom": None, "note": "", "pending": True}
    yield UI
    tgt = s.talk.doctor_lang if s.talk.doctor_lang in ("en",) else "en"
    try:
        tr = talk.translate(text, "patient", s.lang, tgt)
    except Exception as e:  # noqa: BLE001
        print(f"[translate] {type(e).__name__}: {e}", flush=True)
        s.error, s.patient_view["pending"] = "Could not translate that. Please say it again.", False
        yield UI
        return
    english = (tr.get("english") or tr.get("translation") or "").strip()
    turn = {"role": "patient", "said": text, "english": english}
    s.turns.append(turn)
    entry = copilot.match_idiom(text, english, s.lang)
    with s.lock:
        for a in tr.get("allergies", []):
            sub = (a.get("substance") or "").strip().lower()
            if sub:
                s.talk.allergies.append({"substance": sub, "reaction": a.get("reaction"), "quote": english})
                add_note(s, "allergy", f"{sub[:1].upper()}{sub[1:]} allergy")
        idiom = entry["native"] if entry and entry["native"] in text else None
        s.patient_view = {"native": text, "en": english, "idiom": idiom,
                          "note": copilot.explain(entry) if entry else "", "pending": False}
        new = copilot.suggest(s, {"role": "patient", "native": text, "english": english})
        s.suggestions.extend(new)
    yield UI
    if DOCTOR_VOICE and english:
        s.pending.append(Speech(english, "en", "doctor", False, english, kind="turn"))


# ------------------------------------------------------------------ actions
def ask_suggestion(s: Consult, sug_id: str) -> bool:
    sug = next((x for x in s.suggestions if x["id"] == sug_id and x["status"] == "open"), None)
    if not sug:
        return False
    sug["status"] = "asking"
    s.close_notes += 1
    tr = talk.translate(sug["text"], "doctor", "en", s.lang)
    with s.lock:
        sug["status"] = "asked"
        s.turns.append({"role": "doctor", "said": sug["text"], "english": sug["text"], "translation": tr["translation"]})
        s.doctor_view = {"en": sug["text"], "native": tr["translation"], "pending": False}
        s.live, s.tint, s.held = "doctor", "d", None
        s.pending.append(Speech(tr["translation"], s.lang, "patient", True, sug["text"], kind="ask"))
    return True


def held_else(s: Consult):
    with s.lock:
        s.held = None
        s.live, s.tint = "idle", "n"


def held_anyway(s: Consult):
    with s.lock:
        h = s.held
        if not h:
            return
        for t in reversed(s.turns):
            if t["role"] == "doctor" and t.get("held"):
                t["overridden"] = True
                break
        add_note(s, "override", f"{h['drug'][:1].upper()}{h['drug'][1:]} spoken anyway")
        print(f"[audit] override {h['rule']} sid={s.sid[:6]} drug={h['drug']}", flush=True)
        s.held = None
        s.live, s.tint = "doctor", "d"
        s.pending.append(Speech(h["translation"], s.lang, "patient", True, h["dq"], kind="override"))


def again(s: Consult, slow: bool):
    sp = s.last_speech
    if sp and sp.to == "patient":
        with s.lock:
            s.pending.append(Speech(sp.text, sp.lang, "patient", sp.caption, sp.en, slow=slow, kind="again"))


def pop_pending(s: Consult) -> Speech | None:
    with s.lock:
        return s.pending.pop(0) if s.pending else None


# ------------------------------------------------------------------ speaking
def _est_seconds(text: str, lang: str, slow: bool) -> float:
    return 0.8 + len(text) / (CHARS_PER_SEC.get(lang, 11.0) * (0.65 if slow else 1.0))


def _begin_speech(s: Consult, sp: Speech):
    with s.lock:
        s.speaking = True
        s.last_speech = sp if sp.to == "patient" else s.last_speech
        if sp.caption and sp.to == "patient":
            s.caption = {"native": sp.text, "en": sp.en, "key": uuid.uuid4().hex[:8],
                         "rate": CHARS_PER_SEC.get(sp.lang, 11.0) * (0.65 if sp.slow else 1.0)}
            s.live, s.tint = "caption", "p"


def _end_speech(s: Consult, sp: Speech):
    with s.lock:
        s.speaking = False
        if sp.kind == "consent":
            s.consent_spoken = True
        elif sp.caption and s.live == "caption":
            s.live, s.tint = "doctor", "n"
        elif s.live in ("patient", "doctor"):
            s.tint = "n"


def speak_live(s: Consult, sp: Speech):
    """Stream speech into the WebRTC call. Yields UI or (sr, int16 pcm). Holds the mic until playback ends."""
    t_first, played = None, 0.0
    desc = SLOW_DESCRIPTION if sp.slow else ""
    try:
        for out_sr, f32 in talk.speak_chunks(sp.text, sp.lang, desc) if sp.lang != "en" else _doctor_voice(sp.text):
            if t_first is None:
                t_first = time.time()
                _begin_speech(s, sp)
                yield UI
            played += len(f32) / out_sr
            yield out_sr, (np.clip(f32, -1, 1) * 32767).astype(np.int16).reshape(1, -1)
    except Exception as e:  # noqa: BLE001 - keep the visit going in text
        print(f"[speak] failed: {type(e).__name__}: {e}", flush=True)
        s.error = "Voice is offline. Showing text only."
    if t_first is None:  # text only: show the caption long enough to read
        if sp.to == "patient":
            _begin_speech(s, sp)
            yield UI
            time.sleep(min(8.0, _est_seconds(sp.text, sp.lang, sp.slow)))
    else:  # do not let the mic hear Bayan's own voice (echo tail 300 ms)
        time.sleep(max(0.0, t_first + played - time.time()) + 0.3)
    _end_speech(s, sp)
    yield UI


def _doctor_voice(text: str):
    voiced = talk.speak(text, "en")
    if voiced is not None:
        yield voiced


def speak_demo(s: Consult, sp: Speech, voice_on: bool):
    """Demo: synthesize the whole utterance, hand it to the page's audio player, wait for playback.
    Yields UI or ("wav", (sr, int16))."""
    wav = None
    if voice_on and (sp.lang in talk.WORKER_TTS_LANGS or (sp.lang == "en" and DOCTOR_VOICE)):
        try:
            wav = talk.speak(sp.text, sp.lang, SLOW_DESCRIPTION if sp.slow else "")
        except Exception as e:  # noqa: BLE001
            print(f"[demo speak] failed: {type(e).__name__}: {e}", flush=True)
    if wav is None and sp.to == "doctor":
        return
    _begin_speech(s, sp)
    yield UI
    if wav is not None:
        sr, f32 = wav
        f32 = np.asarray(f32).reshape(-1)
        yield "wav", (sr, (np.clip(f32, -1, 1) * 32767).astype(np.int16))
        time.sleep(len(f32) / sr + 0.4)
    else:
        time.sleep(min(7.0, _est_seconds(sp.text, sp.lang, sp.slow)))
    _end_speech(s, sp)
    yield UI


# ------------------------------------------------------------------ end of visit
STEP_LABELS = ["Care plan, in English", "Care plan, in {lang}", "Checking the plan against the safety rules"]


def end_visit(s: Consult, base_url: str):
    """Generator: wrap screen with a live checklist, then the review screen."""
    name = LANGS.get(s.lang, {}).get("name", s.lang)
    labels = [STEP_LABELS[0], STEP_LABELS[1].format(lang=name), STEP_LABELS[2]]
    with s.lock:
        s.screen, s.live, s.tint, s.speaking, s.held, s.error = "wrap", "idle", "n", False, None, ""
        s.pending.clear()
        s.steps = [{"label": labels[0], "state": "doing"}, {"label": labels[1], "state": "todo"},
                   {"label": labels[2], "state": "todo"}]
    yield UI
    try:
        plan_en = careplan.write_plan(s.turns)
    except Exception as e:  # noqa: BLE001
        print(f"[plan] failed: {e}", flush=True)
        plan_en, s.error = "", "Could not write the plan. Please write it here."
    s.steps[0]["state"], s.steps[1]["state"] = "done", "doing"
    yield UI
    try:
        plan_native = careplan.translate_plan(plan_en, s.lang)
    except Exception as e:  # noqa: BLE001
        print(f"[plan translate] failed: {e}", flush=True)
        plan_native = ""
    s.steps[1]["state"], s.steps[2]["state"] = "done", "doing"
    yield UI
    warnings = careplan.safety_check(plan_en, s.talk.allergies)
    time.sleep(0.5)
    s.steps[2]["state"] = "done"
    yield UI
    time.sleep(0.6)
    pid = careplan.create(s.lang, plan_en, plan_native)
    url = f"{base_url.rstrip('/')}/plan/{pid}"
    with s.lock:
        s.review = {"plan_id": pid, "plan_en": plan_en, "plan_native": plan_native, "url": url,
                    "qr": careplan.qr_svg(url), "warnings": warnings, "sending": False}
        s.screen = "review"
    yield UI


def approve(s: Consult, text: str):
    if s.screen != "review" or not s.review:
        return
    text = (text or "").replace("\r\n", "\n").strip()
    native = s.review.get("plan_native", "")
    if text != (s.review.get("plan_en") or "").strip():
        s.review["sending"] = True
        yield UI
        try:
            native = careplan.translate_plan(text, s.lang)
        except Exception as e:  # noqa: BLE001
            print(f"[approve translate] failed: {e}", flush=True)
            native = ""
        s.review["plan_en"] = text
    careplan.approve(s.review["plan_id"], text, native)
    with s.lock:
        s.review["sending"] = False
        s.screen, s.tint = "sent", "p"
    yield UI


# ------------------------------------------------------------------ demo (golden path, text turns)
DEMO_SCRIPT = [
    ("doctor", "Do you have any allergies to medicines?"),
    ("patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर सुन्नियो।"),
    ("patient", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ, काम गर्दा झन् बढ्छ।"),
    ("ask", None),
    ("doctor", "Amoxicillin 500 three times a day, and you can go home."),
    ("held_else", None),
    ("doctor", "Let’s not use amoxicillin. Take paracetamol 1 g up to three times a day. "
               "We will also check your heart with an ECG and a blood test."),
    ("end", None),
]
