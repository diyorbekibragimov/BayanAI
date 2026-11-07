"""Bayan consultation state machine (one Consult per browser tab, keyed by an unguessable sid).

The UI is a static stage (bayan/ui.py) driven by a JSON view rendered here. Every pipeline step
mutates the Consult and yields UI; speech goes out through the live WebRTC stream (live mode)
or a hidden audio player (demo mode).

The clinical engine underneath is bayan.brain: every interpreted turn goes into the Consult's
brain Consultation (`s.brain`); doctor prescriptions pass the rule engine's prescription gate
(held sentences), patient turns feed the idiom lexicon and the background copilot (cards ->
suggestions / notes via bayan.copilot), and the end of the visit runs the wrap-up agent (note,
structured care plan, PDFs) that bayan.careplan serves to the patient.
"""

from __future__ import annotations

import html
import json
import os
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from . import careplan, copilot, talk
from .brain import copilot as brain
from .brain import wrapup
from .brain.state import Consultation, empty_state
from .outputs import retention
from .web import fill, read

UI = "ui"  # sentinel event: re-render the stage

DOCTOR_VOICE = os.environ.get("BAYAN_DOCTOR_VOICE", "0") == "1"  # speak the patient's English to the doctor (Kokoro)
# Read the care plan aloud into a WAV at the end of the visit (one worker TTS call per line: slow, off by default).
PLAN_AUDIO = os.environ.get("BAYAN_PLAN_AUDIO", "off").strip().lower() in ("1", "on", "true", "yes")
CONTEXT_TURNS = 4  # earlier turns sent with each translation (pronouns, "yes" answers)
TICK_S = 5.0       # timer rules (e.g. no ECG 10 min after chest pain) are re-checked this often while live

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

# Bayan does not store audio: consent is to processing only (other languages are translated from CONSENT_EN at
# runtime and cached in memory per process; the spoken audio is synthesised fresh each visit, never cached).
CONSENT_EN = ("Hello, I am Bayan. I translate between you and the doctor. "
              "Your voice is processed to translate it and is not stored. Do you agree?")
# Nepali: machine draft, native check pending.
_CONSENT = {"ne": "नमस्ते। म बयान हुँ। म तपाईं र डाक्टरको कुरा अनुवाद गर्छु। के तपाईं आफ्नो आवाज प्रशोधन गर्न सहमति दिनुहुन्छ?"}
_CONSENT_LOCK = threading.Lock()

END_RE = re.compile(r"\bend\W+(?:the\W+|this\W+)?(?:consultation|consult|visit|session)\b", re.I)

INK, BLUE, GREEN, AMBER = "#173430", "#1F6FB2", "#0E8A6F", "#C2410C"
_STATE = read("templates/state.html")  # the hidden element the stage script reads the JSON view from


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
    brain: Consultation = field(default_factory=lambda: _new_brain("ne"))
    cards_seen: int = -1         # brain card-store version the stage last showed
    card_notes: list = field(default_factory=list)
    file_tokens: list = field(default_factory=list)
    last_tick: float = 0.0
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
    erase(sess)
    return fresh


def _gc():
    cutoff = time.time() - 8 * 3600
    for k in [k for k, v in SESS.items() if v.touched < cutoff]:
        old = SESS.pop(k, None)
        if old is not None:
            erase(old)


def _new_brain(lang: str, started_at: float | None = None) -> Consultation:
    b = Consultation(patient_lang=lang, doctor_lang="en")
    if started_at:
        b.started_at = started_at
    brain.attach(b)
    return b


def begin(s: Consult) -> None:
    """A new visit starts (Start consultation / Play demo): a fresh brain consultation on the visit clock."""
    with s.lock:
        old = s.brain
        s.brain = _new_brain(s.lang, s.started_at)
        s.cards_seen, s.card_notes, s.last_tick = -1, [], time.time()
    if old.turns or old.outputs:
        _purge_brain(old)


def record_consent(s: Consult) -> None:
    """The patient tapped Yes: the consent question and the answer go on the record (not interpreted again)."""
    s.brain.add_turn("bayan", s.lang, s.consent_native or CONSENT_EN, english=f"Consent: {CONSENT_EN}", kind="system")
    s.brain.add_turn("patient", s.lang, "✓", english="Yes (consent given on screen)", kind="system")


def _purge_brain(b: Consultation) -> None:
    """Delete the consultation's files and wipe it in memory (transcript, state, cards, audit, outputs)."""
    try:
        retention.purge(b)
    except Exception as e:  # noqa: BLE001
        print(f"[retention] purge failed: {e}", flush=True)
    rt = getattr(b, "_copilot", None)
    if rt is not None and rt.timer is not None:
        rt.timer.cancel()
    with b.lock:
        b.turns.clear()
        b.trace.clear()
        b.audit.clear()
        b.outputs.clear()
        b.state = empty_state()
        b.ended = True
    brain.attach(b)  # fresh, empty card store


def erase(sess: Consult) -> None:
    """Privacy: drop the session's doctor-side files and its brain consultation (state, transcript, cards, PDFs).
    An approved care plan stays with its /plan/<id> page (in memory, 24 h) for the patient."""
    careplan.forget_files(sess.file_tokens)
    _purge_brain(sess.brain)


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


def _sync_cards(s: Consult) -> None:
    """Pull the brain's cards into the stage: suggestions, card notes, the idiom note under the English line."""
    b = s.brain
    if b.cards is None:
        return
    s.cards_seen = b.cards.version
    asking = {x["id"] for x in s.suggestions if x.get("status") == "asking"}
    sugs = copilot.suggest(b)
    for x in sugs:
        if x["id"] in asking and x["status"] == "open":
            x["status"] = "asking"
    s.suggestions = sugs
    s.card_notes = copilot.notes(b, hide=set((s.held or {}).get("cards") or []))
    pv = s.patient_view
    if pv.get("utt") and not pv.get("pending"):
        pv["idiom"], pv["note"] = copilot.idiom_for(b, pv["utt"], pv.get("native", ""))


def refresh(s: Consult) -> list:
    """Re-read the brain's cards now; returns the suggestions."""
    with s.lock:
        _sync_cards(s)
        return s.suggestions


def view(s: Consult) -> dict:
    s.seq += 1
    _sync_cards(s)
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
        "notes": s.notes + [{"kind": n["kind"], "text": n["text"]} for n in s.card_notes],
        "suggestions": open_sugs, "badge": len(open_sugs),
        "toast": s.error if s.screen in ("start", "wrap", "review", "sent") else "",
        "steps": s.steps, "openNotes": s.open_notes, "closeNotes": s.close_notes, "autoEnd": s.auto_end, "stopMic": s.stop_mic,
    }
    if s.review:
        v["review"] = {k: s.review.get(k) for k in ("plan_id", "plan_en", "note", "qr", "warnings", "sending",
                                                    "doctor_pdf", "patient_pdf", "wa")}
    return v


def render(s: Consult) -> str:
    with s.lock:
        data = json.dumps(view(s), ensure_ascii=False)
    return fill(_STATE, data=html.escape(data, quote=True))


def poll_render(s: Consult | None) -> str | None:
    """For the output pump: re-check timer rules every TICK_S and return a fresh render when the brain's cards
    changed since the stage last saw them (cards arrive from the background copilot); None when nothing changed."""
    if s is None or s.brain.cards is None or s.screen != "live":
        return None
    now = time.time()
    if now - s.last_tick >= TICK_S:
        s.last_tick = now
        brain.tick(s.brain)
    if s.brain.cards.version == s.cards_seen:
        return None
    return render(s)


def wait(s: Consult, seconds: float):
    """time.sleep that re-renders (yields UI) whenever new cards arrive; for generators that drive the stage."""
    end = time.time() + seconds
    while True:
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(0.25, left))
        if s.screen == "live" and s.brain.cards is not None and s.brain.cards.version != s.cards_seen:
            yield UI


# ------------------------------------------------------------------ notes
def add_note(s: Consult, kind: str, text: str):
    if text and not any(n["text"].lower() == text.lower() for n in s.notes):
        s.notes.append({"kind": kind, "text": text})


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", (text or "").strip(), maxsplit=1)[0]


def _held_payload(s: Consult, hits: list[dict], drugs: list[dict], english: str, translation: str, utt: str) -> dict:
    """The held-sentence screen from the rule engine's CRITICAL prescribing hits (ALG-PEN-01 style): one headline,
    the patient's own words, the drug and the rule; plus what is needed to speak or withdraw the sentence."""
    from .brain.vocab import classes_of
    h = hits[0]
    key = str(h.get("key") or "")
    drug = key.split("|", 1)[1] if "|" in key else next(
        (d["name"] for d in drugs if d.get("intent") == "prescribe"), "this medicine")
    head, pq = "", ""
    if h.get("family") == "drug_allergy" or str(h.get("rule_id", "")).startswith("ALG-"):
        d_cls = set(classes_of(drug))
        with s.brain.lock:
            allergies = list(s.brain.state.get("allergies") or [])
        for a in allergies:
            sub = str(a.get("substance") or "").lower()
            shared = d_cls & (set(a.get("class") or []) | set(classes_of(sub)) | {sub})
            if not shared and drug != sub:
                continue
            cls = "penicillin" if "penicillin" in shared else (sorted(shared)[0] if shared else sub)
            head = f"The patient reported {_article(sub)} {sub} allergy."
            head += " This is the same medicine." if drug == sub else f" {drug[:1].upper()}{drug[1:]} is {_article(cls)} {cls}."
            pq = next((e.get("quote") for e in a.get("evidence") or [] if e.get("quote")), "")
            break
    if not head:
        head = _first_sentence(h.get("message", "")) or f"{drug[:1].upper()}{drug[1:]} breaks a safety rule."
        for e in h.get("evidence") or []:
            t = s.brain.turn_by_id(e.get("utt") or "")
            if t is not None and t.role == "patient":
                pq = e.get("quote") or t.english
                break
    return {"headline": head, "pq": pq, "drug": drug, "rule": h.get("rule_id", ""), "dq": english,
            "translation": translation, "utt": utt, "cards": brain.held_card_ids(s.brain, hits)}


def _context(s: Consult) -> list[str]:
    with s.brain.lock:
        turns = [t for t in s.brain.turns if t.kind != "system"][-CONTEXT_TURNS:]
    return [f"{'Patient' if t.role == 'patient' else 'Doctor'}: {t.english or t.text}" for t in turns]


def _discard_held(s: Consult, reason: str) -> None:
    """The held sentence is never spoken: withdrawn in the brain (state + audit), held screen cleared."""
    h = s.held
    if not h:
        return
    brain.withdraw_turn(s.brain, h.get("utt", ""), h.get("cards") or [], reason)
    with s.lock:
        s.held = None


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
    if s.held:  # a new turn while a sentence is held: the held sentence is not spoken
        _discard_held(s, "not spoken: the conversation moved on")
    if role == "doctor":
        src = src or "en"
        s.brain.doctor_lang = src
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
            tr = talk.translate(text, "doctor", src, s.lang, context=_context(s))
        except Exception as e:  # noqa: BLE001
            print(f"[translate] {type(e).__name__}: {e}", flush=True)
            s.error, s.doctor_view["pending"] = "Could not translate that. Please say it again.", False
            yield UI
            return
        english = text if src == "en" else (tr.get("english") or text)
        turn = s.brain.add_turn("doctor", src, text, english=english, translation=tr["translation"])
        tests = [t for t in tr.get("tests", []) if isinstance(t, str) and t.strip()]
        drugs = tr.get("drugs", [])
        hits = brain.prescription_gate(s.brain, drugs, english, turn.id) if drugs else []
        reason = _held_payload(s, hits, drugs, english, tr["translation"], turn.id) if hits else None
        with s.lock:
            s.doctor_view = {"en": text, "native": tr["translation"], "pending": False}
            if tests:
                add_note(s, "test", f"{_join(tests)[:1].upper()}{_join(tests)[1:]} ordered")
            if reason:
                turn.held = True
                s.held = reason
                s.live, s.tint = "held", "h"
                add_note(s, "held", f"{reason['drug'][:1].upper()}{reason['drug'][1:]} held back")
            else:
                for d in drugs:
                    name = (d.get("name") or "").strip()
                    if not name or d.get("intent") == "mention":
                        continue
                    if d.get("intent") == "stop":
                        add_note(s, "drug", f"{name[:1].upper()}{name[1:]} stopped")
                        continue
                    dose = d.get("dose") or (f"{d['dose_mg']:g} mg" if isinstance(d.get("dose_mg"), (int, float)) else "")
                    add_note(s, "drug", f"{name[:1].upper()}{name[1:]}" + (f" {dose}" if dose else ""))
        yield UI
        if not reason:
            brain.on_turn(s.brain, turn)  # a held sentence waits for the doctor's choice
            if tr["translation"].strip():
                s.pending.append(Speech(tr["translation"], s.lang, "patient", True, english, kind="turn"))
        return

    # patient
    with s.lock:
        s.held = None
        s.live, s.tint = "patient", "p"
        s.patient_view = {"native": text, "en": "", "idiom": None, "note": "", "pending": True}
    yield UI
    tgt = s.brain.doctor_lang if s.brain.doctor_lang in ("en",) else "en"
    try:
        tr = talk.translate(text, "patient", s.lang, tgt, context=_context(s))
    except Exception as e:  # noqa: BLE001
        print(f"[translate] {type(e).__name__}: {e}", flush=True)
        s.error, s.patient_view["pending"] = "Could not translate that. Please say it again.", False
        yield UI
        return
    english = (tr.get("english") or tr.get("translation") or "").strip()
    turn = s.brain.add_turn("patient", s.lang, text, english=english, translation=english)
    allergies = tr.get("allergies", [])
    if allergies:
        brain.record_allergies(s.brain, allergies, english, turn.id)
    brain.post_idioms(s.brain, turn)  # sync lexicon: idiom note + one red-flag-first "Ask next"
    with s.lock:
        for a in allergies:
            sub = (a.get("substance") or "").strip().lower()
            if sub:
                add_note(s, "allergy", f"{sub[:1].upper()}{sub[1:]} allergy")
        s.patient_view = {"native": text, "en": english, "idiom": None, "note": "", "pending": False, "utt": turn.id}
    brain.on_turn(s.brain, turn)
    yield UI
    if DOCTOR_VOICE and english:
        s.pending.append(Speech(english, "en", "doctor", False, english, kind="turn"))


# ------------------------------------------------------------------ actions
def ask_suggestion(s: Consult, sug_id: str) -> bool:
    """The doctor tapped "Ask the patient": the card is marked asked in the brain, the question is translated,
    spoken, and recorded as a Bayan "ask" turn."""
    refresh(s)
    sug = next((x for x in s.suggestions if x["id"] == sug_id and x["status"] == "open"), None)
    if not sug:
        return False
    q = brain.ask_card(s.brain, sug_id)
    if not q:
        return False
    sug["status"] = "asking"
    s.close_notes += 1
    try:
        tr = talk.translate(q, "doctor", "en", s.lang, context=_context(s))
    except Exception as e:  # noqa: BLE001
        print(f"[translate] {type(e).__name__}: {e}", flush=True)
        s.error = "Could not translate that. Please ask it yourself."
        return True
    with s.lock:
        sug["status"] = "asked"
        turn = s.brain.add_turn("bayan", "en", q, english=q, translation=tr["translation"], kind="ask")
        s.doctor_view = {"en": q, "native": tr["translation"], "pending": False}
        s.live, s.tint, s.held = "doctor", "d", None
        s.pending.append(Speech(tr["translation"], s.lang, "patient", True, q, kind="ask"))
    brain.on_turn(s.brain, turn)
    return True


def held_else(s: Consult):
    """"Say something else": the held sentence is discarded (never spoken, withdrawn from the plan)."""
    _discard_held(s, "sentence withdrawn by the clinician (said something else)")
    with s.lock:
        s.held = None
        s.live, s.tint = "idle", "n"


def held_anyway(s: Consult):
    """"Speak it anyway": the clinician overrides the alert; recorded in the brain's audit, then spoken."""
    with s.lock:
        h = s.held
        if not h:
            return
        s.held = None
    brain.override_turn(s.brain, h.get("utt", ""), h.get("cards") or [], "spoken anyway by clinician")
    with s.lock:
        add_note(s, "override", f"{h['drug'][:1].upper()}{h['drug'][1:]} spoken anyway")
        print(f"[audit] override {h['rule']} sid={s.sid[:6]} drug={h['drug']}", flush=True)
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
# wrap-up trace lines (bayan.brain.wrapup -> consult.log) that complete steps 1 and 2; step 3 ends with the run
_STEP_DONE = [("care_plan_llm", "build_care_plan"), ("build_care_plan",)]


def _plan_speak_fn():
    if not PLAN_AUDIO:
        return None

    def speak(text: str, lang: str):
        return talk.speak(text, lang) if lang in talk.WORKER_TTS_LANGS else None
    return speak


def _advance_steps(s: Consult, trace: list[dict]) -> bool:
    texts = [str(e.get("text", "")) for e in trace]
    moved = False
    for i, prefixes in enumerate(_STEP_DONE):
        if s.steps[i]["state"] == "doing" and any(t.startswith(prefixes) for t in texts):
            s.steps[i]["state"] = "done"
            s.steps[i + 1]["state"] = "doing"
            moved = True
    return moved


def _review_warnings(out: dict) -> list[str]:
    ws = [w for w in out.get("warnings") or [] if isinstance(w, str) and w.strip()]
    if not PLAN_AUDIO:  # audio is switched off on purpose: not a problem to flag
        ws = [w for w in ws if not w.startswith("Audio not available")]
    return list(dict.fromkeys(ws))


def end_visit(s: Consult, base_url: str):
    """Generator: wrap screen with a live checklist (copilot flush + agentic wrap-up), then the review screen."""
    name = LANGS.get(s.lang, {}).get("name", s.lang)
    labels = [STEP_LABELS[0], STEP_LABELS[1].format(lang=name), STEP_LABELS[2]]
    if s.held:
        _discard_held(s, "not spoken: the consultation ended")
    with s.lock:
        s.screen, s.live, s.tint, s.speaking, s.held, s.error = "wrap", "idle", "n", False, None, ""
        s.pending.clear()
        s.steps = [{"label": labels[0], "state": "doing"}, {"label": labels[1], "state": "todo"},
                   {"label": labels[2], "state": "todo"}]
    yield UI
    b = s.brain
    b.ended = True
    start = len(b.trace)
    base = base_url.rstrip("/")
    box: dict = {}

    def work():
        try:
            brain.flush(b)
            box["out"] = wrapup.run_wrapup(b, agentic=True, speak_fn=_plan_speak_fn(), link_base=f"{base}/files")
        except Exception as e:  # noqa: BLE001
            box["err"] = e

    th = threading.Thread(target=work, name="bayan-wrapup", daemon=True)
    th.start()
    while th.is_alive():
        th.join(0.25)
        if _advance_steps(s, b.trace[start:]):
            yield UI
    out = box.get("out") or {}
    if SESS.get(s.sid) is not s:  # the session was reset or collected meanwhile: erase what the run wrote
        erase(s)
        return
    if "err" in box or not out:
        print(f"[wrapup] failed: {box.get('err')}", flush=True)
        s.error = "Could not write the plan. Please explain it to the patient."
    _advance_steps(s, b.trace[start:])
    for st in s.steps:
        st["state"] = "done"
    yield UI
    time.sleep(0.6)
    plan = out.get("care_plan") or {"lang": s.lang, "medicines": [], "avoid": [], "red_flags": [], "advice": [],
                                     "follow_up": {}, "emergency": "999"}
    token = out.get("token") or secrets.token_urlsafe(16)
    dtoken = secrets.token_urlsafe(16)
    if out.get("out_dir"):
        careplan.register_files(token, Path(out["out_dir"]), ["care_plan.pdf", "care_plan.wav"])
        careplan.register_files(dtoken, Path(out["out_dir"]), ["doctor_report.pdf"])
        s.file_tokens = [token, dtoken]
    pid = careplan.create(s.lang, plan, token=token if out.get("patient_pdf") else None)
    url = f"{base}/plan/{pid}"
    with s.lock:
        s.review = {"plan_id": pid, "plan_en": careplan.plan_text(plan), "note": out.get("note_md") or "",
                    "url": url, "qr": careplan.qr_svg(url), "warnings": _review_warnings(out), "sending": False,
                    "doctor_pdf": f"/files/{dtoken}/doctor_report.pdf" if out.get("doctor_pdf") else "",
                    "patient_pdf": f"/files/{token}/care_plan.pdf" if out.get("patient_pdf") else "",
                    "wa": out.get("wa_link") or ""}
        s.screen = "review"
    yield UI


def approve(s: Consult, text: str = "", note: str | None = None):
    """Approve and send: the (possibly edited) clinic note is saved and the doctor PDF re-rendered; the patient's
    plan page goes live. The care plan itself is the rule-checked structured plan (read-only on the review
    screen), so `text` is not used."""
    if s.screen != "review" or not s.review:
        return
    s.review["sending"] = True
    yield UI
    b = s.brain
    note = (note or "").replace("\r\n", "\n").strip()
    with b.lock:
        if note and note != (b.outputs.get("note_md") or "").strip():
            b.outputs["note_md"], b.outputs["note_edited"] = note, True
            s.review["note"] = note
        b.outputs["approved_at"] = datetime.now().isoformat(timespec="seconds")
        note_md, plan, out_dir = b.outputs.get("note_md") or "", b.outputs.get("care_plan"), b.outputs.get("out_dir")
    if out_dir:
        try:
            from .outputs.report import render_doctor_report
            render_doctor_report(b, note_md, Path(out_dir) / "doctor_report.pdf", care_plan=plan)
            (Path(out_dir) / "note.md").write_text(note_md, encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - the earlier PDF stays
            print(f"[approve] doctor PDF re-render failed: {type(e).__name__}: {e}", flush=True)
    careplan.approve(s.review["plan_id"])
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
