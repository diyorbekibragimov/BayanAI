"""End-to-end check of the Bayan brain on the golden path (docs/02 §8): live models when a token is available.

    python scripts/smoke_e2e.py                 # live: gpt-oss-120b extraction (Groq) + smolagents copilot and
                                                #       wrap-up agents (Cerebras); ~$0.03
    python scripts/smoke_e2e.py --offline       # scripted fake models, no network, no cost

Runs the scripted consultation as text turns (no audio: the voice worker is not involved), then "end consultation":
the wrap-up agent drafts the SOAP note and the Nepali care plan, re-checks every medicine against the rules and
renders both PDFs. Prints every agent tool call, pass/fail checks, latency and measured cost, and renders the PDF
pages to PNG for a visual check.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from bayan.brain import agentkit, copilot, llm, wrapup  # noqa: E402
from bayan.brain.state import Consultation, fmt_t  # noqa: E402
from tests.test_copilot import GOLDEN_TURNS, golden_agent_factory, golden_backend  # noqa: E402


def _token() -> str | None:
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    try:
        from huggingface_hub import get_token
        return get_token()
    except Exception:  # noqa: BLE001
        return None


def play(consult: Consultation) -> None:
    for step in GOLDEN_TURNS:
        if step[0] == "tick":
            consult.set_scenario_time(step[1])
            copilot.tick(consult)
            continue
        if step[0] == "ack":
            consult.set_scenario_time(step[1])
            for c in consult.cards.open_cards():
                if c["source"] == "rules" and c["severity"] == "critical":
                    consult.cards.act(c["id"], "acknowledge", user="doctor")
            continue
        t, role, lang, text, english, drugs = step
        consult.set_scenario_time(t)
        turn = consult.add_turn(role, lang, text, english=english or text)
        if role == "doctor" and drugs:
            turn.held = bool(copilot.prescription_gate(consult, drugs, turn.english, turn.id))
        copilot.think_now(consult)
    copilot.flush(consult)


def render_png(pdf: str, out_dir: Path, stem: str) -> list[str]:
    try:
        import fitz  # pymupdf
    except Exception:  # noqa: BLE001
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc):
            p = out_dir / f"{stem}_p{i + 1}.png"
            page.get_pixmap(dpi=110).save(str(p))
            paths.append(str(p))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--png-dir", default=None, help="where to write PDF page PNGs (default: <out_dir>/png)")
    args = ap.parse_args()

    token = None if args.offline else _token()
    if token:
        os.environ["HF_TOKEN"] = token
        llm.HF_TOKEN = token
        print(f"== LIVE: extraction gpt-oss-120b on {os.environ.get('BAYAN_EXTRACT_PROVIDER', 'groq')}; "
              f"copilot + wrap-up agents on {agentkit.AGENT_PROVIDER} (reasoning {agentkit.AGENT_REASONING}) ==")
    else:
        print("== OFFLINE: scripted fake models (no token or --offline) ==")
        from tests.test_outputs import make_backend   # scripted note writer + care-plan translator

        wrap_backend = make_backend()

        def offline_backend(messages, schema, max_tokens):
            # extraction prompts carry the NEW TURNS block; everything else is the wrap-up (note / care plan)
            if "NEW TURNS (extract from these):" in messages[-1]["content"]:
                return golden_backend(messages, schema, max_tokens)
            return wrap_backend(messages, schema, max_tokens)

        llm.set_backend(offline_backend)
        agentkit.set_model_factory(golden_agent_factory)

    consult = Consultation(patient_lang="ne")
    copilot.attach(consult)
    cost0 = llm.USAGE["cost_usd"]

    # ------------------------------------------------------------ consultation (think loop)
    t0 = time.time()
    play(consult)
    think_s = time.time() - t0
    runs = [m for m in consult.outputs.get("metrics", []) if isinstance(m, dict)]
    think_cost = sum(m.get("cost_usd", 0.0) for m in runs)
    n_trace = len(consult.trace)

    # ------------------------------------------------------------ end consultation (wrap-up agent)
    c1 = llm.USAGE["cost_usd"]
    t1 = time.time()
    out = wrapup.run_wrapup(consult, agentic=True, speak_fn=None, timeout_s=60)
    wrap_s = time.time() - t1
    wrap_llm_cost = llm.USAGE["cost_usd"] - c1
    wm = out.get("wrapup_metrics") or {}

    # ------------------------------------------------------------ what the agents did
    print("\n== Copilot agent: tool calls and decisions (think loop) ==")
    for t in consult.trace[:n_trace]:
        if t["kind"] in ("tool", "agent"):
            print(f"  {fmt_t(t['t_min'])} {t['kind']:<5} {t['text']}")
    print("\n== Wrap-up agent: tool calls ==")
    for t in consult.trace[n_trace:]:
        if t["kind"] in ("tool", "agent", "system", "error"):
            print(f"  {t['kind']:<6} {t['text']}")

    cards = consult.cards.all_cards()
    print("\n== Cards shown to the doctor ==")
    for c in cards:
        extra = f' · Ask: "{c["ask_text"]}"' if c.get("ask_text") else ""
        print(f"  {c['id']} {c['severity']:<8} {c['kind']:<11} {c['source']:<8} {c['status']:<12} {c['title']}{extra}")

    plan = out.get("care_plan") or {}
    meds = [m.get("name", "").lower() for m in plan.get("medicines", [])]
    avoid = " ".join((a.get("en") or "") for a in plan.get("avoid", [])).lower()
    note = out.get("note_md") or ""
    note_txt = consult.outputs.get("note_txt") or note

    def rule_card(rid):
        return next((c for c in cards if c["source"] == "rules" and rid in (c.get("rule_ids") or [])), None)

    checks = [
        ("idiom card npi-005 (gyastrik)", any(c["kind"] == "idiom" and c["grounding"] == "npi-005" for c in cards)),
        ("ALG-PEN-01 critical: amoxicillin held", bool(rule_card("ALG-PEN-01")) and rule_card("ALG-PEN-01")["severity"] == "critical"
         and any(t.held for t in consult.turns)),
        ("chest-pain workup card WORK-CHEST-01..04", bool(rule_card("WORK-CHEST-02")) and sorted(rule_card("WORK-CHEST-02")["rule_ids"])
         == ["WORK-CHEST-01", "WORK-CHEST-02", "WORK-CHEST-03", "WORK-CHEST-04"]),
        ("all rule cards resolved after the corrected plan", not [c for c in consult.cards.open_cards() if c["source"] == "rules"]),
        ("copilot posted an ask card (radiation/exertion/sweating)", any(c["kind"] == "ask" for c in cards)),
        ("no critical card from an agent", not [c for c in cards if c["source"] != "rules" and c["severity"] == "critical"]),
        ("state: amoxicillin withdrawn, paracetamol prescribed",
         [m["drug"] for m in consult.state["prescribed_meds"]] == ["paracetamol"]),
        ("wrap-up ran as an agent (not the fallback)", str(out.get("agentic")).startswith("agent") and out.get("agentic") != "agent→fallback"),
        ("clinical note written by the model with the standard headings", wm.get("note_source") not in (None, "fallback", "state")
         and all(s.lower() in note_txt.lower() for s in ("Allergies", "Presenting complaint", "History", "Assessment",
                                                         "Plan", "Medication changes", "Information given to patient"))),
        ("no utterance codes (u001…) in the clinical note", not re.search(r"\bu\d{3}\b", note_txt)),
        ("note records the penicillin allergy", "penicillin" in note.lower()),
        ("care plan: paracetamol, no amoxicillin", any("paracetamol" in m for m in meds) and not any("amoxi" in m for m in meds)),
        ("care plan: do not take penicillin", "penicillin" in avoid),
        ("care plan is in Nepali (Devanagari)", any("ऀ" <= ch <= "ॿ" for ch in str(plan))),
        ("doctor PDF rendered", bool(out.get("doctor_pdf")) and Path(out["doctor_pdf"]).exists()),
        ("patient PDF rendered", bool(out.get("patient_pdf")) and Path(out["patient_pdf"]).exists()),
        ("WhatsApp link built", str(out.get("wa_link") or "").startswith("https://wa.me/")),
    ]
    print("\n== Checks ==")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if out.get("warnings"):
        print("  warnings:", "; ".join(out["warnings"])[:400])

    pngs = []
    png_dir = Path(args.png_dir) if args.png_dir else Path(out.get("out_dir") or ".") / "png"
    for key, stem in (("doctor_pdf", "doctor_report"), ("patient_pdf", "patient_care_plan_ne")):
        if out.get(key):
            pngs += render_png(out[key], png_dir, stem)

    agent_runs = [m for m in runs if m.get("agent_ran")]
    print("\n== Latency and cost ==")
    print(f"  consultation: {len(runs)} think runs, {len(agent_runs)} copilot agent runs "
          f"(steps/run {sum(m.get('agent_steps', 0) for m in agent_runs) / max(1, len(agent_runs)):.2f}), "
          f"agent p50 {sorted(m['agent_s'] for m in agent_runs)[len(agent_runs) // 2] if agent_runs else 0:.2f}s, "
          f"wall {think_s:.1f}s, cost ${think_cost:.4f}")
    print(f"  wrap-up: mode {out.get('agentic')}, {wm.get('agent_steps', 0)} agent step(s), note via {wm.get('note_source')}, "
          f"{wrap_s:.1f}s, LLM calls ${wrap_llm_cost:.4f} (+ wrap-up agent tokens, see its trace line)")
    print(f"  all llm.chat calls this run: ${llm.USAGE['cost_usd'] - cost0:.4f}")
    print(f"  files: {out.get('doctor_pdf')} | {out.get('patient_pdf')}")
    if pngs:
        print(f"  page images: {png_dir}")
    failed = [n for n, ok in checks if not ok]
    print("\nRESULT:", "ALL PASS" if not failed else f"{len(failed)} FAIL: " + "; ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
