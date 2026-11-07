"""Bayan stage: static markup + CSS + a client-side renderer (ported from the approved prototype).

The server never re-renders this markup. It pushes a JSON view into a hidden gr.HTML
(`.bz-s[data-s]`); the head script watches for it and updates styles/text in place, so every
CSS transition from the prototype still plays. Text is always set with textContent (no HTML
injection). Buttons carry data-act; a capture-phase click listener records the action, and the
gr.HTML click event sends it to Python through a hidden textbox (see app.py).

The markup, CSS, JavaScript and icons live in bayan/web/ (templates/, static/); this module only assembles them:
  templates/head.html   <head> extras: fonts, static/css/duet.css, static/js/stage.js (inlined)
  templates/gate.html   access-code screen          templates/stage.html  every stage screen (start ... sent)
  templates/pearl.html  the pearl                   templates/glow.html   its glow layers
  templates/chip.html   a language chip             templates/wordmark.html
  static/img/*.svg      inline icons                static/js/*_inputs.js  the gr.HTML click -> inputs bridges
"""

from .web import fill, read

CSS = read("static/css/duet.css")
JS = read("static/js/stage.js")
SVG = {k: read(f"static/img/{k}.svg") for k in ("note", "close", "book", "again", "slower", "pause", "check")}
WORDMARK = read("templates/wordmark.html")
GATE_INPUTS_JS = read("static/js/gate_inputs.js")     # gate.click js=: the recorded action + the session id
STAGE_INPUTS_JS = read("static/js/stage_inputs.js")   # stage.click js=: the recorded action, no WebRTC value, sid

_PEARL = read("templates/pearl.html")
_GLOW = read("templates/glow.html")
_CHIP = read("templates/chip.html")
_GATE = read("templates/gate.html")
_STAGE = read("templates/stage.html")
_HEAD = read("templates/head.html")


def _pearl(prefix: str) -> str:
    return fill(_PEARL, prefix=prefix, svg_pause=SVG["pause"], svg_check=SVG["check"])


def _glow(prefix: str) -> str:
    return fill(_GLOW, prefix=prefix)


def gate_html(error: str = "") -> str:
    err = ("That code did not work. Please try again." if error else "")
    return fill(_GATE, glow=_glow("g"), wordmark=WORDMARK, pearl=_pearl("g"), error=err)


def _chip(code, native, name, lang_attr, size, extra=""):
    return fill(_CHIP, sel=" sel" if code == "ne" else "", code=code, native=native, name=name, lang_attr=lang_attr,
                size=size, extra=extra)


STAGE_HTML = fill(
    _STAGE, glow=_glow("s"), wordmark=WORDMARK, pearl=_pearl("s"),
    chip_ne=_chip("ne", "नेपाली", "Nepali", "ne", 20),
    chip_hi=_chip("hi", "हिन्दी", "Hindi", "hi", 20),
    chip_ur=_chip("ur", "اردو", "Urdu", "ur", 22, 'dir="rtl"'),
    chip_bn=_chip("bn", "বাংলা", "Bengali", "bn", 20),
    chip_ml=_chip("ml", "മലയാളം", "Malayalam", "ml", 19),
    chip_tl=_chip("tl", "Filipino", "Tagalog", "tl", 20),
    **{f"svg_{k}": SVG[k] for k in ("note", "close", "book", "again", "slower")},
)

HEAD = fill(_HEAD, css=CSS, js=JS)
