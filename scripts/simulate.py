"""Bayan AI · end-to-end simulation suite: scripted consultations through the real app engine, scored.

Every scenario in scenarios/*.yaml is played as TEXT turns through bayan.consult (the same code path as the live
stage, minus audio): consult.process_text for doctor and patient turns (live translation + prescription gate +
idiom lexicon + background copilot think loop), held-sentence choices (held_else / held_anyway), "Ask" taps,
timer ticks on a scenario clock, then end_visit (wrap-up agent: note, care plan, PDFs) and approve (doctor PDF
re-render). Nothing in bayan/ is modified; the runner only wraps a few functions to measure tokens and to skip the
UX pauses (time.sleep in consult).

    python scripts/simulate.py                         # all scenarios, 4 at a time, default models (gpt-oss-120b)
    python scripts/simulate.py --only alg-01,dose-03   # some ids (prefix match)
    python scripts/simulate.py --lang ne --category allergy
    python scripts/simulate.py --rescore reports/sim/<run-id>   # re-score saved raw results (no LLM calls)
    # another model for the brain (extraction, copilot agent, wrap-up); live translation stays gpt-oss-120b:
    BAYAN_BRAIN_LLM=<model id> BAYAN_BRAIN_PROVIDER=<provider> python scripts/simulate.py --label <name>

Output: reports/sim/<run-id>/results.json (raw + scores), summary.md, pdf/<id>_{doctor,patient}.pdf and
png/<id>_{doctor,patient}_p1.png (page 1 of each PDF, for visual review).
Scenario format and expectation keys: scenarios/README.md.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import copy
import json
import multiprocessing as mp
import os
import re
import shutil
import statistics
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCEN_DIR = ROOT / "scenarios"
REPORTS = ROOT / "reports" / "sim"
SEV = {"info": 0, "caution": 1, "critical": 2}

# Unicode ranges of each patient language's script (native-script presence check in the patient PDF).
SCRIPTS = {
    "devanagari": [(0x0900, 0x097F)], "bengali": [(0x0980, 0x09FF)], "malayalam": [(0x0D00, 0x0D7F)],
    "tamil": [(0x0B80, 0x0BFF)], "telugu": [(0x0C00, 0x0C7F)],
    "arabic": [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "hangul": [(0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F)],
    "japanese": [(0x3040, 0x30FF), (0x4E00, 0x9FFF)], "georgian": [(0x10A0, 0x10FF), (0x1C90, 0x1CBF)],
    "cyrillic": [(0x0400, 0x04FF)], "greek": [(0x0370, 0x03FF)], "thai": [(0x0E00, 0x0E7F)],
}
LANG_SCRIPT = {"ne": "devanagari", "hi": "devanagari", "mr": "devanagari", "bn": "bengali", "ml": "malayalam",
               "ta": "tamil", "te": "telugu", "ur": "arabic", "ar": "arabic", "fa": "arabic", "ko": "hangul",
               "ja": "japanese", "ka": "georgian", "ru": "cyrillic", "uk": "cyrillic", "bg": "cyrillic",
               "el": "greek"}


def _in_script(ch: str, script: str) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in SCRIPTS[script])


def script_count(text: str, script: str) -> int:
    return sum(1 for ch in text if _in_script(ch, script))


# ============================================================================ scenario loading
def load_scenarios() -> list[dict]:
    import yaml
    out = []
    for p in sorted(SCEN_DIR.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else (data.get("scenarios") if isinstance(data, dict) and
                                                      "scenarios" in data else [data])
        for sc in items or []:
            sc = dict(sc)
            sc["_file"] = p.name
            sc.setdefault("category", p.stem)
            sc.setdefault("doctor_lang", "en")
            sc.setdefault("expect", {})
            out.append(sc)
    ids = [s["id"] for s in out]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit(f"duplicate scenario ids: {sorted(dup)}")
    return out


# ============================================================================ prices (HF router, cached per run)
DEFAULT_PRICES = {("openai/gpt-oss-120b", "cerebras"): (0.35, 0.75), ("openai/gpt-oss-120b", "groq"): (0.15, 0.75)}


def fetch_prices(token: str | None) -> dict:
    out = {f"{m}|{p}": list(v) for (m, p), v in DEFAULT_PRICES.items()}
    if not token:
        return out
    try:
        import urllib.request
        req = urllib.request.Request("https://router.huggingface.co/v1/models",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)["data"]
        for m in data:
            for p in m.get("providers") or []:
                pr = p.get("pricing")
                if pr and pr.get("input") is not None:
                    out[f"{m['id']}|{p['provider']}"] = [float(pr["input"]), float(pr.get("output") or 0)]
    except Exception as e:  # noqa: BLE001
        print(f"[prices] router lookup failed ({e}); using defaults", flush=True)
    return out


def price_of(prices: dict, model: str, provider: str) -> tuple[float, float]:
    v = prices.get(f"{model}|{provider}")
    if v:
        return v[0], v[1]
    try:   # not in the router listing: the app's own table (bayan.brain.llm.MODEL_PRICES)
        from bayan.brain import llm
        return llm.price(model, provider)
    except Exception:  # noqa: BLE001
        return 0.35, 0.75


# ============================================================================ worker: one consultation
_W: dict = {}


def _worker_init(env: dict) -> None:
    os.environ.update(env)
    sys.path.insert(0, str(ROOT))
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    from bayan import consult, talk
    from bayan.brain import agentkit, llm

    class _FastTime:
        """consult's clock without UX pauses (time.sleep is a no-op; time.time stays real)."""

        def __getattr__(self, name):
            return getattr(time, name)

        @staticmethod
        def sleep(_s):
            return None

    consult.time = _FastTime()
    talk.speak = lambda *a, **k: None
    talk.speak_chunks = lambda *a, **k: iter(())
    tr_log: list = []
    orig_translate = talk.translate

    def translate(text, role, src, tgt, context=None, hint=""):
        t0 = time.time()
        out = orig_translate(text, role, src, tgt, context=context, hint=hint)
        tr_log.append({"role": role, "src": src, "tgt": tgt, "text": text[:200], "s": round(time.time() - t0, 2),
                       "drugs": out.get("drugs"), "allergies": out.get("allergies"), "tests": out.get("tests")})
        return out

    talk.translate = translate
    _W["tr_log"] = tr_log

    acc = {"chat": {}, "agent": {}}
    lock = threading.Lock()
    orig_record = llm._record

    def record(out, provider, model=None):
        orig_record(out, provider, model)
        u = getattr(out, "usage", None)
        if u is None:
            return
        with lock:   # keyed "model|provider": the brain model may differ from the translation model
            d = acc["chat"].setdefault(f"{model or llm.LLM_MODEL}|{provider}", [0, 0, 0])
            d[0] += int(getattr(u, "prompt_tokens", 0) or 0)
            d[1] += int(getattr(u, "completion_tokens", 0) or 0)
            d[2] += 1

    orig_run = agentkit.run_agent

    def run_agent(*a, **kw):
        res = orig_run(*a, **kw)
        label = kw.get("label", "agent")
        with lock:
            d = acc["agent"].setdefault(label, [0, 0, 0, 0.0, 0])
            d[0] += int(res.get("input_tokens") or 0)
            d[1] += int(res.get("output_tokens") or 0)
            d[2] += 1
            d[3] += float(res.get("latency_s") or 0.0)
            d[4] += 0 if res.get("ok") else 1
        return res

    llm._record = record
    agentkit.run_agent = run_agent
    _install_router_shim(llm, agentkit)
    _W.update(acc=acc, lock=lock)


ROUTER = "https://router.huggingface.co/v1"


def _install_router_shim(llm, agentkit) -> None:
    """Harness-only transport shim. The installed huggingface_hub may not know a provider name (0.36.2 has no
    "deepinfra"): calls for such providers go through the HF router's OpenAI-compatible endpoint with the
    `model:provider` suffix instead. Same model, same provider, same request body; nothing in bayan/ changes and
    providers the library knows (cerebras, groq) are untouched."""
    try:
        from huggingface_hub.inference._providers import PROVIDERS
        known = set(PROVIDERS)
    except Exception:  # noqa: BLE001
        return
    from huggingface_hub import InferenceClient
    orig_client = llm._client

    class _Completions:
        def __init__(self, client, provider):
            self._c, self._p = client, provider

        def create(self, model, **kw):
            return self._c.chat.completions.create(model=f"{model}:{self._p}", **kw)

    class _Chat:
        def __init__(self, client, provider):
            self.completions = _Completions(client, provider)

    class _RouterClient:
        def __init__(self, provider):
            self.chat = _Chat(InferenceClient(base_url=ROUTER, api_key=os.environ.get("HF_TOKEN"),
                                              timeout=llm.LLM_TIMEOUT_S), provider)

    cache: dict = {}

    def client(provider: str):
        if provider in known:
            return orig_client(provider)
        if provider not in cache:
            cache[provider] = _RouterClient(provider)
        return cache[provider]

    llm._client = client
    if agentkit.AGENT_PROVIDER not in known:
        orig_make = agentkit.make_model

        def make_model():
            if agentkit._model_factory is not None:
                return orig_make()
            from smolagents import InferenceClientModel
            kwargs = agentkit.model_kwargs()   # reasoning_effort only for gpt-oss
            return InferenceClientModel(model_id=f"{agentkit.AGENT_MODEL}:{agentkit.AGENT_PROVIDER}", base_url=ROUTER,
                                        api_key=os.environ.get("HF_TOKEN"), timeout=agentkit.AGENT_HTTP_TIMEOUT,
                                        retry=False, **kwargs)

        agentkit.make_model = make_model
    print(f"[shim] router transport for providers not in huggingface_hub: "
          f"{sorted({llm.LLM_PROVIDER, agentkit.AGENT_PROVIDER, llm.brain_route(os.environ.get('BAYAN_EXTRACT_PROVIDER', 'groq'))['provider']} - known)}",
          flush=True)


class CardWatch(threading.Thread):
    """Polls the card store; records first appearance and every change of every card (wall time + turn index)."""

    def __init__(self, brain, clock):
        super().__init__(daemon=True)
        self.brain, self.clock = brain, clock
        self.stop_ev = threading.Event()
        self.seen: dict[str, dict] = {}       # card id -> first sighting
        self.events: list[dict] = []          # changes
        self.rules: dict[str, dict] = {}      # rule id -> first sighting + max item severity
        self._sig: dict[str, tuple] = {}
        self._ver = -1

    def snap(self) -> None:
        cards = self.brain.cards
        if cards is None or cards.version == self._ver:
            return
        self._ver = cards.version
        turn, t_wall, t_turn = self.clock()
        for c in cards.all_cards():
            sig = (c["status"], c["severity"], tuple(c.get("rule_ids") or []), c.get("title"))
            if c["id"] not in self.seen:
                self.seen[c["id"]] = {"turn": turn, "wall": t_wall, "latency_s": round(t_wall - t_turn, 2),
                                      "source": c["source"], "kind": c["kind"], "title": c["title"],
                                      "severity": c["severity"]}
            if self._sig.get(c["id"]) != sig:
                self.events.append({"card": c["id"], "turn": turn, "latency_s": round(t_wall - t_turn, 2),
                                    "status": c["status"], "severity": c["severity"],
                                    "rule_ids": list(c.get("rule_ids") or []), "title": c["title"]})
                self._sig[c["id"]] = sig
            for it in c.get("items") or []:
                rid = it.get("rule_id")
                if not rid:
                    continue
                r = self.rules.get(rid)
                if r is None:
                    self.rules[rid] = {"turn": turn, "latency_s": round(t_wall - t_turn, 2), "card": c["id"],
                                       "severity": it.get("severity"), "family": it.get("family"),
                                       "message": (it.get("message") or "")[:220]}
                elif SEV.get(it.get("severity"), 0) > SEV.get(r["severity"], 0):
                    r["severity"] = it.get("severity")
                    r["escalated_turn"] = turn

    def run(self) -> None:
        while not self.stop_ev.is_set():
            try:
                self.snap()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.05)


def _pdf_info(path: str | None, lang: str, kind: str, dest: Path, png: Path, sid: str) -> dict:
    info: dict = {"path": None, "exists": False}
    if not path or not Path(path).exists():
        return info
    dest.mkdir(parents=True, exist_ok=True)
    png.mkdir(parents=True, exist_ok=True)
    copy_to = dest / f"{sid}_{kind}.pdf"
    shutil.copyfile(path, copy_to)
    info.update(path=str(copy_to), exists=True)
    raw = copy_to.read_bytes()
    info["magic_ok"] = raw[:5] == b"%PDF-"
    info["bytes"] = len(raw)
    try:
        import fitz  # pymupdf
        with fitz.open(str(copy_to)) as doc:
            info["pages"] = doc.page_count
            info["title"] = (doc.metadata or {}).get("title") or ""
            info["text"] = "\n".join(p.get_text() for p in doc)
            fonts = set()
            for p in doc:
                for f in p.get_fonts():
                    fonts.add(str(f[3]))
            info["fonts"] = sorted(fonts)
            pp = png / f"{sid}_{kind}_p1.png"
            doc[0].get_pixmap(dpi=90).save(str(pp))
            info["png"] = str(pp)
    except Exception as e:  # noqa: BLE001
        info["error"] = f"{type(e).__name__}: {e}"
    return info


def run_scenario(sc: dict, run_dir: str, prices: dict) -> dict:
    """Play one scenario in this worker process. Returns the raw record (no scoring)."""
    from bayan import consult
    from bayan.brain import agentkit, llm
    from bayan.brain import copilot as brain
    from bayan.brain.vocab import normalise_drug

    run_dir = Path(run_dir)
    acc, lock = _W["acc"], _W["lock"]
    with lock:
        acc["chat"].clear()
        acc["agent"].clear()
    usage0 = dict(llm.USAGE)
    rec: dict = {"id": sc["id"], "title": sc.get("title", ""), "category": sc.get("category"),
                 "patient_lang": sc["patient_lang"], "doctor_lang": sc.get("doctor_lang", "en"),
                 "turns": [], "holds": [], "errors": [], "started": datetime.now().isoformat(timespec="seconds")}
    t_start = time.time()
    cur = {"turn": -1, "t_turn": time.time()}
    watch = None
    s = None
    try:
        sid = consult.new_sid()
        s = consult.SESS[sid]
        s.lang, s.doc_lang = sc["patient_lang"], sc.get("doctor_lang", "en")
        s.screen, s.started_at = "live", time.time()
        consult.begin(s)
        b = s.brain
        b.set_scenario_time(0.0)
        if sc.get("consent", True):
            try:
                s.consent_native = consult.consent_text(s.lang)
            except Exception as e:  # noqa: BLE001
                rec["errors"].append(f"consent_text: {e}")
            consult.record_consent(s)
        watch = CardWatch(b, lambda: (cur["turn"], time.time(), cur["t_turn"]))
        watch.start()
        t_clock = 0.0
        for i, step in enumerate(sc.get("turns") or []):
            t_clock = float(step.get("t", t_clock + 0.75 if i else 0.5))
            b.set_scenario_time(t_clock)
            cur.update(turn=i, t_turn=time.time())
            tr = {"i": i, "t_min": t_clock, "role": step.get("role"), "action": step.get("action")}
            t0 = time.time()
            action = step.get("action")
            n_turns = len(b.turns)
            if rec["holds"] and rec["holds"][-1].get("resolution") is None and s.held:
                rec["holds"][-1]["resolution"] = {"held_else": "withdrawn", "held_anyway": "overridden"}.get(
                    action or "", "discarded (conversation moved on)")
            if action == "held_else":
                tr["had_held"] = bool(s.held)
                consult.held_else(s)
            elif action == "held_anyway":
                tr["had_held"] = bool(s.held)
                consult.held_anyway(s)
            elif action == "ask":
                kw = [k.lower() for k in step.get("keywords") or []]
                sugs = [x for x in consult.refresh(s) if x["status"] == "open"]
                pick = next((x for x in sugs if not kw or any(k in x["text"].lower() for k in kw)), None)
                tr["asked"] = pick["text"] if pick else None
                if pick:
                    consult.ask_suggestion(s, pick["id"])
                    s.pending.clear()
            elif action == "tick":
                brain.tick(b)
            elif action == "dismiss_open":
                for c in b.cards.open_cards():
                    if not step.get("source") or c["source"] == step["source"]:
                        b.cards.act(c["id"], "dismiss", user="doctor")
            else:
                role = step["role"]
                src = step.get("lang") or (s.doc_lang if role == "doctor" else s.lang)
                list(consult.process_text(s, role, step["text"], src))
                s.pending.clear()
                if s.error:
                    rec["errors"].append(f"turn {i}: {s.error}")
                    tr["error"] = s.error
            tr["process_s"] = round(time.time() - t0, 2)
            tl = _W["tr_log"]
            if tl and tl[-1]["text"] == str(step.get("text") or "")[:200]:
                tr["talk"] = {k: tl[-1][k] for k in ("drugs", "allergies", "tests", "s")}
            new = b.turns[n_turns:]
            if new:
                last = new[-1]
                tr["utt"] = last.id
                tr["english"] = last.english
                tr["translation"] = last.translation if last.role != "patient" else ""
            if s.held:
                hc = [b.cards.get(c) or {} for c in s.held.get("cards") or []]
                hold = {"turn": i, "rule": s.held.get("rule"), "drug": s.held.get("drug"),
                        "headline": s.held.get("headline"),
                        "rule_ids": sorted({r for c in hc for r in c.get("rule_ids") or []}),
                        "drug_norm": normalise_drug(s.held.get("drug") or "")}
                if not rec["holds"] or rec["holds"][-1]["turn"] != i:
                    rec["holds"].append(hold)
                tr["held"] = hold
            t1 = time.time()
            idle = brain.idle(b, 75)
            brain.tick(b)
            brain.idle(b, 30)
            tr["wait_s"] = round(time.time() - t1, 2)
            if not idle:
                rec["errors"].append(f"turn {i}: copilot not idle after 75 s")
            watch.snap()
            tr["open_cards"] = [c["id"] for c in b.cards.open_cards()]
            rec["turns"].append(tr)
        # ------------------------------------------------------------ end of visit
        if rec["holds"] and rec["holds"][-1].get("resolution") is None and s.held:
            rec["holds"][-1]["resolution"] = "discarded (visit ended)"
        cur.update(turn=len(sc.get("turns") or []), t_turn=time.time())
        b.set_scenario_time(t_clock + 1.0)
        t_end = time.time()
        list(consult.end_visit(s, "http://sim.local"))
        rec["end_visit_s"] = round(time.time() - t_end, 2)
        t_ap = time.time()
        list(consult.approve(s))
        rec["approve_s"] = round(time.time() - t_ap, 2)
        rec["screen"] = s.screen
        if s.error:
            rec["errors"].append(f"end: {s.error}")
        watch.snap()
        out = dict(b.outputs)
        rec["warnings"] = list(out.get("warnings") or [])
        rec["review_warnings"] = list((s.review or {}).get("warnings") or [])
        rec["wrapup_metrics"] = out.get("wrapup_metrics") or {}
        rec["agentic"] = out.get("agentic")
        plan = out.get("care_plan") or {}
        rec["care_plan"] = {"lang": plan.get("lang"),
                            "medicines": [{k: m.get(k) for k in ("drug", "name", "name_native", "title_en", "note_en",
                                                                  "note_native", "prn")} for m in plan.get("medicines") or []],
                            "avoid": plan.get("avoid") or [], "red_flags": plan.get("red_flags") or [],
                            "advice": plan.get("advice") or [], "follow_up": plan.get("follow_up") or {}}
        rec["note_md"] = out.get("note_md") or ""
        pdf_dir, png_dir = run_dir / "pdf", run_dir / "png"
        rec["pdf"] = {"patient": _pdf_info(out.get("patient_pdf"), s.lang, "patient", pdf_dir, png_dir, sc["id"]),
                      "doctor": _pdf_info(out.get("doctor_pdf"), s.lang, "doctor", pdf_dir, png_dir, sc["id"])}
        st = copy.deepcopy(b.state)
        rec["state"] = {
            "allergies": [{k: a.get(k) for k in ("substance", "class", "reaction", "severity")} for a in st["allergies"]],
            "current_meds": [{k: m.get(k) for k in ("drug", "dose_mg", "frequency_per_day", "daily_dose_mg")}
                             for m in st["current_meds"]],
            "prescribed_meds": [{k: m.get(k) for k in ("drug", "dose_mg", "frequency_per_day", "daily_dose_mg",
                                                       "dose_raw", "as_needed", "route")} for m in st["prescribed_meds"]],
            "stopped_meds": [m.get("drug") for m in st.get("stopped_meds") or []],
            "symptoms": [x.get("code") for x in st["symptoms"]],
            "investigations": [f"{x.get('code')}:{x.get('status')}" for x in st["investigations"]],
            "assessments": [x.get("code") for x in st["assessments"]],
            "disposition": (st.get("disposition") or {}).get("type"),
            "patient": {k: v for k, v in (st.get("patient") or {}).items() if v not in (None, "unknown", "")},
            "idiom_hits": [h.get("id") for h in st.get("idiom_hits") or []],
            "questions_asked": [q if isinstance(q, str) else q.get("topic") for q in st.get("questions_asked") or []],
        }
        rec["cards"] = [{k: c.get(k) for k in ("id", "source", "kind", "severity", "status", "title", "body", "ask_text",
                                               "grounding", "rule_ids", "t_min")} for c in b.cards.all_cards()]
        rec["audit"] = [{k: a.get(k) for k in ("card_id", "rule_id", "action", "severity", "kind", "source", "title",
                                               "reason", "t_min")} for a in b.audit]
        rec["trace_errors"] = [t["text"][:300] for t in b.trace if t.get("kind") == "error"]
        rec["trace"] = [f"{t.get('t_min', 0):.2f} {t.get('kind')}: {str(t.get('text'))[:240]}" for t in b.trace]
        rec["stats"] = brain.stats(b)
        rec["think_metrics"] = [m for m in (out.get("metrics") or []) if isinstance(m, dict)]
    except Exception as e:  # noqa: BLE001
        rec["errors"].append(f"CRASH {type(e).__name__}: {e}")
        rec["traceback"] = traceback.format_exc()[-3000:]
    finally:
        if watch is not None:
            watch.stop_ev.set()
            try:
                watch.snap()
            except Exception:  # noqa: BLE001
                pass
            rec["card_first_seen"] = watch.seen
            rec["card_events"] = watch.events
            rec["rules_seen"] = watch.rules
        if s is not None:
            try:
                consult.SESS.pop(s.sid, None)
            except Exception:  # noqa: BLE001
                pass
    # ---------------------------------------------------------------- usage and cost
    with lock:
        chat = {k: list(v) for k, v in acc["chat"].items()}
        agent = {k: list(v) for k, v in acc["agent"].items()}
    def _mp(key: str) -> tuple[str, str]:
        m, _, p = key.rpartition("|")
        return (m or llm.LLM_MODEL), p

    cost_chat = sum((v[0] * price_of(prices, *_mp(k))[0] + v[1] * price_of(prices, *_mp(k))[1]) / 1e6
                    for k, v in chat.items())
    pa = price_of(prices, agentkit.AGENT_MODEL, agentkit.AGENT_PROVIDER)
    cost_agent = sum((v[0] * pa[0] + v[1] * pa[1]) / 1e6 for v in agent.values())
    rec["usage"] = {"chat_by_provider": chat, "agent_by_label": agent, "cost_chat_usd": round(cost_chat, 5),
                    "cost_agent_usd": round(cost_agent, 5), "cost_usd": round(cost_chat + cost_agent, 5),
                    "llm_usage_delta": {k: llm.USAGE[k] - usage0.get(k, 0) for k in ("calls", "prompt_tokens",
                                                                                       "completion_tokens")}}
    rec["models"] = {"llm": llm.LLM_MODEL, "llm_provider": llm.LLM_PROVIDER, "agent": agentkit.AGENT_MODEL,
                     "agent_provider": agentkit.AGENT_PROVIDER, "brain": llm.brain_model(),
                     "brain_provider": llm.brain_route().get("provider", "default"),
                     "extract_provider": llm.brain_route(os.environ.get("BAYAN_EXTRACT_PROVIDER", "groq"))["provider"]}
    rec["wall_s"] = round(time.time() - t_start, 1)
    return rec


# ============================================================================ scoring
def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def _drug(name: str) -> str:
    try:
        from bayan.brain.vocab import normalise_drug
        return normalise_drug(name)
    except Exception:  # noqa: BLE001
        return str(name).lower()


def _kw_hit(text: str, keywords: list) -> bool:
    t = _norm(text)
    return any(_norm(str(k)) in t for k in keywords)


def _card_text(c: dict) -> str:
    return " ".join(str(c.get(k) or "") for k in ("title", "body", "ask_text"))


def _card_turn(rec: dict, cid: str) -> int | None:
    return (rec.get("card_first_seen") or {}).get(cid, {}).get("turn")


def _section(text: str, start: str, ends: list[str]) -> str:
    """Text of a patient-sheet section: from its (English) heading to the next heading."""
    low = text.lower()
    i = low.find(start.lower())
    if i < 0:
        return ""
    j = len(text)
    for e in ends:
        k = low.find(e.lower(), i + len(start))
        if 0 <= k < j:
            j = k
    return text[i:j]


# Text-level tofu only where extraction is reliable: a '?' between ASCII letters/digits, replacement boxes, U+FFFD.
# Shaped complex scripts (Indic, Arabic/Urdu) extract with imperfect ToUnicode maps (stray '?', digits, Latin
# letters inside words) even when the page renders perfectly, so they are checked by font coverage instead.
TOFU_RES = [re.compile(r"(?<=[A-Za-z0-9])\?+(?=[A-Za-z0-9])"), re.compile("[□�]")]


def uncovered_chars(texts: list[str]) -> list[str]:
    """Characters in the strings sent to the PDFs that no bundled font can draw (rendered as a box / '?')."""
    try:
        from bayan.outputs.report import _coverage
        cov = _coverage()
    except Exception:  # noqa: BLE001
        return []
    bad = set()
    for t in texts:
        for ch in str(t or ""):
            o = ord(ch)
            if ch in "\n\t\r‌‍​﻿" or o < 32 or 0xD800 <= o <= 0xDFFF or o in cov:
                continue
            bad.add(ch)
    return sorted(bad)


def tofu(text: str) -> list[str]:
    hits = []
    for rx in TOFU_RES:
        for m in rx.finditer(text or ""):
            a, b = max(0, m.start() - 18), min(len(text), m.end() + 18)
            hits.append(text[a:b].replace("\n", " "))
    return hits[:8]


def check(kind: str, desc: str, ok: bool, evidence: str = "", gap: bool = False, note: str = "",
          auto: bool = False) -> dict:
    status = ("GAP" if not ok else "GAP-CLOSED") if gap else ("PASS" if ok else "FAIL")
    return {"type": kind, "desc": desc, "status": status, "ok": ok, "evidence": evidence[:400], "gap": gap,
            "note": note, "auto": auto}


def score(sc: dict, rec: dict) -> list[dict]:
    from bayan.outputs import LANG_NAMES, labels
    exp = sc.get("expect") or {}
    out: list[dict] = []
    if any(e.startswith("CRASH") for e in rec.get("errors", [])):
        out.append(check("run", "scenario ran to completion", False, "; ".join(rec["errors"])[:400], auto=True))
        return out
    cards = rec.get("cards") or []
    rules_seen = rec.get("rules_seen") or {}
    # rule ids seen in the audit too (a card shown and resolved between two polls)
    for a in rec.get("audit") or []:
        for rid in str(a.get("rule_id") or "").split(","):
            if rid and rid not in rules_seen and a.get("action") in ("shown", "escalated", "reopened"):
                rules_seen[rid] = {"turn": None, "severity": a.get("severity"), "card": a.get("card_id")}
    holds = rec.get("holds") or []
    gap_all = bool(sc.get("expected_gap"))

    def gap_of(item):
        return bool(item.get("gap", gap_all)) if isinstance(item, dict) else gap_all

    # ---------------------------------------------------------------- holds
    for h in exp.get("must_hold") or []:
        h = h if isinstance(h, dict) else {"drug": h}
        want_d = _drug(h["drug"]) if h.get("drug") else None
        rules = h.get("rule_any") or ([h["rule"]] if h.get("rule") else [])
        match = [x for x in holds
                 if (not want_d or want_d == x.get("drug_norm") or want_d in _norm(x.get("drug")))
                 and (not rules or x.get("rule") in rules or set(rules) & set(x.get("rule_ids") or []))
                 and (h.get("turn") is None or x["turn"] == h["turn"])]
        ev = "; ".join(f"t{x['turn']} {x['drug']} {x['rule']} {x.get('rule_ids')}" for x in holds) or "no holds"
        out.append(check("hold", f"held: {h.get('drug') or ''} {'/'.join(rules)}"
                         + (f" at turn {h['turn']}" if h.get("turn") is not None else ""), bool(match), ev,
                         gap_of(h), h.get("note", "")))
    mnh = exp.get("must_not_hold")
    if mnh is not None:
        items = mnh if isinstance(mnh, list) else ["*"]
        for d in items:
            d = d if isinstance(d, dict) else {"drug": d}
            if d["drug"] == "*":
                bad = holds
            else:
                bad = [x for x in holds if _drug(d["drug"]) == x.get("drug_norm") or _drug(d["drug"]) in _norm(x["drug"])]
            if d.get("turn") is not None:
                bad = [x for x in bad if x["turn"] == d["turn"]]
            out.append(check("no_hold", f"not held: {d['drug']}", not bad,
                             "; ".join(f"t{x['turn']} {x['drug']} {x['rule']}" for x in bad), gap_of(d), d.get("note", "")))

    # ---------------------------------------------------------------- flags
    def find_flag(f: dict) -> tuple[bool, str]:
        rules = f.get("rule_any") or ([f["rule"]] if f.get("rule") else [])
        by = f.get("by_turn")
        if rules:
            hits = [(r, rules_seen[r]) for r in rules if r in rules_seen]
            if f.get("severity"):
                hits = [(r, x) for r, x in hits if SEV.get(x.get("severity"), 0) >= SEV[f["severity"]]]
            if by is not None:
                hits = [(r, x) for r, x in hits if x.get("turn") is not None and x["turn"] <= by]
            ev = "; ".join(f"{r}@t{x.get('turn')} {x.get('severity')}" for r, x in rules_seen.items()) or "no rule fired"
            return bool(hits), ev
        cand = []
        for c in cards:
            if f.get("kind") and c["kind"] != f["kind"]:
                continue
            if f.get("kind_any") and c["kind"] not in f["kind_any"]:
                continue
            if f.get("source") and c["source"] != f["source"]:
                continue
            if f.get("source_not") and c["source"] in f["source_not"]:
                continue
            if f.get("grounding") and c.get("grounding") != f["grounding"]:
                continue
            if f.get("severity") and SEV.get(c["severity"], 0) < SEV[f["severity"]]:
                continue
            if f.get("family") and not any(str(r).startswith(f["family"]) for r in c.get("rule_ids") or []):
                continue
            if f.get("keywords") and not _kw_hit(_card_text(c), f["keywords"]):
                continue
            if by is not None and (_card_turn(rec, c["id"]) is None or _card_turn(rec, c["id"]) > by):
                continue
            cand.append(c)
        ev = "; ".join(f"{c['source']}/{c['kind']}/{c['severity']} '{c['title'][:50]}'"
                       + (f" ask='{(c.get('ask_text') or '')[:60]}'" if c.get("ask_text") else "") for c in cand[:4])
        if not cand:
            ev = "cards: " + "; ".join(f"{c['source']}/{c['kind']} '{c['title'][:40]}'" for c in cards[:10])
        return bool(cand), ev

    def flag_desc(f):
        parts = [f.get("rule") or "/".join(f.get("rule_any") or []) or f.get("kind") or "/".join(f.get("kind_any") or [])
                 or "card"]
        for k in ("grounding", "severity", "source", "family"):
            if f.get(k):
                parts.append(f"{k}={f[k]}")
        if f.get("keywords"):
            parts.append("~" + "|".join(str(k) for k in f["keywords"][:5]))
        if f.get("by_turn") is not None:
            parts.append(f"by turn {f['by_turn']}")
        return " ".join(parts)

    for f in exp.get("must_flag") or []:
        f = f if isinstance(f, dict) else {"rule": f}
        ok, ev = find_flag(f)
        out.append(check("flag", flag_desc(f), ok, ev, gap_of(f), f.get("note", "")))
    for f in exp.get("must_suggest") or []:
        f = dict(f if isinstance(f, dict) else {"keywords": [f]})
        f.setdefault("kind", "ask")
        ok, ev = find_flag(f)
        out.append(check("suggest", flag_desc(f), ok, ev, gap_of(f), f.get("note", "")))
    for f in exp.get("must_not_flag") or []:
        f = f if isinstance(f, dict) else {"rule": f}
        ok, ev = find_flag(f)
        out.append(check("no_flag", "NOT " + flag_desc(f), not ok, ev if ok else "", gap_of(f), f.get("note", "")))

    # ---------------------------------------------------------------- state / care plan
    st = rec.get("state") or {}
    stx = exp.get("state") or {}
    pres = [_drug(m.get("drug") or "") for m in st.get("prescribed_meds") or []]
    for d in stx.get("prescribed_has") or []:
        out.append(check("state", f"prescribed includes {d}", _drug(d) in pres, f"prescribed={pres}"))
    for d in stx.get("prescribed_not") or []:
        out.append(check("state", f"prescribed excludes {d}", _drug(d) not in pres, f"prescribed={pres}"))
    alls = " ".join(f"{a.get('substance')} {a.get('class')}" for a in st.get("allergies") or []).lower()
    for a in stx.get("allergy_has") or []:
        out.append(check("state", f"allergy recorded: {a}", a.lower() in alls, f"allergies={alls or 'none'}"))
    for a in stx.get("allergy_not") or []:
        out.append(check("state", f"no allergy recorded: {a}", a.lower() not in alls, f"allergies={alls or 'none'}"))
    for k, v in (stx.get("patient") or {}).items():
        got = (st.get("patient") or {}).get(k)
        out.append(check("state", f"patient.{k} == {v}", got == v, f"patient.{k}={got}"))
    for code in stx.get("symptoms_has") or []:
        out.append(check("state", f"symptom {code}", code in (st.get("symptoms") or []), f"symptoms={st.get('symptoms')}"))
    for code in stx.get("investigations_has") or []:
        out.append(check("state", f"investigation {code}", any(i.startswith(code) for i in st.get("investigations") or []),
                         f"investigations={st.get('investigations')}"))
    plan = rec.get("care_plan") or {}
    plan_meds = " ".join(f"{m.get('drug')} {m.get('name')} {m.get('title_en')}" for m in plan.get("medicines") or []).lower()
    plan_avoid = " ".join(f"{a.get('en')}" for a in plan.get("avoid") or []).lower()
    cpx = exp.get("care_plan") or {}
    for d in cpx.get("meds_has") or []:
        out.append(check("care_plan", f"care plan lists {d}", d.lower() in plan_meds, f"medicines: {plan_meds[:200]}"))
    for d in cpx.get("meds_not") or []:
        out.append(check("care_plan", f"care plan does NOT list {d}", d.lower() not in plan_meds,
                         f"medicines: {plan_meds[:200]}"))
    for d in cpx.get("avoid_has") or []:
        out.append(check("care_plan", f"'Do not take' mentions {d}", d.lower() in plan_avoid, f"avoid: {plan_avoid[:200]}"))

    # ---------------------------------------------------------------- PDFs (automatic + scenario)
    lang = rec.get("patient_lang")
    pp = (rec.get("pdf") or {}).get("patient") or {}
    dp = (rec.get("pdf") or {}).get("doctor") or {}
    for name, info in (("patient", pp), ("doctor", dp)):
        ok = bool(info.get("exists") and info.get("magic_ok") and info.get("pages", 0) >= 1 and info.get("text"))
        out.append(check("pdf", f"{name} PDF rendered (%PDF, pages, text)", ok,
                         f"{info.get('path')} pages={info.get('pages')} err={info.get('error')}", auto=True))
        if not ok:
            continue
        txt = info.get("text") or ""
        t = tofu(txt)
        out.append(check("pdf", f"{name} PDF has no tofu/'?' glyph runs", not t, " | ".join(t), auto=True))
        failed = re.findall(r"\[([^\]]{0,60}): this section could not be printed", txt)
        out.append(check("pdf", f"{name} PDF: every section printed", not failed, "; ".join(failed), auto=True))
    plan_c = rec.get("care_plan") or {}
    fed = [str(t.get("text") or "") for t in sc.get("turns") or []] + \
          [str(t.get("translation") or "") for t in rec.get("turns") or []] + \
          [str(m.get(k) or "") for m in plan_c.get("medicines") or [] for k in ("name_native", "note_native")] + \
          [str(a.get("native") or "") for key in ("avoid", "red_flags", "advice") for a in plan_c.get(key) or []]
    unc = uncovered_chars(fed)
    out.append(check("pdf", "every character sent to the PDFs has a glyph in a bundled font", not unc,
                     " ".join(f"{c!r}U+{ord(c):04X}" for c in unc[:12]), auto=True))
    ptxt, dtxt = pp.get("text") or "", dp.get("text") or ""
    lname = LANG_NAMES.get(lang, lang)
    if pp.get("text"):
        script = LANG_SCRIPT.get(lang)
        if script:
            n = script_count(ptxt, script)
            out.append(check("pdf", f"patient PDF has {script} text", n >= 20, f"{n} {script} chars", auto=True))
        elif lang != "en":
            L, E = labels(lang), labels("en")
            nat = L.get("title") if L.get("title") != E.get("title") else None
            out.append(check("pdf", f"patient PDF has the native title ({lang})", bool(nat) and _norm(nat) in _norm(ptxt),
                             f"native title {nat!r}", auto=True))
        if lang != "en":
            L, E = labels(lang), labels("en")
            out.append(check("pdf", f"patient sheet labels exist for {lang}", L["title"] != E["title"],
                             f"title label = {L['title']!r}", auto=True))
        out.append(check("pdf", "patient PDF title names the language", lname.split(" (")[0] in (pp.get("title") or ""),
                         f"title={pp.get('title')!r}", auto=True))
        meds_sec = _section(ptxt, "Your medicines", ["Daily schedule", "Do not take", "Other instructions", "Call 999"])
        for d in (exp.get("pdf") or {}).get("patient_meds_not") or []:
            out.append(check("pdf", f"patient PDF medicines section omits {d}", d.lower() not in meds_sec.lower(),
                             meds_sec[:300].replace("\n", " ")))
        for d in (exp.get("pdf") or {}).get("patient_meds_has") or []:
            out.append(check("pdf", f"patient PDF medicines section has {d}", d.lower() in meds_sec.lower(),
                             meds_sec[:300].replace("\n", " ")))
        for d in (exp.get("pdf") or {}).get("patient_contains") or []:
            out.append(check("pdf", f"patient PDF contains {d!r}", _norm(d) in _norm(ptxt), ""))
        for d in (exp.get("pdf") or {}).get("patient_not_contains") or []:
            out.append(check("pdf", f"patient PDF does not contain {d!r}", _norm(d) not in _norm(ptxt), ""))
    if dp.get("text"):
        out.append(check("pdf", f"doctor PDF names the patient language ({lname})",
                         "patient language" in dtxt.lower() and lname.split(" (")[0].lower() in dtxt.lower(), "",
                         auto=True))
        if rec.get("doctor_lang") == "ar":
            out.append(check("pdf", "doctor PDF records Arabic as clinician language", "arabic" in dtxt.lower(), "",
                             auto=True))
        if any(not str(h.get("resolution") or "").startswith("overridden") for h in holds):
            out.append(check("pdf", "doctor PDF records the held instruction", "held" in dtxt.lower(),
                             "", auto=True))
        if any(str(h.get("resolution") or "").startswith("overridden") for h in holds):
            out.append(check("pdf", "doctor PDF records the clinician's override",
                             any(w in dtxt.lower() for w in ("continued", "overrid", "spoken anyway")), "", auto=True))
        if any(c["source"] == "rules" and c["severity"] in ("critical", "caution") for c in cards):
            out.append(check("pdf", "doctor PDF has a Safety alerts section", "safety alerts" in dtxt.lower(), "",
                             auto=True))
        for d in (exp.get("pdf") or {}).get("doctor_contains") or []:
            out.append(check("pdf", f"doctor PDF contains {d!r}", _norm(d) in _norm(dtxt), ""))
        for d in (exp.get("pdf") or {}).get("doctor_not_contains") or []:
            out.append(check("pdf", f"doctor PDF does not contain {d!r}", _norm(d) not in _norm(dtxt), ""))
    # ---------------------------------------------------------------- run health
    out.append(check("run", "wrap-up reached the review/sent screen", rec.get("screen") == "sent",
                     f"screen={rec.get('screen')} agentic={rec.get('agentic')}", auto=True))
    errs = [e for e in rec.get("errors") or []]
    out.append(check("run", "no talk-loop / translation errors", not errs, "; ".join(errs)[:300], auto=True))
    return out


def safe_score(sc: dict, rec: dict) -> None:
    try:
        rec["checks"] = score(sc, rec)
    except Exception as e:  # noqa: BLE001 - a scorer bug must never lose a run
        rec["checks"] = [check("run", "scorer crashed", False, f"{type(e).__name__}: {e}", auto=True)]
    try:
        rec["unexpected_critical"] = unexpected_criticals(sc, rec)
    except Exception:  # noqa: BLE001
        rec["unexpected_critical"] = []


def unexpected_criticals(sc: dict, rec: dict) -> list[str]:
    exp = sc.get("expect") or {}
    allowed = set()
    for x in (exp.get("must_flag") or []) + (exp.get("must_hold") or []):
        if isinstance(x, dict):
            allowed.update([x["rule"]] if x.get("rule") else [])
            allowed.update(x.get("rule_any") or [])
        elif isinstance(x, str):
            allowed.add(x)
    allowed.update(exp.get("allow_rules") or [])
    return sorted(r for r, x in (rec.get("rules_seen") or {}).items()
                  if x.get("severity") == "critical" and r not in allowed)


# ============================================================================ summary
def _pct(a, b):
    return f"{100.0 * a / b:.0f}%" if b else "-"


def _median(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.median(xs) if xs else None


def summarise(run_dir: Path, results: list[dict], meta: dict) -> str:
    L = []
    L.append(f"# Bayan simulation run {meta['run_id']}")
    L.append("")
    L.append(f"- models: LLM `{meta['models'].get('llm')}` on {meta['models'].get('llm_provider')} "
             f"(extraction on {meta['models'].get('extract_provider')}), agent `{meta['models'].get('agent')}` on "
             f"{meta['models'].get('agent_provider')}")
    L.append(f"- scenarios: {len(results)} · languages: {len({r['patient_lang'] for r in results})} "
             f"({', '.join(sorted({r['patient_lang'] for r in results}))}) · wall {meta.get('wall_s', 0):.0f}s")
    checks = [c for r in results for c in r["checks"]]
    scored = [c for c in checks if c["status"] in ("PASS", "FAIL")]
    npass = sum(1 for c in scored if c["status"] == "PASS")
    gaps = [c for c in checks if c["gap"]]
    sc_pass = sum(1 for r in results if all(c["status"] != "FAIL" for c in r["checks"]))
    L.append(f"- **checks passed: {npass}/{len(scored)} ({_pct(npass, len(scored))})** · scenarios fully passing: "
             f"{sc_pass}/{len(results)} · expected gaps confirmed: {sum(1 for c in gaps if c['status'] == 'GAP')}"
             f" (closed: {sum(1 for c in gaps if c['status'] == 'GAP-CLOSED')})")
    clinical = [c for c in scored if c["type"] in ("hold", "no_hold", "flag", "suggest", "no_flag")]
    L.append(f"- clinical checks (hold/flag/suggest/no-flag): {sum(c['ok'] for c in clinical)}/{len(clinical)} "
             f"({_pct(sum(c['ok'] for c in clinical), len(clinical))})")
    neg = [c for c in scored if c["type"] in ("no_flag", "no_hold")]
    fp = [c for c in neg if not c["ok"]]
    L.append(f"- false-positive traps tripped: {len(fp)}/{len(neg)} ({_pct(len(fp), len(neg))})")
    costs = [r["usage"]["cost_usd"] for r in results if r.get("usage")]
    L.append(f"- cost: total ${sum(costs):.4f} · per consultation median ${_median(costs) or 0:.4f} · "
             f"max ${max(costs or [0]):.4f}")
    lat_rule = [x["latency_s"] for r in results for cid, x in (r.get("card_first_seen") or {}).items()
                if x.get("source") == "rules" and x.get("turn", -1) >= 0 and x.get("latency_s") is not None]
    lat_agent = [x["latency_s"] for r in results for cid, x in (r.get("card_first_seen") or {}).items()
                 if x.get("source") in ("agent",) and x.get("turn", -1) >= 0]
    lat_fb = [x["latency_s"] for r in results for cid, x in (r.get("card_first_seen") or {}).items()
              if x.get("source") in ("fallback", "lexicon") and x.get("turn", -1) >= 0]
    trans = [t["process_s"] for r in results for t in r.get("turns") or [] if t.get("role")]
    wrap = [r.get("end_visit_s") for r in results]
    L.append(f"- latency (median, s from the start of the turn that preceded the card): rule cards "
             f"{_median(lat_rule) or 0:.1f} · agent cards {_median(lat_agent) or 0:.1f} · lexicon/fallback "
             f"{_median(lat_fb) or 0:.1f} · translate+gate per turn {_median(trans) or 0:.1f} · wrap-up "
             f"{_median(wrap) or 0:.1f}")
    runs = [r["stats"]["runs"] for r in results if r.get("stats")]
    agent_calls = sum((r["usage"]["agent_by_label"].get("copilot") or [0, 0, 0])[2] for r in results if r.get("usage"))
    agent_fail = sum((r["usage"]["agent_by_label"].get("copilot") or [0, 0, 0, 0, 0])[4] for r in results if r.get("usage"))
    L.append(f"- copilot: {sum(runs)} think runs, {agent_calls} agent runs ({agent_fail} failed/timed out); "
             f"wrap-up modes: " + ", ".join(f"{m}×{sum(1 for r in results if r.get('agentic') == m)}"
                                           for m in sorted({str(r.get('agentic')) for r in results})))
    L.append("")
    # by category
    L.append("## Pass rate by category")
    L.append("")
    L.append("| category | scenarios | fully passing | checks | clinical checks | gaps |")
    L.append("|---|---|---|---|---|---|")
    for cat in sorted({r["category"] for r in results}):
        rs = [r for r in results if r["category"] == cat]
        cs = [c for r in rs for c in r["checks"] if c["status"] in ("PASS", "FAIL")]
        cl = [c for c in cs if c["type"] in ("hold", "no_hold", "flag", "suggest", "no_flag")]
        L.append(f"| {cat} | {len(rs)} | {sum(1 for r in rs if all(c['status'] != 'FAIL' for c in r['checks']))} | "
                 f"{sum(c['ok'] for c in cs)}/{len(cs)} | {sum(c['ok'] for c in cl)}/{len(cl)} | "
                 f"{sum(1 for r in rs for c in r['checks'] if c['status'] == 'GAP')} |")
    L.append("")
    L.append("## Pass rate by check type")
    L.append("")
    L.append("| type | passed | total |")
    L.append("|---|---|---|")
    for t in sorted({c["type"] for c in scored}):
        cs = [c for c in scored if c["type"] == t]
        L.append(f"| {t} | {sum(c['ok'] for c in cs)} | {len(cs)} |")
    L.append("")
    L.append("## Scenarios")
    L.append("")
    L.append("| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        fails = [c for c in r["checks"] if c["status"] == "FAIL"]
        crit = sorted(k for k, v in (r.get("rules_seen") or {}).items() if v.get("severity") == "critical")
        L.append(f"| {r['id']} | {r['patient_lang']}/{r['doctor_lang']} | {'PASS' if not fails else 'FAIL'} | "
                 f"{len(fails)} | {', '.join(h['drug'] + ':' + str(h['rule']) for h in r.get('holds') or []) or '-'} | "
                 f"{', '.join(crit) or '-'} | {(r.get('usage') or {}).get('cost_usd', 0):.4f} | {r.get('wall_s')} |")
    L.append("")
    L.append("## Failures (with evidence)")
    L.append("")
    for r in results:
        fails = [c for c in r["checks"] if c["status"] == "FAIL"]
        if not fails:
            continue
        L.append(f"**{r['id']}** — {r['title']}")
        for c in fails:
            L.append(f"- [{c['type']}] {c['desc']} — {c['evidence'][:300]}")
        L.append("")
    L.append("## Unexpected critical alerts (not in the scenario's expectations; review for false positives)")
    L.append("")
    any_u = False
    for r in results:
        if r.get("unexpected_critical"):
            any_u = True
            L.append(f"- {r['id']}: " + ", ".join(f"{x} ({(r['rules_seen'][x].get('message') or '')[:120]})"
                                                   for x in r["unexpected_critical"]))
    if not any_u:
        L.append("- none")
    L.append("")
    L.append("## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)")
    L.append("")
    for r in results:
        for c in r["checks"]:
            if c["gap"]:
                L.append(f"- {r['id']}: {c['desc']} → **{c['status']}**" + (f" — {c['note']}" if c["note"] else ""))
    L.append("")
    L.append("## PDF review images")
    L.append("")
    for r in results:
        pngs = [((r.get("pdf") or {}).get(k) or {}).get("png") for k in ("patient", "doctor")]
        pngs = [os.path.relpath(p, run_dir) for p in pngs if p]
        if pngs:
            L.append(f"- {r['id']} ({r['patient_lang']}): " + " · ".join(pngs))
    return "\n".join(L) + "\n"


# ============================================================================ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated scenario ids (prefix match)")
    ap.add_argument("--lang", default="", help="comma-separated patient languages")
    ap.add_argument("--category", default="", help="comma-separated categories")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--label", default="", help="suffix for the run id (e.g. the model)")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--rescore", default="", help="re-score a saved run directory (no LLM calls)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--resume", default="", help="run id: keep the scenarios already in its raw.jsonl, run the rest")
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))

    scenarios = load_scenarios()
    if args.list:
        for s in scenarios:
            print(f"{s['id']:<34} {s['category']:<12} {s['patient_lang']}/{s['doctor_lang']}  {s.get('title', '')}")
        print(f"{len(scenarios)} scenarios")
        return 0
    by_id = {s["id"]: s for s in scenarios}

    if args.rescore:
        run_dir = Path(args.rescore)
        data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        results = data["results"]
        for r in results:
            sc = by_id.get(r["id"])
            if sc is None:
                continue
            safe_score(sc, r)
            r["category"] = sc["category"]
        data["results"] = results
        (run_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        (run_dir / "summary.md").write_text(summarise(run_dir, results, data["meta"]), encoding="utf-8")
        print((run_dir / "summary.md").read_text(encoding="utf-8")[:3000])
        return 0

    sel = scenarios
    if args.only:
        pre = [x.strip() for x in args.only.split(",") if x.strip()]
        sel = [s for s in sel if any(s["id"].startswith(p) for p in pre)]
    if args.lang:
        langs = set(args.lang.split(","))
        sel = [s for s in sel if s["patient_lang"] in langs]
    if args.category:
        cats = set(args.category.split(","))
        sel = [s for s in sel if s["category"] in cats]
    if not sel:
        print("no scenarios selected")
        return 1
    done_recs: list[dict] = []
    if args.resume:
        raw = REPORTS / args.resume / "raw.jsonl"
        if raw.exists():
            for line in raw.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    if r["id"] in by_id and not any(e.startswith("CRASH") for e in r.get("errors") or []):
                        done_recs.append(r)
        done_ids = {r["id"] for r in done_recs}
        sel_ids = {s["id"] for s in sel}
        done_recs = [r for r in done_recs if r["id"] in sel_ids]
        sel = [s for s in sel if s["id"] not in done_ids]
        args.run_id = args.resume
        print(f"resume: {len(done_recs)} done, {len(sel)} to run")

    token = os.environ.get("HF_TOKEN")
    if not token:
        p = Path.home() / ".cache" / "huggingface" / "token"
        if p.exists():
            token = p.read_text().strip()
    if not token:
        print("HF_TOKEN not set and ~/.cache/huggingface/token missing")
        return 1
    run_id = args.run_id or (datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{args.label}" if args.label else ""))
    run_dir = REPORTS / run_id
    (run_dir / "out").mkdir(parents=True, exist_ok=True)
    prices = fetch_prices(token)
    (run_dir / "prices.json").write_text(json.dumps(prices, indent=0), encoding="utf-8")
    env = {"HF_TOKEN": token, "BAYAN_OUTPUT_ROOT": str(run_dir / "out"), "PYTHONUNBUFFERED": "1"}
    models = {"llm": os.environ.get("BAYAN_LLM", "openai/gpt-oss-120b"),
              "llm_provider": os.environ.get("BAYAN_LLM_PROVIDER", "cerebras"),
              "agent": os.environ.get("BAYAN_BRAIN_LLM") or os.environ.get(
                  "BAYAN_AGENT_LLM", os.environ.get("BAYAN_LLM", "openai/gpt-oss-120b")),
              "agent_provider": os.environ.get("BAYAN_BRAIN_PROVIDER") or os.environ.get("BAYAN_AGENT_PROVIDER",
                                                                                         "cerebras"),
              "brain": os.environ.get("BAYAN_BRAIN_LLM") or os.environ.get("BAYAN_LLM", "openai/gpt-oss-120b"),
              "brain_provider": os.environ.get("BAYAN_BRAIN_PROVIDER") or "default",
              "extract_provider": os.environ.get("BAYAN_BRAIN_PROVIDER") or os.environ.get("BAYAN_EXTRACT_PROVIDER",
                                                                                           "groq")}
    print(f"== run {run_id}: {len(sel)} scenarios, {args.workers} at a time · {models}", flush=True)
    t0 = time.time()
    results: list[dict] = []
    for r in done_recs:
        safe_score(by_id[r["id"]], r)
        results.append(r)
    ctx = mp.get_context("spawn")
    with cf.ProcessPoolExecutor(max_workers=max(1, min(args.workers, len(sel) or 1)), mp_context=ctx,
                                initializer=_worker_init, initargs=(env,)) as ex:
        futs = {ex.submit(run_scenario, s, str(run_dir), prices): s for s in sel}
        for fut in cf.as_completed(futs):
            sc = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001
                rec = {"id": sc["id"], "title": sc.get("title", ""), "category": sc["category"],
                       "patient_lang": sc["patient_lang"], "doctor_lang": sc.get("doctor_lang", "en"),
                       "errors": [f"CRASH worker: {type(e).__name__}: {e}"], "usage": {"cost_usd": 0.0}}
            with open(run_dir / "raw.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            safe_score(sc, rec)
            results.append(rec)
            nf = sum(1 for c in rec["checks"] if c["status"] == "FAIL")
            print(f"[{len(results)}/{len(sel)}] {sc['id']:<34} {'PASS' if not nf else f'FAIL({nf})':<8} "
                  f"holds={[h['drug'] + ':' + str(h['rule']) for h in rec.get('holds') or []]} "
                  f"${(rec.get('usage') or {}).get('cost_usd', 0):.4f} {rec.get('wall_s')}s", flush=True)
            for c in rec["checks"]:
                if c["status"] == "FAIL":
                    print(f"      FAIL [{c['type']}] {c['desc']} :: {c['evidence'][:160]}", flush=True)
    order = {s["id"]: i for i, s in enumerate(scenarios)}
    results.sort(key=lambda r: order.get(r["id"], 0))
    try:
        import subprocess
        git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "bayan", "data"], cwd=ROOT, capture_output=True,
                               text=True).stdout.count("\n")
    except Exception:  # noqa: BLE001
        git, dirty = "", 0
    meta = {"run_id": run_id, "models": models, "wall_s": time.time() - t0, "n": len(results),
            "git": git, "dirty_app_files": dirty,
            "created": datetime.now().isoformat(timespec="seconds")}
    (run_dir / "results.json").write_text(json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    summary = summarise(run_dir, results, meta)
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary[:2500])
    print(f"\nresults: {run_dir / 'results.json'}\nsummary: {run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
