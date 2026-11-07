"""Patient care plan: written from the transcript, reviewed by the doctor, opened by QR.

Plans live in memory only (privacy) and expire after PLAN_TTL seconds.
"""

from __future__ import annotations

import html
import re
import secrets
import threading
import time

import segno

from . import talk

PLAN_TTL = 24 * 3600
PLANS: dict[str, dict] = {}
_LOCK = threading.Lock()

SECTIONS = ["Medicine", "At home", "Tests done today", "Call 999 or come back straight away if"]

PLAN_SYSTEM = """You write a patient's care plan at the end of a clinic visit in Qatar, from the
interpreted transcript. Write in plain, short, everyday English for a patient with little schooling.

Use only these section headings, in this order, each on its own line, followed by its lines:
Medicine
At home
Tests done today
Call 999 or come back straight away if

Strict rules:
- Use ONLY what the doctor actually said in the transcript. Never add a medicine, dose, frequency,
  test, result or advice the doctor did not say. If the doctor did not cover a section, leave the
  whole section out (heading too).
- Lines marked [NOT SPOKEN] were held back and never said to the patient: ignore them completely.
- Keep every drug name, dose and frequency exactly as the doctor said them.
- Under Medicine, At home and Tests done today, write short full sentences, each on its own line,
  starting with a capital letter (for example "Paracetamol 1 g, up to three times a day.").
- In "Call 999 or come back straight away if", write each warning sign as a line starting with "- ".
- Separate sections with one blank line. No title, no greeting, no markdown, no extra notes.
- If the doctor gave no plan at all, return an empty answer."""

TRANSLATE_PLAN_SYSTEM = """Translate this patient care plan faithfully into {lang}, in its native script.
Keep the same layout: section headings on their own lines, blank lines between sections, and lines
starting with "- " kept as they are. Keep every drug name, number, dose and frequency exact. Use simple
everyday words. Return only the translation."""


def _chat(system: str, user: str, max_tokens: int = 1200) -> str:
    kwargs = dict(model=talk.LLM_MODEL, temperature=0, max_tokens=max_tokens,
                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        out = talk.llm().chat.completions.create(**kwargs, extra_body={"reasoning_effort": "low"})
    except Exception:  # noqa: BLE001 - provider may reject the extra field; retry plain
        out = talk.llm().chat.completions.create(**kwargs)
    return (out.choices[0].message.content or "").strip()


def transcript_text(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        who = "Doctor" if t["role"] == "doctor" else "Patient"
        said = t.get("english") or t.get("said") or ""
        if not said:
            continue
        flag = " [NOT SPOKEN]" if t.get("held") and not t.get("overridden") else ""
        lines.append(f"{who}{flag}: {said}")
    return "\n".join(lines)


def write_plan(turns: list[dict]) -> str:
    tx = transcript_text(turns)
    if not any(t["role"] == "doctor" for t in turns) or not tx.strip():
        return ""
    out = _chat(PLAN_SYSTEM, f"Transcript:\n{tx}")
    out = re.sub(r"[*#`]+", "", out).strip()
    return re.sub(r"\n{3,}", "\n\n", out)


def translate_plan(plan_en: str, lang: str) -> str:
    if not plan_en.strip() or lang == "en":
        return plan_en
    return _chat(TRANSLATE_PLAN_SYSTEM.format(lang=talk.LANG_NAMES.get(lang, lang)), plan_en, max_tokens=2000)


def safety_check(plan_en: str, allergies: list[dict]) -> list[str]:
    """Deterministic: any medicine named in the plan that shares a class with a reported allergy."""
    warnings = []
    words = set(re.findall(r"[a-z][a-z-]+", plan_en.lower()))
    for a in allergies:
        a_cls = talk.classes_of(a["substance"])
        for w in words:
            shared = talk.classes_of(w) & a_cls
            if shared and w not in a_cls:
                warnings.append(f"The plan mentions {w}; the patient reported a {a['substance']} allergy.")
    return sorted(set(warnings))


# ------------------------------------------------------------------ store
def _purge():
    now = time.time()
    for k in [k for k, v in PLANS.items() if v["expires"] < now]:
        PLANS.pop(k, None)


def create(lang: str, plan_en: str, plan_native: str) -> str:
    with _LOCK:
        _purge()
        pid = secrets.token_urlsafe(18)
        PLANS[pid] = {"lang": lang, "plan_en": plan_en, "plan_native": plan_native, "approved": False,
                      "created": time.time(), "expires": time.time() + PLAN_TTL}
        return pid


def approve(pid: str, plan_en: str, plan_native: str) -> None:
    with _LOCK:
        rec = PLANS.get(pid)
        if rec:
            rec.update(plan_en=plan_en, plan_native=plan_native, approved=True, approved_at=time.time())


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


# ------------------------------------------------------------------ patient page
_FONTS = ("https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=Noto+Sans+Devanagari:wght@400;500;600"
          "&family=Noto+Sans+Bengali:wght@400;500;600&family=Noto+Sans+Malayalam:wght@400;500;600&family=Noto+Naskh+Arabic:wght@400;500;600"
          "&family=Reem+Kufi:wght@500&display=swap")


def _sections_html(text: str, lang: str) -> str:
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        head, rest = lines[0], lines[1:]
        items, paras = [], []
        for ln in rest:
            if ln.startswith(("- ", "• ", "* ")):
                items.append(f"<li>{html.escape(ln[2:].strip())}</li>")
            else:
                paras.append(f"<p>{html.escape(ln)}</p>")
        body = "".join(paras) + (f"<ul>{''.join(items)}</ul>" if items else "")
        out.append(f"<section class='card' lang='{lang}' dir='auto'><h2>{html.escape(head)}</h2>{body}</section>")
    return "".join(out)


def page_html(pid: str) -> tuple[int, str]:
    rec = get(pid)
    if rec is None:
        body = ("<h1>This care plan is no longer available</h1>"
                "<p class='muted'>Care plans are kept for 24 hours only. Please ask the clinic for a new copy.</p>")
        return 404, _page(body, "en")
    if not rec["approved"]:
        body = ("<h1>Your care plan is almost ready</h1>"
                "<p class='muted'>The doctor is still checking it. Scan the code again in a moment.</p>")
        return 200, _page(body, "en")
    lang = rec["lang"]
    native = rec["plan_native"] or ""
    name = talk.LANG_NAMES.get(lang, lang)
    parts = ["<h1>Your care plan</h1>"]
    if native.strip() and lang != "en":
        parts.append(f"<p class='tag'>{html.escape(name)}</p>{_sections_html(native, lang)}")
        parts.append("<p class='tag en'>English</p>")
    parts.append(_sections_html(rec["plan_en"], "en") or "<p class='muted'>No plan was written for this visit.</p>")
    parts.append("<p class='foot'>From your visit today. This page is private and is deleted after 24 hours.</p>")
    return 200, _page("".join(parts), lang)


def _page(body: str, lang: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Your care plan · Bayan</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="{_FONTS}" rel="stylesheet">
<style>
:root{{color-scheme:light}}
body{{margin:0;background:#FBFCFC;color:#173430;font-family:'Instrument Sans',system-ui,sans-serif;-webkit-text-size-adjust:100%}}
main{{max-width:640px;margin:0 auto;padding:28px 20px 56px}}
.top{{display:flex;align-items:center;gap:14px;margin-bottom:26px}}
.pearl{{width:44px;height:44px;border-radius:50%;flex:none;background:radial-gradient(circle at 34% 28%,#FFFFFF 0%,#F2FBF8 18%,#BFEBDF 46%,#C9EDE6 66%,#D9E9FA 100%);box-shadow:0 14px 30px -14px rgba(14,138,111,.42),inset 0 6px 12px rgba(255,255,255,.95)}}
.wm{{display:flex;align-items:baseline;gap:8px}}.wm b{{font-family:'Reem Kufi',sans-serif;font-size:26px;font-weight:500}}.wm span{{font-size:15px;color:#5B6B69}}
h1{{font-size:30px;line-height:1.25;font-weight:600;margin:0 0 18px}}
.tag{{display:inline-block;margin:18px 0 10px;padding:6px 14px;border-radius:999px;background:#E1F3ED;color:#0B6E59;font-size:15px;font-weight:500}}
.tag.en{{background:#EEF5FC;color:#174F80;margin-top:30px}}
.card{{background:#FFFFFF;border:1px solid #E3EAE9;border-radius:22px;padding:18px 20px;margin:0 0 14px}}
.card h2{{margin:0 0 8px;font-size:20px;font-weight:600;color:#0B6E59}}
.card p,.card li{{margin:0 0 8px;font-size:20px;line-height:1.6}}
.card ul{{margin:0;padding-left:22px}}
[lang=ne],[lang=hi]{{font-family:'Noto Sans Devanagari','Instrument Sans',sans-serif}}
[lang=bn]{{font-family:'Noto Sans Bengali','Instrument Sans',sans-serif}}
[lang=ml]{{font-family:'Noto Sans Malayalam','Instrument Sans',sans-serif}}
[lang=ur]{{font-family:'Noto Naskh Arabic',serif;direction:rtl;text-align:right}}
[lang=ur] ul{{padding-left:0;padding-right:22px}}
.muted{{color:#5B6B69;font-size:19px;line-height:1.55}}
.foot{{margin-top:28px;color:#5B6B69;font-size:15px;line-height:1.5}}
</style></head><body><main>
<div class="top"><div class="pearl" aria-hidden="true"></div><div class="wm"><b>بيان</b><span>Bayan</span></div></div>
{body}
</main></body></html>"""
