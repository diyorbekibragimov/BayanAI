# 07 · Compute Budget & Efficiency: $100, Spent on Purpose

> **Judging criterion:** "Efficiency: smart, resourceful use of your compute budget." The pool is **$100 per team, shared, with no top-ups**, and **Jobs, Inference Endpoints and Inference Providers are billed per minute** ([handbook](https://huggingface.co/spaces/qai-hackathon/handbook)).
> **Our position:** one model (`openai/gpt-oss-120b`) on HF Inference Providers, routed by job to the cheaper or the faster provider, plus one private L4 GPU Space for speech. **Measured live on the 9-turn golden path: about $0.015 for the consultation brain (extraction + copilot agent) and about $0.004 for the wrap-up.** A 40-turn consultation is estimated at about $0.06. These numbers exclude the talk-loop translation calls and GPU-worker hours. We keep **at least $25 as an untouchable reserve**. Actual total spend: ⟨measure: billing page⟩.
>
> **Read with:** [03 Architecture](03-architecture.md) · [04 Models & Languages](04-models-and-languages.md) · [08 Build Plan](08-build-plan.md) · [09 Pitch & Demo](09-pitch-and-demo.md) · [11 Clinical Copilot Agent](11-clinical-copilot-agent.md)

---

## 1. Verified price sheet (checked 2026-11-06; LLM prices re-checked 2026-11-07)

Prices change. Re-check the live sources before any big run: `hf jobs hardware`, `GET https://huggingface.co/api/jobs/hardware`, `GET https://router.huggingface.co/v1/models`.

### Compute you rent by the hour (billed per minute)

| Item | Price | Source |
|---|---|---|
| Jobs `cpu-basic` / `cpu-upgrade` | $0.01/h / $0.03/h | `hf jobs hardware`, [Jobs pricing](https://huggingface.co/docs/hub/jobs-pricing) |
| Jobs `t4-small` / `l4x1` | $0.40/h / $0.80/h | same |
| Jobs `a10g-small` / `a10g-large` | $1.00/h / $1.50/h | same |
| Jobs `l40sx1` | $1.80/h | same |
| Jobs **`a100-large`** (80 GB) | **$2.50/h** | same |
| Jobs `h200` | $5.00/h | same |
| Jobs exposed ports | +$0.01/h | [Jobs pricing](https://huggingface.co/docs/hub/jobs-pricing) |
| Endpoints, AWS `nvidia-t4` x1 / `nvidia-l4` x1 / `nvidia-a10g` x1 | $0.50 / $0.80 / $1.00 per h | [Endpoints pricing](https://huggingface.co/docs/inference-endpoints/pricing) |
| Endpoints, GCP `nvidia-l4` x1 | $0.70/h | same |
| Endpoints, AWS `nvidia-l40s` x1 / `nvidia-a100` x1 | $1.80 / $2.50 per h | same |
| Endpoints, AWS CPU `intel-spr` x4 / x16 | $0.134 / $0.536 per h | same |
| Spaces CPU Basic / CPU Upgrade | free / $0.03/h | [Spaces GPUs](https://huggingface.co/docs/hub/spaces-gpus) |
| Spaces T4 small / **L4** / A10G small | $0.40 / **$0.80** / $1.00 per h | same |
| ZeroGPU | free within the daily quota (unauthenticated 2 min, free account 5 min, PRO 40 min); beyond that **$1 per 10 min**, PRO / Team / Enterprise only | [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu) |

Billing details that matter:

- **Upgraded Spaces run, and bill, indefinitely unless you set a sleep time or pause them** ([Spaces GPUs](https://huggingface.co/docs/hub/spaces-gpus)). This applies to our voice worker.
- **Jobs** bill only while Starting or Running. The **default timeout is 30 minutes** ([pricing](https://huggingface.co/docs/hub/jobs-pricing)). We ran no training Jobs for the build.
- **Endpoints** bill while initializing or running. We do not use them.

### Pay-per-use APIs (Inference Providers, routed and billed by HF at provider rates)

HF charges "the same rates as the provider, with no additional fees" ([Providers pricing](https://huggingface.co/docs/inference-providers/pricing)). LLM prices are USD per 1M tokens, input / output, from the live router listing (the same values are in `bayan/brain/llm.py`).

| Model · provider | Price | Listed throughput | Use in Bayan |
|---|---|---|---|
| `openai/gpt-oss-120b` · **cerebras** | $0.35 / $0.75 | ~1,170 tok/s | **Talk-loop translation, copilot agent, wrap-up agent and wrap-up writing** |
| `openai/gpt-oss-120b` · **groq** | **$0.15** / $0.75 | ~420 tok/s | **Background clinical-fact extraction** (and fallback for non-agent brain calls) |
| `openai/gpt-oss-120b` · novita | $0.05 / $0.25 | ~190 tok/s | Not used |
| `hexgrad/Kokoro-82M` | per character (DeepInfra lists $0.99 / 1M characters) | | Optional English doctor voice, off by default (`provider="auto"`) |
| `openai/whisper-large-v3(-turbo)`, `ResembleAI/chatterbox`, small LLMs | DeepInfra list prices | | **Not used.** Whisper runs on our own GPU worker; no Chatterbox; no small model |

Throughput is the router's listed figure, not our measurement. **Check the [usage page](https://huggingface.co/settings/inference-providers/overview) against the in-code cost record** (`llm.USAGE`, `consult.outputs["metrics"]`).

**Not on any provider (needs our own GPU):** IndicConformer (Indic ASR) and Indic Parler-TTS (Indic speech). No Inference Provider serves Indic ASR or TTS today. We put them, plus Whisper turbo and VoxLingua107, on **one private L4 GPU Space** (`dullgrey/team-qh-129-bayan-voice`, `l4x1`, $0.80/h, sleeps when idle), called with `gradio_client` ([04 §0](04-models-and-languages.md)). It is the only fixed-cost item in the architecture.

---

## 2. The $100 budget, line by line

| # | Line item | Basis | Planned | **Cap** |
|---|---|---|---|---|
| 1 | Build-time API calls (LLM while developing; live smoke runs at about $0.02 each) | §1 provider prices | $4.00 | **$8.00** |
| 2 | GPU voice-worker Space during integration (L4, sleep when idle) | $0.80/h × ~7.5 GPU-h | $6.00 | **$10.00** |
| 3 | **Judging-day GPU worker** (awake in the judging window, asleep otherwise) | 1 × L4 Space $0.80/h × 8 h | $6.40 | **$8.00** |
| 4 | **Judging-day API traffic** (rehearsals, video takes, judges' runs) | ~200 runs × $0.02–0.06 (measured golden path to estimated 40-turn visit) + translation calls | $6.00 | **$12.00** |
| 5 | App Space on `cpu-upgrade` | $0.03/h × ~24 h | $0.75 | $1.00 |
| 6 | Fine-tune data, training, eval, serving ([06](06-fine-tuning-plan.md)) | **Not run** | $0.00 | $0.00 |
| 7 | Fanar Endpoint | **Dropped** | $0.00 | $0.00 |
| | **Planned subtotal** | | **≈ $23** | **$39** |
| | **Hard reserve (never planned against)** | ≥ 25% of the pool | | **$25.00** |
| | **Unallocated slack** | | | $36 |

Items 3 and 4 together (cap $20) cover the **≥ $15 judging-day reserve** required by [08 §6](08-build-plan.md). Actual spend per line: ⟨measure: billing page and spend log (§9)⟩. The GPU worker's real hours are the largest unknown; read them off the billing page.

**Ownership:** the captain holds the pool. The Story owner (D in [08](08-build-plan.md)) keeps the spend log (§9) and reads the [billing page](https://huggingface.co/settings/billing) at every checkpoint.

---

## 3. Cost per consultation

### Provider routing (who runs what)

| Job | When it runs | Model · provider | Reasoning | Price (in / out per 1M) | Measured latency |
|---|---|---|---|---|---|
| Talk-loop translation | Every utterance | gpt-oss-120b · Cerebras | low | $0.35 / $0.75 | not in the measured run (text turns) |
| Clinical-fact extraction | Background; skipped for courtesy turns; plain doctor questions batched with the answer | gpt-oss-120b · **Groq**, Cerebras fallback | medium | **$0.15** / $0.75 | ~1.1 s per call |
| Copilot agent (smolagents) | Background, only when the deterministic steps found something new | gpt-oss-120b · Cerebras only | medium | $0.35 / $0.75 | ~1.2–1.6 s per run, 1 step |
| Wrap-up (note + care plan, wrap-up agent) | Once, at "end consultation" | gpt-oss-120b · Cerebras (agent Cerebras-only) | medium | $0.35 / $0.75 | ~6–8 s |
| Rules (81), idiom lexicon, prescription gate | Every turn | Code, no LLM | n/a | $0 | gate ~3 ms |
| Role ID, ASR, patient TTS | Every utterance | GPU worker Space (L4) | n/a | $0.80/h while awake | TTS first audio ~2.2–3.1 s ([04 §7](04-models-and-languages.md)) |

Why not one provider for everything: Groq is cheaper on input and works for JSON-schema extraction, but gpt-oss tool calling through Groq failed (it called a nonexistent `json` tool), so the agents stay on Cerebras. Reasoning `high` was measured to fail (empty replies, about 12 s), so nothing uses it.

### Measured result (one live scenario)

Golden path, 9 turns, run with `python scripts/smoke_e2e.py` (text turns, so the voice worker and the translation calls are not involved):

| Component | Measured cost |
|---|---|
| Consultation brain: extraction (Groq) + copilot agent (Cerebras) | **≈ $0.015** |
| Wrap-up: note + care plan + wrap-up agent | **≈ $0.004** |
| **Total, 9-turn golden path** | **≈ $0.019** |
| Estimate for a 40-turn consultation | ≈ $0.06 |

**Honest caveats** (say them before a judge asks):

1. **One scenario** was measured live. The 40-turn figure is an estimate, not a measurement.
2. **Not included:** talk-loop translation calls (one Cerebras call per utterance), GPU-worker hours, and the optional Kokoro doctor voice.
3. The code records tokens and cost per call, priced at the provider actually used (`bayan/brain/llm.py` `USAGE`, per-run `consult.outputs["metrics"]`). Compare it with the billing page.

### Fixed GPU cost, amortised

| One L4 GPU Space at $0.80/h, awake | 1 consultation/h | 4 / h | 12 / h |
|---|---|---|---|
| Fixed cost per consultation | $0.80 | $0.20 | $0.067 |

During a hackathon demo with one user, the awake GPU costs more per consultation than all the LLM tokens. That is why the worker sleeps when idle. The worker runs one GPU job at a time (`queue(default_concurrency_limit=1)`), so concurrent-consultation capacity on one L4 is **unverified**. Benchmark it before quoting a hospital-scale number.

---

## 4. Efficiency techniques (implemented)

| # | Technique | Saves | Where |
|---|---|---|---|
| 1 | **One model, routed by job**: Cerebras (fast) for the talk loop and agents, Groq (cheaper input) for background extraction | Lower input price on the most frequent background call | `bayan/brain/extract.py`, `llm.py` |
| 2 | **Deterministic spine first**: idiom lexicon, all 81 rules and the prescription gate are code | $0 per check, auditable, ~3 ms gate | `bayan/brain/rules.py`, `idioms.py`, `copilot.py` |
| 3 | **Copilot agent only when something is new**: no new fact, idiom or rule change → the agent is skipped | Most quiet turns cost no agent call | `bayan/brain/copilot.py` |
| 4 | **Trivial turns skipped**: courtesy turns ("okay, thank you") are not extracted; a "yes" that answers a question is | Fewer extraction calls | `copilot.is_trivial` |
| 5 | **Doctor questions batched with the answer**: a plain question waits (up to 20 s) and is extracted with the patient's reply | One extraction call instead of two, with better context | `BAYAN_DEFER_QUESTIONS` |
| 6 | **Bounded extraction input**: a short window of recent turns plus a compact state summary, not the whole transcript | Input tokens stay flat as the visit grows | `bayan/brain/extract.py` |
| 7 | **Agent prompt diet**: smolagents' 3.8k-character default system prompt replaced by a 2-line template; one `final_answer(cards)` call posts all cards and ends the run (typically 1 step); no extra final-answer LLM call at `max_steps` | Fewer tokens and steps per run | `bayan/brain/agentkit.py` |
| 8 | **Hard caps**: agent `max_steps` 4, 20 s timeout, 200k-token cap per consultation, `max_tokens` on every call | A runaway agent cannot bill | `agentkit.py`, `copilot.py` |
| 9 | **Structured outputs** (`json_schema`, then `json_object`, then plain) | Fewer parse failures and retries | `llm.py` |
| 10 | **Wrap-up in parallel**: note and care plan are independent calls; two coarse agent tools; map-reduce only for long consultations | ~6–8 s wall clock | `bayan/brain/wrapup.py` |
| 11 | **Server-side VAD**: Silero in FastRTC; only utterances reach the GPU worker; under 0.3 s dropped | No GPU time on silence | `app.py` |
| 12 | **Batched streaming TTS**: all short segments in one Parler call | First audio for a 3-sentence answer 9.9 s → ~2.2 s | `voice_worker/app.py` |
| 13 | **Cached consent text**: translated once per language (Nepali is built in) | One LLM call per language, not per visit | `bayan/consult.py` |
| 14 | **No paid calls in tests**: `tests/conftest.py` blocks every inference call; fake models; `smoke_e2e.py --offline` is free, the live run about $0.02 | Development without burning credits | `tests/`, `scripts/` |
| 15 | **Sleep time on the GPU Space** | No idle billing overnight | Spaces settings |

---

## 5. Serving, priced

The orchestrator UI runs on the app Space's CPU (`cpu-upgrade`). GPU is needed only for the voice worker.

| Option | GPU cost for an 8 h judging window | Status |
|---|---|---|
| **1 × private L4 GPU Space**, sleep when idle, awake during the window | $0.80 × 8 = **$6.40** | **Chosen** (`dullgrey/team-qh-129-bayan-voice`) |
| Inference Endpoint L4, scale-to-zero | $6.40 | Not used (cold starts return 503; Endpoint access was uncertain, §7) |
| ZeroGPU worker Space | $0 within quota | Not used (each call waits for a GPU allocation) |
| App Space upgraded to L4, voice co-located | $6.40, plus every hour it is left on | Not used |

---

## 6. How to present this to judges (slide-ready)

**Slide title:** *One open model, two providers, one GPU: measured cost of the clinical brain*

| | **Bayan AI (measured, 9-turn golden path)** |
|---|---|
| Consultation brain (extraction + copilot agent) | **≈ $0.015** |
| Wrap-up (note + care plan) | **≈ $0.004** |
| 40-turn consultation (estimate) | ≈ $0.06 |
| Safety checks | **Deterministic rules, $0, ~3 ms gate** |
| Copilot agent | ~1.2–1.6 s per run, 1 step, only when something is new |
| Total spent building and demoing | **$⟨measure⟩ of $100**, with ≥ $25 never touched |

Small print: excludes talk-loop translation calls and GPU-worker hours; one live scenario.

**20-second voice-over:** "Everything runs on one open model, gpt-oss-120b. The frequent background extraction goes to the cheaper provider, and the agent only runs when the rules or the lexicon found something new. Safety checks are code, so they cost nothing and cannot hallucinate. On our golden path the clinical brain cost about one and a half cents, plus less than half a cent for the notes, and the whole build used ⟨measure: $ spent⟩ of our $100."

Fill the `⟨measure⟩` markers from the spend log (§9) and the billing page. [09](09-pitch-and-demo.md) Q&A #6 pulls these numbers.

---

## 7. Account readiness: check before spending anything

These items can block a deliverable regardless of the budget. The captain should check them in **the first hour**.

| Check | Why | How |
|---|---|---|
| **Can the captain's account create a Gradio or Docker Space?** ✅ **Resolved (checked 2026-11-06 via the public Hub API):** the captain `dullgrey` is not PRO but already runs a Gradio Space (`dullgrey/clinic-bridge`) on **`cpu-upgrade`** ($0.03/h), billed to the team pool. Other teams' non-PRO accounts do the same (e.g. `plitip/team-qh-091-safesite-app`, `malmarri/team-qh-167-qatarsignals-app`, both on `cpu-upgrade`). | The general HF rule is: "Gradio and Docker Spaces … require a paid plan to create … Free personal accounts in good standing can still host up to 2 Gradio Spaces running on ZeroGPU" ([Spaces overview](https://huggingface.co/docs/hub/spaces-overview)). The hackathon credits evidently satisfy it. Teammates' personal accounts may still be blocked, which is why **everything is created under the captain's account**. | Create `dullgrey/team-qh-129-bayan-app` with hardware **`cpu-upgrade`**. Budget $0.03/h × ~24 h ≈ **$0.75**. Pause it at night if it isn't needed. |
| **PRO cannot be bought with credits** | "You can only pay for the PRO subscription with a credit card" ([billing](https://huggingface.co/docs/hub/billing)) | Fallbacks: a ZeroGPU Gradio Space (eligible account), or ask the organisers |
| **Can the account create Inference Endpoints?** | Endpoints are "accessible to Hugging Face accounts with an active subscription and credit card on file" ([pricing](https://huggingface.co/docs/inference-endpoints/pricing)), but the handbook says the pool covers Endpoints. A teammate token got `403 … missing permissions: inference.endpoints.read`. | Moot for the build: the voice worker runs on a GPU Space instead. |
| Do the credits cover Spaces hardware? | The billing FAQ lists "GPU Spaces" and "ZeroGPU extra quota" as credit uses ([billing](https://huggingface.co/docs/hub/billing)). The handbook lists Jobs, Endpoints and Providers. | Ask a mentor before upgrading a Space |
| Jobs work | Jobs need a positive credit balance ([Jobs guide](https://huggingface.co/docs/huggingface_hub/guides/jobs)) | `hf jobs run python:3.12 python -c "print(1)"` (about $0.0002) |

---

## 8. Cost guardrails checklist

**Before launching anything that bills**
- [ ] The $/h and the expected minutes are written in the spend log before launch.
- [ ] The GPU voice-worker Space has a sleep time: `hf spaces settings dullgrey/team-qh-129-bayan-voice --sleep-time 900`.
- [x] LLM calls have `max_tokens` set. Structured output is on. Agents have a step cap, a timeout and a per-consultation token cap.
- [x] Tests make no paid calls (`tests/conftest.py`); the live smoke run is about $0.02.

**Protect the public Space (anyone can click it)**
- [x] The Space uses the captain's token server-side, so every visitor would spend our credits. Access code gate (`BAYAN_ACCESS_CODE`) and a no-mic demo mode.
- [x] WebRTC connections are capped (6 concurrent, 1 h per stream).
- [ ] A global daily spend cap in the app (sum of the cost record). Not built.
- [x] No free-text "ask the LLM anything" box.

**While running**
- [ ] Read the [billing page](https://huggingface.co/settings/billing) and the [Providers usage page](https://huggingface.co/settings/inference-providers/overview) at every gate, and update the spend log.
- [ ] Stop rule: if actual spend passes **$50 before Saturday 08:00**, freeze all optional GPU hours.

**Before anyone sleeps (the handbook says "check before you leave at night")**
- [ ] The GPU worker Space is paused or asleep (`hf spaces pause dullgrey/team-qh-129-bayan-voice`). The app Space stays on `cpu-upgrade` (about $0.24 overnight) or is paused if nobody tests overnight.
- [ ] `hf jobs ps` shows nothing running.

**Judging day**
- [ ] Wake the voice worker 15 minutes before the slot (boot is about 99 s). Warm it with one request (`/benchmark` or `/langs`). Check the latency.
- [ ] After the slot: let it sleep again. Keep the app Space running on `cpu-upgrade` until the organisers confirm judging is closed.

**Kill switch (any teammate may run it)**

```bash
hf jobs ps                                          # should be empty
hf spaces pause dullgrey/team-qh-129-bayan-voice    # the GPU worker: the only hourly GPU cost
hf spaces pause dullgrey/team-qh-129-bayan-app      # last resort: the Space must be running at judging
```

---

## 9. Spend log (keep it in the repo or a shared sheet)

| Time (Doha) | Who | What | Flavor / model | Est. $ | Actual $ (billing page) | Running total |
|---|---|---|---|---|---|---|
| | | GPU voice worker hours | Space `l4x1` | | | |
| | | Providers usage (gpt-oss-120b, Kokoro) | Cerebras / Groq | | | |
| | | App Space | `cpu-upgrade` | | | |
| | | … | | | | |

The final row becomes the pitch number: "**$X of $100**".

---

## 10. Unverified items (do not state these as facts)

- End-to-end turn latency (end of speech → first translated audio). The ≤ 3 s figure is a target, not yet measured end to end.
- Cost of the talk-loop translation calls per consultation (not in the measured run).
- GPU-seconds per consultation on the L4, and the resulting worker $ per consultation.
- The 40-turn cost (≈ $0.06) is an estimate from one 9-turn live run.
- Concurrent-consultation capacity per L4 (the hospital-scale claim).
- Whether the cost recorded in code matches the HF invoice line by line. Confirm on the usage page.

---

## Sources

- Hackathon handbook (credits, per-minute billing, Jobs tips, judging criteria): https://huggingface.co/spaces/qai-hackathon/handbook
- Jobs pricing and billing: https://huggingface.co/docs/hub/jobs-pricing · Jobs guide: https://huggingface.co/docs/huggingface_hub/guides/jobs · live hardware: https://huggingface.co/api/jobs/hardware
- Inference Providers pricing (pass-through, credits): https://huggingface.co/docs/inference-providers/pricing · live model/price listing: https://router.huggingface.co/v1/models · structured outputs: https://huggingface.co/docs/inference-providers/guides/structured-output
- Inference Endpoints pricing: https://huggingface.co/docs/inference-endpoints/pricing · autoscaling and scale-to-zero: https://huggingface.co/docs/inference-endpoints/guides/autoscaling
- Spaces hardware, billing, sleep and pause: https://huggingface.co/docs/hub/spaces-gpus · Spaces overview (paid-plan requirement): https://huggingface.co/docs/hub/spaces-overview · ZeroGPU: https://huggingface.co/docs/hub/spaces-zerogpu · Hub billing FAQ: https://huggingface.co/docs/hub/billing
- DeepInfra list price (Kokoro): https://deepinfra.com/hexgrad/Kokoro-82M
