"""Bayan AI · delivery: WhatsApp click-to-chat, sms: URI, and the care plan read aloud as one WAV.

No business API is needed: a person taps Send on the prefilled WhatsApp / SMS message (docs/02 §F5b–F5c).
Phone numbers are used to build the link and are never stored.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import numpy as np

from . import labels

GAP_S = 0.4


def _digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def wa_link(text: str, phone: str | None = None) -> str:
    """https://wa.me/<digits>?text=… (or wa.me/?text=… to let staff pick the chat)."""
    digits = _digits(phone)
    return f"https://wa.me/{digits}?text={quote(text or '', safe='')}"


def sms_link(text: str, phone: str | None = None) -> str:
    """RFC 5724 sms: URI with a prefilled body; keeps a leading + on international numbers."""
    digits = _digits(phone)
    number = ("+" + digits) if digits and (phone or "").strip().startswith("+") else digits
    return f"sms:{number}?body={quote(text or '', safe='')}"


def audio_lines(care_plan: dict) -> list[str]:
    """Native-language lines to read aloud, in reading order. Each medicine is said twice (docs/02 §F5d)."""
    lab = labels(care_plan.get("lang", "en"))
    out: list[str] = [care_plan.get("title_native") or lab["title"]]
    meds = care_plan.get("medicines") or []
    if meds:
        out.append(lab["medicines"])
    for m in meds:
        title = m.get("title_native") or m.get("title_en") or m.get("name") or ""
        line = m.get("note_native") or m.get("note_en") or ""
        if title or line:
            out += [f"{title}. {line}".strip(". ")] * 2   # each medicine is said twice
    avoid = care_plan.get("avoid") or []
    if avoid:
        out.append(lab["avoid"])
    out += [a.get("native") or a.get("en") or "" for a in avoid]
    other = list(care_plan.get("advice") or [])
    fu = care_plan.get("follow_up") or {}
    if fu.get("en") or fu.get("native"):
        other.append(fu)
    if other:
        out.append(lab["other"])
    out += [a.get("native") or a.get("en") or "" for a in other]
    flags = care_plan.get("red_flags") or []
    if flags:
        out.append(lab["red_flags"].rstrip(":："))
        out += [f.get("native") or f.get("en") or "" for f in flags]
    return [s.strip() for s in out if s and s.strip()]


def _resample(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to or len(audio) == 0:
        return audio
    n = int(round(len(audio) * sr_to / sr_from))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def care_plan_audio(care_plan: dict, speak_fn: Callable[[str, str], tuple | None] | None, path) -> str | None:
    """Speak each native line with speak_fn(text, lang) -> (sr, float32 array) | None, join with 0.4 s gaps, write
    one WAV. Returns the path, or None when the language has no voice (or nothing could be spoken)."""
    if speak_fn is None:
        return None
    import soundfile as sf

    lang = care_plan.get("lang", "en")
    sr_out: int | None = None
    pieces: list[np.ndarray] = []
    for line in audio_lines(care_plan):
        try:
            voiced = speak_fn(line, lang)
        except Exception:  # noqa: BLE001 - one failed sentence must not lose the whole recording
            continue
        if voiced is None:
            if not pieces:
                return None  # speak_fn has no voice for this language
            continue
        sr, audio = voiced
        audio = np.asarray(audio, dtype=np.float32).reshape(-1) if np.ndim(audio) <= 1 else \
            np.asarray(audio, dtype=np.float32).mean(axis=1)
        if sr_out is None:
            sr_out = int(sr)
        audio = _resample(audio, int(sr), sr_out)
        if pieces:
            pieces.append(np.zeros(int(GAP_S * sr_out), dtype=np.float32))
        pieces.append(audio)
    if not pieces or sr_out is None:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(np.concatenate(pieces), -1.0, 1.0), sr_out, subtype="PCM_16")
    return str(path)
