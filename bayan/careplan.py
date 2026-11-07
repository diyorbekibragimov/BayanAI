"""Patient care plan hand-off: the review text, the expiring /plan/<id> page, its QR code and the PDF files.

The plan itself is built by the wrap-up agent (bayan.brain.wrapup: structured, every medicine re-checked by the
rule engine, translated with the numbers verified). This module only presents it, with the same content and wording
as the patient PDF (bayan.outputs.report): Your medicines, Daily schedule (regular medicines), Do not take, Other
instructions, Call 999 or come back now if.

Privacy: plans live in memory only and expire after PLAN_TTL seconds. Files are served by unguessable token from the
consultation's retention folder (whitelisted names only); an approved plan keeps an in-memory copy of the patient
PDF so the patient's link outlives the doctor's session (which erases its folder).
"""

from __future__ import annotations

import copy
import html
import os
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

import segno

from .outputs import RTL_LANGS, labels
from .web import fill, read

PLAN_TTL = 24 * 3600
# Links on the patient's page are absolute to the Space's public URL (a phone opens them from the QR page).
PUBLIC_BASE = f"https://{os.environ['SPACE_HOST']}" if os.environ.get("SPACE_HOST") else ""
DOWNLOAD = {"ne": "PDF डाउनलोड गर्नुहोस्", "hi": "PDF डाउनलोड करें", "ur": "PDF ڈاؤن لوڈ کریں", "bn": "PDF ডাউনলোড করুন",
            "ml": "PDF ഡൗൺലോഡ് ചെയ്യുക", "tl": "I-download ang PDF", "ta": "PDF பதிவிறக்கவும்", "sw": "Pakua PDF",
            "ar": "تنزيل ملف PDF"}


from .langs import MORE as _MORE  # noqa: E402 - the "More…" languages bring their own button text

DOWNLOAD.update({code: v["download"] for code, v in _MORE.items()})


def download_button(pdf_url: str, lang: str) -> str:
    """A big "Download PDF" button: the patient's language first, English beneath."""
    native = DOWNLOAD.get(lang, "")
    d = " dir='rtl'" if lang in RTL_LANGS or lang == "ar" else ""
    inner = (f"<span lang='{lang}'{d}>{_e(native)}</span><small>Download PDF</small>" if native else "Download PDF")
    return f"<p><a class='btn' href='{_e(pdf_url)}' download='care_plan.pdf' type='application/pdf'>{inner}</a></p>"
PLANS: dict[str, dict] = {}
FILES: dict[str, dict] = {}   # token -> {"dir": Path, "names": set, "blobs": {name: bytes}, "expires": float}
_LOCK = threading.Lock()
MEDIA = {"care_plan.pdf": "application/pdf", "doctor_report.pdf": "application/pdf", "care_plan.wav": "audio/wav"}
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
SLOTS = ("wake", "breakfast", "lunch", "dinner", "bedtime")


# ------------------------------------------------------------------ review text (doctor)
def plan_text(plan: dict) -> str:
    """The care plan as the doctor reviews it: English first, the patient-language line beneath each item. Same
    content as the patient PDF."""
    lang = plan.get("lang", "en")
    L, E = labels(lang), labels("en")
    nat = lang != "en"
    out: list[str] = []

    def head(key: str):
        out.extend(["", E[key] + (f"  ·  {L[key]}" if nat and L[key] != E[key] else "")])

    def item(en: str, native: str = ""):
        if en:
            out.append(f"- {en}")
        if nat and native:
            out.append(f"  {native}")

    meds = plan.get("medicines") or []
    if meds:
        head("medicines")
        for m in meds:
            item(f"{m.get('title_en') or m.get('name') or ''}: {m.get('note_en') or ''}".strip(": "),
                 " ".join(x for x in (m.get("title_native") or "", m.get("note_native") or "") if x))
    if plan.get("avoid"):
        head("avoid")
        for a in plan["avoid"]:
            item(a.get("en", ""), a.get("native", ""))
    other = list(plan.get("advice") or [])
    fu = plan.get("follow_up") or {}
    if fu.get("en") or fu.get("native"):
        other.append(fu)
    if other:
        head("other")
        for a in other:
            item(a.get("en", ""), a.get("native", ""))
    head("red_flags")
    for f in plan.get("red_flags") or []:
        item(f.get("en", ""), f.get("native", ""))
    if not plan.get("red_flags"):
        out.append(f"- Call {plan.get('emergency') or '999'}.")
    return "\n".join(out).strip()


# ------------------------------------------------------------------ doctor edits (the doctor gives the plan)
TRANSLATE_PLAN_SYSTEM = """Translate this patient care plan faithfully into {lang}, in its native script.
Keep the same layout: one item per line, headings on their own lines, blank lines kept, lines starting with "- " kept.
Keep every drug name recognisable and every number, dose, unit and frequency exact, written with Western digits.
Use simple everyday words. Return only the translation."""

LOCALIZE_PLAN_SYSTEM = """This care plan text mixes English lines with lines in the patient's language. Rewrite ONLY the
English parts into formal Modern Standard Arabic for the doctor; copy every line that is in another language unchanged.
Keep the layout, the "- " bullets, every drug name (Arabic script as Gulf doctors write it), every number, dose, unit and
frequency exactly, with Western digits. Return only the text."""


def translate_plan(text: str, lang: str) -> str:
    """The doctor's own plan text in another language (patient's language, or Arabic for the doctor)."""
    from .brain import llm
    from .talk import LANG_NAMES
    if not (text or "").strip() or lang == "en":
        return text
    return llm.chat_text(TRANSLATE_PLAN_SYSTEM.format(lang=LANG_NAMES.get(lang, lang)), text, max_tokens=2500).strip()


def plan_text_for(plan: dict, doc_lang: str) -> str:
    """plan_text() for the doctor's language: English review lines become Arabic in Arabic mode."""
    from .brain import llm
    text = plan_text(plan)
    if doc_lang != "ar" or not text.strip():
        return text
    try:
        out = llm.chat_text(LOCALIZE_PLAN_SYSTEM, text, max_tokens=2500).strip()
        return out or text
    except Exception as e:  # noqa: BLE001 - the English review text is still correct
        print(f"[plan ar] {type(e).__name__}: {e}", flush=True)
        return text


def set_text(pid: str, doc_text: str, native_text: str, doc_lang: str) -> None:
    """The doctor edited the plan: their text (and its translation) replaces the structured plan on /plan."""
    with _LOCK:
        rec = PLANS.get(pid)
        if rec:
            rec.update(text_doc=doc_text, text_native=native_text, doc_lang=doc_lang, edited=True)


# ------------------------------------------------------------------ store
def _purge():
    now = time.time()
    for k in [k for k, v in PLANS.items() if v["expires"] < now]:
        PLANS.pop(k, None)
    for k in [k for k, v in FILES.items() if v["expires"] < now]:
        FILES.pop(k, None)


def create(lang: str, plan: dict, token: str | None = None) -> str:
    """Store the structured plan (not yet visible to the patient). `token` = the patient-file token (PDF link)."""
    with _LOCK:
        _purge()
        pid = secrets.token_urlsafe(18)
        PLANS[pid] = {"lang": lang, "plan": copy.deepcopy(plan), "token": token, "approved": False,
                      "created": time.time(), "expires": time.time() + PLAN_TTL}
        return pid


def approve(pid: str) -> None:
    """The doctor approved: the page goes live, and the patient files are copied into memory so they outlive the
    doctor's session."""
    with _LOCK:
        rec = PLANS.get(pid)
        if not rec:
            return
        rec.update(approved=True, approved_at=time.time())
        entry = FILES.get(rec.get("token") or "")
    if entry:
        blobs = {}
        for name in entry["names"]:
            p = _safe_path(entry, name)
            if p is not None and p.is_file():
                blobs[name] = p.read_bytes()
        with _LOCK:
            entry["blobs"] = blobs
            entry["expires"] = rec["expires"]


def get(pid: str) -> dict | None:
    with _LOCK:
        _purge()
        return PLANS.get(pid)


def qr_svg(url: str) -> str:
    q = segno.make(url, error="m")
    n = q.symbol_size(scale=1, border=0)[0]
    svg = q.svg_inline(scale=1, border=0, dark="#173430", light=None)
    return re.sub(r'<svg[^>]*?width="\d+" height="\d+"',
                  f'<svg viewBox="0 0 {n} {n}" width="232" height="232" shape-rendering="crispEdges"', svg, count=1)


# ------------------------------------------------------------------ files (token -> retention folder)
def register_files(token: str, directory: Path, names: list[str], ttl: float = PLAN_TTL) -> None:
    """Serve these whitelisted file names of one consultation folder under /files/<token>/<name>."""
    if not _TOKEN.match(token or ""):
        raise ValueError("unsafe token")
    with _LOCK:
        FILES[token] = {"dir": Path(directory).resolve(), "names": {n for n in names if n in MEDIA},
                        "blobs": {}, "expires": time.time() + ttl}


def forget_files(tokens: list[str]) -> None:
    """Session reset / garbage collection: drop the doctor-side tokens. A token whose files were copied into
    memory at approval (the patient's) stays until the plan expires."""
    with _LOCK:
        for t in tokens or []:
            e = FILES.get(t)
            if e is not None and not e.get("blobs"):
                FILES.pop(t, None)


def _safe_path(entry: dict, name: str) -> Path | None:
    d = entry.get("dir")
    if d is None or name not in entry["names"]:
        return None
    p = (d / name).resolve()
    return p if p.parent == d else None


def open_file(token: str, name: str) -> tuple[bytes, str] | None:
    """(bytes, media type) for a registered token + whitelisted name, else None. No other path is reachable."""
    if not _TOKEN.match(token or "") or name not in MEDIA:
        return None
    with _LOCK:
        _purge()
        entry = FILES.get(token)
        if entry is None or name not in entry["names"]:
            return None
        blob = entry["blobs"].get(name)
    if blob is not None:
        return blob, MEDIA[name]
    p = _safe_path(entry, name)
    if p is None or not p.is_file():
        return None
    return p.read_bytes(), MEDIA[name]


# ------------------------------------------------------------------ patient page
# page shell + CSS + the two fixed messages live in bayan/web (templates/plan_*.html, static/css/plan_page.css)
_PAGE = read("templates/plan_page.html")
_PAGE_CSS = read("static/css/plan_page.css")
_UNAVAILABLE = read("templates/plan_unavailable.html")
_PENDING = read("templates/plan_pending.html")


def _e(x) -> str:
    return html.escape(str(x or ""))


def _plan_html(plan: dict, pdf_url: str | None) -> str:
    """The structured plan, native script first and English beneath (the patient PDF's content and wording)."""
    lang = plan.get("lang", "en")
    L, E = labels(lang), labels("en")
    nat = lang != "en"
    d = " dir='rtl'" if lang in RTL_LANGS else " dir='auto'"

    def head(key: str, red: bool = False) -> str:
        cls = " class='red'" if red else ""
        if nat:
            return f"<h2{cls} lang='{lang}'{d}>{_e(L[key])}</h2><p class='h2en'>{_e(E[key])}</p>"
        return f"<h2{cls}>{_e(E[key])}</h2>"

    def pair(native: str, en: str, strong: bool = False) -> str:
        tag = "p class='strong'" if strong else "p"
        if nat and native:
            return f"<{tag} lang='{lang}'{d}>{_e(native)}</p>" + (f"<p class='en'>{_e(en)}</p>" if en else "")
        return f"<{tag}>{_e(en)}</p>" if en else ""

    def items(rows: list[dict]) -> str:
        return "<ul>" + "".join(f"<li>{pair(r.get('native', ''), r.get('en', ''))}</li>" for r in rows) + "</ul>"

    title = (plan.get("title_native") or L["title"]) if nat else E["title"]
    date = plan.get("date") or datetime.now().strftime("%Y-%m-%d")
    try:
        date = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        pass
    meta = " · ".join(x for x in (plan.get("clinic") or "", date) if x)
    parts = [f"<h1 lang='{lang}'{d}>{_e(title)}</h1>" + (f"<p class='h1en'>{_e(E['title'])}</p>" if nat else ""),
             f"<p class='muted meta'>{_e(meta)}</p>"]
    meds = plan.get("medicines") or []
    if meds:
        body = ""
        for m in meds:
            title_en = m.get("title_en") or m.get("name") or ""
            body += "<div class='med'>" + pair(m.get("title_native") or "", title_en, strong=True)
            body += pair(m.get("note_native") or "", m.get("note_en") or "") + "</div>"
        parts.append(f"<section class='card'>{head('medicines')}{body}</section>")
    regular = [m for m in meds if not m.get("prn") and m.get("slots")]
    if regular and os.environ.get("BAYAN_PDF_SCHEDULE_TABLE", "on").strip().lower() not in ("0", "off", "false", "no"):
        used = [sl for sl in SLOTS if any(sl in (m.get("slots") or []) for m in regular)]

        def cell(native: str, en: str) -> str:
            if nat and native:
                return f"<span lang='{lang}'>{_e(native)}</span><small>{_e(en)}</small>"
            return _e(en)
        th = "".join(f"<th>{cell(L[sl], E[sl])}</th>" for sl in used)
        rows = ""
        for m in regular:
            amt = cell(m.get("dose_amount_native") or "", m.get("dose_amount_en") or "")
            rows += (f"<tr><th scope='row'>{cell(m.get('name_native') or '', m.get('name') or '')}</th>"
                     + "".join(f"<td>{amt if sl in (m.get('slots') or []) else ''}</td>" for sl in used) + "</tr>")
        for m in [m for m in meds if m.get("prn")]:
            en_line = ", ".join(x for x in (m.get("dose_amount_en") or "", E["prn"].lower()) if x)
            nat_line = ", ".join(x for x in (m.get("dose_amount_native") or m.get("dose_amount_en") or "", L["prn"]) if x)
            rows += (f"<tr><th scope='row'>{cell(m.get('name_native') or '', m.get('name') or '')}</th>"
                     f"<td colspan='{len(used)}'>{cell(nat_line, en_line) if nat else _e(en_line[:1].upper() + en_line[1:])}</td></tr>")
        parts.append(f"<section class='card'>{head('schedule')}<div class='tw'><table{d}><thead><tr>"
                     f"<th>{cell(L['medicine'], E['medicine'])}</th>{th}</tr></thead><tbody>{rows}</tbody></table></div></section>")
    if plan.get("avoid"):
        parts.append(f"<section class='card'>{head('avoid', red=True)}{items(plan['avoid'])}</section>")
    other = list(plan.get("advice") or [])
    fu = plan.get("follow_up") or {}
    if fu.get("en") or fu.get("native"):
        other.append(fu)
    if other:
        parts.append(f"<section class='card'>{head('other')}{items(other)}</section>")
    parts.append(f"<section class='card'>{head('red_flags', red=True)}{items(plan.get('red_flags') or [])}</section>")
    if pdf_url:
        parts.append(download_button(pdf_url, lang))
    parts.append("<p class='foot'>From your visit today. This page is private and is deleted after 24 hours.</p>")
    return "".join(parts)


def page_html(pid: str) -> tuple[int, str]:
    rec = get(pid)
    if rec is None:
        return 404, _page(_UNAVAILABLE, "en")
    if not rec["approved"]:
        return 200, _page(_PENDING, "en")
    token = rec.get("token")
    pdf_url = f"{PUBLIC_BASE}/files/{token}/care_plan.pdf" if token and open_file(token, "care_plan.pdf") else None
    if rec.get("edited"):
        return 200, _page(_text_html(rec, pdf_url), rec["lang"])
    return 200, _page(_plan_html(rec["plan"], pdf_url), rec["lang"])


def _text_sections(text: str, lang: str) -> str:
    d = " dir='rtl'" if lang in RTL_LANGS or lang == "ar" else " dir='auto'"
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        items = "".join(f"<li>{_e(ln[2:].strip())}</li>" for ln in lines if ln.startswith(("- ", "• ", "* ")))
        paras = "".join(f"<p>{_e(ln)}</p>" for ln in lines if not ln.startswith(("- ", "• ", "* ")))
        out.append(f"<section lang='{lang}'{d}>{paras}{f'<ul>{items}</ul>' if items else ''}</section>")
    return "".join(out)


def _text_html(rec: dict, pdf_url: str | None) -> str:
    """A plan the doctor wrote or corrected: the patient's language first, then the doctor's own words."""
    lang, dl = rec["lang"], rec.get("doc_lang", "en")
    L = labels(lang)
    parts = [f"<h1 lang='{lang}'>{_e(L['title'])}</h1>"]
    if rec.get("text_native") and lang != dl:
        parts.append(_text_sections(rec["text_native"], lang))
        parts.append(f"<p class='h1en'>{'العربية' if dl == 'ar' else 'English'}</p>")
    parts.append(_text_sections(rec.get("text_doc") or "", dl))
    if pdf_url:
        parts.append(download_button(pdf_url, lang))
    parts.append("<p class='foot'>From your visit today. This page is private and is deleted after 24 hours.</p>")
    return "".join(parts)


def _page(body: str, lang: str) -> str:
    return fill(_PAGE, css=_PAGE_CSS, body=body)
