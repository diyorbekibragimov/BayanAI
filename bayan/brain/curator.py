"""Bayan AI · the attention budget: deterministic code between the copilot's review and the doctor's screen.

The copilot agent reviews the consultation like a second clinician and proposes candidate concerns (each quoting
the transcript). Most of them should never reach the screen. The curator decides, with plain arithmetic:

  score = severity_weight x confidence x novelty x recency
    severity_weight  caution 1.0, info 0.6 (agent concerns are never critical; critical belongs to the rule engine);
                     a concern filed under safety or communication weighs as caution; questions keep info weight
    confidence       the reviewer's own 0-1 estimate (deterministic fallback questions: fixed 0.8)
    novelty          1.0 new theme; 0.5 a theme shown before and since resolved/retired; dismissed themes are
                     suppressed for the whole visit (never scored)
    recency          0.8 ** (turns since the newest quoted utterance): concerns about what was just said win; an
                     unaddressed concern (missed / observation) never drops below 0.6, questions keep decaying

  * below THRESHOLD (0.4): held back (logged, never shown); for a ROUTINE question (not filed under safety or
    communication) the bar is THRESHOLD x 1.25 per question already shown in this visit that the doctor did not use
    (reset when the doctor uses one)
  * at most MAX_NEW_PER_TURN (1) new agent card per review
  * near-duplicates (similar titles or questions; or same dimension + overlapping evidence + some shared wording) are
    merged into the card already on screen (its evidence grows; a different second point is appended to its body,
    "Also: ...") instead of adding a card; within one review, a second concern of the same dimension about the same
    words becomes such an "Also:" line of the card just posted rather than being lost to the budget
  * "Ask next" questions are suggestions: always severity info (a warning is its own card)
  * exactly ONE "Ask next" question is open at a time: a new question replaces the current one only if it is worth
    more than the current one's decayed value (ASK_DECAY per turn since it was posted); the old one is retired,
    never stacked
  * at most MAX_VISIBLE (4) agent cards open: the least valuable older one is retired
  * cards resolve themselves when the conversation addresses them: the reviewer lists addressed card ids, and a
    doctor question on the same topic as the open "Ask next" resolves it (resolve_asked)

Rule cards (the deterministic engine) never pass through here: they are unchanged and remain the only source of
critical alerts and held sentences.
"""

from __future__ import annotations

import difflib
import os
from typing import Any

from .cards import REVIEW_DIMENSIONS, norm_text

SEV_WEIGHT = {"info": 0.6, "caution": 1.0}
THRESHOLD = float(os.environ.get("BAYAN_CURATE_MIN", "0.4"))
MAX_NEW_PER_TURN = int(os.environ.get("BAYAN_CURATE_MAX_NEW", "1"))
MAX_VISIBLE = int(os.environ.get("BAYAN_CURATE_MAX_VISIBLE", "4"))
RECENCY_DECAY = 0.8
RECENCY_FLOOR = 0.6       # concerns (not questions) still unaddressed never decay below this
ASK_BUDGET_STEP = 1.25    # each question shown and not used by the doctor raises the bar for the next one
WEIGHTY_DIMENSIONS = ("safety", "communication")
ASK_DECAY = 0.85
SEEN_NOVELTY = 0.5
DIMENSIONS = REVIEW_DIMENSIONS
FALLBACK_CONFIDENCE = 0.8
_CURATED = ("agent", "fallback")        # sources whose cards the curator manages (lexicon idiom cards are not)

_STOP = set("""a an the and or but if then than so to of in on at by for with without from into onto about as is are was
were be been being am do does did done have has had having not no nor yes you your yours i me my we our us he she it its
they them their this that these those there here what which who whom whose when where why how any some all each every
more most less least very just only also again still yet ever never please can could would should will shall may might
must let lets get got make made give given take taken ask asked tell told say said patient doctor clinician visit
today now new note noted card one two after before""".split())


# ------------------------------------------------------------------ text helpers
def content_tokens(text: str | None) -> set[str]:
    out = set()
    for w in norm_text(text).split():
        if len(w) < 3 or w in _STOP or w.isdigit():
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


def theme_sim(a: str | None, b: str | None) -> float:
    """Similarity of two short titles/questions: max of content-word overlap (Jaccard) and character similarity."""
    ta, tb = content_tokens(a), content_tokens(b)
    jac = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    na, nb = norm_text(a), norm_text(b)
    seq = difflib.SequenceMatcher(None, na, nb).ratio() if na and nb else 0.0
    return max(jac, seq if seq >= 0.82 else 0.0)


def _utts(card: dict) -> set[str]:
    return {str(e.get("utt")) for e in card.get("evidence") or [] if isinstance(e, dict) and e.get("utt")}


def _turn_index(consult) -> tuple[dict[str, int], int]:
    turns = [t for t in consult.turns if t.kind != "system"]
    return {t.id: i for i, t in enumerate(turns)}, len(turns)


def turns_since(consult, utts) -> int:
    idx, n = _turn_index(consult)
    pos = [idx[u] for u in utts if u in idx]
    return (n - 1 - max(pos)) if pos else n


def recency(consult, utts) -> float:
    return RECENCY_DECAY ** max(0, turns_since(consult, utts))


def current_value(consult, card: dict) -> float:
    """What an open card is worth now: its score when posted, decayed per turn since then (ASK_DECAY for the
    "Ask next" question, RECENCY_DECAY for other cards). Cards posted outside the curator count as 0.5."""
    base = float(card.get("score") or 0.5)
    _idx, n = _turn_index(consult)
    posted_at = card.get("posted_turn")
    k = (n - 1 - posted_at) if isinstance(posted_at, int) else turns_since(consult, _utts(card))
    return base * (ASK_DECAY if card.get("kind") == "ask" else RECENCY_DECAY) ** max(0, k)


# ------------------------------------------------------------------ the decision
def _sev(c: dict) -> str:
    return "caution" if str(c.get("severity") or "").lower() == "caution" else "info"


def _conf(c: dict, default: float = 0.6) -> float:
    try:
        x = float(c.get("confidence"))
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, x / 100.0 if x > 1.0 else x))


def _dim(c: dict) -> str:
    d = str(c.get("dimension") or "").strip().lower()
    return d if d in DIMENSIONS else ("history" if c.get("kind") == "ask" else "consistency")


def _ev_overlap(c: dict, other: dict) -> bool:
    return bool({str(e.get("utt")) for e in c.get("evidence") or []} & _utts(other))


def _same_theme(c: dict, other: dict) -> bool:
    """Near-duplicate: similar titles / questions, or (not for questions) the same dimension with overlapping
    evidence and some shared wording. Two different questions about the same utterance are NOT duplicates."""
    if theme_sim(c.get("title"), other.get("title")) >= 0.6:
        return True
    if c.get("kind") == "ask" or other.get("kind") == "ask":
        return (c.get("kind") == other.get("kind") and bool(c.get("ask_text")) and bool(other.get("ask_text"))
                and theme_sim(c["ask_text"], other["ask_text"]) >= 0.5)
    if not _ev_overlap(c, other):
        return False
    sim = max(theme_sim(c.get("title"), other.get("title")),
              theme_sim(f"{c.get('title')} {c.get('body')}", f"{other.get('title')} {other.get('body')}"))
    if _dim(c) == str(other.get("dimension") or ""):
        return sim >= 0.25
    return sim >= 0.33         # the same concern restated under another dimension


def _same_point_now(c: dict, other: dict) -> bool:
    """Within ONE review, a second concern of the same dimension about the same words is a second point of the
    card just posted (it becomes an "Also:" line instead of being lost to the one-card-per-turn budget)."""
    if c.get("kind") == "ask" or other.get("kind") == "ask":
        return _same_theme(c, other)
    return _same_theme(c, other) or (_dim(c) == str(other.get("dimension") or "") and _ev_overlap(c, other))


def _dismissed_theme(c: dict, dismissed: list[dict]) -> dict | None:
    for d in dismissed:
        if d.get("source") not in _CURATED:
            continue
        if theme_sim(c.get("title"), d.get("title")) >= 0.5:
            return d
        if c.get("ask_text") and d.get("ask_text") and theme_sim(c["ask_text"], d["ask_text"]) >= 0.5:
            return d
        if (c.get("kind") != "ask" and d.get("kind") != "ask" and str(d.get("dimension") or "") == _dim(c)
                and _ev_overlap(c, d) and theme_sim(c.get("title"), d.get("title")) >= 0.25):
            return d
    return None


def unused_asks(cards: list[dict]) -> int:
    """Questions shown in this visit since the doctor last used one (tapped "Ask" or asked it in their own words).
    Each one the doctor let pass raises the bar for the next question (ask_threshold)."""
    n = 0
    asks = sorted((c for c in cards if c.get("kind") == "ask" and c.get("source") in _CURATED),
                  key=lambda c: (c.get("t_min") or 0, c.get("id")))
    for c in asks:
        used = c.get("status") == "accepted" or any(
            a.get("action") == "ask" for a in c.get("actions") or []) or "the doctor asked it" in str(
            c.get("resolved_reason") or "")
        n = 0 if used else n + 1
    return n


def ask_threshold(cards: list[dict]) -> float:
    return THRESHOLD * ASK_BUDGET_STEP ** unused_asks(cards)


def _weight(c: dict) -> float:
    """Severity weight; a concern (not a question) the reviewer files under safety or communication (incl. the
    patient's understanding and affect) carries caution weight even when labelled info: those are the concerns a
    doctor most often misses, and a confident one must clear the threshold. Questions keep their info weight."""
    if c.get("kind") != "ask" and _dim(c) in WEIGHTY_DIMENSIONS:
        return SEV_WEIGHT["caution"]
    return SEV_WEIGHT[_sev(c)]


def score(consult, c: dict, cards: list[dict]) -> tuple[float, dict]:
    """(score, parts) for one candidate against everything already shown in this visit."""
    conf = _conf(c, FALLBACK_CONFIDENCE if c.get("_source") == "fallback" else 0.6)
    novelty = 1.0
    for o in cards:
        if o.get("source") in _CURATED and o.get("status") in ("resolved", "accepted") and _same_theme(c, o):
            novelty = SEEN_NOVELTY
            break
    rec = recency(consult, {str(e.get("utt")) for e in c.get("evidence") or []})
    if c.get("kind") != "ask":
        # an unaddressed concern does not fade: the reviewer re-raising it now means the topic is still open (an
        # addressed one is resolved / reported addressed instead); questions keep decaying (the moment passes)
        rec = max(rec, RECENCY_FLOOR)
    s = _weight(c) * conf * novelty * rec
    return round(s, 3), {"severity": _sev(c), "confidence": round(conf, 2), "novelty": novelty, "recency": round(rec, 2)}


def offer(consult, candidates: list[dict], addressed: list | None = None, source: str = "agent",
          max_new: int | None = None) -> list[str]:
    """Curate validated candidate concerns (each {kind, dimension, title, body, severity, confidence, evidence:
    [{utt, quote}], ask_text, grounding}) onto the card store. Returns one result per candidate, in order: a card
    id, "duplicate (merged into cXXX)", "held back: ...", or "rejected: ..."."""
    store = consult.cards
    now = consult.now_min()
    max_new = MAX_NEW_PER_TURN if max_new is None else max_new
    for cid in addressed or []:
        card = store.get(str(cid).strip())
        if card and card.get("status") == "open" and card.get("source") in _CURATED:
            store.resolve(card["id"], "addressed in the conversation (copilot review)", now)
            consult.log("card", f"✓ {card['id']} addressed: {card['title'][:60]}")
    results: list[str | None] = [None] * len(candidates)
    cards = store.all_cards()
    dismissed = store.dismissed_cards()
    scored: list[tuple[float, int, dict, dict]] = []
    for i, c in enumerate(candidates):
        c = dict(c, _source=source)
        if c.get("kind") == "ask":
            c["severity"] = "info"      # a question is a suggestion, never a warning: the warning is its own card
        d = _dismissed_theme(c, dismissed)
        if d is not None:
            results[i] = store.reject(c.get("kind") or "", c.get("title") or "",
                                      f"the doctor dismissed a similar card earlier ('{d.get('title', '')[:50]}'); "
                                      "do not raise this theme again", source=source, severity=_sev(c),
                                      grounding=str(c.get("grounding") or ""), t_min=now)
            continue
        s, parts = score(consult, c, cards)
        c["_score"], c["_parts"] = s, parts
        dup = next((o for o in cards if o.get("source") in _CURATED and o.get("status") == "open"
                    and _same_theme(c, o)), None)
        if dup is not None:
            results[i] = _merge_into(consult, dup, c, s)
            continue
        # the per-visit question budget applies to routine questions only: a question filed under safety or
        # communication (affect, understanding) faces the base bar, and still competes for the one Ask-next slot
        routine_q = c.get("kind") == "ask" and _dim(c) not in WEIGHTY_DIMENSIONS
        bar = ask_threshold(cards) if routine_q else THRESHOLD
        if s < bar:
            results[i] = (f"held back: score {s:.2f} < {bar:.2f} "
                          f"({parts['severity']} x conf {parts['confidence']} x novelty {parts['novelty']} x "
                          f"recency {parts['recency']})")
            continue
        scored.append((s, i, c, parts))
    scored.sort(key=lambda x: -x[0])
    posted = 0
    _idx, n_turns = _turn_index(consult)
    shown_now: list[dict] = []
    for s, i, c, parts in scored:
        if posted >= max_new:
            dup = next((o for o in shown_now if _same_point_now(c, o)), None)
            if dup is not None:                  # a second point on the card just posted: merged, not lost
                results[i] = _merge_into(consult, store.get(dup["id"]) or dup, c, s)
            else:
                results[i] = f"held back: one new card per turn (score {s:.2f})"
            continue
        open_ask = None
        if c.get("kind") == "ask":
            open_ask = next((o for o in store.open_cards() if o.get("kind") == "ask"), None)
            if open_ask is not None:
                cur = current_value(consult, open_ask)
                if s <= cur:
                    results[i] = f"held back: the current Ask next ({open_ask['id']}) is still worth more ({cur:.2f} >= {s:.2f})"
                    continue
        res = store.post(c.get("kind") or "", c.get("title") or "", c.get("body") or c.get("title") or "",
                         c.get("evidence") or [], str(c.get("grounding") or _dim(c)), severity=_sev(c),
                         ask_text=c.get("ask_text"), source=source, t_min=now, dimension=_dim(c),
                         confidence=parts["confidence"], score=s, posted_turn=n_turns - 1,
                         supersede=open_ask["id"] if open_ask is not None else None)
        results[i] = res
        if res.startswith("rejected") or res.startswith("duplicate"):
            continue
        posted += 1
        shown_now.append(store.get(res) or {})
        consult.log("card", f"curate: {res} shown (score {s:.2f}: {parts['severity']} x conf {parts['confidence']}"
                            f" x novelty {parts['novelty']} x recency {parts['recency']})")
        _enforce_visible(consult, keep=res)
    for i, r in enumerate(results):
        if r and r.startswith("held back"):
            consult.log("card", f"curate: '{str(candidates[i].get('title') or '')[:60]}' {r}")
    return [r or "held back" for r in results]


def _merge_into(consult, dup: dict, c: dict, s: float) -> str:
    """Fold a near-duplicate into the open card: evidence grows, confidence is the max, and a different second
    point (a worthwhile one, at most two) is appended to the body ("Also: ...")."""
    body = dup.get("body") or ""
    point = (c.get("title") or "").strip()
    points = [dup.get("title") or ""] + [p.strip(" .") for p in body.split(" Also: ")[1:]]
    if (s >= THRESHOLD and point and body.count(" Also: ") < 2 and norm_text(point) not in norm_text(body)
            and all(theme_sim(point, p) < 0.5 for p in points)):
        body = f"{body.rstrip()} Also: {point.rstrip('.')}."
    consult.cards.update(dup["id"], evidence=c.get("evidence") or [], body=body, t_min=consult.now_min(),
                         confidence=max(_conf(dup, 0.0), _conf(c)))
    return f"duplicate (merged into {dup['id']})"


def _enforce_visible(consult, keep: str) -> None:
    store = consult.cards
    opened = [c for c in store.open_cards() if c.get("source") in _CURATED]
    while len(opened) > MAX_VISIBLE:
        victim = min((c for c in opened if c["id"] != keep), key=lambda c: current_value(consult, c), default=None)
        if victim is None:
            return
        store.resolve(victim["id"], "retired: newer concerns are more relevant", consult.now_min())
        opened = [c for c in opened if c["id"] != victim["id"]]


# ------------------------------------------------------------------ deterministic resolution
_Q_END = ("?", "؟")


def resolve_asked(consult, turns: list) -> list[str]:
    """A doctor (or Bayan) question on the same topic as the open "Ask next" resolves it: the doctor asked it in
    their own words. Content-word overlap with the suggested question (at least half of the shorter one's words,
    and two words unless it has only one or two). Returns the resolved card ids."""
    out = []
    store = consult.cards
    for t in turns:
        if t.role not in ("doctor", "bayan") or getattr(t, "kind", "speech") == "system":
            continue
        text = (t.english or t.text or "").strip()
        if not text or "?" not in text and "؟" not in text:
            continue
        said = content_tokens(text)
        for c in store.open_cards():
            if c.get("kind") != "ask" or c.get("source") not in _CURATED or not c.get("ask_text"):
                continue
            want = content_tokens(c["ask_text"])
            if not want or not said:
                continue
            common = want & said
            small = min(len(want), len(said))
            if len(common) >= (1 if small <= 2 else 2) and len(common) / small >= 0.5:
                store.resolve(c["id"], f"the doctor asked it ({t.id})", consult.now_min())
                consult.log("card", f"✓ {c['id']} resolved: the doctor asked about it in {t.id}")
                out.append(c["id"])
    return out


def visible(consult) -> list[dict]:
    """Open curated cards, most valuable first (UI / tests)."""
    cards = [c for c in consult.cards.open_cards() if c.get("source") in _CURATED]
    return sorted(cards, key=lambda c: -current_value(consult, c))


def summary(consult) -> dict[str, Any]:
    v = visible(consult)
    return {"visible": [c["id"] for c in v], "ask": next((c["id"] for c in v if c.get("kind") == "ask"), None)}


__all__ = ["offer", "resolve_asked", "visible", "score", "theme_sim", "content_tokens", "THRESHOLD",
           "MAX_NEW_PER_TURN", "MAX_VISIBLE", "DIMENSIONS"]
