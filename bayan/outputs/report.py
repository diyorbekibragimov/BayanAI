"""Bayan AI · PDF outputs: the patient's medicine and care sheet (native script first) and the clinic note.

Styled as printed hospital documents: black text on white, hairline rules, no tints or colour icons. The patient
sheet follows the AHRQ pill card / Universal Medication Schedule (morning, noon, evening, bedtime; "as needed"
medicines listed separately) and plain-language after-visit-summary practice; dark red marks only the "Do not take"
and "Call 999" headings. The clinic note follows PRSB-style fixed headings with hairline tables.

fpdf2 + uharfbuzz text shaping with the Noto fonts in assets/fonts (Devanagari conjuncts, i-matra reordering,
Bengali/Malayalam clusters, Arabic-script joining/RTL); fallback fonts cover mixed-script lines. Pictograms are
drawn with vector primitives (no emoji fonts).
"""

from __future__ import annotations

import math
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from . import LANG_NAMES, RTL_LANGS, labels

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
SCRIPT_FONTS = {"deva": "NotoSansDevanagari", "beng": "NotoSansBengali", "mlym": "NotoSansMalayalam",
                "taml": "NotoSansTamil", "telu": "NotoSansTelugu", "arab": "NotoNaskhArabic",
                "hang": "NotoSansKR", "jpan": "NotoSansJP"}
LANG_FONT = {"ne": "deva", "hi": "deva", "mr": "deva", "bn": "beng", "as": "beng", "ml": "mlym", "ta": "taml",
             "te": "telu", "ar": "arab", "ur": "arab", "fa": "arab", "ps": "arab", "ko": "hang", "ja": "jpan"}
FALLBACKS = ["sans", "deva", "beng", "mlym", "taml", "telu", "arab", "hang", "jpan"]
# Symbols the Noto text fonts lack, written out instead of printing a box.
_SUBST = {"✓": "Yes", "✔": "Yes", "✗": "No", "✘": "No"}

# palette (the same for both documents)
BLACK = (31, 35, 40)        # #1F2328 text
GREY = (87, 96, 106)        # #57606A secondary text, labels, English lines, page numbers
LIGHT = GREY
RULE_HEAD = (140, 149, 159)  # #8C959F header rule, table header rule
HAIR = (216, 222, 228)      # #D8DEE4 rule under section headings
ROW_RULE = (234, 238, 242)  # #EAEEF2 rules between table rows
PANEL = (246, 248, 250)     # #F6F8FA patient & encounter panel
ACCENT = (11, 92, 107)      # #0B5C6B the Bayan AI wordmark only
RED = (155, 28, 28)         # #9B1C1C "Do not take" and "Call 999" headings only
WHITE = (255, 255, 255)
INK, MUTED = BLACK, GREY    # names used by the shared text primitives
W_HEAD, W_LIGHT, W_ROW = 0.6 * 0.3528, 0.4 * 0.3528, 0.3 * 0.3528   # rule weights (pt -> mm)

MARGIN = 18.0
PT = 0.3528  # mm per pt


def font_for(lang: str) -> str:
    return LANG_FONT.get(lang, "sans")


# ====================================================================== text sanitising (never crash on content)
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​⁠﻿︀-️]|[\U0001f3fb-\U0001f3ff]")
_COVER: set[int] | None = None
_MISSING = "?"


def _coverage() -> set[int]:
    """Code points any bundled font can draw (fallback fonts cover the rest of the line)."""
    global _COVER, _MISSING
    if _COVER is None:
        from fontTools.ttLib import TTFont

        cps: set[int] = set()
        for f in FONT_DIR.glob("*.ttf"):
            try:
                cps |= set(TTFont(str(f), lazy=True).getBestCmap().keys())
            except Exception:  # noqa: BLE001
                continue
        _COVER = cps
        try:
            sans = set(TTFont(str(FONT_DIR / "NotoSans-Regular.ttf"), lazy=True).getBestCmap().keys())
        except Exception:  # noqa: BLE001
            sans = set()
        _MISSING = "□" if 0x25A1 in sans else "?"
    return _COVER


def clean(text) -> str:
    """Control characters removed, tabs/CRs normalised, glyphs no bundled font has (emoji, unknown scripts)
    replaced by a box, so fpdf2 never sees an undrawable character."""
    if text is None:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    for k, v in _SUBST.items():
        text = text.replace(k, v)
    # no em / en dashes in the documents: number ranges keep a hyphen, other dashes read as commas
    text = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1-\2", text)
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    if any(ch.isdigit() and not ch.isascii() for ch in text):  # Latin digits in the documents
        import unicodedata

        text = "".join(str(unicodedata.digit(ch)) if ch.isdigit() and not ch.isascii() else ch for ch in text)
    text = _CTRL_RE.sub("", text)
    cov = _coverage()
    if all(ord(ch) in cov or ch in "\n" for ch in text):
        return text
    out = []
    for ch in text:
        o = ord(ch)
        if o in cov or ch == "\n" or ch in "‌‍":
            out.append(ch)
        elif 0xD800 <= o <= 0xDFFF:
            continue
        else:
            out.append(_MISSING)
    return "".join(out).replace("‍" + _MISSING, _MISSING)


_COMPLEX_RE = re.compile("[\u0300-\u036f\u0590-\u08ff\u0900-\u0dff\u0e00-\u0fff\u1000-\u109f\u1780-\u17ff"
                         "\ufb1d-\ufdff\ufe70-\ufeff]")


def needs_shaping(text: str) -> bool:
    """Complex scripts (Indic, Arabic, Hebrew, Thai, combining marks) need HarfBuzz; Latin does not, and skipping it
    makes long Latin text ~10x faster to lay out."""
    return bool(_COMPLEX_RE.search(text or ""))


def _clusters(word: str) -> list[str]:
    """Rough extended grapheme clusters: a base + its combining marks; a virama/ZWJ glues the next letter on."""
    import unicodedata

    out: list[str] = []
    glue = False
    for ch in word:
        cat = unicodedata.category(ch)
        if out and (glue or cat in ("Mn", "Mc", "Me") or ch in "\u200c\u200d"):
            out[-1] += ch
        else:
            out.append(ch)
        glue = ch == "\u200d" or (cat == "Mn" and "VIRAMA" in unicodedata.name(ch, "")) or \
            "SIGN VIRAMA" in unicodedata.name(ch, "")
    return out


def _lh(size: float, factor: float = 1.45) -> float:
    return size * PT * factor


# ====================================================================== document base
class _Doc(FPDF):
    """A4 portrait, 18 mm margins, Noto families registered, shaping + script fallback on."""

    footer_fn = None

    def __init__(self, features: dict | None = None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("sans", "", FONT_DIR / "NotoSans-Regular.ttf")
        self.add_font("sans", "B", FONT_DIR / "NotoSans-Bold.ttf")
        self.add_font("sans", "I", FONT_DIR / "NotoSans-Italic.ttf")
        self.add_font("semi", "", FONT_DIR / "NotoSans-SemiBold.ttf")
        self.add_font("mono", "", FONT_DIR / "NotoSansMono-Regular.ttf")
        for fam, stem in SCRIPT_FONTS.items():
            self.add_font(fam, "", FONT_DIR / f"{stem}-Regular.ttf")
            self.add_font(fam, "B", FONT_DIR / f"{stem}-Bold.ttf")
        self._features = features or {}
        self.set_text_shaping(True, features=self._features)
        self.set_fallback_fonts(FALLBACKS, exact_match=False)
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(True, margin=26)
        self.alias_nb_pages()
        self.set_creator("Bayan AI")
        self.set_author("Bayan AI")
        self.set_creation_date(datetime.now().astimezone())

    def footer(self):
        if self.footer_fn:
            self.footer_fn(self)

    # ------------------------------------------------------------------ text primitives
    def font(self, fam: str, style: str = "", size: float = 9.5, color=INK, spacing: float = 0.0):
        self.set_font(fam, style, size)
        self.set_text_color(*color)
        self.set_char_spacing(spacing)

    @contextmanager
    def shaping_for(self, text: str):
        if needs_shaping(text):
            yield
            return
        self.set_text_shaping(False)
        try:
            yield
        finally:
            self.set_text_shaping(True, features=self._features)

    def _word_w(self, word: str, key: tuple) -> float:
        cache = self.__dict__.setdefault("_wcache", {})
        k = key + (word,)
        v = cache.get(k)
        if v is None:
            with self.shaping_for(word):
                v = self.get_string_width(word)
            cache[k] = v
        return v

    def _hard_break(self, word: str, key: tuple, w: float) -> list[str]:
        """Split one word wider than the line (URLs, IDs) between grapheme clusters (never inside an Indic
        conjunct or before a vowel sign, which would render a dotted circle)."""
        out, cur = [], ""
        for cl in _clusters(word):
            if cur and self._word_w(cur + cl, key) > w:
                out.append(cur)
                cur = cl
            else:
                cur += cl
        return out + ([cur] if cur else [])

    def fit_size(self, text: str, fam: str, style: str, size: float, w: float, min_size: float) -> float:
        """Largest size <= size at which the longest word of text fits in w (so it never has to be broken)."""
        text = clean(text)
        if not text:
            return size
        longest = max(text.split(), key=len, default="")
        while size > min_size:
            self.set_font(fam, style, size)
            with self.shaping_for(longest):
                if self.get_string_width(longest) + 2 * self.c_margin <= w:
                    return size
            size -= 0.5
        return min_size

    def wrap(self, text: str, fam: str, style: str, size: float, w: float) -> list[str]:
        """Greedy word wrap with cached per-word widths (shaped words for complex scripts, fallback fonts via
        get_string_width) -> list of lines. Much faster than fpdf2's per-character breaker on long transcripts."""
        text = clean(text)
        if not text:
            return []
        self.set_font(fam, style, size)
        self.set_char_spacing(0)
        key = (fam, style, size)
        limit = w * 0.98 - 2 * self.c_margin
        space = self._word_w(" ", key)
        lines: list[str] = []
        for para in text.split("\n"):
            words = [x for x in para.split(" ") if x]
            if not words:
                lines.append("")
                continue
            cur, cur_w = [], 0.0
            for word in words:
                ww = self._word_w(word, key)
                if ww > limit:
                    if cur:
                        lines.append(" ".join(cur))
                        cur, cur_w = [], 0.0
                    pieces = self._hard_break(word, key, limit)
                    lines += pieces[:-1]
                    cur, cur_w = [pieces[-1]], self._word_w(pieces[-1], key)
                    continue
                add = ww + (space if cur else 0.0)
                if cur and cur_w + add > limit:
                    lines.append(" ".join(cur))
                    cur, cur_w = [word], ww
                else:
                    cur.append(word)
                    cur_w += add
            if cur:
                lines.append(" ".join(cur))
        return lines

    def line_out(self, x: float, y: float, w: float, line: str, fam: str, style: str, size: float, color,
                 align: str, lh: float) -> None:
        self.set_xy(x, y)
        self.font(fam, style, size, color)
        with self.shaping_for(line):
            self.cell(w, lh, line, align=align)

    def text_h(self, w: float, text: str, fam: str, style: str, size: float, lh: float | None = None) -> float:
        text = clean(text)
        if not text:
            return 0.0
        self.set_font(fam, style, size)
        self.set_char_spacing(0)
        with self.shaping_for(text):
            return self.multi_cell(w, lh or _lh(size), text, dry_run=True, output="HEIGHT")

    def para(self, x: float, y: float, w: float, text: str, fam: str, style: str = "", size: float = 9.5,
             color=INK, align: str = "L", lh: float | None = None, spacing: float = 0.0) -> float:
        """multi_cell at (x, y); returns the y below it."""
        text = clean(text)
        if not text:
            return y
        self.set_xy(x, y)
        self.font(fam, style, size, color, spacing)
        with self.shaping_for(text):
            self.multi_cell(w, lh or _lh(size), text, align=align, new_x="LEFT", new_y="NEXT")
        self.set_char_spacing(0)
        return self.get_y()

    def label(self, x: float, y: float, w: float, text: str, color=MUTED, size: float = 7.5, align: str = "L",
              bold: bool = False) -> float:
        """Small uppercase letter-spaced label."""
        return self.para(x, y, w, text.upper(), "semi" if bold else "sans", "", size, color, align, _lh(size, 1.35),
                         spacing=0.45)

    def page_number(self, x: float, y: float, w: float, size: float = 7.5) -> None:
        # alias substitution needs the un-shaped text path
        self.set_text_shaping(False)
        self.set_xy(x, y)
        self.font("sans", "", size, MUTED)
        self.cell(w, 4, f"Page {self.page_no()} of {{nb}}", align="R")
        self.set_text_shaping(True, features=self._features)

    def hair(self, x1: float, y1: float, x2: float, y2: float, color=HAIR, width: float = 0.106) -> None:
        self.set_draw_color(*color)
        self.set_line_width(width)
        self.line(x1, y1, x2, y2)


class Bilingual:
    """Native line (larger) with its English line (smaller, dark grey) directly beneath; English only when there is
    no translation."""

    def __init__(self, native: str, english: str, lang: str, size: float = 13.5, esize: float = 9.5,
                 style: str = "", estyle: str = "", color=BLACK, ecolor=GREY):
        native, english = (native or "").strip(), (english or "").strip()
        self.fam = font_for(lang)
        self.rtl = lang in RTL_LANGS
        if not native or lang == "en":
            native, english, self.fam, self.rtl = english, "", "sans", False
            size = min(size, 12) if lang != "en" else min(size, 12)
        self.native, self.english = native, english
        self.size, self.esize, self.style, self.estyle = size, esize, style, estyle
        self.color, self.ecolor = color, ecolor

    def height(self, pdf: _Doc, w: float) -> float:
        return pdf.text_h(w, self.native, self.fam, self.style, self.size) + \
            pdf.text_h(w, self.english, "sans", self.estyle, self.esize, _lh(self.esize, 1.3))

    def draw(self, pdf: _Doc, x: float, y: float, w: float) -> float:
        y = pdf.para(x, y, w, self.native, self.fam, self.style, self.size, self.color, "R" if self.rtl else "L")
        return pdf.para(x, y, w, self.english, "sans", self.estyle, self.esize, self.ecolor,
                        "R" if self.rtl else "L", _lh(self.esize, 1.3))


# ====================================================================== monochrome outline pictograms
def _arc_pts(cx, cy, r, a0, a1, n=24):
    """Points on a circle; angles in radians, y grows downwards (screen coordinates)."""
    return [(cx + math.cos(a0 + (a1 - a0) * k / n) * r, cy - math.sin(a0 + (a1 - a0) * k / n) * r) for k in range(n + 1)]


def _polyline(pdf: FPDF, pts) -> None:
    for p, q in zip(pts, pts[1:]):
        pdf.line(p[0], p[1], q[0], q[1])


def pictogram(pdf: FPDF, slot: str, cx: float, cy: float, r: float, color=BLACK) -> None:
    """Small line pictograms for the times of day: sunrise, sun, sunset, moon (no fills, one colour)."""
    pdf.set_draw_color(*color)
    pdf.set_line_width(0.28)
    if slot in ("morning", "evening"):
        base = cy + r * 0.45
        _polyline(pdf, _arc_pts(cx, base, r * 0.75, 0, math.pi))
        for k in (1, 2, 3):
            a = math.pi * k / 4
            pdf.line(cx + math.cos(a) * r * 1.0, base - math.sin(a) * r * 1.0,
                     cx + math.cos(a) * r * 1.35, base - math.sin(a) * r * 1.35)
        pdf.line(cx - r * 1.45, base, cx + r * 1.45, base)
        ay = base + r * 0.32
        if slot == "morning":   # arrow up
            pdf.line(cx - r * 0.28, ay + r * 0.28, cx, ay)
            pdf.line(cx, ay, cx + r * 0.28, ay + r * 0.28)
        else:                   # arrow down
            pdf.line(cx - r * 0.28, ay, cx, ay + r * 0.28)
            pdf.line(cx, ay + r * 0.28, cx + r * 0.28, ay)
    elif slot == "noon":
        pdf.circle(cx, cy, r * 0.55, style="D")
        for k in range(8):
            a = math.pi * k / 4
            pdf.line(cx + math.cos(a) * r * 0.8, cy - math.sin(a) * r * 0.8,
                     cx + math.cos(a) * r * 1.15, cy - math.sin(a) * r * 1.15)
    else:  # bedtime: crescent moon outline
        R = r * 0.95
        a_end = math.radians(63)
        outer = _arc_pts(cx, cy, R, a_end, 2 * math.pi - a_end, 30)
        ex, ey = math.cos(a_end) * R, math.sin(a_end) * R
        icx = 0.55 * R
        ir = math.hypot(ex - icx, ey)
        t0 = math.atan2(ey, ex - icx)
        inner = _arc_pts(cx + icx, cy, ir, 2 * math.pi - t0, t0, 30)
        _polyline(pdf, outer + inner + [outer[0]])


# ====================================================================== table engine (hairline, no fills)
class Cell:
    """A stack of paragraphs inside a table cell. part = (text, fam, style, size, color[, lh, align]).
    Text is line-broken ONCE per width (cached) and drawn line by line, so a cell taller than a page can be sliced
    across pages without re-measuring (long transcripts stay fast)."""

    def __init__(self, *parts, _layout=None):
        self.parts = [p for p in parts if p and p[0]]
        self._cache = _layout  # (w, [items])

    def layout(self, pdf: _Doc, w: float) -> list:
        if self._cache is not None and abs(self._cache[0] - w) < 1e-6:
            return self._cache[1]
        items = []
        for p in self.parts:
            text, fam, style, size, color = p[:5]
            lh = p[5] if len(p) > 5 and p[5] else _lh(size, 1.32)
            align = p[6] if len(p) > 6 and p[6] else "L"
            try:
                lines = pdf.wrap(text, fam, style, size, w)
            except Exception as e:  # noqa: BLE001 - one bad string must not lose the document
                lines, fam, style, color = [f"[text could not be rendered: {type(e).__name__}]"], "sans", "", BLACK
            if lines:
                items.append(("text", lines, fam, style, size, color, lh, align))
        self._cache = (w, items)
        return items

    @staticmethod
    def _item_h(it) -> float:
        return len(it[1]) * it[6]

    def height(self, pdf: _Doc, w: float) -> float:
        return sum(self._item_h(it) for it in self.layout(pdf, w))

    def draw(self, pdf: _Doc, x: float, y: float, w: float) -> None:
        for it in self.layout(pdf, w):
            _, lines, fam, style, size, color, lh, align = it
            for ln in lines:
                try:
                    pdf.line_out(x, y, w, ln, fam, style, size, color, align, lh)
                except Exception as e:  # noqa: BLE001
                    pdf.line_out(x, y, w, f"[line could not be rendered: {type(e).__name__}]", "sans", "", 7, BLACK,
                                 "L", lh)
                y += lh

    def slice(self, pdf: _Doc, w: float, max_h: float) -> tuple["Cell", "Cell | None"]:
        """(part that fits in max_h, remainder or None), cutting between lines."""
        head, tail, used = [], [], 0.0
        for it in self.layout(pdf, w):
            if tail:
                tail.append(it)
                continue
            h = self._item_h(it)
            if used + h <= max_h:
                head.append(it)
                used += h
            else:
                n = max(0, int((max_h - used) // it[6]))
                if n:
                    head.append(it[:1] + (it[1][:n],) + it[2:])
                tail.append(it[:1] + (it[1][n:],) + it[2:])
        return Cell(_layout=(w, head)), (Cell(_layout=(w, tail)) if tail else None)


def table(pdf: _Doc, widths: list[float], header: list[str], rows: list[list[Cell]], pad: float = 1.5,
          hsize: float = 8.5) -> None:
    """Table: SemiBold grey header, a 0.6 pt rule under it, 0.3 pt light rules between body rows; no outer border,
    no vertical lines, no fills. Normal rows
    never split across pages and the header repeats after every page break; a single row taller than a page (e.g. a
    2,000-character utterance) is sliced between lines across pages."""
    x0 = pdf.l_margin
    total = sum(widths)
    bottom = pdf.h - pdf.b_margin
    hh = max(pdf.text_h(w - 2 * pad, h, "semi", "", hsize, _lh(hsize, 1.3)) for w, h in zip(widths, header)) + 2 * pad

    def draw_header():
        y = pdf.get_y()
        x = x0
        for w, h in zip(widths, header):
            pdf.para(x + pad, y + pad, w - 2 * pad, h, "semi", "", hsize, GREY, "L", _lh(hsize, 1.3))
            x += w
        pdf.hair(x0, y + hh, x0 + total, y + hh, RULE_HEAD, W_HEAD)
        pdf.set_y(y + hh)
        state["first"] = True

    state = {"first": True}

    def draw_row(row, rh):
        y = pdf.get_y()
        if not state["first"]:
            pdf.hair(x0, y, x0 + total, y, ROW_RULE, W_ROW)
        state["first"] = False
        x = x0
        for c, w in zip(row, widths):
            c.draw(pdf, x + pad, y + pad, w - 2 * pad)
            x += w
        pdf.set_y(y + rh)

    def new_page():
        pdf.add_page()
        draw_header()

    if pdf.get_y() + hh + 10 > bottom:
        pdf.add_page()
    draw_header()
    full = bottom - pdf.t_margin - hh
    inner = [w - 2 * pad for w in widths]
    for row in rows:
        rh = max([c.height(pdf, w) for c, w in zip(row, inner)] + [3.5]) + 2 * pad
        if pdf.get_y() + rh <= bottom:
            draw_row(row, rh)
            continue
        if rh <= full - 2:
            new_page()
            draw_row(row, rh)
            continue
        if bottom - pdf.get_y() < 30:
            new_page()
        guard = 0
        while row is not None and guard < 500:
            guard += 1
            avail = bottom - pdf.get_y() - 2 * pad
            heads, tails = [], []
            for c, w in zip(row, inner):
                h, t = c.slice(pdf, w, avail)
                heads.append(h)
                tails.append(t)
            sh = max([c.height(pdf, w) for c, w in zip(heads, inner)] + [3.5]) + 2 * pad
            draw_row(heads, sh)
            if all(t is None for t in tails):
                row = None
            else:
                row = [t if t is not None else Cell() for t in tails]
                new_page()


def _safe(pdf: "_Doc", name: str, fn, *args) -> None:
    """Run one section; on any error render a placeholder instead of failing the whole document."""
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001
        try:
            pdf.set_text_shaping(True, features=pdf._features)
            pdf.set_left_margin(MARGIN)
            pdf.set_right_margin(MARGIN)
            pdf.set_char_spacing(0)
            if pdf.get_y() > pdf.h - pdf.b_margin - 8:
                pdf.add_page()
            pdf.para(pdf.l_margin, pdf.get_y() + 1, pdf.epw,
                     f"[{name}: this section could not be printed ({type(e).__name__}). See the on-screen version.]",
                     "sans", "", 8.5, BLACK)
            pdf.set_y(pdf.get_y() + 2)
        except Exception:  # noqa: BLE001
            pass


def render_plain_pdf(title: str, text: str, path) -> str:
    """Last-resort PDF: plain text, no layout. Tries the Noto fonts with shaping first, then the built-in Helvetica
    (Latin only), so a file always exists."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pdf = _Doc()
        pdf.add_page()
        pdf.para(pdf.l_margin, pdf.get_y(), pdf.epw, title, "sans", "B", 14)
        for line in clean(text).split("\n"):
            pdf.set_x(pdf.l_margin)
            pdf.font("sans", "", 9.5)
            pdf.multi_cell(pdf.epw, 5, line or " ", new_x="LMARGIN", new_y="NEXT")
        pdf.output(str(path))
    except Exception:  # noqa: BLE001
        from fpdf import FPDF as _Core

        pdf = _Core()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        safe = (title + "\n\n" + str(text)).encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 5, safe)
        pdf.output(str(path))
    return str(path)


# ====================================================================== shared section heading (both documents)
SEC_ABOVE, SEC_GAP, SEC_BELOW = 5.0, 1.5, 2.5   # mm: above the heading, heading -> rule, below the rule
# Patient sheet: more air so each section and each medicine reads as its own block (user: "looks confusing")
P_SEC_ABOVE, P_ITEM_GAP, P_MED_GAP = 10.0, 4.5, 7.0


def section_rule(pdf: "_Doc", y: float) -> float:
    """The one light rule under every section heading; returns the y where content starts."""
    pdf.hair(pdf.l_margin, y, pdf.l_margin + pdf.epw, y, HAIR, W_LIGHT)
    return y + SEC_BELOW


# ====================================================================== patient sheet
SLOTS = ("wake", "breakfast", "lunch", "dinner", "bedtime")


def render_care_plan_pdf(care_plan: dict, path, audio_url: str | None = None) -> str:
    """Patient sheet "Your medicines and care instructions": native script first, English directly beneath.
    Sections: Your medicines (every medicine as a small pharmacy-label block: name + strength + form, then one plain
    instruction), Do not take, Other instructions, Call 999 or come back now if. Separators, exactly: one 0.6 pt rule
    under the header and one 0.4 pt light rule under each section heading. No boxes, no QR, no footer (a page number
    only if the sheet runs to 2+ pages). Red only for the two safety headings. `audio_url` is accepted for API
    compatibility and not printed (the audio goes out by WhatsApp)."""
    # Never squeeze the spacing to force one page (that made long sheets cramped and confusing): keep the full
    # spacing and let the sheet continue on page 2, numbered "1/2", "2/2".
    pdf = _render_plan(care_plan, 1.0, numbered=False)
    if pdf.page_no() > 1:
        pdf = _render_plan(care_plan, 1.0, numbered=True)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return str(path)


def _render_plan(care_plan: dict, Z: float, numbered: bool) -> "_Doc":
    """Z (1 .. 0.3) only tightens vertical spacing when the content is long; type sizes stay fixed."""
    lang = care_plan.get("lang", "en")
    L, E = labels(lang), labels("en")
    fam = font_for(lang)
    rtl = lang in RTL_LANGS
    nat = lang != "en"
    al = "R" if rtl else "L"
    pdf = _Doc()
    pdf.set_auto_page_break(True, margin=16 if numbered else 12)  # no footer on a one-page sheet
    pdf.set_title(f"{E['title']} ({LANG_NAMES.get(lang, lang)})")
    pdf.set_lang(lang)

    def footer(p: _Doc):
        if numbered:
            p.set_text_shaping(False)
            p.set_xy(p.l_margin, p.h - 12)
            p.font("sans", "", 8, GREY)
            p.cell(p.epw, 4, f"{p.page_no()}/{{nb}}", align="C")
            p.set_text_shaping(True, features=p._features)

    pdf.footer_fn = footer
    pdf.add_page()
    X0, W = pdf.l_margin, pdf.epw

    def heading(native: str, english: str, color=BLACK, need: float = 24.0):
        y = pdf.get_y() + P_SEC_ABOVE * Z
        if y + need > pdf.h - pdf.b_margin:
            pdf.add_page()
            y = pdf.get_y()
        if nat and native.strip() != english.strip():
            y = pdf.para(X0, y, W, native, fam, "B", 13, color, al, _lh(13, 1.35))
            y = pdf.para(X0, y - 0.3, W, english, "sans", "", 9, color if color != BLACK else GREY, al, 4.2)
        else:
            y = pdf.para(X0, y, W, english, "sans", "B", 13, color, "L", _lh(13, 1.35))
        pdf.set_y(section_rule(pdf, y + SEC_GAP))

    def lines(items: list, indent: float = 4.5):
        for k, b in enumerate(items):
            y = pdf.get_y() + (P_ITEM_GAP * Z if k else 0.0)
            if y + b.height(pdf, W - indent) > pdf.h - pdf.b_margin:
                pdf.add_page()
                y = pdf.get_y()
            nh = _lh(b.size)
            pdf.set_fill_color(*BLACK)
            pdf.circle((X0 + W - 1.3) if b.rtl else (X0 + 1.3), y + nh / 2, 0.6, style="F")
            pdf.set_y(b.draw(pdf, X0 if b.rtl else X0 + indent, y, W - indent))

    def pair(a: dict) -> "Bilingual":
        return Bilingual(a.get("native", ""), a.get("en", ""), lang, 13, 9.5)

    def sec_header():
        y = MARGIN - 4
        if nat and L["title"].strip() != E["title"].strip():
            y1 = pdf.para(X0, y, W, L["title"], fam, "B", 18, BLACK, al, _lh(18, 1.35))
            y1 = pdf.para(X0, y1 - 0.4, W, E["title"], "sans", "", 10, GREY, al, 4.8)
        else:
            y1 = pdf.para(X0, y, W, E["title"], "sans", "B", 18, BLACK, "L", _lh(18, 1.35))
        date = care_plan.get("date") or datetime.now().strftime("%Y-%m-%d")
        try:
            date = datetime.strptime(date, "%Y-%m-%d").strftime("%d %b %Y")
        except ValueError:
            pass
        meta = " · ".join(x for x in (care_plan.get("clinic") or "", date) if x)
        y1 = pdf.para(X0, y1 + 0.8, W, meta, "sans", "", 9, GREY, al, 4.4) + 2.5
        pdf.hair(X0, y1, X0 + W, y1, RULE_HEAD, W_HEAD)
        pdf.set_y(y1 + 1.0)

    def inline_pair(y: float, native: str, english: str, nsize: float, esize: float, nstyle: str = "B") -> float | None:
        """Native (bold) and its English on ONE line when both fit; returns the new y, or None if they do not fit."""
        native, english = clean(native), clean(english)
        pdf.font(fam, nstyle, nsize)
        with pdf.shaping_for(native):
            nw = pdf.get_string_width(native) + 2 * pdf.c_margin
        pdf.font("semi", "", esize)
        ew = pdf.get_string_width(english) + 2 * pdf.c_margin
        if nw + 3 + ew > W:
            return None
        lh = _lh(nsize, 1.35)
        base = y + lh * 0.62  # align the English baseline roughly with the native one
        if rtl:
            pdf.line_out(X0 + W - nw, y, nw, native, fam, nstyle, nsize, BLACK, "R", lh)
            pdf.line_out(X0 + W - nw - 3 - ew, base - _lh(esize, 1.3) * 0.62, ew, english, "semi", "", esize, GREY,
                         "R", _lh(esize, 1.3))
        else:
            pdf.line_out(X0, y, nw, native, fam, nstyle, nsize, BLACK, "L", lh)
            pdf.line_out(X0 + nw + 3, base - _lh(esize, 1.3) * 0.62, ew, english, "semi", "", esize, GREY, "L",
                         _lh(esize, 1.3))
        return y + lh

    def sec_meds():
        meds = care_plan.get("medicines") or []
        if not meds:
            return
        heading(L["medicines"], E["medicines"], need=34)
        for k, m in enumerate(meds):
            title_en = m.get("title_en") or m.get("name") or ""
            tn = bool(nat and m.get("title_native"))
            ln = bool(nat and m.get("note_native"))
            note = [(m["note_native"] if ln else (m.get("note_en") or ""), fam if ln else "sans", "", 13, BLACK,
                     _lh(13, 1.4)),
                    ((m.get("note_en") or "") if ln else "", "sans", "", 9.5, GREY, _lh(9.5, 1.3))]
            note = [b for b in note if b[0]]
            h = _lh(13, 1.35) * (1 if tn else 1) + 5 + sum(pdf.text_h(W, t, f, st, sz, lh) for t, f, st, sz, _c, lh in note)
            y = pdf.get_y() + (P_MED_GAP * Z if k else 0.0)
            if y + h > pdf.h - pdf.b_margin:
                pdf.add_page()
                y = pdf.get_y()
            # line 1: name + strength + form (native bold, English beside it when it fits, else beneath)
            y2 = inline_pair(y, m["title_native"], title_en, 13, 9.5) if tn else None
            if y2 is None:
                y2 = pdf.para(X0, y, W, m["title_native"] if tn else title_en, fam if tn else "sans", "B", 13, BLACK,
                              al, _lh(13, 1.35))
                if tn:
                    y2 = pdf.para(X0, y2, W, title_en, "semi", "", 9.5, GREY, al, _lh(9.5, 1.3))
            y = y2 + 0.8
            # line 2: the instruction (native, English beneath)
            for t, f, st, sz, c, lh in note:
                y = pdf.para(X0, y, W, t, f, st, sz, c, al, lh)
            pdf.set_y(y)

    def sec_schedule():
        """Quick summary of the regular medicines: only the slots somebody uses; the amount only."""
        if os.environ.get("BAYAN_PDF_SCHEDULE_TABLE", "on").strip().lower() in ("0", "off", "false", "no"):
            return
        regular = [m for m in care_plan.get("medicines") or [] if not m.get("prn") and m.get("slots")]
        if not regular:
            return
        used = [sl for sl in SLOTS if any(sl in (m.get("slots") or []) for m in regular)]
        heading(L["schedule"], E["schedule"], need=30)
        # Column widths from the content: the name column only as wide as the longest name (no dead space before
        # the first time column); time columns share the rest evenly up to a comfortable maximum, and the table is
        # simply narrower than the page when there are few columns.
        rows_all = regular + [m for m in care_plan.get("medicines") or [] if m.get("prn")]

        def _w(text: str, family: str, style: str, size: float) -> float:
            if not text:
                return 0.0
            pdf.font(family, style, size)
            with pdf.shaping_for(text):
                return pdf.get_string_width(text)

        longest = max([_w(L["medicine"] if nat else E["medicine"], fam if nat else "sans", "B", 9.5),
                       _w(E["medicine"], "sans", "", 7.5)] +
                      [max(_w(m.get("name_native") or "", fam, "B", 12) if nat else 0.0,
                           _w(m.get("name") or "", "sans", "B" if not nat else "", 12 if not nat else 8.5))
                       for m in rows_all])
        name_w = min(max(longest + 8.0, 30.0), W * 0.42)
        slot_w = min(34.0, (W - name_w) / max(len(used), 1))
        if W - (name_w + slot_w * len(used)) < 25.0:   # nearly full width: fill it, so the rules line up with the page
            slot_w = (W - name_w) / max(len(used), 1)
        TW = name_w + slot_w * len(used)
        TX = X0 + (W - TW) if rtl else X0
        cols = [("name", name_w)] + [(sl, slot_w) for sl in used]
        if rtl:
            cols = cols[::-1]
        hs = min(pdf.fit_size(L[k] if nat else E[k], fam if nat else "sans", "B", 9.5, slot_w - 1.5, 6.5)
                 for k in used)
        # every column has a header (an unlabelled first column read as an empty column)
        heads = [Cell((L["medicine"] if nat else E["medicine"], fam if nat else "sans", "B", hs, BLACK, _lh(hs, 1.3),
                       al), (E["medicine"] if nat else "", "sans", "", 7.5, GREY, 3.4, al)) if k == "name" else
                 Cell((L[k] if nat else E[k], fam if nat else "sans", "B", hs, BLACK, _lh(hs, 1.3), "C"),
                      (E[k] if nat else "", "sans", "", 7.5, GREY, 3.4, "C")) for k, _w in cols]
        y = pdf.get_y()
        hh = max(c.height(pdf, w) for c, (_k, w) in zip(heads, cols)) + 1.5
        if y + hh + 14 > pdf.h - pdf.b_margin:
            pdf.add_page()
            y = pdf.get_y()
        x = TX
        for c, (_k, w) in zip(heads, cols):
            c.draw(pdf, x, y, w)
            x += w
        y += hh
        pdf.hair(TX, y, TX + TW, y, RULE_HEAD, W_HEAD)
        for ri, m in enumerate(regular):
            nn = bool(nat and m.get("name_native"))
            name = Cell((m["name_native"] if nn else m.get("name") or "", fam if nn else "sans", "B", 12, BLACK,
                         _lh(12, 1.4), al), ((m.get("name") or "") if nn else "", "sans", "", 8.5, GREY, 3.6, al))
            an = bool(nat and m.get("dose_amount_native"))
            amt = Cell((m["dose_amount_native"] if an else m.get("dose_amount_en") or "", fam if an else "sans", "B",
                        11, BLACK, _lh(11, 1.4), "C"), ((m.get("dose_amount_en") or "") if an else "", "sans", "", 8,
                                                        GREY, None, "C"))
            rh = max(name.height(pdf, name_w - 2), amt.height(pdf, slot_w - 1.5), 7) + 4.0 * Z
            if y + rh > pdf.h - pdf.b_margin:
                pdf.add_page()
                y = pdf.get_y()
            elif ri:
                pdf.hair(TX, y, TX + TW, y, ROW_RULE, W_ROW)
            x = TX
            for k, w in cols:
                if k == "name":
                    name.draw(pdf, x, y + 2.0 * Z, w - 2)
                elif k in (m.get("slots") or []):
                    amt.draw(pdf, x + 0.75, y + 2.0 * Z, w - 1.5)
                x += w
            y += rh
        # as-needed medicines close the table, so it shows the whole day: one cell across the time columns
        # ("1 g, only when needed"). A sheet with ONLY as-needed medicines gets no table (it would repeat the list).
        span_w = slot_w * len(used)
        for m in [m for m in care_plan.get("medicines") or [] if m.get("prn")]:
            nn = bool(nat and m.get("name_native"))
            name = Cell((m["name_native"] if nn else m.get("name") or "", fam if nn else "sans", "B", 12, BLACK,
                         _lh(12, 1.4), al), ((m.get("name") or "") if nn else "", "sans", "", 8.5, GREY, 3.6, al))
            amt_en = m.get("dose_amount_en") or ""
            amt_nat = m.get("dose_amount_native") or amt_en
            en_line = ", ".join(x for x in (amt_en, E["prn"].lower()) if x)
            nat_line = ", ".join(x for x in (amt_nat, L["prn"]) if x)
            span = Cell((nat_line if nat else en_line[:1].upper() + en_line[1:], fam if nat else "sans", "B", 11,
                         BLACK, _lh(11, 1.4), "C"), (en_line if nat else "", "sans", "", 8, GREY, None, "C"))
            rh = max(name.height(pdf, name_w - 2), span.height(pdf, span_w - 1.5), 7) + 4.0 * Z
            if y + rh > pdf.h - pdf.b_margin:
                pdf.add_page()
                y = pdf.get_y()
            else:
                pdf.hair(TX, y, TX + TW, y, ROW_RULE, W_ROW)
            name_x, span_x = (TX + span_w, TX) if rtl else (TX, TX + name_w)
            name.draw(pdf, name_x, y + 2.0 * Z, name_w - 2)
            span.draw(pdf, span_x + 0.75, y + 2.0 * Z, span_w - 1.5)
            y += rh
        pdf.set_y(y)

    def sec_avoid():
        avoid = care_plan.get("avoid") or []
        if avoid:
            heading(L["avoid"], E["avoid"], color=RED)
            lines([pair(a) for a in avoid])

    def sec_other():
        items = list(care_plan.get("advice") or [])
        fu = care_plan.get("follow_up") or {}
        if fu.get("en") or fu.get("native"):
            items.append(fu)
        if items:
            heading(L["other"], E["other"])
            lines([pair(a) for a in items])

    def sec_red():
        flags = care_plan.get("red_flags") or []
        if flags:
            heading(L["red_flags"], E["red_flags"], color=RED)
            lines([pair(f) for f in flags])
        else:  # never an empty "Call 999 if" heading: one plain line instead
            heading(L["emergency"], E["emergency"], color=RED, need=14)

    _safe(pdf, "Header", sec_header)
    _safe(pdf, "Your medicines", sec_meds)
    _safe(pdf, "Daily schedule", sec_schedule)
    _safe(pdf, "Do not take", sec_avoid)
    _safe(pdf, "Other instructions", sec_other)
    _safe(pdf, "Call 999", sec_red)
    return pdf


# ====================================================================== clinic note (doctor)
_IDS = re.compile(r"\s*\[(?:u\d{3}[^\]]*)\]|\(\s*u\d{3}(?:\s*,\s*u\d{3})*\s*\)|\bu\d{3}\b")
_PROVENANCE = re.compile(r"\s*\((?:as )?stated by (?:the )?clinician\)", re.I)
_SECTION_KEYS = {"allergies": "allergies", "presenting complaint": "presenting_complaint", "history": "history",
                 "observations and investigations": "observations", "assessment": "assessment", "plan": "plan",
                 "medication changes": "medication_changes",
                 "information given to patient": "information_given", "safety alerts": "safety_alerts"}


def _parse_note(md: str) -> tuple[dict[str, list[str]], list[str], bool]:
    """Markdown note -> ({section key: lines}, section order, fallback flag). Unknown headings are kept as-is."""
    secs: dict[str, list[str]] = {}
    order: list[str] = []
    cur = None
    fallback = False
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            title = line[3:].strip()
            cur = _SECTION_KEYS.get(title.lower(), title)
            secs.setdefault(cur, [])
            order.append(cur)
            continue
        if line.startswith(">"):
            fallback = fallback or "auto-generated" in line.lower()
            continue
        if cur is None or not line.strip():
            continue
        body = line.lstrip()[2:] if line.lstrip().startswith(("- ", "* ")) else line.strip()
        body = _IDS.sub("", body).replace("**", "").strip()
        if body:
            secs[cur].append(body)
    return secs, order, fallback


def _doc_heading(pdf: _Doc, title: str, need: float = 16.0) -> None:
    """11 pt SemiBold sentence-case heading + one light rule; identical spacing for every section."""
    y = pdf.get_y() + SEC_ABOVE
    if y + need > pdf.h - pdf.b_margin:
        pdf.add_page()
        y = pdf.get_y()
    y = pdf.para(pdf.l_margin, y, pdf.epw, title, "semi", "", 11, BLACK, "L", 5.6)
    pdf.set_y(section_rule(pdf, y + SEC_GAP))


def _doc_bullets(pdf: _Doc, lines: list[str], size: float = 9.5) -> None:
    x0, w = pdf.l_margin, pdf.epw
    for k, ln in enumerate(lines):
        h = pdf.text_h(w - 4.5, ln, "sans", "", size, _lh(size, 1.35))
        y = pdf.get_y() + (1.0 if k else 0.0)
        if y + h > pdf.h - pdf.b_margin:
            pdf.add_page()
            y = pdf.get_y()
        pdf.set_fill_color(*BLACK)
        pdf.circle(x0 + 1.4, y + _lh(size, 1.35) / 2, 0.5, style="F")
        pdf.set_y(pdf.para(x0 + 4.5, y, w - 4.5, ln, "sans", "", size, BLACK, "L", _lh(size, 1.35)))


def render_doctor_report(consult, note_md: str, path, care_plan: dict | None = None) -> str:
    """Clinic note for the hospital record ("Consultation note"). Separators, exactly: a 0.6 pt rule under the
    header; a light panel (no borders) with 8 identification fields in a 4 x 2 grid; one 0.4 pt light rule under
    each section heading; tables with a 0.6 pt rule under the header row and 0.3 pt light rules between rows;
    sign-off lines; "Page X of Y". Colour only on the Bayan AI wordmark. Text sections come from note_md (the doctor
    may have edited it); the panel and tables come from the structured record. Transcript on a new page. Every block
    renders independently: a failing block becomes a placeholder, never a missing PDF."""
    from bayan.brain import wrapup as WU
    from bayan.brain.state import fmt_t

    with consult.lock:
        turns = list(consult.turns)
    tabs = WU.note_tables(consult, care_plan)
    secs, order, _fallback = _parse_note(clean(note_md or ""))
    started = datetime.fromtimestamp(consult.started_at)
    clinic = (care_plan or {}).get("clinic") or WU.clinic_name(consult)
    pdf = _Doc()
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_title("Consultation note")
    pdf.set_subject(f"Encounter {consult.id}")
    pdf.set_lang("en")

    def footer(p: _Doc):
        p.page_number(p.l_margin + p.epw - 40, p.h - 12, 40, 8)

    pdf.footer_fn = footer
    pdf.add_page()
    X0, Wd = pdf.l_margin, pdf.epw

    def header():
        y = MARGIN - 5
        pdf.para(X0, y, 80, "Bayan AI", "sans", "B", 17, ACCENT, "L", 8)
        yl = pdf.para(X0, y + 8, 90, "Interpreter & Clinical Safety Copilot", "sans", "", 8.5, GREY, "L", 4.2)
        yr = pdf.para(X0 + Wd - 100, y + 0.6, 100, "Consultation note", "semi", "", 12, BLACK, "R", 6)
        if clinic:
            yr = pdf.para(X0 + Wd - 100, yr, 100, clinic, "sans", "", 8.5, GREY, "R", 4.2)
        yr = pdf.para(X0 + Wd - 100, yr, 100, f"Encounter {str(consult.id).upper()}", "sans", "", 8.5, GREY, "R", 4.2)
        yr = pdf.para(X0 + Wd - 100, yr, 100, f"{started:%d %b %Y, %H:%M}", "sans", "", 8.5, GREY, "R", 4.2)
        y = max(yl, yr) + 2.5
        pdf.hair(X0, y, X0 + Wd, y, RULE_HEAD, W_HEAD)
        pdf.set_y(y + 4.0)

    def encounter():
        enc = dict(tabs["encounter"])
        dur = (turns[-1].t_min - turns[0].t_min) if turns else None
        nr = "Not recorded"
        fields = [("Patient ID", enc.get("Patient ID") or nr), ("Age / sex", enc.get("Age / sex") or nr),
                  ("Patient language", WU.LANG_NAME(consult.patient_lang) or nr),
                  ("Clinician language", WU.LANG_NAME(consult.doctor_lang) or nr),
                  ("Interpretation", "Bayan AI"),
                  ("Consent to interpretation", enc.get("Consent to interpretation") or nr),
                  ("Encounter start", f"{started:%Y-%m-%d %H:%M}"),
                  ("Duration", f"{int(round(dur))} min" if dur is not None else nr)]
        cw = Wd / 4
        pad = 2.4
        rows = [fields[:4], fields[4:]]
        heights = [max(pad + 3.6 + 0.6 + pdf.text_h(cw - 2 * pad, v, "sans", "", 9.5, _lh(9.5, 1.35)) for _, v in r)
                   + pad for r in rows]
        y = pdf.get_y()
        total = sum(heights)
        cy = y
        for ri, (r, rh) in enumerate(zip(rows, heights)):
            if ri:
                pdf.hair(X0, cy, X0 + Wd, cy, HAIR, W_ROW)
            for ci, (k, v) in enumerate(r):
                cx = X0 + ci * cw
                if ci:
                    pdf.hair(cx, cy, cx, cy + rh, HAIR, W_ROW)
                yy = pdf.para(cx + pad, cy + pad, cw - 2 * pad, k, "sans", "", 7.5, GREY, "L", 3.6)
                pdf.para(cx + pad, yy + 0.6, cw - 2 * pad, v, "sans", "", 9.5, BLACK, "L", _lh(9.5, 1.35))
            cy += rh
        pdf.set_draw_color(*RULE_HEAD)
        pdf.set_line_width(0.5 * 0.3528)
        pdf.rect(X0, y, Wd, total, style="D")
        pdf.set_y(y + total)

    def allergies():
        _doc_heading(pdf, "Allergies")
        for k, ln in enumerate(secs.get("allergies") or tabs["allergies"] or ["No known allergies recorded"]):
            y = pdf.get_y() + (1.0 if k else 0.0)
            pdf.set_y(pdf.para(X0, y, Wd, ln, "sans", "B", 9.5, BLACK, "L", _lh(9.5, 1.35)))

    def text_section(key: str, title: str):
        lines = [_PROVENANCE.sub("", x) for x in secs.get(key) or []]
        if not lines:
            return
        _doc_heading(pdf, title)
        if key == "presenting_complaint":
            pdf.set_y(pdf.para(X0, pdf.get_y(), Wd, " ".join(lines), "sans", "", 9.5, BLACK, "L", _lh(9.5, 1.35)))
        else:
            _doc_bullets(pdf, lines)

    def observations():
        rows = list(tabs["observations"])
        names = {r[0].lower() for r in rows} | {t.lower() for t, _s, _r in tabs["tests"]}
        extra = [_PROVENANCE.sub("", ln) for ln in secs.get("observations", [])
                 if ln.split(":", 1)[0].strip().lower() not in names and not ln.lower().startswith(("bp ", "hr ",
                                                                                                  "rr ", "spo2", "temp"))]
        if not rows and not extra:
            return
        _doc_heading(pdf, "Observations and investigations", need=24)
        if rows:
            table(pdf, [60, 28, Wd - 88], ["Test", "Status", "Result (as stated by clinician)"],
                  [[Cell((t, "sans", "", 9.5, BLACK)), Cell((s, "sans", "", 9.5, BLACK)),
                    Cell((r, "sans", "", 9.5, BLACK))] for t, s, r in rows])
        if extra:
            pdf.set_y(pdf.get_y() + 2.0)
            _doc_bullets(pdf, extra)

    def med_changes():
        rows = tabs["med_changes"]
        if not rows:
            return
        _doc_heading(pdf, "Medication changes", need=22)
        out = []
        for m in rows:
            st = "S" if m["stopped"] else ""
            col = GREY if m["stopped"] else BLACK
            cells = [m["medicine"], m["dose"], m["route"], m["frequency"], m["duration"]]
            cells = ["" if c in ("—", "Not stated") else c for c in cells]
            out.append([Cell((cells[0], "sans", st, 9.5, col))] + [Cell((c, "sans", "", 9.5, col)) for c in cells[1:]]
                       + [Cell((m["status"], "sans", "", 9.5, BLACK))])
        table(pdf, [30, 17, 18, 45, 22, Wd - 132], ["Medicine", "Dose", "Route", "Frequency", "Duration", "Status"],
              out)

    def signoff():
        if pdf.get_y() + 26 > pdf.h - pdf.b_margin:
            pdf.add_page()
        y = pdf.get_y() + 14
        x = X0
        for lab, cw in (("Reviewed by", 70), ("Signature", 52), ("Date/time", 52)):
            pdf.hair(x, y + 5, x + cw - 6, y + 5, RULE_HEAD, W_HEAD)
            pdf.para(x, y + 6, cw - 6, lab, "sans", "", 8, GREY, "L", 4)
            x += cw
        pdf.set_y(y + 12)

    def appendix():
        pdf.add_page()
        _doc_heading(pdf, "Transcript")
        rows = []
        for t in turns:
            try:
                who = {"doctor": "Clinician", "patient": "Patient", "bayan": "Interpreter"}.get(
                    t.role, str(t.role).capitalize())
                # "Said": the words as spoken. "Interpreted": what the other side got. For the clinician that is the
                # patient-language translation the patient heard (an audit of the interpretation itself); a held
                # sentence was never spoken. For the patient (and Bayan's own lines) it is the English rendering.
                plang = consult.patient_lang
                if t.role == "doctor":
                    said, slang = t.text, t.lang
                    if t.held:
                        interp, ilang = "Not spoken (held by the safety check).", "en"
                    else:
                        interp, ilang = (t.translation or t.english or ""), (plang if t.translation else "en")
                else:
                    said, slang = t.text, t.lang
                    interp, ilang = (t.english if t.english and t.english != t.text else ""), "en"
                rows.append([Cell((fmt_t(t.t_min), "sans", "", 8.5, BLACK)),
                             Cell((who, "sans", "", 8.5, BLACK), ("Held" if t.held else "", "semi", "", 8.5, BLACK)),
                             Cell((said, font_for(slang), "", 9, BLACK, _lh(9, 1.5),
                                   "R" if slang in RTL_LANGS else "L")),
                             Cell((interp, font_for(ilang), "", 8.5, BLACK, _lh(8.5, 1.4),
                                   "R" if ilang in RTL_LANGS else "L"))])
            except Exception as e:  # noqa: BLE001
                rows.append([Cell(), Cell(), Cell((f"[utterance could not be printed: {type(e).__name__}]", "sans", "",
                                                   8, BLACK)), Cell()])
        table(pdf, [16, 22, 69, Wd - 107], ["Time", "Speaker", "Said", "Interpreted"], rows, pad=1.6)

    _safe(pdf, "Header", header)
    _safe(pdf, "Patient and encounter", encounter)
    _safe(pdf, "Allergies", allergies)
    _safe(pdf, "Presenting complaint", text_section, "presenting_complaint", "Presenting complaint")
    _safe(pdf, "History", text_section, "history", "History")
    _safe(pdf, "Observations and investigations", observations)
    _safe(pdf, "Assessment", text_section, "assessment", "Assessment")
    _safe(pdf, "Plan", text_section, "plan", "Plan")
    _safe(pdf, "Medication changes", med_changes)
    _safe(pdf, "Information given to patient", text_section, "information_given", "Information given to patient")
    _safe(pdf, "Safety alerts", text_section, "safety_alerts", "Safety alerts")
    for key in order:  # headings the clinician added by hand
        if key not in _SECTION_KEYS.values():
            _safe(pdf, key, text_section, key, key)
    _safe(pdf, "Sign-off", signoff)
    _safe(pdf, "Transcript", appendix)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return str(path)
