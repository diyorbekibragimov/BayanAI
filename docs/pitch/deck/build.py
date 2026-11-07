"""Build the Bayan pitch deck: docs/pitch/deck/index.html (self-contained HTML, 1920x1080 slides).

Charts are inline SVG generated from docs/pitch/data/*.csv and reports/sim/gptoss120b-full/summary.md numbers.
No network calls except Google Fonts at view time.

    python docs/pitch/deck/build.py            # writes index.html
    python docs/pitch/deck/build.py --export   # also writes preview/*.png and ../Bayan-pitch.pdf (needs playwright)
"""

from __future__ import annotations

import csv
import html
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
OUT = HERE / "index.html"
SPACE_URL = "https://huggingface.co/spaces/dullgrey/team-qh-129-bayan-app"
QR = HERE.parent / "assets" / "qr-space.svg"   # committed; regenerated when segno is installed


def write_qr() -> None:
    try:
        import segno
    except ImportError:
        return
    segno.make(SPACE_URL, error="m").save(str(QR), kind="svg", scale=10, border=0, dark="#173430", light=None,
                                         xmldecl=False, svgns=True)

# Theme tokens (bayan/web/static/css/duet.css, plan_page.css)
BG, INK, MUTED, RULE = "#FBFCFC", "#173430", "#5B6B69", "#E3EAE9"
DOC, PT, DEEP, HELD = "#1F6FB2", "#0E8A6F", "#0B6E59", "#C2410C"
GREY_DARK, GREY_LIGHT = "#83948F", "#A3B3B0"   # de-emphasis series (validated: contrast >= 3:1 / direct-labelled)
FONT = "'Instrument Sans','Noto Sans',system-ui,sans-serif"


def rows(name: str) -> list[dict]:
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def bar(x: float, y: float, w: float, h: float, fill: str, r: float = 4) -> str:
    """Bar anchored square at the baseline (left), 4px rounded data end (right)."""
    w = max(w, 4.0)
    r = min(r, w / 2, h / 2)
    return (f'<path d="M{x:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} '
            f'V{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} H{x:.1f} Z" fill="{fill}"/>')


def text(x, y, s, size=26, fill=INK, weight=400, anchor="start", extra="") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}" font-family="{FONT}" {extra}>{esc(s)}</text>')


# ------------------------------------------------------------------ chart 1: harm (Divi 2007)
def harm_rows() -> str:
    """Artificial-Analysis-style rows: label, two bars (limited English / English-speaking), values, ratio."""
    labels = {
        "adverse events causing physical harm": "Adverse events that caused physical harm",
        "harmful events: moderate temporary harm to death": "Harmful events rated moderate harm or worse, up to death",
        "adverse events caused by communication errors": "Adverse events caused by communication errors",
    }
    px = 15.0   # px per percentage point; 60% = 900 px
    out = []
    for d in rows("lep_adverse_events.csv"):
        lep, eng = float(d["lep_patients_pct"]), float(d["english_speakers_pct"])
        out.append(f'''<div class="aarow">
      <p class="lbl">{esc(labels[d["metric"]])}</p>
      <div class="bars">
        <div class="bl"><span class="b lep" style="width:{lep * px:.0f}px"></span><span class="val">{lep:.0f}%</span></div>
        <div class="bl"><span class="b eng" style="width:{eng * px:.0f}px"></span><span class="val">{eng:.0f}%</span></div>
      </div>
      <p class="mult">{lep / eng:.1f}×</p>
    </div>''')
    return "\n    ".join(out)


def chart_harm() -> str:
    data = rows("lep_adverse_events.csv")
    names = {
        "adverse events causing physical harm": "Adverse events that caused physical harm",
        "harmful events: moderate temporary harm to death": "Harm ranging from moderate to death",
        "adverse events caused by communication errors": "Adverse events caused by a communication error",
    }
    W, scale, bh, gap, group = 1500, 15.0, 34, 4, 168   # 1% = 15 px -> 60% = 900 px
    out = []
    for i, d in enumerate(data):
        y0 = i * group
        lep, eng = float(d["lep_patients_pct"]), float(d["english_speakers_pct"])
        out.append(text(0, y0 + 28, names[d["metric"]], 30, INK, 500))
        yb = y0 + 48
        out.append(bar(0, yb, lep * scale, bh, HELD))
        out.append(bar(0, yb + bh + gap, eng * scale, bh, GREY_DARK))
        vx1, vx2 = lep * scale + 16, eng * scale + 16
        out.append(text(vx1, yb + 26, f"{lep:.0f}%", 28, INK, 600))
        out.append(text(vx2, yb + bh + gap + 26, f"{eng:.0f}%", 28, INK, 600))
        if i == 0:
            out.append(text(vx1 + 70, yb + 26, "patients with limited English", 26, MUTED))
            out.append(text(vx2 + 70, yb + bh + gap + 26, "English speakers", 26, MUTED))
    H = len(data) * group
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="Share of adverse events, patients with limited English versus English speakers">'
            + "".join(out) + "</svg>")


# ------------------------------------------------------------------ chart 2: deployment tiers, cost per consultation (log scale)
TIER_ROW, TIER_HEAD = 120, 68


def tier_ranges() -> list[tuple[float, float, str]]:
    d = {r["option"]: float(r["usd_per_consultation"]) for r in rows("cost_per_consultation.csv")}
    return [
        (d["L4 shared by 4 clinics + LLM + app Space"], d["Dedicated L4 Space 12 h/day + LLM + app Space"], PT),
        (d["S1 edge box: 2x L4 24GB (voice + gpt-oss-20b), 4 clinics"],
         d["S1 edge box: 2x L4 24GB (voice + gpt-oss-20b), 1 clinic"], PT),
        (d["S2 sovereign: 1x H100 80GB (gpt-oss-120b) + 1x L40S 48GB (voice), 10 clinics / 1 hospital"],
         d["S2 sovereign: 1x H100 80GB (gpt-oss-120b) + 1x L40S 48GB (voice), 1 clinic"], PT),
        (d["Phone or video interpreter, CyraCom/Propio published rates $0.75-0.81/min (used $0.76)"],
         d["Phone interpreter, LanguageLine public contract $0.99-1.10/min (mid $1.05)"], GREY_LIGHT),
    ]


def money(v: float) -> str:
    """Two decimals, half-even on the decimal string, so 0.165 prints as $0.16 as in research.md §6.3."""
    from decimal import Decimal, ROUND_HALF_EVEN
    return "$" + format(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN), ",")


def chart_tiers() -> str:
    """Range capsules on one shared log axis ($0.03 to $30), drawn over the table's last column."""
    import math
    W, x0, x1 = 600, 70, 520
    lo_l, hi_l = math.log10(0.03), math.log10(30)
    X = lambda v: x0 + (math.log10(v) - lo_l) / (hi_l - lo_l) * (x1 - x0)
    tiers = tier_ranges()
    H = TIER_HEAD + len(tiers) * TIER_ROW
    out = []
    for v, lab in ((0.1, "$0.10"), (1, "$1"), (10, "$10")):
        out.append(f'<line x1="{X(v):.1f}" y1="{TIER_HEAD - 8}" x2="{X(v):.1f}" y2="{H}" stroke="{RULE}" stroke-width="1.5"/>')
        out.append(text(X(v), TIER_HEAD - 18, lab, 19, MUTED, 400, "middle"))
    for i, (lo, hi, col) in enumerate(tiers):
        cy = TIER_HEAD + i * TIER_ROW + 40
        a, b = X(lo), X(hi)
        out.append(f'<rect x="{a - 8:.1f}" y="{cy - 8}" width="{b - a + 16:.1f}" height="16" rx="8" fill="{col}"/>')
        out.append(text(a - 18, cy + 8, money(lo), 24, INK, 600, "end"))
        out.append(text(b + 18, cy + 8, money(hi), 24, INK, 600, "start"))
    return (f'<svg class="tierchart" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="US dollars per consultation by deployment, log scale">' + "".join(out) + "</svg>")


# ------------------------------------------------------------------ chart 3: latency (simulation medians)
def chart_latency() -> str:
    # reports/sim/gptoss120b-full/summary.md: translate+gate per turn 0.9, rule cards 0.9, agent cards 5.7, wrap-up 6.3
    pick = [
        ("Translation and prescription gate, per turn", 0.9),
        ("Rule alert on the doctor's screen", 0.9),
        ("Copilot agent card", 5.7),
        ("Care plan and note, after End", 6.3),
    ]
    W, scale, bh, row = 1100, 130.0, 22, 70
    out = []
    for i, (label, v) in enumerate(pick):
        y0 = i * row
        out.append(text(0, y0 + 24, label, 25, INK))
        out.append(bar(0, y0 + 36, v * scale, bh, PT))
        out.append(text(v * scale + 14, y0 + 36 + 19, f"{v:.1f} s", 25, INK, 600))
    H = len(pick) * row
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="Median seconds from the turn to the result">' + "".join(out) + "</svg>")


# ------------------------------------------------------------------ slides
# ------------------------------------------------------------------ architecture diagram (Transformer figure style)
A_GREY, A_BLUE, A_GREEN, A_VERM = "#EEF2F1", "#DCEBF8", "#D8F0E8", "#FCE5DA"
A_BOX, A_BOX_LINE = "#F4F7F7", "#C9D4D2"


def _ablock(cx: float, cy: float, title: str, sub: str, fill: str, stroke: str = INK, w: float = 340, h: float = 68) -> str:
    x, y = cx - w / 2, cy - h / 2
    sw = "2.4" if stroke == HELD else "1.6"
    return (f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
            + text(cx, cy - 3, title, 22, INK, 600, "middle")
            + (text(cx, cy + 21, sub, 17, MUTED, 400, "middle") if sub else ""))


def _arrow(points: list[tuple[float, float]], color: str = INK, width: float = 2) -> str:
    pts = " ".join(f"{x:.0f},{y:.0f}" for x, y in points)
    mk = "ahv" if color == HELD else "ah"
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" marker-end="url(#{mk})"/>'


def chart_arch() -> str:
    """Transformer-figure style: per-turn interpretation stack (left), reasoning loop (centre, focus), wrap-up (right)."""
    W, H = 1664, 770
    out = ['<defs>'
           f'<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker>'
           f'<marker id="ahv" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{HELD}"/></marker>'
           '</defs>']

    def blk(cx, cy, w, h, title, subs, fill, stroke=INK, sw=1.6, tsize=22):
        s = (f'<rect x="{cx - w / 2:.0f}" y="{cy - h / 2:.0f}" width="{w:.0f}" height="{h:.0f}" rx="12" fill="{fill}" '
             f'stroke="{stroke}" stroke-width="{sw}"/>')
        n = len(subs)
        ty = cy - 3 - 10 * n + (10 if n <= 1 else 0)
        s += text(cx, ty, title, tsize, INK, 600, "middle")
        for k, sub in enumerate(subs):
            s += text(cx, ty + 24 + 20 * k, sub, 17, MUTED, 400, "middle")
        return s

    def box(x0, y0, x1, y1):
        return (f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="22" fill="{A_BOX}" '
                f'stroke="{A_BOX_LINE}" stroke-width="1.6"/>')

    def nlabel(x, y, big, lines):
        s = text(x, y, big, 30, INK, 600, "middle")
        for k, line in enumerate(lines):
            s += text(x, y + 26 + 20 * k, line, 16, MUTED, 400, "middle")
        return s

    # ---- interpretation stack (each turn)
    R = [612, 508, 404, 300, 196]
    ix, iw = 232, 300
    out.append(box(72, 128, 392, 660))
    out.append(nlabel(36, 552, "N×", ["each", "turn"]))
    talk = [("Speaker check", ["VoxLingua107"], A_GREY, INK, 1.6),
            ("Speech-to-text", ["Whisper, IndicConformer, MMS"], A_GREY, INK, 1.6),
            ("Translate + extract", ["gpt-oss-120b"], A_GREY, INK, 1.6),
            ("Safety gate", ["83 rules + coherence check"], A_VERM, HELD, 2.4),
            ("Text-to-speech", ["Parler, MMS, Supertonic, Piper"], A_GREY, INK, 1.6)]
    for i, (t, sub, fill, st, sw) in enumerate(talk):
        out.append(blk(ix, R[i], iw, 68, t, sub, fill, st, sw))
        if i < 4:
            out.append(_arrow([(ix, R[i] - 34), (ix, R[i + 1] + 36)]))
    out.append(_arrow([(ix, R[4] - 34), (ix, 96)]))
    out.append(text(ix, 80, "Spoken translation", 24, INK, 600, "middle"))
    for cx, label, fill in ((154, "Doctor speech", A_BLUE), (312, "Patient speech", A_GREEN)):
        out.append(f'<rect x="{cx - 75}" y="702" width="150" height="48" rx="12" fill="{fill}" stroke="{INK}" stroke-width="1.6"/>')
        out.append(text(cx, 733, label, 18, INK, 600, "middle"))
        out.append(_arrow([(cx, 702), (cx, R[0] + 36)]))
    out.append(_arrow([(382, R[3]), (404, R[3])], HELD, 2.4))
    out.append(text(410, R[3] - 4, "Paused for the", 18, HELD, 600))
    out.append(text(410, R[3] + 18, "doctor to check", 18, HELD, 600))

    # ---- reasoning loop (each substantive turn, in the background) - the focus
    cx, bw = 830, 424
    C = {"sum": 596, "rev": 478, "con": 368, "fil": 270, "out": 150}
    out.append(f'<rect x="598" y="206" width="464" height="454" rx="26" fill="{A_BOX}" stroke="{INK}" stroke-width="1.8"/>')
    out.append(nlabel(522, 552, "N×", ["each turn", "background"]))
    out.append(blk(cx, C["sum"], bw, 88, "Case summary", ["complaint, history, diagnosis,", "plan, understanding, mood"], A_BLUE))
    out.append(blk(cx, C["rev"], bw, 88, "Clinical review agent", ["smolagents + gpt-oss-120b, five checks: safety,", "history, plan, communication, consistency"], A_BLUE, INK, 2.4))
    out.append(blk(cx, C["con"], bw, 68, "Candidate concerns", ["each quotes the transcript"], A_BLUE))
    out.append(blk(cx, C["fil"], bw, 68, "Attention filter", ["severity × confidence × novelty"], A_BLUE))
    out.append(blk(cx, C["out"], bw, 68, "Doctor's screen", ["one Ask next + flags"], A_BLUE))
    out.append(_arrow([(cx, C["sum"] - 44), (cx, C["rev"] + 46)]))
    out.append(_arrow([(cx, C["rev"] - 44), (cx, C["con"] + 36)]))
    out.append(_arrow([(cx, C["con"] - 34), (cx, C["fil"] + 36)]))
    out.append(_arrow([(cx, C["fil"] - 34), (cx, C["out"] + 36)]))
    # loop: doctor's screen / next turn back into the case summary
    out.append(_arrow([(cx - bw / 2, C["out"]), (580, C["out"]), (580, C["sum"]), (cx - bw / 2 - 2, C["sum"])], INK, 2))
    out.append(f'<text x="568" y="{(C["out"] + C["sum"]) / 2 - 40:.0f}" font-size="17" fill="{MUTED}" text-anchor="middle" '
               f'font-family="{FONT}" transform="rotate(-90 568 {(C["out"] + C["sum"]) / 2 - 40:.0f})">next turn</text>')
    # feed from the interpretation stack into the case summary
    out.append(_arrow([(382, R[2]), (470, R[2]), (470, 700), (cx, 700), (cx, C["sum"] + 46)], INK, 1.6))
    out.append(text(650, 692, "updates the case summary", 16, MUTED, 400, "middle"))
    # agent tools
    tx0, tx1 = 1118, 1324
    ty0, ty1 = 330, 626
    out.append(f'<rect x="{tx0}" y="{ty0}" width="{tx1 - tx0}" height="{ty1 - ty0}" rx="18" fill="#FFFFFF" stroke="{A_BOX_LINE}" stroke-width="1.6"/>')
    out.append(text((tx0 + tx1) / 2, ty0 + 30, "Agent tools", 19, INK, 600, "middle"))
    tools = ["Safety rules (83)", "Idiom lexicon (98)", "Drug check", "Case lookup"]
    for k, t in enumerate(tools):
        y = ty0 + 50 + k * 60
        out.append(f'<rect x="{tx0 + 14}" y="{y}" width="{tx1 - tx0 - 28}" height="48" rx="10" fill="{A_GREY}" stroke="{INK}" stroke-width="1.4"/>')
        out.append(text((tx0 + tx1) / 2, y + 31, t, 18, INK, 600, "middle"))
    out.append(f'<line x1="{cx + bw / 2 + 2}" y1="{C["rev"]}" x2="{tx0 - 2}" y2="{C["rev"]}" stroke="{INK}" stroke-width="2" '
               'marker-start="url(#ah)" marker-end="url(#ah)"/>')
    out.append(text((cx + bw / 2 + tx0) / 2, C["rev"] - 16, "calls", 16, MUTED, 400, "middle"))

    # ---- wrap-up (once, at the end)
    wx, ww = 1478, 230
    out.append(box(1352, 232, 1604, 660))
    out.append(nlabel(1634, 552, "1×", ["at End"]))
    wrap = [("Wrap-up agent", ["smolagents"]), ("Rule re-check", ["83 rules"]), ("PDFs", ["patient's script"]), ("QR code", ["phone page"])]
    for i, (t, sub) in enumerate(wrap):
        out.append(blk(wx, R[i], ww, 68, t, sub, A_GREEN))
        if i < 3:
            out.append(_arrow([(wx, R[i] - 34), (wx, R[i + 1] + 36)]))
    out.append(_arrow([(wx, R[3] - 34), (wx, 210)]))
    out.append(text(wx, 194, "Care plan, PDF, QR", 22, INK, 600, "middle"))
    out.append(_arrow([(wx, 712), (wx, R[0] + 36)]))
    out.append(text(wx, 738, "full record", 18, MUTED, 400, "middle"))

    return (f'<svg class="arch" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            'aria-label="Bayan architecture: each turn is heard, transcribed, translated and checked by the prescription gate; '
            'in the background a clinical review agent reads the case summary, calls tools, and an attention filter sends one '
            'question or flag to the doctor, then loops on the next turn; at the end a wrap-up agent writes the care plan.">'
            + "".join(out) + "</svg>")


def chart_arch_overview() -> str:
    """Simplified architecture: three parts and the loop, large blocks (Transformer-figure style)."""
    W, H = 1664, 790
    out = ['<defs>'
           f'<marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker>'
           f'<marker id="ahv2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{HELD}"/></marker>'
           '</defs>']

    def arrow(points, color=INK, width=2.2):
        pts = " ".join(f"{x:.0f},{y:.0f}" for x, y in points)
        mk = "ahv2" if color == HELD else "ah2"
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" marker-end="url(#{mk})"/>'

    def blk(cx, cy, w, h, title, subs, fill, stroke=INK, sw=1.8):
        s = (f'<rect x="{cx - w / 2:.0f}" y="{cy - h / 2:.0f}" width="{w:.0f}" height="{h:.0f}" rx="14" fill="{fill}" '
             f'stroke="{stroke}" stroke-width="{sw}"/>')
        n = len(subs)
        ty = cy + 10 - 12 * n
        s += text(cx, ty, title, 28, INK, 600, "middle")
        for k, sub in enumerate(subs):
            s += text(cx, ty + 30 + 23 * k, sub, 19, MUTED, 400, "middle")
        return s

    def nlabel(x, y, big, lines):
        s = text(x, y, big, 32, INK, 600, "middle")
        for k, line in enumerate(lines):
            s += text(x, y + 26 + 20 * k, line, 17, MUTED, 400, "middle")
        return s

    R = [600, 480, 360, 240]   # block centres, bottom to top
    bh = 96

    # interpretation stack
    ix, iw = 300, 380
    out.append(f'<rect x="100" y="178" width="400" height="482" rx="24" fill="{A_BOX}" stroke="{A_BOX_LINE}" stroke-width="1.6"/>')
    out.append(nlabel(48, 560, "N×", ["each", "turn"]))
    talk = [("Hear", ["speaker check, speech-to-text", "Whisper, IndicConformer, MMS"], A_GREY, INK, 1.8),
            ("Interpret", ["translate with gpt-oss-120b"], A_GREY, INK, 1.8),
            ("Safety gate", ["83 rules + coherence check"], A_VERM, HELD, 2.6),
            ("Speak", ["voice in the listener's language"], A_GREY, INK, 1.8)]
    for i, (t, sub, fill, st, sw) in enumerate(talk):
        out.append(blk(ix, R[i], iw, bh, t, sub, fill, st, sw))
        if i < 3:
            out.append(arrow([(ix, R[i] - bh / 2), (ix, R[i + 1] + bh / 2 + 2)]))
    out.append(arrow([(ix, R[3] - bh / 2), (ix, 120)]))
    out.append(text(ix, 100, "Spoken translation", 28, INK, 600, "middle"))
    for cx, label, fill in ((200, "Doctor speech", A_BLUE), (400, "Patient speech", A_GREEN)):
        out.append(f'<rect x="{cx - 92}" y="712" width="184" height="58" rx="14" fill="{fill}" stroke="{INK}" stroke-width="1.8"/>')
        out.append(text(cx, 749, label, 22, INK, 600, "middle"))
        out.append(arrow([(cx, 712), (cx, R[0] + bh / 2 + 2)]))
    out.append(arrow([(ix + iw / 2, R[2]), (ix + iw / 2 + 34, R[2])], HELD, 2.6))
    out.append(text(ix + iw / 2 + 42, R[2] - 4, "paused for the", 21, HELD, 600))
    out.append(text(ix + iw / 2 + 42, R[2] + 20, "doctor to check", 21, HELD, 600))

    # reasoning loop (one grouped block)
    rx, rw = 990, 440
    out.append(f'<rect x="750" y="178" width="480" height="482" rx="26" fill="{A_BOX}" stroke="{INK}" stroke-width="2"/>')
    out.append(nlabel(1290, 560, "N×", ["each turn,", "background"]))
    loop = [("Case summary", ["what the doctor and patient have said"], 88),
            ("Clinical review agent", ["smolagents + gpt-oss-120b", "tools: rules, idioms, drug check"], 100),
            ("Attention filter", ["what is worth showing now"], 88),
            ("Doctor's screen", ["one Ask next + flags"], 88)]
    ys = [604, 480, 360, 244]
    for i, (t, sub, h) in enumerate(loop):
        out.append(blk(rx, ys[i], rw, h, t, sub, A_BLUE, INK, 2.6 if i == 1 else 1.8))
    hs = [88, 100, 88, 88]
    for i in range(3):
        out.append(arrow([(rx, ys[i] - hs[i] / 2), (rx, ys[i + 1] + hs[i + 1] / 2 + 2)]))
    # loop arrow
    out.append(arrow([(rx - rw / 2, ys[3]), (728, ys[3]), (728, ys[0]), (rx - rw / 2 - 2, ys[0])], INK, 2.2))
    my = (ys[3] + ys[0]) / 2
    out.append(f'<text x="714" y="{my:.0f}" font-size="19" fill="{MUTED}" text-anchor="middle" font-family="{FONT}" '
               f'transform="rotate(-90 714 {my:.0f})">next turn</text>')
    # feed from Interpret into the case summary
    out.append(arrow([(ix + iw / 2, R[1]), (600, R[1]), (600, 696), (rx, 696), (rx, ys[0] + 46)], INK, 1.8))
    out.append(text(800, 688, "each turn's text", 18, MUTED, 400, "middle"))

    # wrap-up
    wx = 1500
    out.append(blk(wx, 420, 270, 150, "Wrap-up", ["at the end:", "care plan, PDFs, QR"], A_GREEN))
    out.append(arrow([(wx, 600), (wx, 420 + 75 + 2)]))
    out.append(text(wx, 628, "full record", 19, MUTED, 400, "middle"))
    out.append(arrow([(wx, 420 - 75), (wx, 262)]))
    out.append(text(wx, 244, "Care plan for the patient", 22, INK, 600, "middle"))

    return (f'<svg class="arch" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            'aria-label="Bayan architecture overview: hear, interpret, safety gate and speak on each turn; a background loop '
            'of case summary, clinical review agent, attention filter and the doctor\'s screen; wrap-up at the end.">'
            + "".join(out) + "</svg>")


# ------------------------------------------------------------------ Hugging Face stack slide
HF_LOGO = "../assets/brand/huggingface_logo-noborder.svg"


def _hfbox(org: str, name: str) -> str:
    return (f'<div class="hfbox"><img src="{HF_LOGO}" alt=""><p><span>{esc(org)}</span><b>{esc(name)}</b></p></div>')


def hf_stack() -> str:
    voice = [("openai", "whisper-large-v3-turbo"), ("ai4bharat", "indic-conformer-600m-multilingual"),
             ("facebook", "mms-1b-all"), ("speechbrain", "lang-id-voxlingua107-ecapa"),
             ("ai4bharat", "indic-parler-tts"), ("facebook", "mms-tts-tgl, mms-tts-swh"),
             ("Supertone", "supertonic-3"), ("rhasspy", "piper-voices")]
    app = [("gradio-app", "gradio"), ("huggingface", "smolagents")]
    return f'''<div class="hfstack">
    <div class="hfcol">
      <div class="spacecard"><span class="tag">CPU upgrade</span><span class="emoji">🩺</span><p class="st">Bayan AI</p><p class="sid">dullgrey/team-qh-129-bayan-app</p></div>
      <div class="hfgrid one">{"".join(_hfbox(o, n) for o, n in app)}</div>
    </div>
    <div class="hfcol wide">
      <div class="spacecard"><span class="tag">NVIDIA L4</span><span class="emoji">🎙️</span><p class="st">Bayan Voice Worker</p><p class="sid">dullgrey/team-qh-129-bayan-voice</p></div>
      <div class="hfgrid two">{"".join(_hfbox(o, n) for o, n in voice)}</div>
    </div>
    <div class="hfcol">
      <div class="spacecard prov"><span class="tag">Cerebras, Groq</span><img class="plogo" src="{HF_LOGO}" alt=""><p class="st">Inference Providers</p><p class="sid">router.huggingface.co</p></div>
      <div class="hfgrid one">{_hfbox("openai", "gpt-oss-120b")}</div>
    </div>
  </div>'''


def brand() -> str:
    return ('<div class="brand"><span class="pearl sm"></span><b lang="ar">بيان</b><span>Bayan</span></div>')


def foot(n: int, note: str = "") -> str:
    """Page number only. `note` keeps each slide's sources next to the slide in this file; the deck shows no
    footnotes (sources live in docs/pitch/script.md and research.md). Numbers are filled in by position."""
    return '<span class="pg">{PG}</span>'


def slides() -> list[str]:
    S = []
    total = 18

    # 1 Title
    S.append(f'''
<section class="slide s-title" data-title="Title">
  <div class="title">
    <h1><span class="ar" lang="ar">بيان</span><span>Bayan AI</span></h1>
    <p class="tag">A clinical AI system that interprets between doctors and patients in Qatar, reasons about the consultation, and flags what gets missed.</p>
    <p class="meta"><span>Team QH-129</span><span>Qai × Hugging Face Hackathon O1</span><span>Doha, 5–7 Nov 2026</span></p>
  </div>
  <div class="orb big r"><span class="ring r1"></span><span class="ring r2"></span><span class="pearl"></span></div>
</section>''')

    # 2 Anurag
    S.append(f'''
<section class="slide s-anurag" data-title="Anurag">
  {brand()}
  <img class="anurag-img" src="../assets/anurag.png" alt="Illustration of Anurag, a construction worker in a hard hat">
  <h2>Meet Anurag</h2>
  <p class="lede">29, a Nepali construction worker in Doha</p>
  <p class="aq">“My chest is burning. It’s just <i>gyastrik</i>.”</p>
  <p class="ag"><span lang="ne">ग्यास्ट्रिक</span>, Nepali for “gastric”</p>
  <p class="ah">The doctor hears reflux.</p>
  <p class="ar2">It could be his heart.</p>
  <span class="pg">{{PG}}</span>
</section>''')

    # 2 Qatar
    S.append(f'''
<section class="slide" data-title="Qatar">
  {brand()}
  <h2>Language barriers in Qatar</h2>
  <div class="figs">
    <div><p class="v">65%</p><p class="l">of HMC ambulance staff face language barriers at work</p></div>
    <div><p class="v">71%</p><p class="l">are comfortable letting family members interpret</p></div>
    <div><p class="v">9</p><p class="l">languages with face-to-face interpreters at Sidra; Nepali, Malayalam, Bengali and Tagalog are not among them</p></div>
  </div>
  {foot(2, "Farhat et al., Qatar Medical Journal 2025, survey of HMC Ambulance Service staff (n = 312): 24% very often, 41% occasionally. Sidra Medicine, Medical interpreters (2026): 9 languages in person, 66 by phone or video. About 94% of Qatar's workforce is non-Qatari (Labour Force Survey 2024, via GLMM).")}
</section>''')

    # 2c Adverse events and language
    S.append(f'''
<section class="slide s-harm" data-title="Adverse events">
  {brand()}
  <h2>Adverse events and language</h2>
  <p class="lede">Many patients in Qatar don’t share a language with their doctor. US hospitals that measured the effect found this.</p>
  <div class="aa">
    <p class="aaleg"><span class="sw lep"></span>Patients with limited English<span class="sw eng"></span>English-speaking patients</p>
    <span class="base"></span>
    {harm_rows()}
  </div>
  <p class="bridge">Bayan is built to close this gap: it interprets, reasons about the consultation and flags what gets missed.</p>
  {foot(4, "Divi et al., six US Joint Commission hospitals, voluntarily reported adverse events (pilot); docs/pitch/data/lep_adverse_events.csv.")}
</section>''')

    # 3 What Bayan does
    S.append(f'''
<section class="slide s-does" data-title="What Bayan does">
  {brand()}
  <h2>What Bayan does</h2>
  <p class="lede">It listens to both sides of the consultation.</p>
  <div class="four">
    <div><p class="k">Interprets</p><p class="d">37 patient languages. The doctor speaks English or Arabic.</p></div>
    <div><p class="k">Reasons</p><p class="d">Keeps a running case summary and reviews it after every turn.</p></div>
    <div><p class="k">Flags</p><p class="d">Allergies, doses, interactions, missed workup, plans that don’t fit the complaint, patient confusion, mood cues.</p></div>
    <div><p class="k">Suggests</p><p class="d">One next question at a time, asked in the patient’s language with one tap.</p></div>
  </div>
  <div class="shot s1"><img src="../assets/screens/01-start-en.png" alt="Start screen: choose the patient's language, Nepali selected"></div>
  <div class="shot s2"><img src="../assets/screens/05-live-doctor-caption.png" alt="The doctor's question shown to the patient in Nepali, English beneath"></div>
  {foot(3, "bayan/ui.py (37 languages); reasoning design: case summary, clinical review agent, attention filter. Screens: 01-start-en, 05-live-doctor-caption.")}
</section>''')

    # 4 Demo
    S.append(f'''
<section class="slide s-demo" data-title="Demo">
  <div class="screen video">
    <video id="demo" src="../assets/demo-fast.mp4" muted playsinline preload="auto" poster="../assets/screens/06-live-patient-notes.png"></video>
    <img class="poster" src="../assets/screens/06-live-patient-notes.png" alt="Bayan live consultation: the patient's Nepali, the English for the doctor, the idiom note and the Notes panel">
  </div>
  <div class="cap">
    <p class="t">Doctor and patient take turns tapping the pearl. Bayan translates, speaks, and checks.</p>
    <p class="s">Recorded on the live Space: scripted Nepali consultation, live translation and voices. Played at 2× speed.</p>
  </div>
  <span class="pg">{{PG}}</span>
</section>''')

    # 5 Pause (hero)
    S.append(f'''
<section class="slide s-held" data-title="Pause">
  {brand()}
  <h2>Check before it is said</h2>
  <div class="pausewrap"><img src="../assets/screens/07-held-penicillin-amoxicillin.png" alt="Bayan paused the doctor's sentence: the patient reported a penicillin allergy; amoxicillin is a penicillin"></div>
  <p class="heldcap">The patient mentioned a penicillin allergy, and the doctor then prescribed amoxicillin. Bayan paused the sentence before the patient heard it, so the doctor can say something else or speak it anyway.</p>
  <span class="pg">{{PG}}</span>
</section>''')

    # 6 Take-home
    S.append(f'''
<section class="slide s-out" data-title="Take-home">
  {brand()}
  <h2>Care plan and doctor’s note</h2>
  <div class="outs">
    <figure class="phone"><div class="img"><img src="../assets/screens/11-plan-phone.png" alt="Care plan page on a phone, in Nepali with English beneath"></div>
      <figcaption>Phone page, via QR code</figcaption></figure>
    <figure class="page"><div class="img"><img src="../assets/screens/13-care-plan-pdf.png" alt="Patient care sheet PDF in Tamil"></div>
      <figcaption>Patient sheet in Tamil: penicillins under “Do not take”</figcaption></figure>
    <figure class="page doc"><div class="img"><img src="../assets/screens/14-doctor-report-pdf.png" alt="Doctor's consultation note PDF"></div>
      <figcaption>Doctor’s note: the paused amoxicillin, on the record</figcaption></figure>
  </div>
  {foot(6, "Phone page: current build, Nepali demo plan, rendered locally. PDFs: simulation scenario alg-09, Tamil patient (reports/sim/gptoss120b-full). The care plan is re-checked against the rules before rendering.")}
</section>''')

    # 7 Architecture / agentic loop
    # Architecture overview (alternate to the detailed slide)
    S.append(f'''
<section class="slide s-arch" data-title="Architecture overview">
  {brand()}
  <h2>Architecture (overview)</h2>
  <div class="archwrap ov">{chart_arch_overview()}</div>
  {foot(8, "Alternate to the detailed architecture slide; same design.")}
</section>''')

    S.append(f'''
<section class="slide s-arch" data-title="Architecture">
  {brand()}
  <h2>Architecture</h2>
  <div class="archwrap">{chart_arch()}</div>
  {foot(8, "bayan/brain/copilot.py, rules.py, wrapup.py; voice_worker/app.py.")}
</section>''')

    # 8 Hugging Face mapping
    S.append(f'''
<section class="slide s-hf" data-title="Hugging Face">
  {brand()}
  <h2 class="hfh"><img src="../assets/brand/huggingface_logo-noborder.svg" alt="Hugging Face">Hugging Face stack</h2>
  {hf_stack()}
  {foot(9, "Space READMEs (emoji, colorFrom green, colorTo indigo, suggested_hardware); voice_worker/app.py model ids.")}
</section>''')

    # 9 Proof
    S.append(f'''
<section class="slide s-proof" data-title="Proof">
  {brand()}
  <h2>Simulation results</h2>
  <p class="lede">Scripted consultations run through the real engine as text, with gpt-oss-120b. Results vary between runs.</p>
  <div class="evals">
    <div class="eg">
      <p class="eh">Safety rules</p>
      <p class="es">38 consultations, 14 languages</p>
      <div class="er"><p class="v">99%</p><p class="l">of 727 checks passed</p></div>
      <div class="er"><p class="v">0 of 44</p><p class="l">false-alarm traps tripped</p></div>
      <div class="er"><p class="v">100%</p><p class="l">of 477 PDF checks: native script, paused drug never on the patient sheet</p></div>
    </div>
    <div class="eg">
      <p class="eh">Clinical review</p>
      <p class="es">16 consultations, 9 languages: 7 with a plan that doesn’t fit, 6 quiet visits, 3 repeats of rule cases</p>
      <div class="er"><p class="v">8 of 12</p><p class="l">expected concerns flagged</p></div>
      <div class="er"><p class="v">0</p><p class="l">false caution alerts on the 6 quiet visits</p></div>
      <div class="er"><p class="v">30 of 30</p><p class="l">rule checks still passed, 0 of 22 traps tripped</p></div>
    </div>
  </div>
  <p class="evfoot">Translation and gate: 0.9 s per turn. Agent card: about 7 s after the turn. LLM cost: about $0.014 per consultation.</p>
  {foot(10, "reports/sim/gptoss120b-full/summary.md; reports/sim/coherence-r2/summary.md (one full run); smaller reruns coherence-r3 (4 of 7) and coherence-r4 (2 of 5).")}
</section>''')

    # 10 Buyers
    S.append(f'''
<section class="slide s-buy" data-title="Buyers">
  {brand()}
  <h2>First customers in Qatar</h2>
  <div class="figs">
    <div><p class="v">1.46 M</p><p class="l">visits to the four QRCS workers' health centres in 2025</p></div>
    <div><p class="v">1.56 M</p><p class="l">HMC emergency visits in 2025, adult and paediatric</p></div>
    <div><p class="v">5.17 M</p><p class="l">visits to PHCC's 31 health centres in 2024</p></div>
  </div>
  <p class="price">Pricing to test: QAR 2–3 per consultation. A phone interpreter costs about QAR 40–60 per visit.</p>
  {foot(10, "Qatar Tribune 2026 (QRCS, with MOPH); Gulf Times, 15 May 2026 (HMC); The Peninsula 2024–25 (PHCC). Pricing is a hypothesis, not validated (docs/pitch/research.md §6.4). Employer-paid health insurance (Law 22 of 2021) also moves workers into private clinics.")}
</section>''')

    # 11 Deployment and cost
    S.append(f'''
<section class="slide s-deploy" data-title="Deployment">
  {brand()}
  <h2>Deployment and cost</h2>
  <p class="lede">All models are open-weight, so the system can also run on a hospital’s own servers.</p>
  <div class="tiers">
    <div class="th">Where it runs</div><div class="th">Up-front hardware</div><div class="th">Per clinic-month</div><div class="th">Per consultation, log scale</div>
    <div class="tn"><b>Online on Hugging Face</b><span>Voice on one NVIDIA L4 Space ($0.80/h), app on CPU ($0.03/h), gpt-oss-120b per token on Cerebras</span></div>
    <div class="tc">None</div><div class="tc">$107 if 4 clinics share<br>$339 alone</div><div class="tg"></div>
    <div class="tn"><b>Clinic box</b><span>2× NVIDIA L4, about $2,800 each: all voice models plus <i class="nw">gpt-oss-20b</i>, on site</span></div>
    <div class="tc">$14.6k<small>QAR 53k</small></div><div class="tc">$607 alone<br>$152 each if 4 share</div><div class="tg"></div>
    <div class="tn"><b>Hospital, in-country</b><span>1× H100 80 GB, about $27.5k, runs gpt-oss-120b (MXFP4, one GPU); 1× L40S, about $8.5k, for voice</span></div>
    <div class="tc">$48k<small>QAR 175k</small></div><div class="tc">$1,980 per server<br>$198 per clinic across 10</div><div class="tg"></div>
    <div class="tn human"><b>Phone interpreter</b><span>CyraCom or Propio $0.76/min, LanguageLine $1.05/min; 15 minutes a visit</span></div>
    <div class="tc human">None</div><div class="tc human">$13,680–18,900</div><div class="tg"></div>
    {chart_tiers()}
  </div>
  {foot(11, "Cost model, docs/pitch/research.md §6 and data/cost_model.json: 1,200 consultations per clinic-month; online GPU awake 12 h a day; LLM $0.025 per consultation from the token model (measured median in simulation: $0.011). Self-hosted: street GPU prices plus a $9–12k server, 36-month amortisation, support at 15% of capex a year, Qatar business electricity QAR 0.13/kWh with PUE 1.5. Ranges: shared to single-clinic use; interpreter, CyraCom/Propio to LanguageLine contract. L4 sharing across clinics not yet load-tested; offline not yet demonstrated end to end.")}
</section>''')

    # 11 Competition
    S.append(f'''
<section class="slide s-comp" data-title="Competition">
  {brand()}
  <h2>Comparison</h2>
  <table class="cmp">
    <thead><tr><th></th><th>Nepali, Malayalam, Bengali in the room</th><th>Checks allergy, dose, missed workup</th><th>Pauses a sentence for the doctor to check</th><th>Can run in-country</th><th>Cost per visit</th></tr></thead>
    <tbody>
      <tr class="us"><th>Bayan</th><td>Yes, 37 languages</td><td>Yes, 83 cited rules</td><td>Yes</td><td>Yes, open weights</td><td>$0.09–0.28</td></tr>
      <tr><th>Phone and video interpreters</th><td>Yes, remote</td><td>Human judgement</td><td>No</td><td>No</td><td>$11–74</td></tr>
      <tr><th>Google, Microsoft Translate</th><td>Text; speech unverified</td><td>No</td><td>No</td><td>No</td><td>Free</td></tr>
      <tr><th>AI medical interpreters</th><td>Claimed 40–150+</td><td>Translation checks only</td><td>No</td><td>Some (Mabel)</td><td>Not public</td></tr>
      <tr><th>Ambient AI scribes</th><td>No, English notes</td><td>No, documentation</td><td>No</td><td>No</td><td>$150–600 per doctor-month</td></tr>
    </tbody>
  </table>
  {foot(12, "Vendor pages and press, 2025–26 (docs/pitch/research.md §5): LanguageLine, CyraCom/Propio, Google, Microsoft, Opalite Health, No Barrier, Mabel, Abridge, Dragon Copilot. Opalite's Guardian checks translation fidelity, not clinical content. Interpreter cost per 15-minute visit; scribe prices are third-party estimates. We found no product that gates interpreted speech on clinical content.")}
</section>''')

    # 12 Close
    S.append(f'''
<section class="slide s-close" data-title="Close">
  {brand()}
  <div class="orb big l"><span class="ring r1"></span><span class="ring r2"></span><span class="pearl"></span></div>
  <div class="close">
    <h2>Next steps</h2>
    <ul class="ask">
      <li>A pilot at one QRCS workers' health centre</li>
      <li>Clinicians to review our 83 rules and 98 idioms</li>
      <li>Native speakers to validate each language</li>
    </ul>
    <p class="lim">Decision support for clinicians.<br>Not a certified interpreter or a medical device.</p>
    <p class="team">Team QH-129<br><span>huggingface.co/spaces/dullgrey/team-qh-129-bayan-app</span></p>
  </div>
  {foot(13, "Limits we state up front: machine translation is not certified interpreting; Bayan covers the visits that today get a roommate or no one, not consent or bad news. Rules and idioms are cited but not yet clinician-reviewed; accuracy varies by language.")}
</section>''')
    # Team
    people = [("DI", "Diyorbek Ibragimov", "diyorbek.jpg"), ("SL", "Sangyoon Lim", "sangyoon.jpg"),
              ("MA", "Mohammed Al-Kuwari", "mohammed.jpg"), ("GC", "George Chkhaidze", "george.jpg")]

    def avatar(i, n, photo):
        if photo and (HERE.parent / "assets" / "team" / photo).exists():  # initials until the photo is added
            return f'<img class="photo av" src="../assets/team/{photo}" alt="Photo of {n}">'
        return f'<span class="pearl av"><b>{i}</b></span>'

    S.append(f'''
<section class="slide s-team" data-title="Team">
  {brand()}
  <h2>Team</h2>
  <p class="lede">Team QH-129</p>
  <div class="people">{"".join(f'<figure>{avatar(i, n, ph)}<figcaption>{n}</figcaption></figure>' for i, n, ph in people)}</div>
  {foot(0)}
</section>''')

    # Thank you
    S.append(f'''
<section class="slide s-thanks" data-title="Thank you">
  {brand()}
  <div class="orb mid"><span class="ring r1"></span><span class="ring r2"></span><span class="pearl"></span></div>
  <div class="thanks">
    <p class="ty">Thank you</p>
    <p class="q">Questions</p>
    <div class="try">
      <span class="qrbox"><img src="../assets/qr-space.svg" alt="QR code: the Bayan Space on Hugging Face"></span>
      <div><p class="tl">Try it live</p><p class="url">huggingface.co/spaces/dullgrey/team-qh-129-bayan-app</p></div>
    </div>
  </div>
</section>''')

    assert len(S) == total
    return [sl.replace("{PG}", str(k + 1)) for k, sl in enumerate(S)]


CSS = r"""
:root{--bg:#FBFCFC;--ink:#173430;--muted:#5B6B69;--rule:#E3EAE9;--doc:#1F6FB2;--pt:#0E8A6F;--deep:#0B6E59;--held:#C2410C}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#FBFCFC;overflow:hidden}
body{font-family:'Instrument Sans','Noto Sans',system-ui,sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
#deck{position:absolute;left:0;top:0;width:1920px;height:1080px;transform-origin:0 0}
.slide{position:absolute;inset:0;width:1920px;height:1080px;background:var(--bg);overflow:hidden;display:none}
.slide.on{display:block}
p,h2,ul,ol,figure{margin:0;padding:0}
[lang=ne]{font-family:'Noto Sans Devanagari','Instrument Sans',sans-serif}
[lang=ar]{font-family:'Reem Kufi',sans-serif}

.pearl{display:block;border-radius:50%;background:radial-gradient(circle at 34% 28%,#FFFFFF 0%,#F2FBF8 20%,#BFEBDF 48%,#C9EDE6 68%,#D9E9FA 100%);
  box-shadow:0 8px 18px -10px rgba(14,138,111,.45),inset 0 4px 8px rgba(255,255,255,.95)}
.pearl.sm{width:30px;height:30px}
.brand{position:absolute;left:128px;top:58px;display:flex;align-items:center;gap:14px}
.brand b{font-size:34px;font-weight:500;line-height:1;transform:translateY(-3px)}
.brand>span:last-child{font-size:24px;color:var(--muted)}
.fn{position:absolute;left:128px;bottom:40px;width:1520px;font-size:17px;line-height:1.45;color:var(--muted)}
.pg{position:absolute;right:128px;bottom:40px;font-size:17px;color:var(--muted);font-variant-numeric:tabular-nums}
h2{position:absolute;left:128px;top:168px;width:1500px;font-size:68px;line-height:1.08;font-weight:600;letter-spacing:-.015em}

/* big pearl with rings, as on the app's start screen */
.orb{position:absolute;width:560px;height:560px}
.orb .pearl{position:absolute;inset:0;box-shadow:0 70px 120px -60px rgba(31,111,178,.40),0 30px 60px -40px rgba(14,138,111,.35),inset 0 22px 44px rgba(255,255,255,.95)}
.orb .pearl{overflow:hidden}
.orb .pearl::before{content:"";position:absolute;inset:-25%;background:conic-gradient(from 90deg,rgba(255,255,255,0) 0deg,rgba(189,235,230,.75) 70deg,rgba(255,255,255,0) 140deg,rgba(207,227,255,.75) 210deg,rgba(255,255,255,0) 280deg,rgba(228,222,250,.7) 330deg,rgba(255,255,255,0) 360deg);filter:blur(40px)}
.orb .pearl::after{content:"";position:absolute;left:16%;top:11%;width:44%;height:30%;border-radius:50%;background:radial-gradient(closest-side,rgba(255,255,255,.95),rgba(255,255,255,0))}
.orb .ring{position:absolute;border-radius:50%;border:2px solid rgba(14,138,111,.22)}
.orb .r1{inset:-46px}.orb .r2{inset:-120px;border-color:rgba(14,138,111,.10)}
.orb.r{left:1196px;top:250px}
.orb.l{left:190px;top:250px}

/* 1 title */
.title{position:absolute;left:128px;top:300px;width:980px}
.title h1{margin:0;display:flex;align-items:baseline;gap:64px;font-size:168px;line-height:1.1;font-weight:600;letter-spacing:-.03em;white-space:nowrap}
.title h1 .ar{font-family:'Reem Kufi',sans-serif;font-size:150px;font-weight:500;letter-spacing:0}
.title .tag{margin-top:34px;font-size:40px;line-height:1.3;font-weight:500;width:900px}
.title .meta{margin-top:48px;display:flex;gap:56px;font-size:24px;color:var(--muted)}

/* 2 anurag */
.s-anurag .lede{position:absolute;left:128px;top:262px;font-size:34px;color:var(--muted)}
.s-anurag .anurag-img{position:absolute;right:0;top:0;width:1080px;height:1080px;object-fit:cover;
  -webkit-mask-image:linear-gradient(90deg,transparent 0,#000 22%);mask-image:linear-gradient(90deg,transparent 0,#000 22%)}
.s-anurag h2,.s-anurag .lede{z-index:2}
.s-anurag .pg{display:none}
.s-anurag .aq{position:absolute;left:128px;top:400px;width:760px;margin:0;font-size:56px;line-height:1.18;font-weight:600;letter-spacing:-.01em;color:var(--ink)}
.s-anurag .ag{position:absolute;left:128px;top:560px;margin:0;font-size:26px;color:var(--muted)}
.s-anurag .ag span{font-family:'Noto Sans Devanagari',sans-serif;color:var(--ink);text-decoration:underline dotted #8E7CC3;text-underline-offset:8px}
.s-anurag .ah{position:absolute;left:128px;top:690px;margin:0;font-size:40px;font-weight:500;color:var(--ink)}
.s-anurag .ar2{position:absolute;left:128px;top:756px;margin:0;font-size:40px;font-weight:600;color:var(--held)}
.three{position:absolute;left:128px;top:470px;width:1664px;list-style:none;display:grid;grid-template-columns:620px 560px 380px;column-gap:52px}
.three li{border-top:1px solid var(--rule);padding-top:30px}
.three .k{font-size:26px;color:var(--muted)}
.three .q{margin-top:18px;font-size:58px;line-height:1.15;font-weight:600;letter-spacing:-.01em}
.three .g{margin-top:24px;font-size:26px;line-height:1.4;color:var(--muted)}
.three .g [lang=ne]{color:var(--ink);font-weight:500;text-decoration:underline;text-decoration-style:dotted;text-decoration-color:#6B4FA8;text-decoration-thickness:2px;text-underline-offset:8px}
.three .alarm .q{color:var(--held)}
.three .alarm{border-top-color:var(--held)}

/* 2 and 9: figures */
.figs{position:absolute;left:128px;top:420px;display:grid;grid-template-columns:repeat(3,456px);column-gap:96px}
.figs .v{font-size:150px;line-height:1;font-weight:600;letter-spacing:-.03em}
.figs .l{margin-top:26px;font-size:30px;line-height:1.4;color:var(--muted)}
.evals{position:absolute;left:128px;top:356px;width:1664px;display:grid;grid-template-columns:800px 800px;column-gap:64px}
.eg{border-top:1px solid var(--rule);padding-top:26px}
.eh{font-size:36px;font-weight:600}
.es{margin-top:8px;font-size:22px;line-height:1.4;color:var(--muted);min-height:62px}
.er{display:grid;grid-template-columns:250px 1fr;align-items:baseline;column-gap:24px;margin-top:22px}
.er .v{font-size:64px;font-weight:600;line-height:1.05;letter-spacing:-.02em}
.er .l{font-size:25px;line-height:1.35;color:var(--muted)}
.evfoot{position:absolute;left:128px;top:880px;font-size:24px;color:var(--ink)}

/* 2b qatar: four figures */

/* 3 what bayan does */
.s-does .lede{position:absolute;left:128px;top:262px;font-size:32px;color:var(--muted)}
.four{position:absolute;left:128px;top:400px;width:1664px;display:grid;grid-template-columns:repeat(4,380px);column-gap:48px}
.s-does .four{top:370px}
/* screenshot strips: frame 808x320; each image scaled and offset so the useful band of the 1920x1080 screen fills it */
.s-does .shot{position:absolute;top:695px;width:808px;height:320px;overflow:hidden;border-radius:16px;border:1px solid var(--rule);background:var(--bg);
  box-shadow:0 30px 60px -40px rgba(23,52,48,.35)}
.s-does .shot.s1{left:128px}.s-does .shot.s2{left:984px}
.s-does .shot img{position:absolute;height:auto}
.s-does .s1 img{width:835px;left:6px;top:-62px}
.s-does .s2 img{width:930px;left:-61px;top:-178px}
.four>div{border-top:1px solid var(--rule);padding-top:30px}
.four .k{font-size:44px;font-weight:600;letter-spacing:-.01em}
.four .d{margin-top:18px;font-size:28px;line-height:1.42;color:var(--muted)}

/* 3 harm (benchmark rows) */
.chartwrap.harm{position:absolute;left:128px;top:350px}
.aa{position:absolute;left:128px;top:340px;width:1664px}
.aaleg{display:flex;align-items:center;gap:14px;font-size:22px;color:var(--muted);margin-bottom:34px}
.aaleg .sw{display:inline-block;width:18px;height:18px;border-radius:4px}
.aaleg .sw.eng{margin-left:28px}
.sw.lep,.b.lep{background:#C2410C}
.sw.eng,.b.eng{background:#83948F}
.aa .base{position:absolute;left:538px;top:72px;bottom:0;width:2px;background:#9FB0AD}
.aarow{display:grid;grid-template-columns:520px 1000px 104px;column-gap:20px;align-items:center;height:150px}
.aarow .lbl{font-size:28px;line-height:1.3;font-weight:500;padding-right:24px}
.aarow .bars{display:flex;flex-direction:column;gap:8px}
.aarow .bl{display:flex;align-items:center;gap:18px;height:40px}
.aarow .b{display:block;height:40px;border-radius:0 6px 6px 0}
.aarow .val{font-size:34px;font-weight:600;color:var(--ink);font-variant-numeric:normal}
.aarow .mult{font-size:30px;font-weight:500;color:var(--muted);text-align:right}
.bridge{position:absolute;left:128px;top:880px;width:1500px;font-size:30px;line-height:1.4;font-weight:500}

/* 4 demo */
.screen{position:absolute;overflow:hidden;background:var(--bg);border-radius:22px;box-shadow:0 0 0 1px var(--rule),0 50px 90px -60px rgba(23,52,48,.45)}
.screen.video{left:240px;top:60px;width:1440px;height:810px}
.screen video,.screen img{display:block;width:100%;height:100%;object-fit:cover}
.screen .poster{display:none}
body.still .screen video{display:none}
body.still .screen .poster{display:block}
.s-demo .cap{position:absolute;left:240px;top:912px;width:1440px}
.s-demo .cap .t{font-size:32px;line-height:1.3;font-weight:500}
.s-demo .cap .s{margin-top:10px;font-size:20px;color:var(--muted)}

/* 5 held */
.bleed{position:absolute;inset:0;width:1920px;height:1080px}
.pausewrap{position:absolute;left:128px;top:330px;width:1120px;height:540px;overflow:hidden;border-radius:16px;background:var(--bg);border:1px solid var(--rule);box-sizing:content-box}
.pausewrap img{display:block;width:1120px;height:auto}
.heldcap{position:absolute;left:1316px;top:330px;width:476px;height:540px;display:flex;align-items:center;margin:0;font-size:30px;line-height:1.5;color:var(--ink)}

/* 6 outputs */
.outs{position:absolute;left:128px;top:300px;display:flex;align-items:flex-start;gap:58px}
.outs figure .img{overflow:hidden;background:#fff;box-shadow:0 0 0 1px var(--rule),0 40px 70px -50px rgba(23,52,48,.45)}
.outs img{display:block;width:100%}
.outs .phone .img{width:300px;height:570px;border-radius:32px}
.outs .page .img{width:600px;height:570px;border-radius:6px}
.outs .page img{width:760px;margin-left:-46px;margin-top:-22px}
.outs .page.doc img{width:680px;margin-left:-44px;margin-top:-18px}
.outs figcaption{margin-top:20px;font-size:23px;line-height:1.4;color:var(--muted);max-width:600px}
.outs .phone figcaption{max-width:300px}

/* 7 architecture */
.archwrap{position:absolute;left:128px;top:262px}
.archwrap svg{display:block}
.archwrap.ov{top:250px}

/* 8 hugging face */
h2.hfh{display:flex;align-items:center;gap:22px}
h2.hfh img{width:76px;height:auto}
.hfstack{position:absolute;left:128px;top:300px;width:1664px;display:grid;grid-template-columns:400px 816px 400px;column-gap:16px;align-items:start}
.spacecard{position:relative;height:168px;border-radius:18px;padding:22px 24px;color:#fff;
  background:linear-gradient(135deg,#16A34A 0%,#4F46E5 100%);box-shadow:0 24px 40px -30px rgba(23,52,48,.6)}
.spacecard .emoji{display:block;font-size:40px;line-height:1;font-family:'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif}
.spacecard .st{margin-top:18px;font-size:32px;font-weight:600;line-height:1.1}
.spacecard .sid{margin-top:6px;font-size:17px;opacity:.85}
.spacecard .tag{position:absolute;right:20px;top:20px;padding:5px 12px;border-radius:999px;background:rgba(255,255,255,.2);font-size:16px;font-weight:500}
.spacecard.prov{background:#FFFFFF;color:var(--ink);box-shadow:0 0 0 1px var(--rule),0 24px 40px -30px rgba(23,52,48,.4)}
.spacecard.prov .tag{background:#F1F5F4;color:var(--muted)}
.spacecard.prov .sid{color:var(--muted);opacity:1}
.spacecard .plogo{display:block;width:44px;height:40px}
.hfgrid{display:grid;gap:16px;margin-top:16px}
.hfgrid.one{grid-template-columns:400px}
.hfgrid.two{grid-template-columns:400px 400px}
.hfbox{height:92px;display:flex;align-items:center;gap:14px;padding:0 18px;border-radius:14px;background:#FFFFFF;box-shadow:0 0 0 1px var(--rule)}
.hfbox img{width:30px;height:28px;flex:none}
.hfbox p{min-width:0}
.hfbox span{display:block;font-size:16px;color:var(--muted);line-height:1.2}
.hfbox b{display:block;font-size:18.5px;font-weight:600;line-height:1.25;white-space:nowrap}

/* 9 proof */
.lat{position:absolute;left:128px;top:648px}
.lat .ct{font-size:26px;font-weight:600;margin-bottom:20px}

/* 10 buyers */
.s-buy .figs{top:400px}
.s-buy .figs .v{font-size:132px}
.price{position:absolute;left:128px;top:790px;width:1500px;font-size:34px;line-height:1.35;font-weight:500}

/* 11 deployment */
.lede{position:absolute;left:128px;top:262px;font-size:32px;color:var(--muted)}
.tiers{position:absolute;left:128px;top:336px;width:1664px;display:grid;grid-template-columns:540px 200px 300px 600px;column-gap:8px;grid-auto-rows:120px;grid-template-rows:68px}
.tiers .th{font-size:19px;color:var(--muted);align-self:start}
.tiers .tn,.tiers .tc,.tiers .tg{border-top:1px solid var(--rule);padding-top:22px}
.tiers .tn b{display:block;font-size:27px;font-weight:600;line-height:1.2}
.tiers .tn span{display:block;margin-top:6px;font-size:19px;line-height:1.38;color:var(--muted);width:520px}
.tiers .tc{font-size:23px;line-height:1.38}
.tiers .tc small{display:block;font-size:19px;color:var(--muted)}
.tiers .human b,.tiers .tc.human{color:var(--muted)}
.tierchart{position:absolute;left:1064px;top:0}
.nw{white-space:nowrap;font-style:normal}

/* 11 competition */
table.cmp{position:absolute;left:128px;top:330px;width:1664px;border-collapse:collapse}
.cmp th,.cmp td{text-align:left;vertical-align:top;font-weight:400;padding:20px 24px 20px 0;border-top:1px solid var(--rule);font-size:24px;line-height:1.35}
.cmp thead th{border-top:none;font-size:20px;color:var(--muted);padding-bottom:16px;line-height:1.35}
.cmp tbody th{font-weight:500;width:330px}
.cmp tbody td{color:var(--muted)}
.cmp tr.us th,.cmp tr.us td{color:var(--ink);font-weight:600}
.cmp col{width:auto}

/* team */
.people{position:absolute;left:128px;top:400px;width:1664px;display:grid;grid-template-columns:repeat(4,1fr);column-gap:48px}
.people figure{margin:0;display:flex;flex-direction:column;align-items:center}
.pearl.av{position:relative;width:220px;height:220px;display:flex;align-items:center;justify-content:center;
  box-shadow:0 40px 70px -40px rgba(31,111,178,.40),0 20px 40px -30px rgba(14,138,111,.35),inset 0 10px 24px rgba(255,255,255,.95)}
.photo.av{width:220px;height:220px;border-radius:50%;object-fit:cover;object-position:50% 30%;display:block;
  box-shadow:0 0 0 6px #fff,0 0 0 7px var(--rule),0 40px 70px -40px rgba(31,111,178,.40),0 20px 40px -30px rgba(14,138,111,.35)}
.pearl.av b{font-size:64px;font-weight:600;color:var(--ink);letter-spacing:.01em}
.people figcaption{margin-top:36px;font-size:32px;font-weight:600;text-align:center}

/* thank you */
.orb.mid{width:300px;height:300px;left:810px;top:120px}
.orb.mid .r1{inset:-34px}.orb.mid .r2{inset:-80px}
.thanks{position:absolute;left:0;right:0;top:530px;text-align:center}
.thanks .ty{font-size:120px;font-weight:600;letter-spacing:-.03em;line-height:1.05}
.thanks .q{margin-top:18px;font-size:48px;color:var(--muted)}
.thanks .try{margin-top:44px;display:inline-flex;align-items:center;gap:32px;text-align:left}
.thanks .qrbox{display:block;width:196px;height:196px;padding:14px;background:#fff;border:1px solid var(--rule);border-radius:16px}
.thanks .qrbox img{display:block;width:100%;height:100%}
.thanks .tl{margin:0;font-size:32px;font-weight:600;color:var(--ink)}
.thanks .url{margin:10px 0 0;font-size:22px;color:var(--muted)}

/* 12 close */
.close{position:absolute;left:1000px;top:330px;width:800px}
.close h2{position:static;width:auto;font-size:84px;line-height:1.1}
.close .ask{margin-top:40px}
.close .sub{margin-top:22px;font-size:32px;line-height:1.35;color:var(--muted)}
.close .ch{margin-top:56px;font-size:28px;font-weight:600}
.close .ask{list-style:none;margin-top:18px}
.close .ask li{font-size:34px;line-height:1.4;margin-bottom:14px}
.close .lim{margin-top:36px;font-size:24px;line-height:1.4;color:var(--muted)}
.close .team{margin-top:40px;font-size:24px;font-weight:600}
.close .team span{font-weight:400;color:var(--muted)}

@page{size:1920px 1080px;margin:0}
@media print{
  html,body{width:1920px;height:auto;overflow:visible;background:var(--bg)}
  #deck{position:static;transform:none!important;width:1920px;height:auto}
  .slide{display:block!important;position:relative;break-after:page;page-break-after:always}
  .slide:last-child{break-after:auto;page-break-after:auto}
  .screen video{display:none}
  .screen .poster{display:block}
}
"""

JS = r"""
(function(){
  const deck=document.getElementById('deck');
  const slides=[...deck.querySelectorAll('.slide')];
  const vid=document.getElementById('demo');
  const params=new URLSearchParams(location.search);
  if(params.has('still')) document.body.classList.add('still');
  let i=Math.max(0,Math.min(slides.length-1,(parseInt(location.hash.slice(1))||1)-1));
  function fit(){const s=Math.min(innerWidth/1920,innerHeight/1080);
    deck.style.transform=`translate(${(innerWidth-1920*s)/2}px,${(innerHeight-1080*s)/2}px) scale(${s})`;}
  function video(on){ if(!vid||document.body.classList.contains('still')) return;
    if(on){ try{vid.currentTime=0;}catch(e){} vid.playbackRate=1; vid.play().catch(()=>{}); } else vid.pause(); }
  function go(n){ i=Math.max(0,Math.min(slides.length-1,n));
    slides.forEach((el,k)=>el.classList.toggle('on',k===i));
    history.replaceState(null,'','#'+(i+1)); video(slides[i].classList.contains('s-demo')); }
  window.go=go;
  addEventListener('resize',fit);
  addEventListener('keydown',e=>{
    if(['ArrowRight','ArrowDown','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();go(i+1);}
    else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(e.key)){e.preventDefault();go(i-1);}
    else if(e.key==='Home') go(0); else if(e.key==='End') go(slides.length-1);
    else if(e.key==='f'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();}
    else if(e.key==='r' && slides[i].classList.contains('s-demo')) video(true);
    else if(e.key==='p' && vid){vid.paused?vid.play():vid.pause();}
  });
  addEventListener('click',e=>{ if(e.target.closest('video')) return; go(e.clientX<innerWidth/3?i-1:i+1); });
  fit(); go(i);
})();
"""


def build() -> None:
    body = "\n".join(slides())
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bayan pitch</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Noto+Sans+Devanagari:wght@500;600&family=Reem+Kufi:wght@500&display=swap">
<style>{CSS}</style>
</head>
<body>
<main id="deck">
{body}
</main>
<script>{JS}</script>
</body>
</html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT}")


def export() -> None:
    """PNG previews (one per slide, still poster for the video) and the PDF, with new-headless Chromium."""
    import asyncio
    from playwright.async_api import async_playwright

    prev = HERE / "preview"
    prev.mkdir(exist_ok=True)
    url = OUT.as_uri()

    async def run():
        async with async_playwright() as p:
            b = await p.chromium.launch(channel="chromium")
            pg = await b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            await pg.goto(url + "?still#1")
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_load_state("networkidle")
            n = await pg.evaluate("document.querySelectorAll('.slide').length")
            for k in range(n):
                await pg.evaluate(f"go({k})")
                await pg.wait_for_timeout(250)
                await pg.screenshot(path=str(prev / f"slide-{k + 1:02d}.png"))
            # The PDF is one 2x raster per slide. A vector PDF from Chromium keeps blurred box-shadows, masks and
            # blend modes that macOS Preview / Quick Look / PDFKit draw as solid coloured boxes (the pearl, cards,
            # photos). Flattening makes every viewer show exactly what Chromium shows; text is not selectable.
            hi = await b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=2)
            await hi.goto(url + "?still#1")
            await hi.evaluate("document.fonts.ready")
            await hi.wait_for_load_state("networkidle")
            tmp = Path(tempfile.mkdtemp(prefix="bayan-pdf-"))
            for k in range(n):
                await hi.evaluate(f"go({k})")
                await hi.wait_for_timeout(250)
                await hi.screenshot(path=str(tmp / f"{k + 1:02d}.jpg"), type="jpeg", quality=92)
            pages = "".join(f'<img src="{k + 1:02d}.jpg">' for k in range(n))
            (tmp / "pages.html").write_text(
                "<!doctype html><style>@page{size:1920px 1080px;margin:0}html,body{margin:0}"
                "img{display:block;width:1920px;height:1080px;break-after:page}</style>" + pages, encoding="utf-8")
            pdf = await b.new_page()
            await pdf.goto((tmp / "pages.html").as_uri())
            await pdf.wait_for_load_state("networkidle")
            await pdf.pdf(path=str(HERE.parent / "Bayan-pitch.pdf"), width="1920px", height="1080px",
                          print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            shutil.rmtree(tmp, ignore_errors=True)
            await b.close()
        print(f"wrote {n} previews to {prev} and {HERE.parent / 'Bayan-pitch.pdf'}")

    asyncio.run(run())


if __name__ == "__main__":
    write_qr()
    build()
    if "--export" in sys.argv:
        export()
