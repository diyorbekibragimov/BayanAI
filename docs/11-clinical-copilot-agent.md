# 11 · The Clinical Copilot: a Deterministic Spine Plus Two smolagents Agents

> **One line:** after every turn, a deterministic spine (idiom lexicon, fact extraction, state merge, 81 rules) runs first and is logged as tool calls. Then, only if something is new, a **smolagents** `ToolCallingAgent` on `gpt-oss-120b` proposes 0–2 cards for the doctor: a question worth asking, workup that may be missing, or a pattern worth noticing. A second agent runs the wrap-up. The doctor acts on every card; the agents never speak to the patient, prescribe or diagnose.
>
> **Code:** `bayan/brain/copilot.py` (think loop, gate, tools), `bayan/brain/agentkit.py` (smolagents plumbing), `bayan/brain/cards.py` (guardrails), `bayan/brain/wrapup.py` (wrap-up agent).
>
> **Status (2026-11-07):** built, tested (269 offline tests with fake models; live `scripts/smoke_e2e.py` 17/17 on the merged code) and wired into the UI shell in the local code, not yet deployed to the Space. `bayan/copilot.py` maps these cards to the Notes panel.
>
> **Read with:** [03 · Architecture](03-architecture.md) · [05 · Clinical Safety](05-clinical-safety-and-cultural-intelligence.md) · [07 · Budget](07-compute-budget-and-efficiency.md)

---

## 1. Why an agent, and why not only an agent

A translator says what was said. Bayan also says **what wasn't**: radiation of pain not asked, no ECG before discharge, an idiom that can hide cardiac pain. That needs reasoning over the whole consultation, which is what the agent adds.

Safety cannot depend on a model deciding to call a tool. So the checks that can raise an alert run as plain code on every turn, and the agent only sees their results.

| Layer | Runs | Can raise | LLM |
|---|---|---|---|
| Prescription gate | Synchronously on doctor turns with drugs | Critical (holds the sentence) | None |
| Deterministic spine | Every think run | Critical / caution / info rule cards, idiom cards | One extraction call |
| Copilot agent | Only when the spine found something new | Ask / missed / observation, **at most caution** | 1 step typically |
| Fallback | Agent off, failed, timed out or no valid card | Up to 2 "ask" cards | None |

## 2. One think run

Triggered by `on_turn()`, debounced ~1.2 s, at most one run in flight per consultation (a turn arriving mid-run triggers exactly one rerun).

| Step | Trace line | What it does |
|---|---|---|
| 1 | `lookup_idiom('gyastrik') → npi-005` | Lexicon match on new patient turns (native script, romanized, loanwords); idiom card posted at once |
| 2 | `update_state → +chest_burning, …` | One `gpt-oss-120b` JSON-schema call on **Groq** (Cerebras fallback, then a keyword fallback). Courtesy turns ("okay, thank you") skip it; a doctor's plain question waits and is extracted with the patient's answer (`update_state deferred: …`) |
| 3 | `check_safety_rules → ALG-PEN-01, WORK-CHEST-02, …` | All 81 rules → rule cards; `WORK-CHEST-*` collapse into one "Chest-pain workup" card; ask/missed cards whose checklist item is now done resolve themselves |
| 4 | `copilot agent: …` or `copilot skipped: nothing new` | smolagents run on **Cerebras**, reasoning medium |
| 5 | `fallback (agent failed): 2 ask card(s)` | Deterministic ask cards from the idiom's clarifying questions and the open checklist |

Per-run latency, tokens and cost go to `consult.outputs["metrics"]`. `BAYAN_AGENT=off` disables the LLM agent (fallback only).

Synchronous hooks for the talk loop, no LLM: `prescription_gate()` (intent-aware: `prescribe` is checked and holds on a critical hit, `stop` removes the drug from the state, a mention is ignored; a missing intent counts as prescribe, about 3 ms) and `record_allergies()` (so the gate never waits for the background extractor).

## 3. The copilot agent's tools

The task prompt already contains the recent transcript (new turns marked), the compact state, fired rules, idiom hits, the open checklist, open and dismissed cards, and the list of valid grounding ids. So a typical run is **one LLM step**: a single `final_answer` call.

| Tool | Returns | Grounded in |
|---|---|---|
| `lookup_idiom(phrase, lang="")` | Literal meaning, likely meanings, red flags it can mask, clarifying questions, tags | `data/idiom_lexicon.json` (59 entries) |
| `lookup_drug(name)` | Generic name, classes, the curated rules that mention it | `data/safety_rules.json` meta + rules |
| `check_safety_rules()` | Rules firing on the current state (read-only) | Rule engine |
| `final_answer(cards)` | Posts 0–2 cards through the card store and **ends the run** | Replaces smolagents' default `final_answer` |

All tools are read-only except `final_answer`, which goes through the same guardrails as every other card. There is no web search, no free-form medical lookup and no tool that speaks to the patient. A fixable mistake (bad grounding, missing evidence, a "critical" severity) raises once with a short message; the model gets one retry.

## 4. Cards the doctor sees

| Kind | Source | Example (golden path) | Doctor actions |
|---|---|---|---|
| **Safety** | Rules | Penicillin allergy reported vs amoxicillin (`ALG-PEN-01`, critical) | Acknowledge · override (logged) |
| **Missed** | Rules or agent | Chest-pain workup: discharge with no ECG or troponin (`WORK-CHEST-01…04`) | Acknowledge · accept · dismiss |
| **Idiom** | Lexicon | *gyastrik* (ग्यास्ट्रिक): usually dyspepsia; can mask cardiac pain (`npi-005`) | Dismiss |
| **Ask** | Agent or fallback | "Does the burning spread to your arm, jaw or back?" | **Ask** (Bayan translates and speaks it) · dismiss |
| **Observation** | Agent | A dose stated twice with different numbers | Accept · dismiss |

Every card shows why: quoted utterances plus the rule, lexicon entry or checklist item behind it. A "wrong fact" action records an extraction error.

## 5. Guardrails (enforced in code, `bayan/brain/cards.py`)

| Rule | Enforcement |
|---|---|
| Only the rule engine raises **critical** | Agent and fallback cards above caution are rejected |
| Every agent card cites real evidence | Utterance ids must exist in the transcript |
| Every agent card has a real grounding | An existing rule, idiom or checklist id (an observation may cite an utterance id) |
| No duplicates of what is on screen | Dedupe on kind + grounding + normalised title, fuzzy match on the question; "missed" cards for workup a fired rule already flags are dropped |
| No alert fatigue | At most 3 open "ask" cards; a dismissed card never returns in that consultation |
| The agent never speaks to the patient | Only the doctor's "Ask" tap queues speech |
| Bounded cost and time | `max_steps=4`, 20 s timeout per run (late cards ignored), 200k-token cap per consultation, no extra LLM call at `max_steps` |
| Audit | Every card change and doctor action lands in an append-only audit |

## 6. smolagents details that mattered (verified against 1.26.0)

- `InferenceClientModel(model_id="openai/gpt-oss-120b", provider="cerebras", …)` with `extra_body={"reasoning_effort": "medium"}` and `max_tokens` 6000 (reasoning tokens count against it).
- smolagents' 3.8k-character default system prompt is replaced by a two-line template; the clinical instructions go in `instructions`; tool schemas go in the API `tools` field.
- A user tool named `final_answer` replaces the default one, so posting the cards and ending the run is one call.
- `provide_final_answer()` at `max_steps` is overridden to a no-op (it would cost one more LLM call).
- Measured failures: reasoning **"high"** gave empty replies at ~12 s; on **Groq**, gpt-oss called a nonexistent `json` tool. Both agents therefore run on Cerebras only, and failures fall back to deterministic code, never to Groq.

## 7. Wrap-up agent

`wrapup.run_wrapup(consult, agentic=True)` runs a second `ToolCallingAgent` with two coarse tools, so a typical run is two tool steps plus the final answer:

| Tool | Does |
|---|---|
| `draft_outputs` | Note and care plan in parallel (the note is one JSON-schema call, map-reduce over chunks for long consultations; the care plan is a deterministic skeleton plus one call for plain-English and patient-language lines), then every medicine re-checked by the rule engine and `check_care_plan` (numbers, stopped drugs, 999, missing translations) |
| `render_outputs` | Consultation note PDF, patient sheet PDF, care-plan audio, `wa.me` and `sms:` links |

The agent is told never to write clinical content itself. Any failure, timeout or skipped step falls back to the same steps in a fixed order, reusing whatever the agent finished, so the outputs always exist.

## 8. Measured latency and cost

Live golden path, 9 turns, text turns via `scripts/smoke_e2e.py` (2026-11-07):

| | Measured |
|---|---|
| Copilot agent run | ~1.2–1.6 s, 1 step (p50 ~1.8 s on the merged code) |
| Extraction call | ~1.1 s |
| Wrap-up (agentic) | ~6–8 s |
| Consultation brain (extraction + agent) | ≈ $0.015 |
| Wrap-up | ≈ $0.004 |
| 40-turn consultation | ≈ $0.06 (**estimate** scaled from the above) |

Not included: the talk-loop translation calls and the GPU worker's hours. Prices used by the cost meter: Cerebras $0.35 / $0.75 and Groq $0.15 / $0.75 per 1M input / output tokens (`bayan/brain/llm.py`).

## 9. Evaluation

| What | How | Status |
|---|---|---|
| Golden-path cards | `tests/test_copilot.py` (scripted fake models) and `scripts/smoke_e2e.py` live: gyastrik idiom card, `ALG-PEN-01` critical with amoxicillin held, one chest-pain workup card covering `WORK-CHEST-01…04`, an ask card, all rule cards resolved after the corrected plan | 17 live checks |
| Authority | No critical card from an agent; fake agents that try are rejected and fall back | Tested offline and live |
| Failure paths | Agent exception, timeout with late cards, stringified or missing cards, fixable error with one retry | Tested offline |
| Model quality | Fake models test our logic, not the model. One live scenario so far | Limitation |

## 10. Where it can go next

- More live scenarios (heat illness, pregnancy, abdominal pain) next to the golden path.
- Clinician review of the rules and lexicon before any pilot.
- A smaller fine-tuned extractor ([06](06-fine-tuning-plan.md), not trained) if extraction cost or latency becomes the bottleneck.
