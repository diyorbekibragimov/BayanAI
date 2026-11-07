"""Live smoke test of the Bayan clinical copilot on the golden path (docs/02 §8, docs/09 §2.2) as TEXT turns.

    HF_TOKEN=hf_xxx python scripts/smoke_copilot.py            # real gpt-oss-120b (extraction + smolagents agent)
    python scripts/smoke_copilot.py --offline                   # scripted fakes from tests/test_copilot.py
    BAYAN_AGENT=off python scripts/smoke_copilot.py             # extraction live, deterministic fallback cards only

Per turn it prints: the prescription-gate result (held or not), the agent-activity trace lines, new/changed cards,
latency, tokens and cost (Cerebras gpt-oss-120b $0.35 / $0.75 per 1M tokens in/out). At the end: the expected-card
checklist (PASS/FAIL), the decision-support audit and a per-consultation cost estimate.
Things to watch live: agent steps per run (target 1), "error" trace lines (tool-call format problems), wrong
groundings (rejected cards), extraction misses (e.g. chest_burning, the penicillin allergy, discharge, ECG ordered).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from bayan.brain import agentkit, copilot, llm  # noqa: E402
from bayan.brain.state import Consultation, fmt_t  # noqa: E402
from tests.test_copilot import GOLDEN_TURNS, golden_agent_factory, golden_backend  # noqa: E402

ICON = {"critical": "🔴", "caution": "🟠", "info": "⚪"}


def show_card(c: dict, tag: str) -> None:
    extra = f" · Ask: “{c['ask_text']}”" if c.get("ask_text") else ""
    rules = f" [{', '.join(c['rule_ids'])}]" if c.get("rule_ids") else ""
    print(f"    {tag} {ICON.get(c['severity'], '?')} {c['id']} {c['kind']}/{c['source']} {c['status']}: "
          f"{c['title']}{rules} (grounding {c['grounding']}){extra}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="scripted fake LLM + fake agent (no network)")
    ap.add_argument("--quiet", action="store_true", help="hide the trace lines")
    args = ap.parse_args()
    offline = args.offline or not (os.environ.get("HF_TOKEN") or llm.HF_TOKEN)
    if offline:
        print("== OFFLINE: scripted extraction + scripted agent (set HF_TOKEN for the live models) ==")
        llm.set_backend(golden_backend)
        agentkit.set_model_factory(golden_agent_factory)
    else:
        print(f"== LIVE: extraction {llm.LLM_MODEL} on {llm.LLM_PROVIDER} (fallback {llm.LLM_FALLBACK_PROVIDER}); "
              f"agent {agentkit.AGENT_MODEL} on {agentkit.AGENT_PROVIDER}, reasoning {agentkit.AGENT_REASONING}, "
              f"max_tokens {agentkit.AGENT_MAX_TOKENS}; BAYAN_AGENT={os.environ.get('BAYAN_AGENT', 'on')} ==")

    consult = Consultation(patient_lang="ne")
    copilot.attach(consult)
    trace_seen = 0
    card_state: dict[str, tuple] = {}
    t_all = time.time()

    def report(label: str) -> None:
        nonlocal trace_seen
        if not args.quiet:
            for t in consult.trace[trace_seen:]:
                print(f"    · {fmt_t(t['t_min'])} {t['kind']:<5} {t['text']}")
        trace_seen = len(consult.trace)
        for c in consult.cards.all_cards():
            sig = (c["status"], c["severity"], tuple(c.get("rule_ids") or []))
            if card_state.get(c["id"]) != sig:
                show_card(c, "NEW " if c["id"] not in card_state else "CHG ")
                card_state[c["id"]] = sig

    for step in GOLDEN_TURNS:
        if step[0] == "tick":
            consult.set_scenario_time(step[1])
            print(f"\n[{fmt_t(step[1])}] (timer tick)")
            copilot.tick(consult)
            report("tick")
            continue
        if step[0] == "ack":
            consult.set_scenario_time(step[1])
            print(f"\n[{fmt_t(step[1])}] doctor acknowledges the critical cards")
            for c in consult.cards.open_cards():
                if c["source"] == "rules" and c["severity"] == "critical":
                    consult.cards.act(c["id"], "acknowledge", user="doctor")
            report("ack")
            continue
        t, role, lang, text, english, drugs = step
        consult.set_scenario_time(t)
        turn = consult.add_turn(role, lang, text, english=english or text)
        print(f"\n[{fmt_t(t)}] {turn.id} {role.upper()} ({lang}): {text}" + (f"\n          EN: {english}" if english else ""))
        if role == "doctor" and drugs:
            g0 = time.perf_counter()
            held = copilot.prescription_gate(consult, drugs, turn.english, turn.id)
            turn.held = bool(held)
            print(f"    gate ({(time.perf_counter() - g0) * 1000:.1f} ms): "
                  + ("HELD by " + ", ".join(h["rule_id"] for h in held) if held else "spoken"))
        s = copilot.think_now(consult)
        report(turn.id)
        a = s.get("agent") or {}
        print(f"    run: {s['latency_s']:.2f}s (extract {s.get('extract_s', 0):.2f}s, agent {a.get('latency_s', 0):.2f}s, "
              f"{a.get('steps', 0)} step(s)) · extract tok {s['extract_tokens'][0]}/{s['extract_tokens'][1]} · "
              f"agent tok {s['agent_tokens'][0]}/{s['agent_tokens'][1]}"
              + (f" · agent skipped ({s['agent_skipped']})" if s.get("agent_skipped") else "")
              + (f" · fallback {s['fallback']}" if s.get("fallback") else "")
              + (f" · ERROR {s['error']}" if s.get("error") else ""))

    # ---------------------------------------------------------------- expected outcome
    cards = consult.cards.all_cards()

    def rule_card(rid):
        return next((c for c in cards if c["source"] == "rules" and rid in (c.get("rule_ids") or [])), None)

    asks = [c for c in cards if c["kind"] == "ask"]
    checks = [
        ("npi-005 idiom card", any(c["kind"] == "idiom" and c["grounding"] == "npi-005" for c in cards)),
        ("Chest-pain workup card has WORK-CHEST-01..04", bool(rule_card("WORK-CHEST-02")) and sorted(
            rule_card("WORK-CHEST-02")["rule_ids"]) == ["WORK-CHEST-01", "WORK-CHEST-02", "WORK-CHEST-03", "WORK-CHEST-04"]),
        ("ALG-PEN-01 critical card", bool(rule_card("ALG-PEN-01")) and rule_card("ALG-PEN-01")["severity"] == "critical"),
        ("ask card about radiation/sweating", any(any(w in (c.get("ask_text") or "").lower()
                                                     for w in ("spread", "radiat", "arm", "sweat")) for c in asks)),
        ("all rule cards resolved after the corrected plan", not [c for c in consult.cards.open_cards()
                                                                  if c["source"] == "rules"]),
        ("no DOSE-PARA rule", not any(c for c in cards if any(r.startswith("DOSE-PARA") for r in c.get("rule_ids") or []))),
        ("no critical card from the agent", not [c for c in cards if c["source"] != "rules" and c["severity"] == "critical"]),
        ("amoxicillin withdrawn, paracetamol prescribed", [m["drug"] for m in consult.state["prescribed_meds"]] == ["paracetamol"]),
    ]
    print("\n== Expected outcome ==")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    extra = [c for c in cards if c["source"] in ("agent", "fallback")]
    print(f"  ({len(extra)} agent/fallback card(s): " + "; ".join(f"{c['kind']} '{c['title']}'" for c in extra) + ")")

    print("\n== Audit (decision-support log) ==")
    for a in consult.audit:
        if a["action"] in ("shown", "acknowledge", "override", "dismiss", "rejected", "resolved", "escalated"):
            print(f"  {fmt_t(a['t_min'])} {a['action']:<11} {a.get('card_id') or '-':<5} {a.get('rule_id') or a.get('grounding') or ''}"
                  + (f" · {a['reason']}" if a.get("reason") else ""))

    m = consult.outputs.get("metrics", [])
    tin = sum(x["input_tokens"] for x in m)
    tout = sum(x["output_tokens"] for x in m)
    agent_runs = [x for x in m if x["agent_ran"]]
    print("\n== Metrics (consult.outputs['metrics']) ==")
    print(f"  think runs: {len(m)} · agent runs: {len(agent_runs)} · skipped: {sum(1 for x in m if x['agent_skipped'])}")
    if m:
        lat = sorted(x["latency_s"] for x in m)
        print(f"  run latency p50 {lat[len(lat) // 2]:.2f}s · max {lat[-1]:.2f}s")
    if agent_runs:
        al = sorted(x["agent_s"] for x in agent_runs)
        print(f"  agent latency p50 {al[len(al) // 2]:.2f}s · steps/run {sum(x['agent_steps'] for x in agent_runs) / len(agent_runs):.2f}")
    cost = agentkit.cost_usd(tin, tout)
    print(f"  tokens in/out: {tin}/{tout} · cost ${cost:.4f} for {len(m)} turns "
          f"(≈ ${cost / max(1, len(m)) * 40:.3f} for a 40-turn consultation)")
    print(f"  wall time {time.time() - t_all:.1f}s")
    return 0 if all(ok for _n, ok in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
