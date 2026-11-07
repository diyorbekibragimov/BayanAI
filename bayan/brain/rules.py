"""Bayan AI · deterministic rule engine over data/safety_rules.json (docs/05 §2.5).

Trigger language: all / any / none, exists_in / none_in over a state collection (with a `where` that may
itself be nested logic), and fact comparisons eq, neq, in, not_in, gt, gte, lt, lte, exists, not_exists,
contains_any. Missing data makes a comparison false (except not_exists), so a rule never fires on absent
data; none_in is designed to fire when, e.g., an investigation is missing. `escalate_to_critical_if`
raises severity. `elapsed_min_since.first_match` = now - earliest first_mention_min among the items matched
by the rule's exists_in clauses. No LLM anywhere in this file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .merge import combine_same_drug, normalise_med
from .state import fmt_t
from .vocab import LEXICON_PATH, RULES_PATH, classes_of, literal_gloss, normalise_drug

_MISSING = object()
GLOBAL_ROOTS = {"patient", "vitals", "disposition", "elapsed_min_since", "questions_asked"}
COLLECTIONS = {"allergies", "current_meds", "prescribed_meds", "all_meds", "symptoms", "investigations",
               "interventions", "assessments", "idiom_hits"}
MED_COLLS = {"prescribed_meds", "current_meds", "all_meds"}
ALIAS = {"allergies": "allergy", "prescribed_meds": "rx", "current_meds": "rx", "all_meds": "rx",
         "symptoms": "symptom", "idiom_hits": "idiom", "investigations": "inv", "interventions": "intervention",
         "assessments": "assessment"}
OPS = {"eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "exists", "not_exists", "contains_any"}
SEVERITY_RANK = {"info": 0, "caution": 1, "critical": 2}
# Which med clause {rx.*} refers to when a rule has several (default: the last one).
RX_CLAUSE = {"DDI-PDE5-01": 0, "DDI-SERO-01": 0}
# Fallback text for a placeholder whose value is not recorded (a rendered message never contains "{").
_FIELD_DEFAULTS = {
    "drug": "the prescribed drug", "substance": "the recorded allergen", "code": "a red-flag symptom",
    "evidence": "quote not captured", "duration_days": "an unrecorded number of", "route": "an unrecorded route",
    "travel_country": "country not recorded", "romanized": "an idiom", "literal_en": "meaning not recorded",
}


# ----------------------------------------------------------------------------- comparisons
def _ns(v: Any) -> Any:
    """Normalise a string for comparison: lowercase, spaces/hyphens -> underscores."""
    if isinstance(v, str):
        return re.sub(r"[\s\-]+", "_", v.strip().lower())
    return v


def _is_missing(v: Any) -> bool:
    return v is _MISSING or v is None


def _is_absent(v: Any) -> bool:
    """For exists/not_exists: None, empty, or the literal 'unknown' all count as not captured."""
    if _is_missing(v):
        return True
    if isinstance(v, str):
        return v.strip() == "" or v.strip().lower() == "unknown"
    if isinstance(v, (list, tuple, set, dict)):
        return len(v) == 0
    return False


def _to_num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def _eq(a: Any, b: Any) -> bool:
    if isinstance(b, bool) or isinstance(a, bool):
        if isinstance(a, str):
            a = {"true": True, "yes": True, "false": False, "no": False}.get(a.strip().lower(), a)
        if isinstance(b, str):
            b = {"true": True, "yes": True, "false": False, "no": False}.get(b.strip().lower(), b)
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    na, nb = _to_num(a), _to_num(b)
    if na is not None and nb is not None and not isinstance(a, str) and not isinstance(b, str):
        return na == nb
    return _ns(a) == _ns(b)


def compare(op: str, actual: Any, value: Any) -> bool:
    if op == "exists":
        return not _is_absent(actual)
    if op == "not_exists":
        return _is_absent(actual)
    if _is_missing(actual):
        return False
    vals = value if isinstance(value, (list, tuple, set)) else [value]
    if isinstance(actual, (list, tuple, set)):
        acts = list(actual)
        if op == "eq":
            return any(_eq(a, value) for a in acts)
        if op == "neq":
            return bool(acts) and not any(_eq(a, value) for a in acts)
        if op in ("in", "contains_any"):
            return any(_eq(a, v) for a in acts for v in vals)
        if op == "not_in":
            return bool(acts) and not any(_eq(a, v) for a in acts for v in vals)
        return False  # numeric comparison on a list
    if op == "eq":
        return _eq(actual, value)
    if op == "neq":
        return not _eq(actual, value)
    if op in ("in", "contains_any"):
        return any(_eq(actual, v) for v in vals)
    if op == "not_in":
        return not any(_eq(actual, v) for v in vals)
    a, b = _to_num(actual), _to_num(value)
    if a is None or b is None:
        return False
    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}.get(op, False)


# ----------------------------------------------------------------------------- formatting
def _fmt_num(v: Any) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        f = float(v)
        if f.is_integer():
            return str(int(f))
        return f"{f:.2f}".rstrip("0").rstrip(".")
    return str(v)


def _fmt_ev(ev: list[dict] | None) -> str | None:
    ev = [e for e in (ev or []) if e.get("quote") or e.get("utt")]
    if not ev:
        return None
    e = min(ev, key=lambda x: x.get("t_min") if isinstance(x.get("t_min"), (int, float)) else 1e9)
    quote = str(e.get("quote") or "").strip()
    if len(quote) > 90:
        quote = quote[:87].rstrip() + "…"
    when = fmt_t(e["t_min"]) if isinstance(e.get("t_min"), (int, float)) else None
    if quote:
        return f"“{quote}”, {when}" if when else f"“{quote}”"
    return f"{e.get('utt')}, {when}" if when else str(e.get("utt"))


# ----------------------------------------------------------------------------- evaluation context
class _Ctx:
    """One evaluation of one state: normalised collection views + match cache."""

    def __init__(self, engine: "RuleEngine", state: dict, now_min: float | None, candidate_ids: set[int] = frozenset()):
        self.engine = engine
        self.state = state or {}
        self.now = now_min
        self.patient = self.state.get("patient") or {}
        self.candidate_ids = candidate_ids
        self._colls: dict[str, list[dict]] = {}
        self.cache: dict[int, list[dict]] = {}

    # -- collections
    def coll(self, name: str) -> list[dict]:
        if name not in self._colls:
            if name == "all_meds":
                self._colls[name] = self.coll("current_meds") + self.coll("prescribed_meds")
            else:
                raw = self.state.get(name) or []
                self._colls[name] = [self._view(name, it) for it in raw if isinstance(it, dict)]
        return self._colls[name]

    def _view(self, coll: str, item: dict) -> dict:
        v = dict(item)
        v["_src"] = item
        v["_coll"] = coll
        v["_candidate"] = id(item) in self.candidate_ids
        if coll in MED_COLLS:
            drug = normalise_drug(item.get("drug") or item.get("name") or "")
            v["drug"] = drug
            cls = item.get("class")
            cls = list(cls) if isinstance(cls, (list, tuple)) else ([cls] if cls else [])
            for c in classes_of(drug):
                if c not in cls:
                    cls.append(c)
            v["class"] = cls
            names = [drug]
            dose = _to_num(item.get("dose_mg"))
            freq = _to_num(item.get("frequency_per_day"))
            if drug == "aspirin" and dose is not None and dose <= 150:
                names.append("aspirin_low_dose")
            v["_drug_names"] = names
            if v.get("daily_dose_mg") is None and dose is not None and freq is not None:
                v["daily_dose_mg"] = dose * freq
            if v.get("dose_mcg") is None and dose is not None:
                v["dose_mcg"] = dose * 1000
            if isinstance(v.get("route"), str):
                v["route"] = v["route"].strip().lower()
            w = _to_num(self.patient.get("weight_kg"))
            daily = _to_num(v.get("daily_dose_mg"))
            if v.get("daily_dose_mg_per_kg") is None and w and daily is not None:
                v["daily_dose_mg_per_kg"] = round(daily / w, 2)
            if v.get("daily_puffs") is None:
                puffs = _to_num(item.get("puffs") or item.get("puffs_per_dose"))
                if puffs is not None and freq is not None:
                    v["daily_puffs"] = puffs * freq
            if v.get("daily_clavulanate_mg") is None and drug == "co-amoxiclav":
                clav = _to_num(item.get("clavulanate_mg"))
                if clav is not None and freq is not None:
                    v["daily_clavulanate_mg"] = clav * freq
        elif coll == "allergies":
            sub = item.get("substance") or ""
            cls = item.get("class")
            cls = list(cls) if isinstance(cls, (list, tuple)) else ([cls] if cls else [])
            for c in list(cls):
                for c2 in classes_of(str(c)):
                    if c2 not in cls:
                        cls.append(c2)
            for c in classes_of(sub):
                if c not in cls:
                    cls.append(c)
            v["class"] = cls
            if sub:
                v["substance"] = normalise_drug(sub) or sub
        elif coll == "idiom_hits":
            if not v.get("red_flag_tags"):
                entry = self.engine.idiom(v.get("id"))
                v["red_flag_tags"] = list((entry or {}).get("red_flag_tags") or [])
        elif coll == "symptoms":
            if v.get("first_mention_min") is None:
                ts = [e.get("t_min") for e in v.get("evidence") or [] if isinstance(e.get("t_min"), (int, float))]
                if ts:
                    v["first_mention_min"] = min(ts)
        return v

    # -- facts
    def global_fact(self, fact: str, rc: "_RuleCtx | None") -> Any:
        parts = fact.split(".")
        if parts[0] == "elapsed_min_since":
            if self.now is None:
                return _MISSING
            if len(parts) >= 2 and parts[1] == "first_match":
                return rc.elapsed_first_match() if rc else _MISSING
            if len(parts) >= 3 and parts[1] == "symptom":
                code = _ns(".".join(parts[2:]))
                ts = [s.get("first_mention_min") for s in self.coll("symptoms")
                      if _ns(s.get("code")) == code and isinstance(s.get("first_mention_min"), (int, float))]
                return self.now - min(ts) if ts else _MISSING
            return _MISSING
        cur: Any = self.state
        for p in parts:
            if not isinstance(cur, dict) or p not in cur:
                return _MISSING
            cur = cur[p]
        return cur

    def item_fact(self, item: dict, fact: str, rc: "_RuleCtx | None") -> Any:
        if fact == "drug" and "_drug_names" in item:
            return item["_drug_names"]
        if fact in item:
            return item[fact]
        if "." in fact:
            root = fact.split(".", 1)[0]
            if root in item:
                cur: Any = item
                for p in fact.split("."):
                    if not isinstance(cur, dict) or p not in cur:
                        return _MISSING
                    cur = cur[p]
                return cur
            if root in GLOBAL_ROOTS:
                return self.global_fact(fact, rc)
        return _MISSING


class _RuleCtx:
    """Bindings for one rule evaluation."""

    def __init__(self, ctx: _Ctx, rule: dict):
        self.ctx = ctx
        self.rule = rule
        self.binds: list[tuple[str, list[dict]]] = []   # (collection, matched items) per exists_in clause
        self.extra_binds: list[tuple[str, list[dict]]] = []
        self.escalating = False
        self._elapsed: Any = None

    def bind(self, coll: str, matched: list[dict]) -> None:
        (self.extra_binds if self.escalating else self.binds).append((coll, matched))

    def elapsed_first_match(self) -> Any:
        if self._elapsed is None:
            items: list[dict] = []
            for node in _exists_nodes(self.rule.get("trigger")):
                items.extend(self.ctx.engine._matches(node, self.ctx, self))
            ts = [it.get("first_mention_min") for it in items if isinstance(it.get("first_mention_min"), (int, float))]
            if not ts:
                ts = [e.get("t_min") for it in items for e in it.get("evidence") or []
                      if isinstance(e.get("t_min"), (int, float))]
            self._elapsed = (self.ctx.now - min(ts)) if ts and self.ctx.now is not None else _MISSING
        return self._elapsed


def _exists_nodes(node: Any):
    """exists_in nodes of a trigger, outside `where` and outside `none`."""
    if isinstance(node, dict):
        if "exists_in" in node:
            yield node
            return
        for k in ("all", "any"):
            for ch in node.get(k, []) or []:
                yield from _exists_nodes(ch)


# ----------------------------------------------------------------------------- engine
class RuleEngine:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else RULES_PATH
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.meta: dict = data.get("meta", {})
        self.rules: list[dict] = data["rules"]
        self.by_id: dict[str, dict] = {r["id"]: r for r in self.rules}
        self.unevaluable: list[tuple[str, str]] = []
        for r in self.rules:
            for where in ("trigger", "escalate_to_critical_if"):
                if r.get(where) is not None:
                    self._validate(r[where], r["id"], inside_where=False)
        self._lexicon: dict[str, dict] | None = None

    # -- lexicon (for {idiom.*} placeholders and missing tags)
    def idiom(self, idiom_id: str | None) -> dict | None:
        if self._lexicon is None:
            try:
                with open(LEXICON_PATH, encoding="utf-8") as f:
                    self._lexicon = {e["id"]: e for e in json.load(f).get("entries", [])}
            except OSError:
                self._lexicon = {}
        return self._lexicon.get(idiom_id or "")

    def _validate(self, node: Any, rid: str, inside_where: bool) -> None:
        if not isinstance(node, dict):
            self.unevaluable.append((rid, f"non-object node {node!r}"))
            return
        if any(k in node for k in ("all", "any", "none")):
            for k in ("all", "any", "none"):
                for ch in node.get(k, []) or []:
                    self._validate(ch, rid, inside_where)
            return
        q = node.get("exists_in") or node.get("none_in")
        if q:
            if q not in COLLECTIONS:
                self.unevaluable.append((rid, f"unknown collection {q}"))
            if node.get("where") is not None:
                self._validate(node["where"], rid, True)
            return
        if "fact" in node:
            if node.get("op") not in OPS:
                self.unevaluable.append((rid, f"unknown op {node.get('op')}"))
            root = node["fact"].split(".", 1)[0]
            if not inside_where and root not in GLOBAL_ROOTS:
                self.unevaluable.append((rid, f"unknown global fact {node['fact']}"))
            return
        self.unevaluable.append((rid, f"unknown node {sorted(node)}"))

    # -- core recursion
    def _matches(self, node: dict, ctx: _Ctx, rc: _RuleCtx | None) -> list[dict]:
        key = id(node)
        if key not in ctx.cache:
            items = ctx.coll(node.get("exists_in") or node.get("none_in"))
            where = node.get("where")
            ctx.cache[key] = [it for it in items if where is None or self._eval(where, ctx, rc, it, record=False)]
        return ctx.cache[key]

    def _eval(self, node: Any, ctx: _Ctx, rc: _RuleCtx | None, item: dict | None = None, record: bool = True) -> bool:
        if not isinstance(node, dict):
            return False
        if "all" in node:
            return all(self._eval(ch, ctx, rc, item, record) for ch in node["all"])
        if "any" in node:
            results = [self._eval(ch, ctx, rc, item, record) for ch in node["any"]]   # no short-circuit: bind all
            return any(results)
        if "none" in node:
            return not any(self._eval(ch, ctx, rc, item, False) for ch in node["none"])
        if "exists_in" in node:
            matched = self._matches(node, ctx, rc)
            if matched and record and rc is not None:
                rc.bind(node["exists_in"], matched)
            return bool(matched)
        if "none_in" in node:
            return not self._matches(node, ctx, rc)
        if "fact" in node:
            fact = node["fact"]
            actual = ctx.item_fact(item, fact, rc) if item is not None else ctx.global_fact(fact, rc)
            return compare(node.get("op"), actual, node.get("value"))
        return False

    # -- public API
    def evaluate(self, state: dict, now_min: float | None, fire_on: str | set | None = None) -> list[dict]:
        """ALL rules whose trigger holds now (optionally only those with the given fire_on value(s))."""
        ctx = _Ctx(self, state, now_min)
        return self._run(ctx, fire_on)

    def _run(self, ctx: _Ctx, fire_on: str | set | None) -> list[dict]:
        wanted = {fire_on} if isinstance(fire_on, str) else (set(fire_on) if fire_on else None)
        fired = []
        for rule in self.rules:
            if wanted and rule.get("fire_on") not in wanted:
                continue
            rc = _RuleCtx(ctx, rule)
            if self._eval(rule["trigger"], ctx, rc):
                fired.append(self._fire(rule, ctx, rc))
        return fired

    def check_prescription(self, state: dict, candidate_meds: list[dict], now_min: float | None) -> list[dict]:
        """on_prescribe rules that WOULD fire if candidate_meds were added to prescribed_meds and that involve a
        candidate. The state is not mutated. Candidates may be talk-loop items ({"name","dose_mg",
        "frequency_per_day","intent"}); intents other than "prescribe" are ignored."""
        cands = []
        for c in candidate_meds or []:
            if not isinstance(c, dict):
                c = {"drug": c}
            intent = str(c.get("intent") or "prescribe").lower()
            if intent != "prescribe":
                continue
            cands.append(c)
        cands = [m for m in (normalise_med(c) for c in combine_same_drug(cands)) if m["drug"]]
        if not cands:
            return []
        names = {m["drug"] for m in cands}
        new_state = dict(state or {})
        new_state["prescribed_meds"] = [m for m in (state or {}).get("prescribed_meds") or []
                                        if normalise_drug(m.get("drug") or "") not in names] + cands
        ctx = _Ctx(self, new_state, now_min, candidate_ids={id(m) for m in cands})
        out = []
        for f in self._run(ctx, "on_prescribe"):
            if f.pop("_involves_candidate", False):
                out.append(f)
        return out

    # -- fired dict
    def _fire(self, rule: dict, ctx: _Ctx, rc: _RuleCtx) -> dict:
        severity = rule["severity"]
        escalated = False
        esc = rule.get("escalate_to_critical_if")
        if esc is not None:
            rc.escalating = True
            if self._eval(esc, ctx, rc):
                escalated = severity != "critical"
                severity = "critical"
            rc.escalating = False

        chosen: dict[str, dict] = {}
        med_choices: list[dict] = []
        for coll, matched in rc.binds:
            item = self._choose(coll, matched)
            alias = ALIAS.get(coll, coll)
            if coll in MED_COLLS:
                med_choices.append(item)
            else:
                chosen[alias] = item      # several clauses on one collection: the last (most specific) wins
        if med_choices:
            idx = RX_CLAUSE.get(rule["id"], len(med_choices) - 1)
            chosen["rx"] = med_choices[min(idx, len(med_choices) - 1)]

        evidence = self._evidence(rule, ctx, rc, chosen, med_choices)
        message = self._render(rule, ctx, rc, chosen, evidence)
        rid = rule["id"]
        out = {
            "rule_id": rid,
            "family": rule.get("family"),
            "severity": severity,
            "base_severity": rule["severity"],
            "escalated": escalated,
            "message": message,
            "rationale": rule.get("rationale", ""),
            "source_urls": list(rule.get("source_urls") or []),
            "fire_on": rule.get("fire_on"),
            "verification": rule.get("verification"),
            "evidence": evidence,
            "group": _group(rid),
            "key": self._key(rule, chosen, med_choices),
        }
        if ctx.candidate_ids:
            out["_involves_candidate"] = any(it.get("_candidate") for _, m in rc.binds for it in m
                                             if it.get("_coll") in MED_COLLS)
        return out

    @staticmethod
    def _choose(coll: str, matched: list[dict]) -> dict:
        if coll in MED_COLLS:
            for pref in (lambda m: m.get("_candidate"), lambda m: m.get("_coll") == "prescribed_meds"):
                hits = [m for m in matched if pref(m)]
                if hits:
                    return hits[-1]
            return matched[-1]
        if coll == "symptoms":
            return min(matched, key=lambda s: s.get("first_mention_min") if isinstance(
                s.get("first_mention_min"), (int, float)) else 1e9)
        return matched[0]

    @staticmethod
    def _item_evidence(item: dict) -> list[dict]:
        if item.get("_coll") == "idiom_hits":
            ev = list(item.get("evidence") or [])
            if not ev and (item.get("utt") or item.get("matched")):
                ev = [{"utt": item.get("utt"), "t_min": item.get("t_min"), "quote": item.get("matched") or ""}]
            return ev
        return list(item.get("evidence") or [])

    def _evidence(self, rule, ctx, rc, chosen, med_choices) -> list[dict]:
        items = list(chosen.values()) + [m for m in med_choices if m not in chosen.values()]
        for coll, matched in rc.extra_binds:
            it = self._choose(coll, matched)
            if all(it is not x for x in items):
                items.append(it)
        ev: list[dict] = []
        for it in items:
            ev.extend(self._item_evidence(it))
        blob = json.dumps(rule.get("trigger"))
        if "disposition." in blob and (ctx.state.get("disposition") or {}).get("type"):
            ev.extend((ctx.state.get("disposition") or {}).get("evidence") or [])
        by_key: dict[Any, dict] = {}
        for e in ev:
            if not isinstance(e, dict):
                continue
            k = e.get("utt") or ("q", e.get("quote"))
            prev = by_key.get(k)
            if prev is None or len(str(e.get("quote") or "")) > len(str(prev.get("quote") or "")):
                by_key[k] = e      # one evidence item per utterance: keep the fuller quote
        out = list(by_key.values())
        out.sort(key=lambda e: e.get("t_min") if isinstance(e.get("t_min"), (int, float)) else 1e9)
        return out

    def _key(self, rule: dict, chosen: dict, med_choices: list[dict]) -> str:
        rid = rule["id"]
        if med_choices:
            drugs = []
            for m in med_choices:
                if m.get("drug") and m["drug"] not in drugs:
                    drugs.append(m["drug"])
            subject = "+".join(drugs)
            if rule.get("family") == "dose_ceiling":
                rx = chosen.get("rx") or {}
                dose = rx.get("daily_dose_mg") if rx.get("daily_dose_mg") is not None else rx.get("dose_mg")
                if dose is not None:
                    subject += f"|{_fmt_num(dose)}"
            return f"{rid}|{subject}"
        for alias, field in (("allergy", "substance"), ("idiom", "id"), ("symptom", "code")):
            if alias in chosen and chosen[alias].get(field):
                return f"{rid}|{chosen[alias][field]}"
        return rid

    def _placeholder(self, key: str, ctx: _Ctx, rc: _RuleCtx, chosen: dict, evidence: list[dict]) -> str:
        if key == "elapsed":
            e = rc.elapsed_first_match()
            return _fmt_num(max(0, int(round(e)))) if not _is_missing(e) else "more than 10"
        alias, _, field = key.partition(".")
        if alias in GLOBAL_ROOTS:
            v = ctx.global_fact(key, rc)
            if _is_absent(v):
                return _FIELD_DEFAULTS.get(field, "not recorded")
            return _fmt_num(v)
        item = chosen.get(alias)
        if field == "evidence":
            txt = _fmt_ev(self._item_evidence(item)) if item is not None else None
            return txt or _fmt_ev(evidence) or _FIELD_DEFAULTS["evidence"]
        if item is None:
            return _FIELD_DEFAULTS.get(field, "not recorded")
        if alias == "idiom" and field in ("romanized", "literal_en", "native"):
            entry = self.idiom(item.get("id")) or {}
            v = entry.get(field) or item.get("matched")
            if field == "literal_en" and entry.get(field):
                v = literal_gloss(entry[field])      # "'gastric' (English loanword)" -> "gastric"
            return str(v) if v else _FIELD_DEFAULTS.get(field, "not recorded")
        v = item.get(field)
        if field == "dose_raw" and _is_absent(v):
            if item.get("dose_mg") is not None:
                v = f"{_fmt_num(item['dose_mg'])} mg"
        if _is_absent(v):
            return _FIELD_DEFAULTS.get(field, "unrecorded")
        if field == "code":
            return str(v).replace("_", " ")
        return _fmt_num(v)

    def _render(self, rule: dict, ctx: _Ctx, rc: _RuleCtx, chosen: dict, evidence: list[dict]) -> str:
        tpl = rule.get("message_en") or rule["id"]
        parts: list[str] = []
        pos = 0
        for m in re.finditer(r"\{([^{}]*)\}", tpl):
            before = tpl[pos:m.start()]
            parts.append(before)
            val = self._placeholder(m.group(1).strip(), ctx, rc, chosen, evidence)
            sofar = "".join(parts).rstrip()
            if (not sofar or sofar[-1] in ".!?") and val and val[0].isalpha():
                val = val[0].upper() + val[1:]
            parts.append(val)
            pos = m.end()
        parts.append(tpl[pos:])
        return "".join(parts).replace("{", "(").replace("}", ")")


def _group(rule_id: str) -> str | None:
    if rule_id.startswith("WORK-CHEST-"):
        return "chest_pain_workup"
    if rule_id.startswith("WORK-HEAT-") or rule_id.startswith("HEAT-MED-"):
        return "heat_illness"
    return None


_ENGINE: RuleEngine | None = None


def default_engine() -> RuleEngine:
    """Shared engine over the default rules file."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RuleEngine()
    return _ENGINE
