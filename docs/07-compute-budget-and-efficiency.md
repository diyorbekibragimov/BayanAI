# 07 · Compute Budget & Efficiency: $100, Spent on Purpose

> **Judging criterion:** "Efficiency: smart, resourceful use of your compute budget." The pool is **$100 per team, shared, with no top-ups**, and **Jobs, Inference Endpoints and Inference Providers are billed per minute** ([handbook](https://huggingface.co/spaces/qai-hackathon/handbook)).
> **Our position:** we plan to spend **about $30–35**, cap planned spend at **$58.60**, and keep **at least $25 (25%+) as an untouchable reserve**. A Bayan consultation costs about **$0.015 in marginal API spend**, about **3× less than a naive build** of the same features. The rest of this doc shows the arithmetic, so judges can check it.
>
> **Read with:** [03 Architecture](03-architecture.md) · [06 Fine-Tuning Plan](06-fine-tuning-plan.md) · [08 Build Plan](08-build-plan.md) · [09 Pitch & Demo](09-pitch-and-demo.md) · [10 Submission Checklist](10-submission-checklist.md)

---

## 1. Verified price sheet (checked 2026-11-06)

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
| Spaces T4 small / L4 / A10G small | $0.40 / $0.80 / $1.00 per h | same |
| ZeroGPU | free within the daily quota (unauthenticated 2 min, free account 5 min, PRO 40 min); beyond that **$1 per 10 min**, PRO / Team / Enterprise only | [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu) |

Billing details that matter:

- **Jobs** bill only while Starting or Running. The **default timeout is 30 minutes** ([pricing](https://huggingface.co/docs/hub/jobs-pricing)).
- **Endpoints** bill while initializing or running. When scaled to zero they cost nothing, but a **cold start takes minutes and the proxy returns 503** meanwhile. The default idle timeout is 1 h ([autoscaling](https://huggingface.co/docs/inference-endpoints/guides/autoscaling)).
- **Upgraded Spaces run, and bill, indefinitely unless you set a sleep time or pause them** ([Spaces GPUs](https://huggingface.co/docs/hub/spaces-gpus)).

### Pay-per-use APIs (Inference Providers, routed and billed by HF at provider rates)

HF charges "the same rates as the provider, with no additional fees" ([Providers pricing](https://huggingface.co/docs/inference-providers/pricing)). LLM prices are USD per 1M tokens, input / output, from the live router listing.

| Model · provider | Price | Listed throughput | Use in Bayan |
|---|---|---|---|
| `openai/gpt-oss-120b` · **novita** | **$0.05 / $0.25** | ~190 tok/s | Cheapest: synthetic data, batch eval |
| `openai/gpt-oss-120b` · **groq** | $0.15 / $0.75 | ~420 tok/s | Talk-loop translation (latency) |
| `openai/gpt-oss-120b` · cerebras | $0.35 / $0.75 | ~1,170 tok/s | Lowest-latency option |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` · deepinfra | $0.09 / $0.55 | ~24 tok/s | Alternative teacher / judge |
| `google/gemma-3-4b-it` · deepinfra | $0.05 / $0.10 | ~53 tok/s | **Proxy price for a 4B-class model** (our fine-tune is self-hosted, see §3) |
| `openai/whisper-large-v3` · deepinfra | **$0.00045 / audio-minute** | | Patient-side ASR for Tagalog/Filipino and Indonesian only; also the Arabic fallback ([DeepInfra](https://deepinfra.com/openai/whisper-large-v3)) |
| `openai/whisper-large-v3-turbo` · deepinfra | **$0.00020 / audio-minute** | | Doctor-side ASR, English ([DeepInfra](https://deepinfra.com/openai/whisper-large-v3-turbo)) |
| `ResembleAI/chatterbox` multilingual · deepinfra | **$1.00 / 1M characters** (23 languages incl. Arabic, Hindi, Swahili, Malay) | | TTS where supported ([DeepInfra](https://deepinfra.com/ResembleAI/chatterbox-multilingual)) |
| `hexgrad/Kokoro-82M` · deepinfra | $0.99 / 1M characters | | English TTS ([DeepInfra](https://deepinfra.com/hexgrad/Kokoro-82M)) |

Throughput is the router's listed figure, not our measurement. The ASR and TTS prices are DeepInfra's public list prices, and HF passes provider prices through. We have **not** confirmed that the per-minute and per-character prices appear identically on the HF invoice, so **check the [usage page](https://huggingface.co/settings/inference-providers/overview) after the first test calls.**

**Not on any provider (needs our own GPU):** the speech models of the **GPU voice worker** ([04 §0](04-models-and-languages.md)): `ai4bharat/indic-conformer-600m-multilingual` (Indic ASR, incl. Nepali), `mistralai/Voxtral-Mini-4B-Realtime-Arabic` (Arabic incl. Gulf), Omnilingual ASR (long-tail languages), `ai4bharat/indic-parler-tts` (Nepali, Malayalam and other Indic TTS), `facebook/mms-tts-*` and OmniVoice. No Inference Provider serves Indic ASR or TTS today. Our fine-tuned `dullgrey/team-qh-129-bayan` also needs a GPU. These are the only fixed-cost items in the architecture.

---

## 2. The $100 budget, line by line

| # | Line item | Basis | Planned | **Cap** |
|---|---|---|---|---|
| 1 | Build-time API calls (ASR / LLM / TTS while developing) | §1 provider prices; ~300 test turns | $4.00 | **$8.00** |
| 2 | Synthetic data generation ([06 §5](06-fine-tuning-plan.md)) | ~1M in + 1.5–3M out tokens on gpt-oss-120b · novita | $1.50 | **$5.00** |
| 3 | Data-gen runner Job | `cpu-basic` $0.01/h × 1 h | $0.01 | $0.10 |
| 4 | Fine-tune: smoke test + full run + ≤ 1 retry | `a100-large` $2.50/h × (0.33 + 0.75 + 0.75 h) | $3.50 | **$6.00** |
| 5 | Evaluation (base + FT on `l4x1`, teacher + judge via Providers) | $0.80/h × 2 × 0.75 h + ~$0.30 API | $1.50 | **$3.00** |
| 6 | GGUF conversion | [gguf-my-repo](https://huggingface.co/spaces/ggml-org/gguf-my-repo) Space | $0.00 | $0.00 |
| 7 | GPU serving during integration (voice-worker Endpoint: Indic/Arabic ASR + Indic/MMS TTS; FT model Endpoint; scale-to-zero, paused when idle) | L4 $0.80/h × ~7.5 GPU-h | $6.00 | **$10.00** |
| 8 | **Judging-day GPU serving** (same 2 Endpoints warm in the judging window, scale-to-zero otherwise) | 2 × L4 $0.80/h × 8 h | $12.80 | **$14.00** |
| 9 | **Judging-day API traffic** (rehearsals, video takes, judges' runs) | ~200 consultations × ~$0.015–0.05 | $3.00 | **$5.00** |
| 10 | *Optional:* `QCRI/Fanar-2-27B-Instruct` Endpoint for the Arabic doctor side (no provider serves it) | A100 $2.50/h × 3 h, only if items 1–9 are on track | $0.00 | $7.50 |
| | **Planned subtotal** | | **≈ $32.30** | **$58.60** |
| | **Hard reserve (never planned against)** | ≥ 25% of the pool | | **$25.00** |
| | **Unallocated slack** | | | $16.40 |

Items 8 and 9 together are the **≥ $15 judging-day reserve** required by [08 §6](08-build-plan.md). If serving runs on **ZeroGPU** instead of Endpoints (§5), items 7 and 8 drop to about $0. Planned spend then falls to **about $13**. The app Space itself on `cpu-upgrade` ($0.03/h, ≈ $0.75 for ~24 h) is paid from the unallocated slack.

**Ownership:** the captain holds the pool. The Story owner (D in [08](08-build-plan.md)) keeps the spend log (§9) and reads the [billing page](https://huggingface.co/settings/billing) at every checkpoint.

---

## 3. Cost per consultation

### Formulas

```
C_consult = C_asr + C_talk + C_think + C_wrap + C_tts (+ C_fixed / consultations_per_hour)

C_asr   = Σ_side  speech_minutes_side × price_per_audio_minute_side
C_llm   = Σ_calls (input_tokens × p_in + output_tokens × p_out) / 1e6
C_tts   = characters_spoken × price_per_char                 (provider TTS)
        = gpu_seconds × (endpoint $/h ÷ 3600)                 (self-hosted TTS / small model)
C_fixed = hourly price of any always-on GPU while warm
```

### Assumptions for one "standard consultation" (state them on the slide)

| Parameter | Value | Why |
|---|---|---|
| Wall-clock length | 12 min | Planning assumption, not a measured clinic average |
| Speech after browser VAD | 8 min (4 doctor, 4 patient) | Silence and room noise are never sent ([03](03-architecture.md)) |
| Turns | 40 (20 per side) | |
| Talk-loop translation call | 400 in / 100 out tokens | Short system prompt, last few turns as context |
| Think loop, **naive** | 40 calls × (3,000 in / 400 out) on gpt-oss-120b | Re-sends the growing transcript every turn |
| Think loop, **Bayan** | 40 STATE calls × (700 in / 150 out) on a 4B model, plus 5 IDIOM calls × (900 / 250) | Incremental state. The idiom call fires only when the retriever finds a candidate |
| Wrap-up | 1 call, 8,000 in / 1,500 out, gpt-oss-120b · groq | SOAP note + care plan |
| Patient-side TTS | 3,900 characters naive; 2,700 with the fixed-phrase cache (~30% of characters are canned lines) | Consent line, "please wait", medication-time phrases, red-flag instructions |

### Result (marginal API cost, prices from §1)

| Component | Naive build | Bayan | How Bayan saves |
|---|---|---|---|
| ASR | 12 min × $0.00045 = **$0.0054** | 4 × $0.00045 + 4 × $0.00020 = **$0.0026** | VAD; turbo for en/ar |
| Talk-loop translation (groq) | $0.0054 | $0.0054 | Same, because latency matters here |
| Think loop | 40 × 120B = **$0.0300** | 40 × 4B STATE + 5 × 4B IDIOM = **$0.0024** | Incremental state, small model, gated idiom calls |
| Wrap-up (1 call) | $0.0023 | $0.0023 | Same: the big model runs once |
| TTS (provider price) | $0.0039 | $0.0027 | Fixed-phrase cache |
| **Total per consultation** | **≈ $0.047** | **≈ $0.015** | **≈ 3× cheaper** |
| Consultations per $100 (marginal API spend only) | ≈ 2,100 | **≈ 6,500** | |
| Think-loop input tokens | 120,000 | 28,000 | **4.3× fewer** |

**Honest caveats** (say them before a judge asks):

1. The Bayan think-loop line uses a **4B-class serverless price as a proxy** (`gemma-3-4b-it` on DeepInfra). Our own fine-tune runs on **our** GPU, so its real cost is the GPU-hour (next table).
2. In the recommended stack ([04 §0](04-models-and-languages.md)), Nepali/Indic and Arabic **ASR** (IndicConformer, Voxtral-Arabic) and Indic **TTS** (Indic Parler-TTS) run on our **self-hosted** GPU voice worker, so the ASR and TTS lines above (priced with Whisper and Chatterbox provider rates) are proxies. Their real cost is GPU-seconds, and its real-time factor on L4 is **unverified**. Measure it in Phase 1. Example: if 2,700 characters take 150 GPU-seconds, that is 150 × $0.80/3600 ≈ **$0.033**, which would make TTS the largest line. That is a reason to cache phrases and to keep the Endpoint scaled to zero.
3. All numbers are **estimates from list prices**. The live cost meter in the UI footer ([08 Phase 4](08-build-plan.md)) replaces them with **measured** numbers for the pitch.

### Fixed GPU cost, amortised

| One L4 Endpoint at $0.80/h, warm | 1 consultation/h | 4 / h | 12 / h |
|---|---|---|---|
| Fixed cost per consultation | $0.80 | $0.20 | $0.067 |

During a hackathon demo with one user, a dedicated GPU is **more expensive per consultation than serverless tokens**. That is why the default path is Providers, and why GPUs scale to zero. In a hospital (many concurrent consultations, continuous batching on vLLM) the fixed cost spreads thin, and a 4B model on one in-country GPU becomes the cheaper and more private option. Concurrency capacity on an L4 is **unverified**. Benchmark it before quoting a number.

---

## 4. Efficiency techniques (what we do and why it counts)

| # | Technique | Saves | HF feature |
|---|---|---|---|
| 1 | **Three loops, three model tiers**: fast provider for talk, 4B for think, 120B once for wrap-up ([03 §2](03-architecture.md)) | Big-model calls drop from per-turn to once per consultation | Inference Providers routing |
| 2 | **Incremental state**: send previous state JSON plus new turns, never the whole transcript | 4.3× fewer think-loop input tokens | — |
| 3 | **Retriever-gated idiom calls**: the LLM is called only when the lexicon retriever scores a candidate | ~40 calls → ~5 | Hub dataset (lexicon) |
| 4 | **Deterministic safety rules**: drug–allergy, dose ceilings and missing workup are code, not tokens | $0 per check, and auditable | — |
| 5 | **Browser VAD**: only speech is uploaded | ~33% fewer audio-minutes in our assumption | — |
| 6 | **Right-sized ASR per language**: turbo for English; IndicConformer / Voxtral-Arabic / Omnilingual on the GPU worker; large-v3 only for Tagalog and Indonesian | 55% cheaper per minute on the English side, and no Whisper on languages where its FLEURS WER is ≥ 99% | Providers + GPU worker |
| 7 | **TTS cache** for fixed phrases (consent, wait, med-time, red flags), generated once and stored as Space assets | ~30% of TTS characters, plus latency | Spaces storage |
| 8 | **Structured outputs** (`response_format: json_schema`) | No parse-fail retries | [Providers structured output](https://huggingface.co/docs/inference-providers/guides/structured-output) |
| 9 | **Non-thinking small model**, `max_tokens` caps, short system prompts | No hidden reasoning tokens on the hot path | — |
| 10 | **Cheapest adequate provider per job**: novita for batch, groq or cerebras for live | 3× cheaper input for batch work | Providers multi-provider routing |
| 11 | **LoRA on a 4B model**, not full fine-tuning or a 9B model | ~$1–2 per training run | TRL + PEFT on Jobs |
| 12 | **A100 over A10G for training**: higher $/h, fewer minutes | Cheaper per run and saves wall-clock time (confirmed by the smoke test) | Jobs flavors |
| 13 | **Smoke test before the full run**; timeout set from measured s/step | A stuck job cannot bill for hours | Jobs `--timeout` |
| 14 | **Scale-to-zero + pause** on Endpoints; sleep time on any upgraded Space | No idle billing overnight | Endpoints autoscaling, Spaces sleep |
| 15 | **Free tooling first**: gguf-my-repo, CPU-basic Jobs for data generation, ZeroGPU if eligible | $0 lines | Spaces, Jobs |

---

## 5. Serving options for the demo, priced

The orchestrator UI runs on the Space's CPU (`cpu-upgrade`). GPU is needed only for the voice worker (Indic/Arabic ASR, Indic/MMS TTS) and our fine-tuned model.

| Option | GPU cost for an 8 h judging window | Cold-start risk | When to choose |
|---|---|---|---|
| 2 × Endpoint L4, scale-to-zero, warm during the window | 2 × $0.80 × 8 = **$12.80** | Pre-warm 15 min before. Send `X-Scale-Up-Timeout` | Default if Endpoints work on the captain's account |
| 1 × Endpoint L4 for TTS only; FT model via Providers fallback | $6.40 | Same | If the FT gate (G3 in [06](06-fine-tuning-plan.md)) is red |
| ZeroGPU worker Space hosting the voice worker + FT model | **$0** within quota | Queueing. Quota is per caller: 5 min/day free, 40 min/day PRO | If the account is eligible (verified email, account older than 30 days, or PRO) |
| GGUF on a CPU Endpoint (`intel-spr` x4) | $0.134 × 8 = $1.07 | Low | Offline / on-prem story only. Speed **unverified** |
| Space itself upgraded to L4, voice worker + FT co-located | $0.80 × 8 = $6.40, **plus every hour it is left on** | None | Only with `hf spaces settings <id> --sleep-time 900` set |

---

## 6. How to present this to judges (slide-ready)

**Slide title:** *Bayan runs a full multilingual consultation for about 1.5 cents*

| | Naive build | **Bayan AI** |
|---|---|---|
| 120B-model calls for background reasoning | 40 per consultation | **0** (4B fine-tune); 120B only **once** for notes |
| Think-loop input tokens | 120k | **28k** (4.3× fewer) |
| Audio minutes sent to ASR | 12 | **8** (browser VAD) |
| Safety checks | LLM tokens | **Deterministic rules, $0** |
| Marginal cost per consultation | ≈ $0.047 | **≈ $0.015** → ⟨measure: value from the UI cost meter⟩ |
| Fine-tune (data + training + eval) | — | **$⟨measure⟩**, A100 for ⟨measure⟩ min, on HF Jobs |
| Total spent building and demoing | — | **$⟨measure⟩ of $100**, with ≥ $25 never touched |

**20-second voice-over:** "Every patient turn goes to a 4-billion-parameter model we fine-tuned on HF Jobs for about two dollars. It reads idioms and keeps the clinical state. The big model runs once, at the end, to write the notes. Safety checks are rules, so they cost nothing and cannot hallucinate. Silence is never sent, and fixed phrases are cached. A consultation costs about one and a half cents, and the whole build used ⟨measure: $ spent⟩ of our $100."

Fill the `⟨measure⟩` markers from the spend log (§9) and the cost meter. Do not present the estimates as measurements. [09](09-pitch-and-demo.md) Q&A #6 pulls these numbers.

---

## 7. Account readiness: check before spending anything

These items can block a deliverable regardless of the budget. The captain should check them in **the first hour**.

| Check | Why | How |
|---|---|---|
| **Can the captain's account create a Gradio or Docker Space?** ✅ **Resolved (checked 2026-11-06 via the public Hub API):** the captain `dullgrey` is not PRO but already runs a Gradio Space (`dullgrey/clinic-bridge`) on **`cpu-upgrade`** ($0.03/h), billed to the team pool. Other teams' non-PRO accounts do the same (e.g. `plitip/team-qh-091-safesite-app`, `malmarri/team-qh-167-qatarsignals-app`, both on `cpu-upgrade`). | The general HF rule is: "Gradio and Docker Spaces … require a paid plan to create … Free personal accounts in good standing can still host up to 2 Gradio Spaces running on ZeroGPU" ([Spaces overview](https://huggingface.co/docs/hub/spaces-overview)). The hackathon credits evidently satisfy it. Teammates' personal accounts may still be blocked, which is why **everything is created under the captain's account**. | Create `dullgrey/team-qh-129-bayan-app` with hardware **`cpu-upgrade`**. Budget $0.03/h × ~24 h ≈ **$0.75**. Pause it at night if it isn't needed. |
| **PRO cannot be bought with credits** | "You can only pay for the PRO subscription with a credit card" ([billing](https://huggingface.co/docs/hub/billing)) | Fallbacks: a ZeroGPU Gradio Space (eligible account), or ask the organisers |
| **Can the account create Inference Endpoints?** | Endpoints are "accessible to Hugging Face accounts with an active subscription and credit card on file" ([pricing](https://huggingface.co/docs/inference-endpoints/pricing)), but the handbook says the pool covers Endpoints. A teammate token got `403 … missing permissions: inference.endpoints.read`. | `hf endpoints ls`. If refused, ask the captain for a token with Endpoints scope, or ask a mentor. Fallback: ZeroGPU or Providers. |
| Do the credits cover Spaces hardware? | The billing FAQ lists "GPU Spaces" and "ZeroGPU extra quota" as credit uses ([billing](https://huggingface.co/docs/hub/billing)). The handbook lists Jobs, Endpoints and Providers. | Ask a mentor before upgrading a Space |
| Jobs work | Jobs need a positive credit balance ([Jobs guide](https://huggingface.co/docs/huggingface_hub/guides/jobs)) | `hf jobs run python:3.12 python -c "print(1)"` (about $0.0002) |

---

## 8. Cost guardrails checklist

**Before launching anything that bills**
- [ ] `hf jobs hardware` checked. The $/h and the expected minutes are written in the spend log before launch.
- [ ] Every Job has an explicit `--timeout` derived from a measured smoke test (no "24h just in case").
- [ ] Every Job is launched with `--detach --name <owner>-<purpose>` so anyone can identify and cancel it.
- [ ] Every Endpoint is created with `--min-replica 0 --scale-to-zero-timeout 15` and `--max-replica 1`.
- [ ] Any upgraded Space has a sleep time: `hf spaces settings <space> --sleep-time 900`.
- [ ] LLM calls have `max_tokens` set. Structured output is on. Retries are capped at 1.
- [ ] Big runs (data generation, eval) are smoke-tested first with `LIMIT=5`.

**Protect the public Space (anyone can click it)**
- [ ] The Space uses the captain's token server-side, so **every visitor spends our credits**. Add a demo passcode, or gate live mode behind HF OAuth, and keep a "Play sample consultation" mode ([08 Phase 4](08-build-plan.md)).
- [ ] Per-session caps: at most 3 consultations and 15 minutes of audio per session.
- [ ] A global daily spend cap in the app (sum of the cost meter). When it is hit, switch to demo playback only.
- [ ] No free-text "ask the LLM anything" box.

**While running**
- [ ] `hf jobs ps` at every checkpoint. Cancel anything unnamed or finished-but-hanging: `hf jobs cancel <id>`.
- [ ] `hf endpoints ls` at every checkpoint. `hf endpoints pause <name>` if nobody is testing.
- [ ] Read the [billing page](https://huggingface.co/settings/billing) and the [Providers usage page](https://huggingface.co/settings/inference-providers/overview) at every gate, and update the spend log.
- [ ] Stop rule: if actual spend passes **$50 before Saturday 08:00**, freeze all optional items (Fanar Endpoint, FT retry, ZeroGPU top-ups).

**Before anyone sleeps (the handbook says "check before you leave at night")**
- [ ] `hf jobs ps` shows nothing running, or only a named job with a timeout that ends before morning.
- [ ] All Endpoints are paused, or scaled to zero with the 15-minute timeout.
- [ ] Any GPU Space is paused (`hf spaces pause <space>`). The app Space stays on `cpu-upgrade` (about $0.24 overnight) or is paused if nobody tests overnight.

**Judging day**
- [ ] Resume the Endpoints 15 minutes before the slot. Warm them with one request. Check the latency.
- [ ] After the slot: pause again. After results: delete the Endpoints (`hf endpoints delete`). Keep the app Space running on `cpu-upgrade` until the organisers confirm judging is closed.

**Kill switch (any teammate may run it)**

```bash
hf jobs ps                                     # list running Jobs
hf jobs ls -q | xargs -n1 hf jobs cancel       # cancel every running Job in the namespace
hf endpoints ls && hf endpoints pause <name>   # repeat per Endpoint
hf spaces pause dullgrey/team-qh-129-bayan-app   # last resort: the Space must be running at judging
```

---

## 9. Spend log (keep it in the repo or a shared sheet)

| Time (Doha) | Who | What | Flavor / model | Est. $ | Actual $ (billing page) | Running total |
|---|---|---|---|---|---|---|
| Fri 18:10 | captain | Jobs sanity check | cpu-basic | 0.00 | | |
| | | Data generation | gpt-oss-120b · novita | 1.50 | | |
| | | FT smoke test | a100-large | 0.83 | | |
| | | … | | | | |

The final row becomes the pitch number: "**$X of $100**".

---

## 10. Unverified items (do not state these as facts)

- Training time for our data on `a100-large` (estimated at 20–40 min): measure it with the smoke test.
- Real-time factor of Indic Parler-TTS on an L4, and the resulting TTS $ per consultation.
- Tokens/s of the fine-tuned 4B on an L4 (vLLM) and on CPU (GGUF Q4_K_M, llama.cpp).
- Concurrent-consultation capacity per L4 (the hospital-scale claim).
- Whether the per-minute and per-character provider prices (ASR, TTS) bill on HF exactly as DeepInfra lists them. Confirm on the usage page after the first calls.
- Whether the captain's account can create Inference Endpoints with the hackathon credits (§7). Gradio Spaces on `cpu-upgrade` are confirmed.
- The 12-minute / 8-minute-speech / 40-turn consultation profile is a planning assumption, not clinic data.

---

## Sources

- Hackathon handbook (credits, per-minute billing, Jobs tips, judging criteria): https://huggingface.co/spaces/qai-hackathon/handbook
- Jobs pricing and billing: https://huggingface.co/docs/hub/jobs-pricing · Jobs guide: https://huggingface.co/docs/huggingface_hub/guides/jobs · live hardware: https://huggingface.co/api/jobs/hardware
- Inference Providers pricing (pass-through, credits): https://huggingface.co/docs/inference-providers/pricing · live model/price listing: https://router.huggingface.co/v1/models · structured outputs: https://huggingface.co/docs/inference-providers/guides/structured-output
- Inference Endpoints pricing: https://huggingface.co/docs/inference-endpoints/pricing · autoscaling and scale-to-zero: https://huggingface.co/docs/inference-endpoints/guides/autoscaling · llama.cpp engine: https://huggingface.co/docs/inference-endpoints/engines/llama_cpp
- Spaces hardware, billing, sleep and pause: https://huggingface.co/docs/hub/spaces-gpus · Spaces overview (paid-plan requirement): https://huggingface.co/docs/hub/spaces-overview · ZeroGPU: https://huggingface.co/docs/hub/spaces-zerogpu · Hub billing FAQ: https://huggingface.co/docs/hub/billing
- DeepInfra list prices: https://deepinfra.com/openai/whisper-large-v3 · https://deepinfra.com/openai/whisper-large-v3-turbo · https://deepinfra.com/ResembleAI/chatterbox-multilingual · https://deepinfra.com/hexgrad/Kokoro-82M
