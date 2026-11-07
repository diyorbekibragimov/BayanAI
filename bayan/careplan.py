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
    inner = (f"<span lang='{lang}'{d}>{_e(native)}</span><small>Download PDF</small>" if native else "<span>Download PDF</span>")
    return f"<a class='btn' href='{_e(pdf_url)}' download='care_plan.pdf' type='application/pdf'>{inner}</a>"
PLANS: dict[str, dict] = {}
FILES: dict[str, dict] = {}   # token -> {"dir": Path, "names": set, "blobs": {name: bytes}, "expires": float}
_LOCK = threading.Lock()
MEDIA = {"care_plan.pdf": "application/pdf", "doctor_report.pdf": "application/pdf", "care_plan.wav": "audio/wav"}
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
SLOTS = ("wake", "breakfast", "lunch", "dinner", "bedtime")


# ------------------------------------------------------------------ review text (doctor)
def _one_line(x) -> str:
    """Whitespace (newlines, tabs, runs of spaces) collapsed: every item is exactly one line per language."""
    return " ".join(str(x or "").split())


def plan_text(plan: dict) -> str:
    """The care plan as the doctor reviews it (the Review screen's editable text). Same content as the patient PDF.
    Plain text, one layout for every language:

        Your medicines            <- section heading, English
        तपाईंका औषधिहरू             <- the same heading in the patient's language (own line)
        - Paracetamol 1 g: ...    <- one item, English
          प्यारासिटामोल ...         <- its patient-language line, indented two spaces
                                  <- one blank line between sections
        Do not take
        ...

    No separators, no trailing spaces, never two blank lines; _text_sections() parses it back."""
    lang = plan.get("lang", "en")
    L, E = labels(lang), labels("en")
    nat = lang != "en"
    sections: list[list[str]] = []

    def head(key: str) -> list[str]:
        sec = [E[key]]
        if nat and L[key] and L[key] != E[key]:
            sec.append(L[key])
        sections.append(sec)
        return sec

    def item(sec: list[str], en: str, native: str = ""):
        en, native = _one_line(en), _one_line(native)
        if en:
            sec.append(f"- {en}")
        if nat and native and native != en:
            sec.append(f"  {native}" if en else f"- {native}")

    meds = plan.get("medicines") or []
    if meds:
        sec = head("medicines")
        for m in meds:
            item(sec, f"{_one_line(m.get('title_en') or m.get('name'))}: {_one_line(m.get('note_en'))}".strip(": "),
                 ": ".join(x for x in (_one_line(m.get("title_native")), _one_line(m.get("note_native"))) if x))
    if plan.get("avoid"):
        sec = head("avoid")
        for a in plan["avoid"]:
            item(sec, a.get("en", ""), a.get("native", ""))
    other = list(plan.get("advice") or [])
    fu = plan.get("follow_up") or {}
    if fu.get("en") or fu.get("native"):
        other.append(fu)
    if other:
        sec = head("other")
        for a in other:
            item(sec, a.get("en", ""), a.get("native", ""))
    sec = head("red_flags")
    for f in plan.get("red_flags") or []:
        item(sec, f.get("en", ""), f.get("native", ""))
    if not plan.get("red_flags"):
        sec.append(f"- Call {plan.get('emergency') or '999'}.")
    return "\n\n".join("\n".join(ln.rstrip() for ln in sec) for sec in sections).strip()


# ------------------------------------------------------------------ doctor edits (the doctor gives the plan)
TRANSLATE_PLAN_SYSTEM = """Translate this patient care plan faithfully into {lang}, in its native script.
Keep the same layout: one item per line, headings on their own lines, blank lines kept, lines starting with "- " kept,
lines indented with two spaces keep their two leading spaces.
Keep every drug name recognisable and every number, dose, unit and frequency exact, written with Western digits.
Use simple everyday words. Return only the translation."""

LOCALIZE_PLAN_SYSTEM = """This care plan text mixes English lines with lines in the patient's language. Rewrite ONLY the
English parts into formal Modern Standard Arabic for the doctor; copy every line that is in another language unchanged.
Keep the layout (headings on their own lines, blank lines, the "- " bullets, the two-space indent), every drug name
(Arabic script as Gulf doctors write it), every number, dose, unit and frequency exactly, with Western digits.
Return only the text."""


def translate_plan(text: str, lang: str) -> str:
    """The doctor's own plan text in another language (patient's language, or Arabic for the doctor)."""
    from .brain import llm
    from .talk import LANG_NAMES
    if not (text or "").strip() or lang == "en":
        return text
    system = TRANSLATE_PLAN_SYSTEM.format(lang=LANG_NAMES.get(lang, lang))
    return tidy_text(llm.chat_text(system, text, max_tokens=2500))


def tidy_text(text: str) -> str:
    """plan_text()'s plain-text hygiene for text that came back from a model: no trailing spaces, at most one blank
    line in a row, no leading/trailing blank lines (indentation kept)."""
    out: list[str] = []
    for ln in (text or "").replace("\r\n", "\n").split("\n"):
        ln = ln.rstrip()
        if not ln and (not out or not out[-1]):
            continue
        out.append(ln)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def plan_text_for(plan: dict, doc_lang: str) -> str:
    """plan_text() for the doctor's language: English review lines become Arabic in Arabic mode."""
    from .brain import llm
    text = plan_text(plan)
    if doc_lang != "ar" or not text.strip():
        return text
    try:
        out = tidy_text(llm.chat_text(LOCALIZE_PLAN_SYSTEM, text, max_tokens=2500))
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


def _latin(text: str) -> str:
    """Western digits everywhere, as on the PDF (doses must read the same on both)."""
    import unicodedata
    return "".join(str(unicodedata.digit(ch)) if ch.isdigit() and not ch.isascii() else ch for ch in str(text or ""))


def _plan_html(plan: dict, pdf_url: str | None) -> str:
    """The structured plan, the patient's script first with the English beneath (the patient PDF's content)."""
    lang = plan.get("lang", "en")
    L, E = labels(lang), labels("en")
    nat = lang != "en"
    d = " dir='rtl'" if lang in RTL_LANGS else " dir='auto'"
    t = lambda x: _e(_latin(x))  # noqa: E731

    def head(key: str, red: bool = False) -> str:
        cls = "h red" if red else "h"
        if nat and L[key] != E[key]:
            return f"<h2 class='{cls}'><span lang='{lang}'{d}>{t(L[key])}</span><small>{t(E[key])}</small></h2>"
        return f"<h2 class='{cls}'><span>{t(E[key])}</span></h2>"

    def line(native: str, en: str, strong: bool = False) -> str:
        cls = " class='b'" if strong else ""
        if nat and native:
            return f"<p{cls} lang='{lang}'{d}>{t(native)}</p>" + (f"<p class='en'>{t(en)}</p>" if en else "")
        return f"<p{cls}>{t(en)}</p>" if en else ""

    def items(rows: list[dict]) -> str:
        return "<ul class='dots'>" + "".join(f"<li>{line(r.get('native', ''), r.get('en', ''))}</li>" for r in rows) + "</ul>"

    title = (plan.get("title_native") or L["title"]) if nat else E["title"]
    date = plan.get("date") or datetime.now().strftime("%Y-%m-%d")
    try:
        date = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        pass
    meta = " · ".join(x for x in (plan.get("clinic") or "", date) if x)
    parts = [f"<header class='title'><h1 lang='{lang}'{d}>{t(title)}</h1>"
             + (f"<p class='sub'>{t(E['title'])}</p>" if nat and title != E["title"] else "")
             + f"<p class='meta'>{t(meta)}</p></header>"]
    if pdf_url:
        parts.append(download_button(pdf_url, lang))
    meds = plan.get("medicines") or []
    if meds:
        body = "".join("<div class='med'>" + line(m.get("title_native") or "", m.get("title_en") or m.get("name") or "", True)
                       + line(m.get("note_native") or "", m.get("note_en") or "") + "</div>" for m in meds)
        parts.append(f"<section>{head('medicines')}{body}</section>")
    regular = [m for m in meds if not m.get("prn") and m.get("slots")]
    if regular and os.environ.get("BAYAN_PDF_SCHEDULE_TABLE", "on").strip().lower() not in ("0", "off", "false", "no"):
        # one row per time of day: "Breakfast — Paracetamol, 2 tablets" (reads on a phone; no wide grid)
        rows = ""
        for sl in [sl for sl in SLOTS if any(sl in (m.get("slots") or []) for m in regular)]:
            label = (f"<span lang='{lang}'{d}>{t(L[sl])}</span><small>{t(E[sl])}</small>" if nat and L[sl] != E[sl]
                     else f"<span>{t(E[sl])}</span>")
            what = ""
            for m in regular:
                if sl in (m.get("slots") or []):
                    nm = m.get("name_native") if nat and m.get("name_native") else (m.get("name") or "")
                    amt = m.get("dose_amount_native") if nat and m.get("dose_amount_native") else (m.get("dose_amount_en") or "")
                    what += (f"<p lang='{lang}'{d}>{t(nm)}" + (f"<span class='amt'>{t(amt)}</span>" if amt else "") + "</p>")
            rows += f"<tr><th scope='row'>{label}</th><td>{what}</td></tr>"
        parts.append(f"<section>{head('schedule')}<table class='sched'{d}><tbody>{rows}</tbody></table></section>")
    if plan.get("avoid"):
        parts.append(f"<section>{head('avoid', red=True)}{items(plan['avoid'])}</section>")
    other = list(plan.get("advice") or [])
    fu = plan.get("follow_up") or {}
    if fu.get("en") or fu.get("native"):
        other.append(fu)
    if other:
        parts.append(f"<section>{head('other')}{items(other)}</section>")
    if plan.get("red_flags"):
        parts.append(f"<section>{head('red_flags', red=True)}{items(plan['red_flags'])}</section>")
    else:  # as on the PDF: one plain emergency line, never an empty "Call 999 if" heading
        parts.append(f"<section>{head('emergency', red=True)}</section>")
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


def parse_text(text: str) -> list[dict]:
    """Plain plan text (plan_text()'s layout, or the doctor's own) -> [{"heading": [lines], "items": [[lines]]}].
    A line starting with "- " (or "• ", "* ") is an item; an indented line right after an item is that item's next
    line (the other language); any other line is a heading, and a heading line right under another one (no blank
    line, no item between) is the same heading in the other language. A blank line ends a section's heading block.
    A line that only repeats the line above it (a translation that left a line unchanged) is dropped."""
    out: list[dict] = []
    cur: dict | None = None
    blank = True
    for raw in (text or "").splitlines():
        st = raw.strip()
        if not st:
            blank = True
            continue
        if st[:2] in ("- ", "• ", "* "):
            if cur is None:
                cur = {"heading": [], "items": []}
                out.append(cur)
            cur["items"].append([st[2:].strip()])
        elif raw[:1].isspace() and cur is not None and cur["items"]:
            if st != cur["items"][-1][-1]:
                cur["items"][-1].append(st)
        elif cur is not None and cur["heading"] and not cur["items"] and not blank:
            if st != cur["heading"][-1]:
                cur["heading"].append(st)
        else:
            cur = {"heading": [st], "items": []}
            out.append(cur)
        blank = False
    return out


def _text_sections(text: str, lang: str) -> str:
    """Plain plan text -> HTML sections (see parse_text): a two-line heading shows its second line small beneath."""
    d = " dir='rtl'" if lang in RTL_LANGS or lang == "ar" else " dir='auto'"
    red_keys = {lab[k].strip() for lab in (labels(lang), labels("en")) for k in ("avoid", "red_flags", "emergency")}
    out = []
    for sec in parse_text(text):
        heading = sec["heading"]
        red = any(k and h and (k in h or h in k) for k in red_keys for h in heading)
        h = ""
        if heading:
            h = (f"<h2 class='h{' red' if red else ''}'><span>{_e(_latin(heading[0]))}</span>"
                 + "".join(f"<small>{_e(_latin(x))}</small>" for x in heading[1:]) + "</h2>")
        en_cls = " class='en'"
        lis = "".join("<li>" + "".join(f"<p{en_cls if k else ''}>{_e(_latin(x))}</p>" for k, x in enumerate(it))
                      + "</li>" for it in sec["items"])
        out.append(f"<section lang='{lang}'{d}>{h}" + (f"<ul class='dots'>{lis}</ul>" if lis else "") + "</section>")
    return "".join(out)


def _text_html(rec: dict, pdf_url: str | None) -> str:
    """A plan the doctor wrote or corrected: the patient's language first; the doctor's own words folded beneath."""
    lang, dl = rec["lang"], rec.get("doc_lang", "en")
    L, E = labels(lang), labels("en")
    d = " dir='rtl'" if lang in RTL_LANGS else " dir='auto'"
    parts = [f"<header class='title'><h1 lang='{lang}'{d}>{_e(L['title'])}</h1>"
             + (f"<p class='sub'>{_e(E['title'])}</p>" if L["title"] != E["title"] else "") + "</header>"]
    if pdf_url:
        parts.append(download_button(pdf_url, lang))
    if rec.get("text_native") and lang != dl:
        parts.append(_text_sections(rec["text_native"], lang))
        parts.append(f"<details class='orig'><summary>{'العربية' if dl == 'ar' else 'English'}</summary>"
                     f"{_text_sections(rec.get('text_doc') or '', dl)}</details>")
    else:
        parts.append(_text_sections(rec.get("text_doc") or "", dl))
    return "".join(parts)


def _page(body: str, lang: str) -> str:
    return fill(_PAGE, css=_PAGE_CSS, body=body)
