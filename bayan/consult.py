"""Bayan consultation state machine (one Consult per browser tab, keyed by an unguessable sid).

The UI is a static stage (bayan/ui.py) driven by a JSON view rendered here. Every pipeline step
mutates the Consult and yields UI. Tap-to-talk: the browser records one utterance per tap (the doctor
picks whose turn it is) and sends 16 kHz PCM; every reply is streamed to the page's WebAudio player.
The doctor works in English or Arabic (s.doc_lang); the whole doctor-facing text follows it.

The clinical engine underneath is bayan.brain: every interpreted turn goes into the Consult's
brain Consultation (`s.brain`); doctor prescriptions pass the rule engine's prescription gate
(held sentences), patient turns feed the idiom lexicon and the background copilot (cards ->
suggestions / notes via bayan.copilot), and the end of the visit runs the wrap-up agent (note,
structured care plan, PDFs) that bayan.careplan serves to the patient.
"""

from __future__ import annotations

import html
import itertools
import json
import os
import re
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from . import careplan, copilot, talk, ui
from .langs import MORE
from .brain import copilot as brain
from .brain import llm as brain_llm
from .brain.idioms import default_index as idiom_index
from .brain import wrapup
from .brain.state import Consultation, empty_state
from .outputs import retention
from .web import fill, read

UI = "ui"  # sentinel event: re-render the stage

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
    "ta": {"name": "Tamil", "native": "தமிழ்"},
    "sw": {"name": "Swahili", "native": "Kiswahili"},
    **{code: {"name": v["en"], "native": v["native"]} for code, v in MORE.items()},   # the "More…" sheet (incl. Korean)
}
CHARS_PER_SEC = {"ne": 11.0, "hi": 12.0, "ur": 12.0, "bn": 12.0, "ml": 10.0, "tl": 13.0, "ta": 10.0, "sw": 13.0,
                 "en": 14.0, "ar": 12.0, **{code: v["cps"] for code, v in MORE.items()}}
# "Slower" replays the cached clip at this rate in the browser (pitch preserved) with longer sentence gaps; the worker's
# TTS ignored the old "speak slowly" voice description (Indic Parler pace did not change), so nothing is re-synthesised.
SLOW_RATE = 0.8
SLOW_GAP_EXTRA_S = 0.35   # extra silence (playback time) at each sentence gap
SLOW_GAP_MIN_S = 0.4      # a sentence gap: a run of (near) zeros at least this long

# Bayan does not store audio: consent is to processing only (other languages are translated from CONSENT_EN at
# runtime and cached in memory per process; the spoken audio is synthesised fresh each visit, never cached).
# One source: the brain record / PDF transcript use exactly the consent sentence the doctor's screen shows.
CONSENT_EN = ui.t("en", "consent_doc")
# Nepali: machine draft, native check pending.
_CONSENT = {
    "ne": "नमस्ते। म बयान हुँ। म तपाईं र डाक्टरको कुरा अनुवाद गर्छु। के तपाईं आफ्नो आवाज प्रशोधन गर्न सहमति दिनुहुन्छ?",
    # gpt-oss drafts, hand-corrected (Swahili, Korean); native check pending.
    "ta": "வணக்கம், நான் பயான். நான் உங்களுக்கும் மருத்துவருக்கும் இடையில் மொழிபெயர்க்கிறேன். உங்கள் குரல் மொழிபெயர்ப்புக்காக மட்டுமே செயலாக்கப்படுகிறது, சேமிக்கப்படாது. நீங்கள் ஒப்புக்கொள்கிறீர்களா?",
    "sw": "Habari, mimi ni Bayan. Ninatafsiri kati yako na daktari. Sauti yako inachakatwa ili kutafsiriwa tu, na haihifadhiwi. Je, unakubali?",
    **{code: v["consent"] for code, v in MORE.items()},
}
_CONSENT_LOCK = threading.Lock()

# Whisper's stock outputs for non-speech (tones, breath, room noise). Dropped instead of translated.
HALLUCINATIONS = {
    "اشتركوا في القناة", "ترجمة نانسي قنقر", "شكرا للمشاهدة", "شكرا لكم على المشاهدة", "شكرا على المشاهدة",
    "thanks for watching", "thank you for watching", "please subscribe", "subscribe to the channel",
    "subtitles by the amara.org community", "you",
}


_LOOP_RE = re.compile(r"(.{1,6}?)\1{5,}", re.S)
NOT_CAUGHT = "not_caught"  # UI string key (bayan/ui.py STRINGS)


def _hallucinated(text: str) -> bool:
    t = re.sub(r"[\s.!?،,…]+", " ", text.lower()).strip()
    return t in HALLUCINATIONS


def garbled(text: str) -> bool:
    """Repetition loops ("ماهوهوهو…") and other degenerate transcripts: never translate or show them.
    Same rule as Whisper's own fallback: zlib compression ratio > 2.4, or a short unit repeated 6+ times."""
    import zlib
    if not text:
        return False
    # One byte per character, not UTF-8: non-Latin scripts share 2-byte UTF-8 prefixes, which made long, correct
    # Georgian/Devanagari sentences look "compressible" (see voice_worker _degenerate). Real loops still score > 3.
    raw = bytes(ord(c) & 0xFF for c in text)
    return len(raw) / max(1, len(zlib.compress(raw))) > 2.4 or bool(_LOOP_RE.search(text))


END_RE = re.compile(r"\bend\W+(?:the\W+|this\W+)?(?:consultation|consult|visit|session)\b", re.I)

INK, BLUE, GREEN, AMBER = "#173430", "#1F6FB2", "#0E8A6F", "#C2410C"
_STATE = read("templates/state.html")  # the hidden element the stage script reads the JSON view from


def consent_text(lang: str) -> str:
    """Spoken consent in the patient's language; translated once with the LLM, then cached."""
    with _CONSENT_LOCK:
        if lang in _CONSENT:
            return _CONSENT[lang]
    out = talk.translate(CONSENT_EN, "doctor", "en", lang).get("translation", "").strip()
    if out and speakable(out, lang, CONSENT_EN):
        with _CONSENT_LOCK:
            _CONSENT[lang] = out
        return out
    return CONSENT_EN   # shown to the doctor; queue_speech never says it in the patient's voice


@dataclass
class Speech:
    text: str
    lang: str
    to: str = "patient"          # patient | doctor
    caption: bool = True         # caption mode while speaking (patient-facing doctor speech)
    en: str = ""                 # English shown under the caption
    slow: bool = False           # "Slower": the browser replays the clip at SLOW_RATE (no new synthesis)
    kind: str = "turn"           # turn | consent | ask | override | again
    cid: str = ""                # the consultation it belongs to (stamped by queue_speech); speak_clip refuses others


def _cid() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Consult:
    sid: str
    cid: str = field(default_factory=_cid)  # this consultation (a reset is a new Consult, so a new cid); every audio
                                            # payload carries it and the page plays only the current one's
    lang: str = "ne"
    doc_lang: str = "en"         # doctor's language, chosen on the start screen: en | ar (UI follows it)
    next_speaker: str = "doctor" # whose turn it is; flips after each completed turn (the page can override)
    turn_seq: int = 0
    confirm: dict | None = None  # speaker mismatch waiting for the doctor's decision
    confirm_pcm: tuple | None = None
    settling: bool = False       # the 3 s pause after Bayan spoke (caption stays; any tap ends it)
    settle_cancel: bool = False
    last_n: object = None        # last action id from the page (dedupe)
    audio_ack: object = None     # id of the last recording the server took (the page waits for it)
    last_act: str = ""
    shown: dict = field(default_factory=dict)  # brain turn id -> that turn as the doctor saw it (doctor's language)
    loc_seen: int = -1           # localisation version the stage last showed
    screen: str = "start"        # start | consent | live | wrap | review | sent
    live: str = "idle"           # idle | doctor | patient | held | caption | confirm
    tint: str = "n"
    speaking: bool = False
    processing: bool = False     # recording received: hearing / translating / preparing the voice
    started_at: float | None = None
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
    error: str = ""                # a UI string key (bayan/ui.py STRINGS)
    notice: dict = field(default_factory=lambda: {"id": 0, "text": ""})
    steps: list = field(default_factory=list)
    review: dict = field(default_factory=dict)
    open_notes: int = 0
    close_notes: int = 0
    auto_end: int = 0
    stop_mic: int = 0
    seq: int = 0
    hearing: bool = False        # a recording is being heard / translated (one turn at a time)
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


def alive(s: Consult) -> bool:
    """This Consult is still the tab's current consultation (not reset by Home / No / new, not collected)."""
    return SESS.get(s.sid) is s


def reset(sess: Consult) -> Consult:
    """Drop the visit: a fresh Consult (new cid) replaces it. Everything still running for the old one (talk loop,
    speech, demo) sees alive() turn False and stops; its queued speech is cleared so nothing of it is ever said."""
    fresh = Consult(sid=sess.sid, lang=sess.lang, doc_lang=sess.doc_lang)
    SESS[sess.sid] = fresh
    with sess.lock:
        sess.pending.clear()
        sess.last_speech = None
    erase(sess)
    return fresh


def _gc():
    cutoff = time.time() - 8 * 3600
    for k in [k for k, v in SESS.items() if v.touched < cutoff]:
        old = SESS.pop(k, None)
        if old is not None:
            erase(old)


def _new_brain(lang: str, started_at: float | None = None, doc_lang: str = "en") -> Consultation:
    b = Consultation(patient_lang=lang, doctor_lang=doc_lang)
    if started_at:
        b.started_at = started_at
    brain.attach(b)
    return b


def begin(s: Consult) -> None:
    """A new visit starts (Start consultation / Play demo): a fresh brain consultation on the visit clock."""
    with s.lock:
        old = s.brain
        s.brain = _new_brain(s.lang, s.started_at, s.doc_lang)
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
    drop_clips(sess.cid)
    _purge_brain(sess.brain)


# ------------------------------------------------------------------ view
def status(s: Consult) -> list:
    """[title, subtitle, colour] in the doctor's language."""
    dl = s.doc_lang
    T = lambda k, **kw: ui.t(dl, k, **kw)  # noqa: E731
    name, doc_name = T("lang_" + s.lang), T("lang_" + dl)
    if s.screen == "start":
        return [T("st_ready"), "", INK]
    if s.screen == "consent":
        return [T("st_speaking_patient"), T("st_consent"), GREEN]
    if s.screen == "wrap":
        return [T("st_writing"), T("st_writing_sub"), INK]
    if s.live == "held":
        return [T("st_held"), "", AMBER]
    if s.processing:
        return [T("st_translating"), "", INK]
    if s.speaking and s.live == "patient":
        return [T("st_speaking_you"), doc_name, BLUE]
    if s.speaking:
        return [T("st_speaking_patient"), name, GREEN]
    if s.pending and s.live in ("doctor", "patient"):  # translated, voice not started yet
        return [T("st_translating"), "", INK]
    return [T("st_tap"), T("st_or", a=doc_name, b=name), INK]


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


_SEQ = itertools.count(1)  # view order across every Consult of the process: a reset never restarts it


def view(s: Consult) -> dict:
    s.seq = next(_SEQ)
    _sync_cards(s)
    st = status(s)
    err = ui.t(s.doc_lang, s.error) if s.error else ""
    if err:
        st = [st[0], err, st[2]]
    open_sugs = [x for x in s.suggestions if x["status"] == "open"]
    card_notes = [{"kind": n["kind"], "text": n["text"]} for n in s.card_notes]
    pv = dict(s.patient_view)
    # Card-derived text (suggestions, rule/agent notes, the idiom explanation) in the doctor's language: from the
    # cache when ready, else English now and the stage refreshes when the translation lands (never blocks).
    if s.doc_lang != "en":
        texts = [x["text"] for x in open_sugs] + [n["text"] for n in card_notes] + ([pv["note"]] if pv.get("note") else [])
        out = loc_soon(s, texts)
        k = 0
        open_sugs = [{**x, "text": out[k + i]} for i, x in enumerate(open_sugs)]
        k += len(open_sugs)
        card_notes = [{**n, "text": out[k + i]} for i, n in enumerate(card_notes)]
        k += len(card_notes)
        if pv.get("note"):
            pv["note"] = out[k]
    s.loc_seen = _LOC_VERSION[0]
    v = {
        "seq": s.seq, "cid": s.cid, "screen": s.screen, "live": s.live, "tint": s.tint, "lang": s.lang,
        "langName": LANGS.get(s.lang, {}).get("name", s.lang),
        "elapsed": round(time.time() - s.started_at, 1) if s.started_at else 0,
        "docLang": s.doc_lang, "settle": s.settling, "ack": s.audio_ack, "turn": s.next_speaker,
        "turnSeq": s.turn_seq,
        "confirm": ({"detected": s.confirm["detected"], "selected": s.confirm["selected"]} if s.confirm else None),
        "speak": s.speaking, "processing": s.processing, "queued": bool(s.pending), "status": st, "demo": s.demo, "notice": s.notice,
        "consent": {"native": s.consent_native, "en": CONSENT_EN},
        "doctor": s.doctor_view, "patient": pv, "caption": s.caption, "held": s.held,
        "notes": s.notes + card_notes,
        "suggestions": open_sugs, "badge": len(open_sugs),
        "toast": err if s.screen in ("start", "wrap", "review", "sent") else "",
        "steps": s.steps, "openNotes": s.open_notes, "closeNotes": s.close_notes, "autoEnd": s.auto_end, "stopMic": s.stop_mic,
    }
    if s.review:
        v["review"] = {k: s.review.get(k) for k in ("plan_id", "plan", "plan_en", "note", "qr", "warnings", "sending",
                                                    "doctor_pdf", "patient_pdf", "confirm")}
    return v


def render(s: Consult) -> str:
    """The stage view of the tab's CURRENT consultation. A generator still running for a dropped visit (Home, No,
    new consultation) renders the fresh one, never its own stale state."""
    cur = SESS.get(s.sid)
    if cur is not None:
        s = cur
    with s.lock:
        data = json.dumps(view(s), ensure_ascii=False)
    return fill(_STATE, data=html.escape(data, quote=True), cid=s.cid)


def poll_render(s: Consult | None) -> str | None:
    """For the output pump: re-check timer rules every TICK_S and return a fresh render when the brain's cards
    changed since the stage last saw them (cards arrive from the background copilot); None when nothing changed."""
    if s is None or s.brain.cards is None or s.screen != "live":
        return None
    now = time.time()
    if now - s.last_tick >= TICK_S:
        s.last_tick = now
        brain.tick(s.brain)
    if s.brain.cards.version == s.cards_seen and _LOC_VERSION[0] == s.loc_seen:
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


def notify(s: Consult, key: str):
    """One-off toast on the stage (shown once per id), in the doctor's language."""
    s.notice = {"id": s.notice["id"] + 1, "text": ui.t(s.doc_lang, key)}


# ------------------------------------------------------------------ who hears what (one rule for every speak path)
# Bayan only ever says the current consultation's utterance, in the listener's language. Anything else (an English
# fallback, a translation that came back in another language, an echo of the source) is shown, never spoken.
_SCRIPT_RANGES = {
    "deva": "\u0900-\u097F\uA8E0-\uA8FF", "arab": "\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF",
    "beng": "\u0980-\u09FF", "mlym": "\u0D00-\u0D7F", "taml": "\u0B80-\u0BFF", "telu": "\u0C00-\u0C7F",
    "geor": "\u10A0-\u10FF\u1C90-\u1CBF\u2D00-\u2D2F", "hang": "\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F",
    "jpan": "\u3040-\u30FF\u31F0-\u31FF\u3400-\u4DBF\u4E00-\u9FFF\uFF66-\uFF9F",
    "grek": "\u0370-\u03FF\u1F00-\u1FFF", "cyrl": "\u0400-\u052F",
    "latn": "A-Za-z\u00C0-\u024F\u1E00-\u1EFF",
}
_SCRIPT_RE = {k: re.compile(f"[{v}]") for k, v in _SCRIPT_RANGES.items()}
LANG_SCRIPT = {"ne": "deva", "hi": "deva", "ur": "arab", "ar": "arab", "bn": "beng", "ml": "mlym", "ta": "taml",
               "te": "telu", "ka": "geor", "ko": "hang", "ja": "jpan", "el": "grek", "ru": "cyrl", "uk": "cyrl",
               "bg": "cyrl"}  # everything else (en, tl, sw, id, es, fr, ...) is Latin


def listener_lang(s: Consult, to: str) -> str:
    """The language the listener hears in THIS consultation: the patient's (s.lang) or the doctor's (s.doc_lang)."""
    return s.lang if to == "patient" else s.doc_lang


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", " ", (text or "").lower()).strip()


def speakable(text: str, lang: str, source: str = "") -> bool:
    """Is `text` really in `lang`? At least a third of its letters (vowel signs included) in the language's script, so
    a drug name or "ECG" in Latin inside a Nepali sentence is fine but an untranslated English sentence is not; and not an
    echo of the source sentence. Same-script languages (tl/sw/id/en...) cannot be told apart by script; the echo check
    catches the common failure there."""
    import unicodedata
    letters = [c for c in text or "" if c.isalpha() or unicodedata.category(c).startswith("M")]
    if not letters:
        return False
    rx = _SCRIPT_RE[LANG_SCRIPT.get(lang, "latn")]
    if sum(1 for c in letters if rx.match(c)) * 3 < len(letters):
        return False
    src = _norm(source)
    return not (src and len(src.split()) >= 3 and _norm(text) == src)


def queue_speech(s: Consult, sp: Speech, source: str = "") -> bool:
    """Queue one utterance for the voice, stamped with this consultation. Refused (False; the text stays on screen)
    when it is not in the listener's language of this consultation."""
    want = listener_lang(s, sp.to)
    if sp.lang != want or not speakable(sp.text, sp.lang, source):
        print(f"[speak] not queued: to={sp.to} lang={sp.lang} want={want} kind={sp.kind} text={sp.text[:60]!r}", flush=True)
        return False
    sp.cid = s.cid
    with s.lock:
        s.pending.append(sp)
    return True


def _may_speak(s: Consult, sp: Speech) -> bool:
    return (alive(s) and s.screen in ("consent", "live") and bool(sp.cid) and sp.cid == s.cid
            and sp.lang == listener_lang(s, sp.to))


# App-generated English (notes, held headline, idiom notes, suggestions) -> the doctor's language.
_LOC: dict[str, str] = {}
_LOC_LOCK = threading.Lock()
LOC_SYSTEM = """Translate each English string into formal Modern Standard Arabic for a doctor's screen in a clinic in Qatar.
Rules: keep it short and clear; use the standard Arabic medical term; write medicine names in the Arabic script
doctors in the Gulf use (for example: البنسلين، أموكسيسيلين، باراسيتامول); keep every number, dose and unit exactly,
with Western digits (500 mg -> 500 ملغ); never add, drop or soften information.
Return ONLY a JSON object {"ar": [...]} with exactly one translation per input string, in the same order."""


def loc(s: Consult, texts: list[str]) -> list[str]:
    """Strings in the doctor's language (LLM once per string, cached for every visit). English: unchanged."""
    if s.doc_lang == "en":
        return list(texts)
    with _LOC_LOCK:
        need = [x for x in dict.fromkeys(texts) if x and x not in _LOC]
    if need:
        try:
            out = brain_llm.chat_json(LOC_SYSTEM, json.dumps(need, ensure_ascii=False), max_tokens=1500).get("ar")
            if isinstance(out, list) and len(out) == len(need):
                with _LOC_LOCK:
                    _LOC.update({k: str(v).strip() or k for k, v in zip(need, out)})
        except Exception as e:  # noqa: BLE001 - fall back to English rather than block the visit
            print(f"[loc] {type(e).__name__}: {e}", flush=True)
    with _LOC_LOCK:
        return [_LOC.get(x, x) for x in texts]


_LOC_VERSION = [0]   # bumped whenever background translations land (poll_render re-renders)
_LOC_PENDING: set = set()


def loc_soon(s: Consult, texts: list[str]) -> list[str]:
    """Non-blocking loc(): cached translations now, English for the rest while a background call fills the cache."""
    if s.doc_lang == "en":
        return list(texts)
    with _LOC_LOCK:
        need = [x for x in dict.fromkeys(texts) if x and x not in _LOC and x not in _LOC_PENDING]
        _LOC_PENDING.update(need)
        out = [_LOC.get(x, x) for x in texts]
    if need:
        def work():
            try:
                loc(s, need)
            finally:
                with _LOC_LOCK:
                    _LOC_PENDING.difference_update(need)
                _LOC_VERSION[0] += 1
        threading.Thread(target=work, name="bayan-loc", daemon=True).start()
    return out


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
    drug = key.split("|")[1] if "|" in key else next(
        (d["name"] for d in drugs if d.get("intent") == "prescribe"), "this medicine")
    head, pq, allergies = "", "", []
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
    if s.doc_lang != "en":  # the patient's words as the doctor saw them; the headline in the doctor's language
        for a in allergies if head else []:
            for e in a.get("evidence") or []:
                if e.get("utt") in s.shown:
                    pq = s.shown[e["utt"]]
                    break
        head = loc(s, [head])[0]
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
def set_turn(s: Consult, who: str):
    s.next_speaker = who
    s.turn_seq += 1


def _hear(s: Consult, sr: int, arr: np.ndarray, role: str = "") -> dict | None:
    """Worker ASR; None (and a gentle notice) when nothing usable was heard."""
    try:
        heard = talk.hear(sr, arr, s.lang, s.doc_lang, role)
    except Exception as e:  # noqa: BLE001
        print(f"[hear] {type(e).__name__}: {e}", flush=True)
        s.error = "err_voice_service"
        return None
    text = (heard.get("text") or "").strip()
    if heard.get("unclear") or (text and (_hallucinated(text) or garbled(text))):
        print(f"[hear] unclear={bool(heard.get('unclear'))} dropped: {text[:80]!r}", flush=True)
        text = ""
    if not text:
        with s.lock:
            s.processing = False
            if s.live in ("doctor", "patient"):
                s.tint = "n"
        notify(s, NOT_CAUGHT)
        return None
    heard["text"] = text
    return heard


MISMATCH_CONFIDENCE = 0.9  # the worker's language ID must be this sure before Bayan questions the doctor's choice
# ...and the clip long enough: on 1-2 s answers ("হ্যাঁ, গতকাল থেকে", "نعم، منذ أمس") VoxLingua107 was ~0.95 sure of the
# WRONG side (2 of 48 live calls). Short clips need near-certainty before the confirm prompt interrupts the doctor.
MISMATCH_MIN_SECONDS, MISMATCH_SHORT_CONFIDENCE = 2.0, 0.99
ROLES = ("doctor", "patient")


def _confidence(s: Consult, heard: dict, role: str) -> float:
    lid = heard.get("lid") or {}
    if role == "patient":
        return float(lid.get(s.lang, 0.0))
    return float(sum(v for k, v in lid.items() if k in ("en", "ar")))


def process_audio(s: Consult, sr: int, arr: np.ndarray, speaker: str = ""):
    """One tapped recording. `speaker` is whose turn the doctor selected; the worker transcribes with that
    role forced. Its own language ID is only a safety check: a confident disagreement asks the doctor first."""
    speaker = speaker if speaker in ROLES else ""
    heard = _hear(s, sr, arr, speaker)
    if heard is None or not alive(s):   # nothing usable, or the visit was dropped while the worker listened
        yield UI
        return
    role = heard.get("role")
    detected = heard.get("detected_role") or role
    if role not in ROLES or (not speaker and detected not in ROLES):
        # No role at all (old worker, odd reply): never guess a direction. Say it again.
        print(f"[hear] no usable role: role={role!r} detected={detected!r} speaker={speaker!r}", flush=True)
        notify(s, NOT_CAUGHT)
        yield UI
        return
    if speaker:
        conf = _confidence(s, heard, detected) if detected in ROLES else 0.0
        short = float(heard.get("audio_seconds") or 0.0) < MISMATCH_MIN_SECONDS
        if detected in ROLES and detected != speaker and conf >= (MISMATCH_SHORT_CONFIDENCE if short
                                                                     else MISMATCH_CONFIDENCE):
            with s.lock:
                s.confirm = {"selected": speaker, "detected": detected, "forced": bool(heard.get("role_forced")),
                             "engine_role": role, "text": heard["text"], "lang": heard.get("lang")}
                s.confirm_pcm = (sr, arr)
                s.live, s.tint, s.processing = "confirm", "n", False
            print(f"[hear] speaker mismatch: selected={speaker} detected={detected} lid={heard.get('lid')}", flush=True)
            yield UI
            return
        if role != speaker:
            # The worker did not transcribe with the chosen role forced (its text is in the other side's language):
            # translating it in the chosen direction would say the wrong thing. Ask for it again instead.
            print(f"[hear] role not forced: selected={speaker} engine={role}", flush=True)
            notify(s, NOT_CAUGHT)
            yield UI
            return
    src = heard.get("lang") or ("en" if role == "doctor" else s.lang)
    if role == "doctor" and src not in ("en", "ar"):
        src = s.doc_lang
    yield from process_text(s, role, heard["text"], src)


def resolve_confirm(s: Consult, take_detected: bool):
    """The doctor answered the mismatch question. Re-transcribe with the chosen role unless the first pass
    already used that role's engine."""
    c, pcm = s.confirm, s.confirm_pcm
    with s.lock:
        s.confirm, s.confirm_pcm = None, None
        s.live, s.processing = "idle", True
    if not c:
        s.processing = False
        yield UI
        return
    role = c["detected"] if take_detected else c["selected"]
    if role not in ROLES:
        s.processing = False
        yield UI
        return
    yield UI
    if role == c["engine_role"]:
        text, src = c["text"], c["lang"]
    else:
        heard = _hear(s, pcm[0], pcm[1], role)
        if heard is None or not alive(s):
            yield UI
            return
        if heard.get("role") != role:   # the worker did not honour the forced role: never translate the wrong way
            notify(s, NOT_CAUGHT)
            s.processing = False
            yield UI
            return
        text, src = heard["text"], heard.get("lang")
    if role == "doctor" and src not in ("en", "ar"):
        src = s.doc_lang
    yield from process_text(s, role, text, src or (s.doc_lang if role == "doctor" else s.lang))


def _cap(x: str) -> str:
    return x[:1].upper() + x[1:]


def process_text(s: Consult, role: str, text: str, src: str | None = None):
    """Translate one utterance, update the stage, and queue what Bayan should say.
    The doctor sees everything in their own language (s.doc_lang); the patient hears theirs (s.lang)."""
    if role not in ROLES or not alive(s):
        yield UI
        return
    s.error = ""
    if not text.strip() or garbled(text):  # safety net: nothing degenerate reaches the translator or the screen
        notify(s, NOT_CAUGHT)
        yield UI
        return
    if s.held:  # a new turn while a sentence is held: the held sentence is not spoken
        _discard_held(s, "not spoken: the conversation moved on")
    if role == "doctor":
        src = src if src in ("en", "ar") else s.doc_lang
        s.brain.doctor_lang = src
        if END_RE.search(text) or "إنهاء الاستشارة" in text:
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
            s.error, s.doctor_view["pending"] = "err_translate", False
            yield UI
            return
        if not alive(s):  # the visit was dropped while translating: nothing of it is recorded or said
            return
        english = text if src == "en" else (tr.get("english") or text)
        turn = s.brain.add_turn("doctor", src, text, english=english, translation=tr["translation"])
        s.shown[turn.id] = text
        tests = [t for t in tr.get("tests", []) if isinstance(t, str) and t.strip()]
        drugs = tr.get("drugs", [])
        hits = brain.prescription_gate(s.brain, drugs, english, turn.id) if drugs else []
        reason = _held_payload(s, hits, drugs, english, tr["translation"], turn.id) if hits else None
        if reason:
            reason["dq"] = text  # the doctor's own words
        en_notes = [("test", f"{_cap(_join(tests))} ordered")] if tests else []
        if reason:
            en_notes.append(("held", f"{_cap(reason['drug'])}: held, not said to the patient"))
        else:
            for d in drugs:
                name = (d.get("name") or "").strip()
                if not name or d.get("intent") == "mention":
                    continue
                if d.get("intent") == "stop":
                    en_notes.append(("drug", f"{_cap(name)} stopped"))
                    continue
                dose = d.get("dose") or (f"{d['dose_mg']:g} mg" if isinstance(d.get("dose_mg"), (int, float)) else "")
                en_notes.append(("drug", _cap(name) + (f" {dose}" if dose else "")))
        shown = loc(s, [n for _, n in en_notes])
        with s.lock:
            s.doctor_view = {"en": text, "native": tr["translation"], "pending": False}
            for (kind, _), txt in zip(en_notes, shown):
                add_note(s, kind, txt)
            if reason:
                turn.held = True
                s.held = reason
                s.live, s.tint = "held", "h"
            else:
                # Queued before the stage sees the new turn: the page keeps the turn switch until this is spoken.
                if tr["translation"].strip() and not queue_speech(
                        s, Speech(tr["translation"], s.lang, "patient", True, text, kind="turn"), source=text):
                    notify(s, "voice_unavailable")   # not in the patient's language: shown, never spoken
                set_turn(s, "patient")
        yield UI
        if not reason:
            brain.on_turn(s.brain, turn)  # a held sentence waits for the doctor's choice
        return

    # patient
    with s.lock:
        s.held = None
        s.live, s.tint = "patient", "p"
        s.patient_view = {"native": text, "en": "", "idiom": None, "note": "", "pending": True}
    yield UI
    tgt = s.doc_lang
    hint = ""
    try:  # a lexicon idiom in the patient's words: keep it as said so the doctor sees it (the card explains it)
        hits = idiom_index().match(text, "", s.lang)
        pre = hits[0]["entry"] if hits else None
    except Exception:  # noqa: BLE001
        pre = None
    if pre:
        hint = (f"the patient uses the cultural idiom '{pre.get('native')}' ({pre.get('romanized')}, literally "
                f"{pre.get('literal_en')}). Keep it in the translation as \"{pre.get('romanized')}\" so the doctor sees it; "
                f"do not translate it as a body part or object.")
    try:
        tr = talk.translate(text, "patient", s.lang, tgt, context=_context(s), hint=hint)
    except Exception as e:  # noqa: BLE001
        print(f"[translate] {type(e).__name__}: {e}", flush=True)
        s.error, s.patient_view["pending"] = "err_translate", False
        yield UI
        return
    if not alive(s):
        return
    shown_text = (tr.get("translation") or tr.get("english") or "").strip()  # in the doctor's language
    english = (tr.get("english") or shown_text).strip()                      # the record, rules and care plan
    turn = s.brain.add_turn("patient", s.lang, text, english=english, translation=english)
    s.shown[turn.id] = shown_text
    allergies = tr.get("allergies", [])
    if allergies:
        brain.record_allergies(s.brain, allergies, english, turn.id)
    brain.post_idioms(s.brain, turn)  # sync lexicon: idiom note + one red-flag-first "Ask next"
    subs = [(a.get("substance") or "").strip().lower() for a in allergies]
    shown = loc(s, [f"{_cap(x)} allergy" for x in subs if x])
    with s.lock:
        for txt in shown:
            add_note(s, "allergy", txt)
        s.patient_view = {"native": text, "en": shown_text, "idiom": None, "note": "", "pending": False, "utt": turn.id}
        # The doctor hears the patient's words in their own language (worker voice; text stays on screen). Only the
        # translation itself: an English rendering is never read out in an Arabic voice, nor an echo of the patient.
        said = (tr.get("translation") or "").strip() or (english if s.doc_lang == "en" else "")
        if said:
            queue_speech(s, Speech(said, s.doc_lang, "doctor", False, shown_text, kind="turn"), source=text)
        set_turn(s, "doctor")
    brain.on_turn(s.brain, turn)
    yield UI


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
        s.error = "err_ask"
        return True
    with s.lock:
        sug["status"] = "asked"
        turn = s.brain.add_turn("bayan", "en", q, english=q, translation=tr["translation"], kind="ask")
        shown_q = loc(s, [q])[0]
        s.doctor_view = {"en": shown_q, "native": tr["translation"], "pending": False}
        s.live, s.tint, s.held = "doctor", "d", None
        if not queue_speech(s, Speech(tr["translation"], s.lang, "patient", True, shown_q, kind="ask"), source=q):
            notify(s, "voice_unavailable")
        set_turn(s, "patient")
    brain.on_turn(s.brain, turn)
    return True


def held_else(s: Consult):
    """"Say something else": the held sentence is discarded (never spoken, withdrawn from the plan)."""
    _discard_held(s, "sentence withdrawn by the clinician (said something else)")
    with s.lock:
        s.held = None
        s.live, s.tint = "idle", "n"
        set_turn(s, "doctor")


def held_anyway(s: Consult):
    """"Speak it anyway": the clinician overrides the alert; recorded in the brain's audit, then spoken."""
    with s.lock:
        h = s.held
        if not h:
            return
        s.held = None
    brain.override_turn(s.brain, h.get("utt", ""), h.get("cards") or [], "spoken anyway by clinician")
    with s.lock:
        add_note(s, "override", loc(s, [f"{_cap(h['drug'])} spoken anyway"])[0])
        print(f"[audit] override {h['rule']} sid={s.sid[:6]} drug={h['drug']}", flush=True)
        s.live, s.tint = "doctor", "d"
        if not queue_speech(s, Speech(h["translation"], s.lang, "patient", True, h["dq"], kind="override"), source=h["dq"]):
            notify(s, "voice_unavailable")
        set_turn(s, "patient")


def again(s: Consult, slow: bool):
    """Say it again / Slower: the last thing said to the patient in THIS consultation (the clip comes from the cache;
    Slower is the same clip replayed slower by the page)."""
    sp = s.last_speech
    if sp and sp.to == "patient" and sp.cid == s.cid:
        queue_speech(s, Speech(sp.text, sp.lang, "patient", sp.caption, sp.en, slow=slow, kind="again"))


def pop_pending(s: Consult) -> Speech | None:
    with s.lock:
        return s.pending.pop(0) if s.pending else None


# ------------------------------------------------------------------ speaking
def _est_seconds(text: str, lang: str, slow: bool) -> float:
    return 0.8 + len(text) / (CHARS_PER_SEC.get(lang, 11.0) * (0.65 if slow else 1.0))


def _begin_speech(s: Consult, sp: Speech, dur: float | None, audio: bool = True):
    with s.lock:
        s.speaking, s.processing = True, False
        s.last_speech = sp if sp.to == "patient" else s.last_speech
        if sp.caption and sp.to == "patient":
            rate = (len(sp.text) / max(0.6, dur - 0.7)) if dur else 13.0 * (0.65 if sp.slow else 1.0)
            s.caption = {"native": sp.text, "en": sp.en, "key": uuid.uuid4().hex[:8], "rate": round(rate, 2), "audio": audio}
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


# ------------------------------------------------------------------ speech out (streamed to the page)
# Finished worker clips, so consent and "Say it again" / "Slower" play at once without a GPU call. Key:
# (scope, text, lang, voice): scope is the consultation id (a visit's sentences are never served to another visit, and
# erase() drops them) or "consent" for the fixed consent lines; voice = worker URL + voice version + failure epoch.
# Never cached: a clip that failed or was cut off, one too short or silent for its text, mixed sample rates, or one
# that was streaming when the worker failed (a failure clears the cache and bumps the epoch).
CLIP_MAX = 48
CLIP_MAX_BYTES = 24 << 20
CLIP_TTL_S = 1800.0
CLIP_MIN_S = 0.3
_CLIPS: "OrderedDict[tuple, tuple]" = OrderedDict()   # key -> (sr, int16, stored_at)
_CLIPS_LOCK = threading.Lock()
_VOICE_EPOCH = [0]


def _voice_id() -> tuple:
    return (talk.WORKER_URL, os.environ.get("BAYAN_VOICE_VERSION", ""), _VOICE_EPOCH[0])


def voice_failed() -> None:
    """The worker failed (down, rebooting, cut a stream): nothing synthesised before now is trusted any more."""
    with _CLIPS_LOCK:
        _VOICE_EPOCH[0] += 1
        _CLIPS.clear()


def drop_clips(scope: str) -> None:
    with _CLIPS_LOCK:
        for k in [k for k in _CLIPS if k[0] == scope]:
            del _CLIPS[k]


def _clip_get(key: tuple):
    with _CLIPS_LOCK:
        hit = _CLIPS.get(key)
        if hit and time.time() - hit[2] > CLIP_TTL_S:
            del _CLIPS[key]
            return None
        if hit:
            _CLIPS.move_to_end(key)
        return hit


def _clip_put(key: tuple, sr: int, pcm: np.ndarray, text: str, lang: str) -> bool:
    if pcm.size / sr < max(CLIP_MIN_S, 0.25 * _est_seconds(text, lang, False)):
        return False                                   # far too short for the text: a cut or garbage clip
    if int(np.abs(pcm.astype(np.int32)).max()) < 300:
        return False                                   # silence
    with _CLIPS_LOCK:
        if key[3] != _voice_id():
            return False                               # the worker failed while this clip was streaming
        _CLIPS[key] = (sr, pcm, time.time())
        _CLIPS.move_to_end(key)
        while len(_CLIPS) > CLIP_MAX or sum(v[1].nbytes for v in _CLIPS.values()) > CLIP_MAX_BYTES:
            _CLIPS.popitem(last=False)
    return True


def _to_i16(f32) -> np.ndarray:
    return (np.clip(np.asarray(f32, dtype=np.float32).reshape(-1), -1, 1) * 32767).astype(np.int16)


def _half_rate(sr: int, pcm: np.ndarray) -> tuple[int, np.ndarray]:
    """44.1/48 kHz speech -> half rate (pairwise mean): half the bytes to the browser, no audible loss."""
    if sr < 32000:
        return sr, pcm
    n = pcm.size // 2 * 2
    return sr // 2, ((pcm[:n:2].astype(np.int32) + pcm[1:n:2].astype(np.int32)) // 2).astype(np.int16)


def voice_chunks(text: str, lang: str, scope: str):
    """(sr, int16) chunks as the voice worker produces them; cached (under `scope`) once complete and sane."""
    key = (scope, text, lang, _voice_id())
    hit = _clip_get(key)
    if hit:
        sr, pcm, _ = hit
        for i in range(0, pcm.size, sr):   # 1 s pieces
            yield sr, pcm[i:i + sr]
        return
    if lang not in talk.WORKER_TTS_LANGS:
        return
    parts, rates = [], set()
    try:
        for sr, f in talk.speak_chunks(text, lang):
            sr, pcm = _half_rate(sr, _to_i16(f))
            if pcm.size == 0:
                continue
            parts.append(pcm)
            rates.add(sr)
            yield sr, pcm
    except Exception as e:
        if not _refused(e):   # a refusal (no voice / wrong script) is not a worker failure
            voice_failed()
        raise
    if parts and len(rates) == 1:   # reached only when the stream completed (a closed generator never stores)
        _clip_put(key, rates.pop(), np.concatenate(parts), text, lang)


def _refused(e: BaseException) -> bool:
    nv = getattr(talk, "NoVoice", None)
    return nv is not None and isinstance(e, nv)


def sentence_gaps(pcm: np.ndarray, sr: int) -> list[int]:
    """Sample positions (middles) of the pauses between sentences: interior runs of zeros >= SLOW_GAP_MIN_S."""
    quiet = (np.abs(pcm.astype(np.int32)) <= 2).astype(np.int8)
    if not quiet.any():
        return []
    d = np.diff(np.concatenate(([0], quiet, [0])))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    min_len = int(SLOW_GAP_MIN_S * sr)
    return [int((a + b) // 2) for a, b in zip(starts, ends) if b - a >= min_len and a > 0 and b < pcm.size]


def slow_seconds(n: int, sr: int, gaps: int) -> float:
    """How long the page's slow replay lasts: the clip at SLOW_RATE plus the stretched sentence gaps."""
    return n / sr / SLOW_RATE + gaps * SLOW_GAP_EXTRA_S


def _audio_item(s: Consult, key: str, i: int, sr: int, pcm: np.ndarray, slow: bool = False) -> str:
    import base64
    return (f"<i class='bz-au' data-c='{s.cid}' data-k='{key}' data-i='{i}' data-sr='{sr}'"
            + (f" data-rate='{SLOW_RATE}'" if slow else "")
            + f" data-p='{base64.b64encode(pcm.astype('<i2').tobytes()).decode('ascii')}'></i>")


def speak_clip(s: Consult, sp: Speech, voice_on: bool = True):
    """Stream one utterance to the page's WebAudio player. Yields UI, or ("say", audio_html) when the
    stage and the (cumulative, append-only) audio must go out together. Returns after playback ends.
    Speaks only the current consultation's utterance in its listener's language (else: silent, nothing yielded).
    Every audio item carries the consultation id (data-c): the page discards items of any other consultation.
    "Slower" (sp.slow) streams the same clip marked with data-rate: the page replays it slower, pitch preserved."""
    if not _may_speak(s, sp):
        print(f"[speak] refused: cid={sp.cid} current={s.cid} lang={sp.lang} to={sp.to} alive={alive(s)} "
              f"screen={s.screen}", flush=True)
        return
    key = uuid.uuid4().hex[:10]
    scope = "consent" if sp.to == "patient" and sp.text == s.consent_native else s.cid
    audio_html, t_first, total, i, parts = "", None, 0.0, 0, []
    if voice_on:
        try:
            for sr, pcm in voice_chunks(sp.text, sp.lang, scope):
                if not _may_speak(s, sp):
                    return  # the visit ended or was dropped while we were synthesising: say nothing more
                if pcm.size == 0:
                    continue
                audio_html += _audio_item(s, key, i, sr, pcm, sp.slow)
                i += 1
                total += pcm.size / sr
                if sp.slow:
                    parts.append((sr, pcm))
                if t_first is None:
                    t_first = time.time()
                    _begin_speech(s, sp, None)
                yield "say", audio_html
        except Exception as e:  # noqa: BLE001 - keep the visit going in text
            print(f"[speak] {type(e).__name__}: {e}", flush=True)
            if _refused(e):
                notify(s, "voice_unavailable")   # this sentence only: the worker would not voice it in sp.lang
            else:
                s.error = "err_voice_off"
    if t_first is None:
        if sp.to == "doctor" or not _may_speak(s, sp):
            return
        _begin_speech(s, sp, None, audio=False)   # text only: the caption shows "voice unavailable"
        yield "say", None
        time.sleep(min(8.0, _est_seconds(sp.text, sp.lang, sp.slow)))
    else:
        end = f"data-end='1'"
        if sp.slow:   # the page plays a slow replay once it has every chunk (from the cache: at once)
            sr0, all_pcm = parts[0][0], np.concatenate([p for _, p in parts])
            gaps = sentence_gaps(all_pcm, sr0) if all(r == sr0 for r, _ in parts) else []
            total = slow_seconds(all_pcm.size, sr0, len(gaps))
            end += (f" data-rate='{SLOW_RATE}' data-gapx='{SLOW_GAP_EXTRA_S}'"
                    f" data-gaps='{','.join(str(g) for g in gaps)}'")
            t_first = time.time()
        audio_html += f"<i class='bz-au' data-c='{s.cid}' data-k='{key}' data-i='{i}' {end} data-dur='{total:.3f}'></i>"
        if not _may_speak(s, sp):
            return
        yield "say", audio_html
        # The page starts ~0.15 s after the first chunk lands; keep the stage in "speaking" until it is done.
        time.sleep(max(0.0, t_first + total + 0.35 - time.time()))
    yield from _settle(s)
    _end_speech(s, sp)
    yield UI


SETTLE_SECONDS = 3.0


def _settle(s: Consult):
    """Breathing room: the caption stays up for 3 s after Bayan finishes, then the stage moves on.
    Ends early on any tap/key (settle_skip), queued speech (Say it again), or the visit ending."""
    with s.lock:
        s.settling, s.settle_cancel = True, False
    yield UI
    t_end = time.time() + SETTLE_SECONDS
    while (time.time() < t_end and not s.settle_cancel and not s.pending
           and SESS.get(s.sid) is s and s.screen in ("consent", "live")):
        time.sleep(0.05)
    with s.lock:
        s.settling = False


# ------------------------------------------------------------------ end of visit
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


_RULE_PREFIX = re.compile(r"^[A-Z]+(?:-[A-Z0-9]+)+ \((?:critical|caution|info)\):\s*")
_QUOTE_PAREN = re.compile(r"\s*\(“[^”]*”(?:,\s*\d\d:\d\d)?\)")


def _plain_reason(reason: str) -> str:
    """'ALG-PEN-01 (critical): Penicillin allergy reported (“...”, 00:19). Amoxicillin is a penicillin.'
    -> 'Penicillin allergy reported. Amoxicillin is a penicillin.' (first rule only)."""
    first = re.split(r"; (?=[A-Z]+(?:-[A-Z0-9]+)+ \()", reason or "")[0]
    return re.sub(r"\.\.+", ".", _QUOTE_PAREN.sub("", _RULE_PREFIX.sub("", first))).strip()


def _review_warnings(out: dict) -> list[str]:
    """What the doctor must know before sending, in plain words. Internal notes (dropped note lines, layout
    fallbacks, emergency-number resets…) stay in the doctor PDF's audit trail, not on the review screen."""
    plan = out.get("care_plan") or {}
    ws = []
    for e in plan.get("excluded") or []:
        name = str(e.get("name") or "").strip().capitalize()
        if name:
            ws.append(f"{name} was left off the patient's sheet. {_plain_reason(e.get('reason', ''))}".strip())
    for w in out.get("warnings") or []:
        if not isinstance(w, str):
            continue
        if w.startswith("Removed ") and "not in the doctor's final prescription" in w:
            ws.append(w)
        elif w.startswith("Translation of") or "translation; they are shown in English" in w:
            ws.append(w)
        elif "a translated line has numbers not in the prescription" in w:
            ws.append(w)
    return list(dict.fromkeys(ws))


def end_visit(s: Consult, base_url: str):
    """Generator: wrap screen with a live checklist (copilot flush + agentic wrap-up), then the review screen."""
    if s.held:
        _discard_held(s, "not spoken: the consultation ended")
    with s.lock:
        s.screen, s.live, s.tint, s.speaking, s.held, s.error = "wrap", "idle", "n", False, None, ""
        s.pending.clear()
        s.processing, s.settling = False, False
        # labels are built on the page in the doctor's language: "Care plan, in <lang>", "Checking ... safety rules"
        s.steps = [{"k": "plan", "lang": s.doc_lang, "state": "doing"}, {"k": "plan", "lang": s.lang, "state": "todo"},
                   {"k": "safety", "state": "todo"}]
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
        s.error = "err_plan"
    _advance_steps(s, b.trace[start:])
    plan = out.get("care_plan") or {"lang": s.lang, "medicines": [], "avoid": [], "red_flags": [], "advice": [],
                                     "follow_up": {}, "emergency": "999"}
    plan_doc = careplan.plan_text_for(plan, s.doc_lang)  # Arabic review text in Arabic mode (one LLM call)
    warnings = loc(s, _review_warnings(out))
    for st in s.steps:
        st["state"] = "done"
    yield UI
    time.sleep(0.6)
    token = out.get("token") or secrets.token_urlsafe(16)
    dtoken = secrets.token_urlsafe(16)
    if out.get("out_dir"):
        careplan.register_files(token, Path(out["out_dir"]), ["care_plan.pdf", "care_plan.wav"])
        careplan.register_files(dtoken, Path(out["out_dir"]), ["doctor_report.pdf"])
        s.file_tokens = [token, dtoken]
    pid = careplan.create(s.lang, plan, token=token if out.get("patient_pdf") else None)
    url = f"{base}/plan/{pid}"
    with s.lock:
        s.review = {"plan_id": pid, "plan": plan_doc, "plan_en": careplan.plan_text(plan), "note": out.get("note_md") or "",
                    "url": url, "qr": careplan.qr_svg(url), "warnings": warnings, "sending": False, "confirm": False,
                    "doctor_pdf": f"{base}/files/{dtoken}/doctor_report.pdf" if out.get("doctor_pdf") else "",
                    "patient_pdf": f"{base}/files/{token}/care_plan.pdf" if out.get("patient_pdf") else ""}
        s.screen = "review"
    yield UI


def _plan_conflicts(s: Consult, text: str) -> list[str]:
    """Cheap re-check of an edited plan: medicines in it that share a class with a recorded allergy."""
    from .brain.vocab import classes_of
    try:
        drugs = talk.translate(text, "doctor", s.doc_lang, "en").get("drugs") or []
    except Exception as e:  # noqa: BLE001
        print(f"[plan check] {type(e).__name__}: {e}", flush=True)
        return []
    with s.brain.lock:
        allergies = list(s.brain.state.get("allergies") or [])
    out = []
    for d in drugs:
        if d.get("intent") == "stop":
            continue
        name = d["name"]
        d_cls = set(classes_of(name)) | {name}
        for a in allergies:
            sub = str(a.get("substance") or "").lower()
            if sub and d_cls & (set(a.get("class") or []) | set(classes_of(sub)) | {sub}):
                out.append(f"The edited plan has {name}; the patient reported {_article(sub)} {sub} allergy.")
    return loc(s, list(dict.fromkeys(out)))


def _to_english(text: str, lang: str) -> str:
    if lang == "en" or not text.strip():
        return text
    try:
        return brain_llm.chat_text(careplan.TRANSLATE_PLAN_SYSTEM.format(lang="English"), text, max_tokens=2500).strip()
    except Exception:  # noqa: BLE001
        return text


def approve(s: Consult, text: str = "", note: str | None = None, force: bool = False):
    """Approve and send. The doctor gives the plan: if they edited the review text, their text becomes the plan
    (re-translated for the patient, digits and drug names exact; /plan and the patient PDF are rendered from it and
    the doctor PDF records the edit). Unchanged: the wrap-up agent's structured, rule-checked plan goes out as is.
    An edited plan is re-checked against recorded allergies first; a conflict asks for a second tap."""
    if s.screen != "review" or not s.review:
        return
    text = (text or "").replace("\r\n", "\n").strip()
    edited = bool(text) and text != (s.review.get("plan") or "").strip()
    s.review["sending"] = True
    yield UI
    b = s.brain
    with b.lock:
        out_dir = b.outputs.get("out_dir")
    if edited:
        if not force:
            conflicts = _plan_conflicts(s, text)
            if conflicts:
                s.review.update(warnings=conflicts, confirm=True, sending=False)
                yield UI
                return
        try:
            native = careplan.translate_plan(text, s.lang) if s.lang != s.doc_lang else text
        except Exception as e:  # noqa: BLE001
            print(f"[approve translate] {type(e).__name__}: {e}", flush=True)
            native = ""
        careplan.set_text(s.review["plan_id"], text, native, s.doc_lang)
        english = _to_english(text, s.doc_lang)
        with b.lock:
            base_note = (b.outputs.get("note_md") or s.review.get("note") or "").rstrip()
        note = base_note + "\n\n## Care plan (edited by the doctor before sending)\n" + english
        if out_dir:
            try:
                from .outputs.report import render_plain_pdf
                title = ui.t("en", "rev_label")
                render_plain_pdf(title, (native + "\n\n" if native and native != text else "") + text,
                                 Path(out_dir) / "care_plan.pdf")
            except Exception as e:  # noqa: BLE001
                print(f"[approve] patient PDF re-render failed: {type(e).__name__}: {e}", flush=True)
        s.review["plan"] = text
    note = (note or "").replace("\r\n", "\n").strip()
    with b.lock:
        if note and note != (b.outputs.get("note_md") or "").strip():
            b.outputs["note_md"], b.outputs["note_edited"] = note, True
            s.review["note"] = note
        if edited:
            b.outputs["plan_edited_by_doctor"] = True
        b.outputs["approved_at"] = datetime.now().isoformat(timespec="seconds")
        note_md, plan = b.outputs.get("note_md") or "", b.outputs.get("care_plan")
    if out_dir:
        try:
            from .outputs.report import render_doctor_report
            render_doctor_report(b, note_md, Path(out_dir) / "doctor_report.pdf", care_plan=plan)
            (Path(out_dir) / "note.md").write_text(note_md, encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - the earlier PDF stays
            print(f"[approve] doctor PDF re-render failed: {type(e).__name__}: {e}", flush=True)
    careplan.approve(s.review["plan_id"])
    with s.lock:
        s.review["sending"], s.review["confirm"] = False, False
        s.screen, s.tint = "sent", "p"
    yield UI


# ------------------------------------------------------------------ demo (golden path, text turns)
DEMO_SCRIPT = [
    ("doctor", "Do you have any allergies to medicines?"),
    ("patient", "एकपटक पेनिसिलिन सुई लगाउँदा मेरो शरीर फुलेर आयो।"),
    ("patient", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ, काम गर्दा झन् बढ्छ।"),
    ("ask", None),
    ("doctor", "Amoxicillin 500 three times a day, and you can go home."),
    ("held_else", None),
    ("doctor", "Let’s not use amoxicillin. Take paracetamol 1 g up to three times a day. "
               "We will also check your heart with an ECG and a blood test."),
    ("end", None),
]
