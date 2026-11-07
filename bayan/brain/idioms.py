"""Bayan AI · deterministic idiom matching over data/idiom_lexicon.json.

Three matchers, no LLM:
  1. native-script substring (Devanagari/Bengali/Arabic/... ; suffixes such as Nepali -ले attach directly);
  2. romanized / Latin-script forms, normalised (case, diacritics, common transliteration variants such as
     c/k, aspirates, doubled vowels), matched token by token with a small affix allowance and a rapidfuzz
     ratio >= 90 for longer forms;
  3. English loanword entries ("gastric", "gas", "tension", "gas trouble"), matched in the English rendering too.
When the patient's language is given, romanized forms are only tried for entries of that language (so an
English word in the sentence cannot hit an unrelated language's romanization) and same-language entries win
over other-language entries matched on the same words.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

try:
    from rapidfuzz import fuzz as _fuzz

    def _ratio(a: str, b: str) -> float:
        return _fuzz.ratio(a, b)
except ImportError:  # pragma: no cover - rapidfuzz is a declared dependency
    import difflib

    def _ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100

from .vocab import LEXICON_PATH

FUZZY_THRESHOLD = 90
_LANG = {
    "ne": "npi", "nep": "npi", "npi": "npi", "nepali": "npi",
    "hi": "hin", "hin": "hin", "hindi": "hin",
    "ur": "urd", "urd": "urd", "urdu": "urd",
    "bn": "ben", "ben": "ben", "bengali": "ben", "bangla": "ben",
    "ml": "mal", "mal": "mal", "malayalam": "mal",
    "ta": "tam", "tam": "tam", "tamil": "tam",
    "tl": "tgl", "fil": "tgl", "tgl": "tgl", "tagalog": "tgl", "filipino": "tgl", "ceb": "tgl", "cebuano": "tgl",
    "ar": "ara", "ara": "ara", "arb": "ara", "apc": "ara", "afb": "ara", "arz": "ara", "apd": "ara", "arabic": "ara",
    "am": "amh", "amh": "amh", "amharic": "amh",
    "pa": "pan", "pan": "pan", "punjabi": "pan",
    "en": "eng", "eng": "eng", "english": "eng",
    "sw": "swh", "swa": "swh", "swh": "swh", "swahili": "swh", "kiswahili": "swh",
}
# English loanwords / code-mixed forms, matched in the patient's text AND in the English rendering.
LOANWORDS = {
    "npi-005": ["gyastrik", "gastric", "gastrik"],
    "ben-007": ["gastric", "gas problem"],
    "hin-004": ["gas"],
    "mal-001": ["gas trouble"],
    "mul-001": ["tension"],
}
# Extra spellings / variants named in the entries' notes or literal glosses.
EXTRA_FORMS = {
    "npi-006": ["kat kat khanchha"],
    "npi-010": ["dar laagyo"],
    "npi-011": ["bhoot laagyo"],
    "mul-001": ["टेन्सन", "टेन्शन"],          # Nepali spellings of 'tension'
    "npi-005": ["ग्यास्टिक"],                 # common misspelling without the र
}
_PREFIXES = ("", "ma", "na", "naka", "nag", "pinag", "kina", "ki", "in")          # Tagalog affixes
_SUFFIXES = ("", "le", "ko", "ma", "lai", "ka", "ki", "ke", "haru", "ta", "ra", "er", "e",   # Nepali/Hindi/Bengali
             "an", "in", "han", "hin", "ado", "ada")                                      # Tagalog
_ZW = dict.fromkeys(map(ord, "​‌‍﻿"), None)


def _strip_marks(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _is_latin(s: str) -> bool:
    letters = [ch for ch in s if ch.isalpha()]
    return bool(letters) and all(ord(_strip_marks(ch) or "a") < 0x250 for ch in letters)


def _latin_tokens(s: str) -> list[str]:
    s = _strip_marks(s.lower()).replace("'", "").replace("’", "").replace("`", "")
    return re.findall(r"[a-z0-9]+", s)


def _phon(tok: str) -> str:
    t = tok.replace("ck", "k")
    t = re.sub(r"c(?!h)", "k", t)
    t = t.replace("ph", "f").replace("ee", "i").replace("oo", "u")
    for a, b in (("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"), ("bh", "b"), ("jh", "j"), ("sh", "s"),
                 ("ch", "c")):
        t = t.replace(a, b)
    t = t.replace("w", "v").replace("z", "j").replace("q", "k")
    return re.sub(r"(.)\1+", r"\1", t)


def _native_norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).translate(_ZW).lower()


def _split_forms(field: str, romanized: bool) -> list[str]:
    """'a / b (c, d)' -> ['a', 'b', 'c', 'd'], dropping English glosses and labels inside parentheses."""
    if not field:
        return []
    out: list[str] = []
    paren = re.findall(r"\(([^)]*)\)", field)
    main = re.sub(r"\([^)]*\)", " ", field)
    for part in re.split(r"\s*/\s*", main):
        part = part.strip(" '\"")
        if part:
            out.append(part)
    for p in paren:
        for seg in re.split(r"\s*[,/]\s*", p):
            seg = seg.strip()
            if not seg or "reported as" in seg.lower():
                continue
            if ":" in seg:
                seg = seg.split(":", 1)[1].strip()
            if seg.startswith("'") or seg.startswith("‘") or seg.startswith('"'):
                continue  # quoted English gloss
            if romanized and seg.lower() in ("tagalog", "cebuano", "bengali", "hindi", "urdu", "nepali"):
                continue
            seg = seg.strip(" '\"")
            if seg:
                out.append(seg)
    return out


def _infinitive_stems(forms: list[str]) -> list[str]:
    """Hindi/Urdu/Punjabi verb idioms are listed as infinitives ('dil ghabrana', 'दिल घबराना'); patients
    conjugate them ('दिल घबरा रहा है'). Add the stem of the last word so the conjugated forms match."""
    out = []
    for f in forms:
        words = f.split()
        if len(words) < 2:
            continue
        last = words[-1]
        for suf in ("ना", "نا", "na"):
            if last.endswith(suf) and len(last) - len(suf) >= 2:
                out.append(" ".join(words[:-1] + [last[: -len(suf)]]))
    return out


@dataclass
class _Form:
    entry_id: str
    surface: str
    latin: bool
    loan: bool
    tokens: tuple[str, ...] = ()      # phonetic-normalised tokens (latin forms)
    native: str = ""                  # NFC-normalised (native-script forms)

    @property
    def joined(self) -> str:
        return " ".join(self.tokens)


class IdiomIndex:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else LEXICON_PATH
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.meta = data.get("meta", {})
        self.entries: list[dict] = data["entries"]
        self.by_id: dict[str, dict] = {e["id"]: e for e in self.entries}
        self.langs: dict[str, set[str]] = {e["id"]: self._entry_langs(e) for e in self.entries}
        self.forms: list[_Form] = []
        for e in self.entries:
            seen: set[tuple] = set()
            surfaces = [(s, False) for s in _split_forms(e.get("native", ""), False)]
            surfaces += [(s, False) for s in _split_forms(e.get("romanized", ""), True)]
            surfaces += [(s, False) for s in EXTRA_FORMS.get(e["id"], [])]
            surfaces += [(s, True) for s in LOANWORDS.get(e["id"], [])]
            if "hin" in self.langs[e["id"]] or "pan" in self.langs[e["id"]]:
                surfaces += [(st, False) for st in _infinitive_stems([x for x, _ in surfaces])]
            for s, loan in surfaces:
                if _is_latin(s):
                    toks = tuple(_phon(t) for t in _latin_tokens(s))
                    if not toks or (toks, loan) in seen:
                        continue
                    seen.add((toks, loan))
                    self.forms.append(_Form(e["id"], s, True, loan, tokens=toks))
                else:
                    n = _native_norm(s).strip()
                    if not n or (n,) in seen:
                        continue
                    seen.add((n,))
                    self.forms.append(_Form(e["id"], s, False, loan, native=n))

    @staticmethod
    def _entry_langs(e: dict) -> set[str]:
        langs = {_LANG.get(str(e.get("iso639_3", "")).lower(), str(e.get("iso639_3", "")).lower())}
        for code in e.get("also_used_in") or []:
            langs.add(_LANG.get(str(code).lower(), str(code).lower()))
        for word in re.findall(r"[A-Za-z]+", e.get("language", "")):
            if word.lower() in _LANG and word.lower() != "english":   # "(English loanword)" is not a language
                langs.add(_LANG[word.lower()])
        return langs

    def _loan_tokens(self, entry_id: str) -> set[str]:
        if not hasattr(self, "_loans"):
            self._loans: dict[str, set[str]] = {}
            for f in self.forms:
                if f.loan:
                    self._loans.setdefault(f.entry_id, set()).update(f.tokens)
        return self._loans.get(entry_id, set())

    def get(self, idiom_id: str) -> dict | None:
        return self.by_id.get(idiom_id)

    def _in_lang(self, entry_id: str, lang: str | None) -> bool:
        return lang is not None and lang in self.langs.get(entry_id, set())

    # ------------------------------------------------------------------ matching
    @staticmethod
    def _tok_match(f: str, t: str) -> bool:
        if t == f:
            return True
        if len(f) < 4 or len(t) <= len(f):
            return False
        for p in _PREFIXES:
            if not t.startswith(p):
                continue
            rest = t[len(p):]
            if rest.startswith(f) and rest[len(f):] in _SUFFIXES:
                return True
        return False

    def _latin_hits(self, form: _Form, toks: list[str], raw: list[str]) -> tuple[float, str] | None:
        """Best window of the text matching the form -> (score, the original words matched)."""
        k = len(form.tokens)
        best: tuple[float, str] | None = None
        for i in range(0, len(toks) - k + 1):
            window = toks[i:i + k]
            if all(self._tok_match(f, t) for f, t in zip(form.tokens, window)):
                score = 96.0 if list(form.tokens) == window else 93.0
            elif len(form.joined) >= 6:
                r = _ratio(form.joined, " ".join(window))
                if r < FUZZY_THRESHOLD:
                    continue
                score = r * 0.9
            else:
                continue
            if best is None or score > best[0]:
                best = (score, " ".join(raw[i:i + k]))
        return best

    def match(self, text: str, english: str = "", lang: str | None = None) -> list[dict]:
        """Idiom entries present in an utterance, best first, no duplicates:
        [{"id","matched","red_flag_tags","entry"}]."""
        lang_c = _LANG.get(str(lang).lower(), str(lang).lower()) if lang else None
        text = text or ""
        native_text = _native_norm(text)
        raw_tokens = _latin_tokens(text)
        toks = [_phon(t) for t in raw_tokens]
        en_tokens_raw = _latin_tokens(english or "")
        en_toks = [_phon(t) for t in en_tokens_raw]
        native_words = set(re.split(r"[\s।॥.,!?;:\"'()\-،؟]+", native_text))
        english_utterance = lang_c == "eng" or (bool(english) and text.strip().lower() == english.strip().lower())

        found: dict[str, tuple[float, str, set[str]]] = {}   # id -> (score, matched, matched-token set)
        via: dict[str, set[str]] = {}                          # id -> {"text", "loan_text", "english"}

        def add(eid: str, score: float, matched: str, span: set[str], how: str):
            via.setdefault(eid, set()).add(how)
            if self._in_lang(eid, lang_c):
                score += 5
            prev = found.get(eid)
            if prev is None or score > prev[0]:
                found[eid] = (score, matched, span)

        for form in self.forms:
            eid = form.entry_id
            if not form.latin:
                if not form.native:
                    continue
                short = len(form.native.replace(" ", "")) <= 3
                hit = (form.native in native_words) if short else (form.native in native_text)
                if hit:
                    add(eid, 100.0 + min(len(form.native), 20) / 10, form.surface, {form.native}, "text")
                continue
            # latin / romanized form. Loanwords count only for entries of the patient's language (when given);
            # an English utterance (lang "en", or text identical to its English rendering) is only searched
            # for loanwords, so English words such as "mass" or "init" never hit a romanization.
            if form.loan:
                allowed = not lang_c or self._in_lang(eid, lang_c)
            elif english_utterance:
                allowed = False
            else:
                single_short = len(form.tokens) == 1 and len(form.tokens[0]) <= 4
                allowed = self._in_lang(eid, lang_c) if lang_c else not single_short
            if not allowed:
                continue
            if toks:
                h = self._latin_hits(form, toks, raw_tokens)
                if h:
                    add(eid, h[0] + min(len(form.joined), 20) / 10, h[1], {_phon(w) for w in h[1].split()},
                        "loan_text" if form.loan else "text")
            if form.loan and en_toks:
                h = self._latin_hits(form, en_toks, en_tokens_raw)
                if h:
                    add(eid, h[0] - 8 + min(len(form.joined), 20) / 10, h[1], {_phon(w) for w in h[1].split()}, "english")

        if lang_c:
            # Other-language entries are dropped when they were found only through the English rendering,
            # when they share a loanword with a same-language hit ('gastric': npi-005 vs ben-007), or when
            # they matched the same words as a same-language hit.
            mine = [k for k in found if self._in_lang(k, lang_c)]
            mine_spans = [found[k][2] for k in mine]
            mine_loans = set().union(*[self._loan_tokens(k) for k in mine]) if mine else set()
            for k in list(found):
                if self._in_lang(k, lang_c):
                    continue
                if (via[k] == {"english"} or (self._loan_tokens(k) & mine_loans and via[k] <= {"english", "loan_text"})
                        or any(found[k][2] & sp for sp in mine_spans)):
                    del found[k]

        ranked = sorted(found.items(), key=lambda kv: (-kv[1][0], kv[0]))
        out = []
        for eid, (score, matched, _) in ranked:
            e = self.by_id[eid]
            out.append({"id": eid, "matched": matched, "red_flag_tags": list(e.get("red_flag_tags") or []),
                        "entry": e, "score": round(score, 1)})
        return out

    def lookup(self, phrase: str, lang: str | None = None) -> dict | None:
        """Best single match for a phrase (agent tool). Accepts an idiom id too."""
        if not phrase:
            return None
        if phrase in self.by_id:
            e = self.by_id[phrase]
            return {"id": phrase, "matched": phrase, "red_flag_tags": list(e.get("red_flag_tags") or []), "entry": e}
        for lg in ([lang, None] if lang else [None]):
            hits = self.match(phrase, english="", lang=lg)
            if hits:
                return hits[0]
        return None


_INDEX: IdiomIndex | None = None


def default_index() -> IdiomIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = IdiomIndex()
    return _INDEX
