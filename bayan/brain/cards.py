"""Bayan AI · decision-support cards for the doctor, with the guardrails enforced in code.

Cards come from four sources:
  "rules"    the deterministic rule engine (the only source allowed to be critical)
  "lexicon"  the idiom lexicon (idiom cards)
  "agent"    the smolagents copilot (ask / missed / observation, at most caution)
  "fallback" deterministic ask cards when the agent fails or is switched off

Guardrails: agent/fallback cards need evidence that quotes real utterance ids and a grounding that exists
(rule id, idiom id, checklist id; observations may also cite an utterance id); at most 3 open "ask" cards;
dedupe on (kind, grounding, normalised title) plus fuzzy matching of the question; a card the doctor dismissed
never comes back in that consultation. WORK-CHEST-* rule hits collapse into one "Chest-pain workup" card.
Every change bumps `version` (the UI polls it) and every alert/action lands in the append-only `audit`.
"""

from __future__ import annotations

import copy
import difflib
import re
import threading
from typing import Callable

SEVERITIES = ("info", "caution", "critical")
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
KINDS = ("safety", "missed", "ask", "idiom", "observation")
AGENT_KINDS = ("ask", "missed", "observation")
KINDS_BY_SOURCE = {
    "rules": ("safety", "missed"),
    "lexicon": ("idiom", "observation"),
    "agent": AGENT_KINDS,
    "fallback": AGENT_KINDS,
}
# doctor action -> resulting status
ACTIONS = {
    "acknowledge": "acknowledged",
    "override": "overridden",
    "dismiss": "dismissed",
    "accept": "accepted",
    "ask": "accepted",          # the doctor tapped "Ask": the question is spoken, the card is done
    "wrong_fact": "overridden",  # extraction error: the doctor corrects the state; logged as such
}
MAX_OPEN_ASK = 3
GROUP_TITLES = {
    "chest_pain_workup": "Chest-pain workup",
    "heat_illness": "Heat-illness workup",
    "heat_workup": "Heat-illness workup",
    "heat_illness_workup": "Heat-illness workup",
}
FAMILY_TITLES = {
    "drug_allergy": "Allergy conflict",
    "dose_ceiling": "Dose ceiling",
    "dose": "Dose ceiling",
    "drug_drug": "Drug interaction",
    "drug_drug_interaction": "Drug interaction",
    "missing_workup": "Possibly missed workup",
    "pregnancy": "Pregnancy safety",
    "heat_medication": "Heat & medication",
}
_SIMILAR = 0.82   # fuzzy threshold for "same card, reworded"


def norm_text(s: str | None) -> str:
    return " ".join(re.findall(r"\w+", (s or "").lower()))


def group_of(fired: dict) -> str | None:
    """Rule hits that collapse into one grouped card (WORK-CHEST-* -> chest_pain_workup)."""
    rid = str(fired.get("rule_id") or "")
    if rid.startswith("WORK-CHEST-"):
        return "chest_pain_workup"
    g = fired.get("group")
    if g and fired.get("family") == "missing_workup":
        return str(g)
    return None


_CHECKLIST_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_UTT_ID = re.compile(r"^u\d+$")


def _is_checklist_id(grounding: str | None) -> bool:
    return bool(grounding) and bool(_CHECKLIST_ID.match(grounding)) and not _UTT_ID.match(grounding)


def _similar(a: str, b: str) -> bool:
    a, b = norm_text(a), norm_text(b)
    if not a or not b:
        return False
    if a == b:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= _SIMILAR


def _merge_evidence(*lists: list[dict]) -> list[dict]:
    out, seen = [], set()
    for lst in lists:
        for ev in lst or []:
            if not isinstance(ev, dict):
                continue
            k = (ev.get("utt"), norm_text(ev.get("quote")))
            if k in seen:
                continue
            seen.add(k)
            out.append(dict(ev))
    return out


class CardStore:
    """Thread-safe card list for one consultation.

    grounding_check(kind, grounding) -> bool   validates agent/fallback groundings (None: any non-empty string)
    turn_lookup(utt) -> Turn | None            validates evidence utterance ids and fills t_min / quote
    clock() -> float                           consultation minutes for actions (default 0.0)
    state_version() -> int                     recorded in audit entries
    log(kind, text)                            activity-feed hook (consult.log)
    audit                                      list to append audit entries to (consult.audit when attached)
    """

    def __init__(self, grounding_check: Callable[[str, str], bool] | None = None,
                 turn_lookup: Callable[[str], object] | None = None,
                 clock: Callable[[], float] | None = None,
                 state_version: Callable[[], int] | None = None,
                 log: Callable[[str, str], None] | None = None,
                 audit: list | None = None,
                 max_open_ask: int = MAX_OPEN_ASK):
        self._lock = threading.RLock()
        self._cards: dict[str, dict] = {}
        self._by_key: dict[tuple, str] = {}
        self._dismissed: list[tuple] = []      # (kind, grounding, title, ask_text) of dismissed cards
        self._seq = 0
        self.version = 0
        self.audit: list[dict] = audit if audit is not None else []
        self.grounding_check = grounding_check
        self.turn_lookup = turn_lookup
        self.clock = clock or (lambda: 0.0)
        self.state_version = state_version or (lambda: 0)
        self._log = log
        self._logbuf: list[tuple[str, str]] = []
        self.max_open_ask = max_open_ask

    # ------------------------------------------------------------------ internals
    def _now(self) -> float:
        try:
            return float(self.clock())
        except Exception:  # noqa: BLE001
            return 0.0

    def _sv(self) -> int:
        try:
            return int(self.state_version())
        except Exception:  # noqa: BLE001
            return 0

    def _emit(self, kind: str, text: str) -> None:
        """Buffered: flushed by _flush() after the store lock is released, so the log callback (which takes the
        consultation lock) never runs under the store lock (no lock-order deadlock with callers)."""
        if self._log is not None:
            self._logbuf.append((kind, text))

    def _flush(self) -> None:
        with self._lock:
            buf, self._logbuf = self._logbuf, []
        for kind, text in buf:
            try:
                self._log(kind, text)
            except Exception:  # noqa: BLE001
                pass

    def _bump(self) -> None:
        self.version += 1

    def _new_id(self) -> str:
        self._seq += 1
        return f"c{self._seq:03d}"

    def _audit(self, card: dict | None, action: str, reason: str | None = None, user: str = "system",
               t_min: float | None = None, rule_id: str | None = None, extra: dict | None = None) -> None:
        entry = {
            "card_id": card["id"] if card else None,
            "rule_id": rule_id if rule_id is not None else (
                ",".join(card.get("rule_ids") or []) or None if card else None),
            "grounding": card.get("grounding") if card else (extra or {}).get("grounding"),
            "kind": card.get("kind") if card else (extra or {}).get("kind"),
            "severity": card.get("severity") if card else (extra or {}).get("severity"),
            "title": card.get("title") if card else (extra or {}).get("title"),
            "source": card.get("source") if card else (extra or {}).get("source"),
            "action": action,
            "reason": reason,
            "user": user,
            "t_min": self._now() if t_min is None else t_min,
            "state_version": self._sv(),
            "evidence_utts": [e.get("utt") for e in (card.get("evidence") or [])] if card else [],
        }
        self.audit.append(entry)

    @staticmethod
    def _public(card: dict) -> dict:
        return copy.deepcopy({k: v for k, v in card.items() if not k.startswith("_")})

    def _open_ask_count(self) -> int:
        return sum(1 for c in self._cards.values() if c["kind"] == "ask" and c["status"] == "open")

    def _is_dismissed(self, kind: str, grounding: str, title: str, ask_text: str | None) -> bool:
        for k, g, t, q in self._dismissed:
            if k != kind:
                continue
            if g == grounding and norm_text(t) == norm_text(title):
                return True
            if _similar(t, title) or (ask_text and q and _similar(q, ask_text)):
                return True
        return False

    def _find_duplicate(self, kind: str, grounding: str, title: str, ask_text: str | None) -> dict | None:
        key = (kind, grounding, norm_text(title))
        cid = self._by_key.get(key)
        if cid is not None:
            return self._cards[cid]
        for c in self._cards.values():
            if c["kind"] != kind or c["status"] in ("dismissed", "resolved"):
                continue
            # one open agent/fallback ask or missed card per checklist item, however the title is worded
            # ("BP not recorded" vs "No blood pressure recorded"); observations may share an utterance
            # Checklist ids are snake_case (bp, troponin, ask_pain_radiation); idiom ids (npi-005) and rule ids
            # (ALG-PEN-01) may back several different questions, so they keep the title/question similarity test.
            if (kind in ("ask", "missed") and _is_checklist_id(grounding) and c["grounding"] == grounding
                    and c.get("source") != "rules"):
                return c
            if c["grounding"] == grounding and _similar(c["title"], title):
                return c
            if ask_text and c.get("ask_text") and _similar(c["ask_text"], ask_text):
                return c
        return None

    def _clean_evidence(self, evidence) -> list[dict]:
        if isinstance(evidence, (str, dict)):
            evidence = [evidence]
        out = []
        for ev in evidence or []:
            if isinstance(ev, str):
                ev = {"utt": ev.strip()}
            if not isinstance(ev, dict):
                continue
            utt = str(ev.get("utt") or "").strip()
            if not utt:
                continue
            item = {"utt": utt, "t_min": ev.get("t_min"), "quote": ev.get("quote") or ""}
            if self.turn_lookup is not None:
                turn = self.turn_lookup(utt)
                if turn is None:
                    continue           # cites an utterance that does not exist: drop it
                if item["t_min"] is None:
                    item["t_min"] = getattr(turn, "t_min", None)
                if not item["quote"]:
                    item["quote"] = (getattr(turn, "english", "") or getattr(turn, "text", ""))[:200]
            out.append(item)
        return _merge_evidence(out)

    def _grounding_ok(self, kind: str, grounding: str) -> bool:
        if not grounding:
            return False
        if kind == "observation" and self.turn_lookup is not None and self.turn_lookup(grounding) is not None:
            return True
        if self.grounding_check is None:
            return True
        try:
            return bool(self.grounding_check(kind, grounding))
        except Exception:  # noqa: BLE001
            return False

    def _active_rule_ids(self) -> set[str]:
        out: set[str] = set()
        for c in self._cards.values():
            if c["source"] == "rules" and c["status"] not in ("resolved",):
                out.update(c.get("rule_ids") or [])
        return out

    # ------------------------------------------------------------------ agent / lexicon / fallback cards
    def post(self, kind: str, title: str, body: str, evidence: list[dict], grounding: str, severity: str = "caution",
             ask_text: str | None = None, source: str = "agent", t_min: float = 0.0, **extra) -> str:
        """Returns the new card id, "duplicate", or "rejected: <why>". Never raises."""
        kind = (kind or "").strip().lower()
        grounding = (grounding or "").strip()
        ev = self._clean_evidence(evidence)            # callbacks run outside the store lock
        grounding_ok = self._grounding_ok(kind, grounding)
        try:
            with self._lock:
                return self._post(kind, title, body, ev, grounding, grounding_ok, severity, ask_text, source,
                                  t_min, extra)
        finally:
            self._flush()

    def _post(self, kind, title, body, ev, grounding, grounding_ok, severity, ask_text, source, t_min, extra) -> str:
        source = (source or "agent").strip().lower()
        severity = (severity or "caution").strip().lower()
        title = (title or "").strip()
        body = (body or "").strip()
        ask_text = (ask_text or "").strip() or None
        why = None
        if source not in KINDS_BY_SOURCE:
            why = f"unknown source '{source}'"
        elif kind not in KINDS_BY_SOURCE[source]:
            why = f"kind '{kind}' not allowed for source '{source}' (allowed: {', '.join(KINDS_BY_SOURCE[source])})"
        elif severity not in SEVERITIES:
            why = f"severity must be one of {', '.join(SEVERITIES)}"
        elif severity == "critical" and source != "rules":
            why = "only the rule engine can raise critical alerts (use caution)"
        elif not title:
            why = "title is required"
        elif source in ("agent", "fallback") and not ev:
            why = "evidence must cite at least one existing utterance id"
        elif not grounding_ok:
            why = (f"grounding '{grounding}' not found (use a fired rule id, an idiom id, an open checklist id"
                   + (", or an utterance id" if kind == "observation" else "") + ")")
        elif kind == "ask" and not ask_text:
            if title.endswith("?"):
                ask_text = title
            else:
                why = "ask cards need ask_text: one plain English question for the patient"
        if why is None and source != "rules" and kind == "missed" and grounding in self._active_rule_ids():
            return "duplicate"     # already on screen as a rule card
        if why is None and self._is_dismissed(kind, grounding, title, ask_text):
            why = "the doctor dismissed this card earlier; do not repeat it"
        if why is None:
            dup = self._find_duplicate(kind, grounding, title, ask_text)
            if dup is not None:
                if source == "lexicon" and dup["status"] == "open":
                    merged = _merge_evidence(dup["evidence"], ev)
                    if len(merged) != len(dup["evidence"]):
                        dup["evidence"] = merged
                        dup["updated_t_min"] = t_min
                        self._bump()
                return "duplicate"
        if why is None and kind == "ask" and self._open_ask_count() >= self.max_open_ask:
            why = f"ask-card cap reached ({self.max_open_ask} open); wait for the doctor"
        if why is not None:
            self._audit(None, "rejected", reason=why, user=source, t_min=t_min,
                        extra={"grounding": grounding, "kind": kind, "severity": severity, "title": title,
                               "source": source})
            self._emit("card", f"✗ rejected {kind} card '{title[:60]}': {why}")
            self._bump()
            return f"rejected: {why}"
        cid = self._new_id()
        card = {
            "id": cid, "kind": kind, "severity": severity, "title": title, "body": body,
            "evidence": ev, "grounding": grounding, "items": [], "ask_text": ask_text,
            "status": "open", "source": source, "t_min": t_min, "updated_t_min": t_min,
            "rule_ids": [], "actions": [],
        }
        for k, v in extra.items():
            if k not in card:
                card[k] = v
        self._cards[cid] = card
        self._by_key[(kind, grounding, norm_text(title))] = cid
        self._audit(card, "shown", user=source, t_min=t_min)
        self._emit("card", f"+ {severity} {kind} card {cid}: {title[:80]} [{grounding}]")
        self._bump()
        return cid

    # ------------------------------------------------------------------ rule cards
    @staticmethod
    def _item(f: dict) -> dict:
        return {
            "rule_id": f.get("rule_id"), "severity": f.get("severity", "caution"), "message": f.get("message", ""),
            "rationale": f.get("rationale", ""), "source_urls": list(f.get("source_urls") or []),
            "evidence": list(f.get("evidence") or []), "fire_on": f.get("fire_on"), "family": f.get("family"),
            "key": f.get("key") or f.get("rule_id"), "verification": f.get("verification"),
        }

    def _rule_content(self, ck: tuple, hits: list[dict]) -> dict:
        items = sorted((self._item(f) for f in hits),
                       key=lambda i: (-SEV_RANK.get(i["severity"], 0), str(i["rule_id"])))
        sev = max((i["severity"] for i in items), key=lambda s: SEV_RANK.get(s, 0))
        evidence = _merge_evidence(*[i["evidence"] for i in items])
        urls = list(dict.fromkeys(u for i in items for u in i["source_urls"]))
        if ck[0] == "group":
            g = ck[1]
            title = GROUP_TITLES.get(g) or g.replace("_", " ").capitalize()
            body = "\n".join(f"{i['rule_id']}: {i['message']}" for i in items)
            grounding = g
            kind = "missed"
        else:
            i = items[0]
            fam = i.get("family") or ""
            title = f"{FAMILY_TITLES.get(fam, 'Safety alert')} · {i['rule_id']}"
            body = i["message"]
            grounding = i["rule_id"]
            kind = "missed" if fam == "missing_workup" else "safety"
        return {"kind": kind, "severity": sev, "title": title, "body": body, "evidence": evidence,
                "grounding": grounding, "items": items, "rule_ids": [i["rule_id"] for i in items],
                "source_urls": urls, "rationale": "\n".join(dict.fromkeys(i["rationale"] for i in items if i["rationale"]))}

    def _upsert_rule_cards(self, fired: list[dict], t_min: float, resolve_missing: bool) -> list[str]:
        changed: list[str] = []
        buckets: dict[tuple, list[dict]] = {}
        for f in fired or []:
            if not isinstance(f, dict) or not f.get("rule_id"):
                continue
            g = group_of(f)
            ck = ("group", g) if g else ("rule", str(f.get("key") or f["rule_id"]))
            buckets.setdefault(ck, []).append(f)
        for ck, hits in buckets.items():
            content = self._rule_content(ck, hits)
            rkey = ("rules",) + ck
            cid = self._by_key.get(rkey)
            if cid is None:
                cid = self._new_id()
                card = {"id": cid, "status": "open", "source": "rules", "ask_text": None, "t_min": t_min,
                        "updated_t_min": t_min, "actions": [], "_item_keys_at_action": None, **content}
                self._cards[cid] = card
                self._by_key[rkey] = cid
                self._audit(card, "shown", user="rules", t_min=t_min)
                self._emit("card", f"+ {card['severity']} {card['kind']} card {cid}: {card['title']} "
                                   f"[{', '.join(card['rule_ids'])}]")
                changed.append(cid)
                continue
            card = self._cards[cid]
            old_keys = {i["key"] for i in card["items"]}
            new_keys = {i["key"] for i in content["items"]}
            old_sev = card["severity"]
            differs = (old_keys != new_keys or old_sev != content["severity"]
                       or card["body"] != content["body"] or len(card["evidence"]) != len(content["evidence"]))
            if card["status"] == "resolved":
                card.update(content)
                card["status"] = "open"
                card["updated_t_min"] = t_min
                self._audit(card, "reopened", reason="rule fires again", user="rules", t_min=t_min)
                self._emit("card", f"↺ reopened {cid}: {card['title']}")
                changed.append(cid)
                continue
            if not differs:
                continue
            card.update(content)
            card["updated_t_min"] = t_min
            acted = card.get("_item_keys_at_action")
            fresh = new_keys - set(acted or old_keys)
            if card["status"] in ("acknowledged", "overridden", "accepted") and fresh:
                card["status"] = "open"
                self._audit(card, "reopened", reason=f"new rule hits: {', '.join(sorted(fresh))}", user="rules",
                            t_min=t_min)
            elif card["status"] == "dismissed" and fresh and content["severity"] == "critical" \
                    and any(i["severity"] == "critical" and i["key"] in fresh for i in content["items"]):
                card["status"] = "open"
                self._audit(card, "reopened", reason="new critical rule hit after dismissal", user="rules",
                            t_min=t_min)
            if SEV_RANK.get(content["severity"], 0) > SEV_RANK.get(old_sev, 0):
                self._audit(card, "escalated", reason=f"{old_sev} -> {content['severity']}", user="rules",
                            t_min=t_min)
                self._emit("card", f"▲ {cid} {card['title']}: {old_sev} → {content['severity']} "
                                   f"[{', '.join(card['rule_ids'])}]")
            elif old_keys != new_keys:          # body-only changes (e.g. "first mentioned 11 min ago") stay quiet
                self._emit("card", f"~ updated {cid}: {card['title']} [{', '.join(card['rule_ids'])}]")
            changed.append(cid)
        if resolve_missing:
            live = {("rules",) + ck for ck in buckets}
            for rkey, cid in list(self._by_key.items()):
                if rkey[0] != "rules" or rkey in live:
                    continue
                card = self._cards[cid]
                if card["status"] in ("resolved", "dismissed"):
                    continue
                card["status"] = "resolved"
                card["updated_t_min"] = t_min
                self._audit(card, "resolved", reason="rule no longer fires", user="rules", t_min=t_min)
                self._emit("card", f"✓ resolved {cid}: {card['title']}")
                changed.append(cid)
        if changed:
            self._bump()
        return changed

    def sync_rules(self, fired: list[dict], t_min: float) -> list[str]:
        """Make rule cards match `fired` (ALL rules firing now): create/update, group WORK-CHEST-*, resolve cards
        whose rules no longer fire. Returns ids of created/changed/resolved cards."""
        try:
            with self._lock:
                return self._upsert_rule_cards(fired, t_min, resolve_missing=True)
        finally:
            self._flush()

    def add_rule_hits(self, fired: list[dict], t_min: float) -> list[str]:
        """Create/update rule cards without resolving anything (prescription gate)."""
        try:
            with self._lock:
                return self._upsert_rule_cards(fired, t_min, resolve_missing=False)
        finally:
            self._flush()

    # ------------------------------------------------------------------ doctor actions
    def act(self, card_id: str, action: str, reason: str | None = None, user: str = "doctor") -> dict:
        """Doctor action (acknowledge|override|dismiss|accept|ask|wrong_fact) -> updated card dict with "ok"."""
        try:
            return self._act(card_id, (action or "").strip().lower(), reason, user)
        finally:
            self._flush()

    def _act(self, card_id: str, action: str, reason: str | None, user: str) -> dict:
        with self._lock:
            card = self._cards.get(card_id)
            if card is None:
                return {"ok": False, "error": f"unknown card {card_id}"}
            if action not in ACTIONS:
                return {"ok": False, "error": f"unknown action {action}; one of {', '.join(ACTIONS)}"}
            if action == "override" and not reason:
                reason = "no reason given"
            if action == "wrong_fact" and not reason:
                reason = "extraction error (wrong fact)"
            t = self._now()
            card["status"] = ACTIONS[action]
            card["updated_t_min"] = t
            card["actions"].append({"action": action, "reason": reason, "user": user, "t_min": t})
            if card["source"] == "rules":
                card["_item_keys_at_action"] = [i["key"] for i in card["items"]]
            if action == "dismiss":
                self._dismissed.append((card["kind"], card["grounding"], card["title"], card.get("ask_text")))
            self._audit(card, action, reason=reason, user=user, t_min=t)
            self._emit("card", f"{user} {action} {card_id}: {card['title'][:60]}" + (f" ({reason})" if reason else ""))
            self._bump()
            out = self._public(card)
            out["ok"] = True
            return out

    def resolve(self, card_id: str, reason: str, t_min: float | None = None) -> bool:
        """Mark an open non-rule card resolved (e.g. its checklist item is now done). Rule cards resolve via
        sync_rules only."""
        try:
            return self._resolve(card_id, reason, t_min)
        finally:
            self._flush()

    def _resolve(self, card_id: str, reason: str, t_min: float | None) -> bool:
        with self._lock:
            card = self._cards.get(card_id)
            if card is None or card["status"] != "open" or card["source"] == "rules":
                return False
            t = self._now() if t_min is None else t_min
            card["status"] = "resolved"
            card["updated_t_min"] = t
            self._audit(card, "resolved", reason=reason, user="system", t_min=t)
            self._emit("card", f"✓ resolved {card_id}: {card['title'][:60]} ({reason})")
            self._bump()
            return True

    # ------------------------------------------------------------------ views
    def get(self, card_id: str) -> dict | None:
        with self._lock:
            c = self._cards.get(card_id)
            return self._public(c) if c else None

    def open_cards(self) -> list[dict]:
        """Cards awaiting the doctor (status "open"), critical first, then newest first."""
        with self._lock:
            cards = [self._public(c) for c in self._cards.values() if c["status"] == "open"]
        cards.sort(key=lambda c: (-SEV_RANK.get(c["severity"], 0), -(c.get("updated_t_min") or 0)))
        return cards

    def active_cards(self) -> list[dict]:
        """Everything still relevant on screen: not dismissed and not resolved."""
        with self._lock:
            cards = [self._public(c) for c in self._cards.values() if c["status"] not in ("dismissed", "resolved")]
        cards.sort(key=lambda c: (-SEV_RANK.get(c["severity"], 0), -(c.get("updated_t_min") or 0)))
        return cards

    def all_cards(self) -> list[dict]:
        with self._lock:
            return [self._public(c) for c in self._cards.values()]

    def dismissed_titles(self) -> list[str]:
        with self._lock:
            return [t for _k, _g, t, _q in self._dismissed]
