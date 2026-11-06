# 10 · Submission & Rules-Compliance Checklist

> Source of truth: the official [Participant Handbook](https://huggingface.co/spaces/qai-hackathon/handbook) and [Agenda](https://huggingface.co/spaces/qai-hackathon/agenda) of the Qai × Hugging Face Hackathon O1 (Doha, 5–7 Nov 2026).
> **Hard deadline: Saturday 7 Nov 2026, 2:00 PM Doha time.** Late rows in the submission sheet cannot be judged.

**Team ID:** `QH-129` · **Captain (HF account that owns the credits and all repos):** [`dullgrey`](https://huggingface.co/dullgrey) · Hub names use the lowercase form `team-qh-129`.

---

## 1. Hard rules (any miss = risk of disqualification)

| # | Rule (handbook wording, condensed) | How Bayan AI complies | Owner | ✅ |
|---|---|---|---|---|
| R1 | Build an AI system that **solves a real problem in Qatar** | Language-barrier and medication-safety gap for Qatar's migrant majority in HMC / PHCC / worker health centres. See [01 · Problem & Impact](01-problem-and-impact.md) | Pitch lead | ☐ |
| R2 | **Grounded in Qatar or the wider Middle East**, or disqualified | Qatar demographics and health system, Gulf-specific clinical risks (heat illness), doctor-side Arabic through QCRI's **Fanar** (Qatar's national Arabic LLM), PDPPL (Law No. 13 of 2016) privacy design. The Qatar grounding must be **visible in the first 15 s** of the README, the video and the pitch | Everyone | ☐ |
| R3 | **Built with Hugging Face** (open-source libs and/or platform) | Inference Providers (LLMs, English ASR, English/Arabic TTS) plus an Inference Endpoint GPU voice worker (IndicConformer, Voxtral-Arabic, Indic Parler-TTS), open models from the Hub, Transformers / Gradio Space, optional Jobs fine-tune and Hub dataset. See [04 · Models](04-models-and-languages.md) | Tech lead | ☐ |
| R4 | Frontier models (GPT, Claude…) only "around the edges" | **No frontier model sits in the runtime path.** If one was used for anything (e.g. a coding assistant), say so once in the README | Tech lead | ☐ |
| R5 | **Everything built during the event** | Repo history starts at the event; commit often with real timestamps | Everyone | ☐ |
| R6 | Stay within the **$100 shared credit pool** (no top-ups) | Budget and guardrails in [07 · Compute Budget](07-compute-budget-and-efficiency.md). Cancel idle Jobs and Endpoints every night | Captain | ☐ |

## 2. Deliverables

| # | Deliverable | Exact requirement | ✅ |
|---|---|---|---|
| D1 | **Live HF Space** | Under the **captain's account**: `dullgrey/team-qh-129-bayan-app` (lowercase, hyphens). **Running** at judging time | ☐ |
| D2 | Space tag | `qai-hf-hackathon-2026` in the README YAML `tags:` | ☐ |
| D3 | Model *(only if we fine-tune)* | `dullgrey/team-qh-129-bayan` on the Hub, with a **model card** and the tag `qai-hf-hackathon-2026`, **linked from the Space** | ☐ |
| D4 | Dataset *(optional, recommended)* | `dullgrey/team-qh-129-bayan-idioms` with a dataset card and the tag. Link it from the Space and the model card | ☐ |
| D5 | **Demo video, 2–3 min** | Link viewable by anyone (YouTube unlisted or a public Drive link; test it in an incognito window). This is our backup if the live demo breaks | ☐ |
| D6 | **Submission sheet row** | All links pasted, row marked **Submitted** before 2:00 PM | ☐ |
| D7 | Blog post *(optional)* | HF community blog or Space article; link goes in the "Blog URL" column | ☐ |

## 3. Space readiness (judges must be able to "try it")

- [ ] The Space builds from a clean state. Pin all dependency versions in `requirements.txt`.
- [ ] Secrets (`HF_TOKEN`, any Twilio keys) are set as **Space secrets**, never committed.
- [ ] **Demo mode** works without a microphone: a "Play sample consultation" button feeds the pre-recorded golden-path audio through the full pipeline.
- [ ] Live mode works with the browser microphone over HTTPS (Spaces are HTTPS by default).
- [ ] Cold-start time is known. If we use an Endpoint with scale-to-zero, **warm it up 15 min before judging**.
- [ ] The main Space stays on `cpu-upgrade`. The only GPUs are the voice worker and the fine-tune Endpoint (if it ships). Both scale to zero and are warmed 15 min before judging (efficiency criterion).
- [ ] The README states the patient languages supported, with a clear tier (demo-verified, supported, text-only).
- [ ] A clinical disclaimer is visible in the UI: decision support for licensed clinicians, not a medical device.

## 4. Judging criteria → where we prove each one

| Criterion | What judges look for | Our proof point | Where |
|---|---|---|---|
| **Impact & relevance** | A real, worthwhile Qatar/ME problem, solved well | The migrant majority, cited evidence on interpreter errors, Qatar heat-illness context, personas | README §Why, [01](01-problem-and-impact.md) |
| **Use of Hugging Face** | Genuinely built with HF | Fully open-model cascade on Inference Providers and Inference Endpoints, a **smolagents** clinical copilot agent, Hub dataset and fine-tuned model, Gradio Space, Fanar from QCRI | README §Built with HF, [04](04-models-and-languages.md), [06](06-fine-tuning-plan.md) |
| **Technical execution** | Works end to end | The live golden path: voice → translation → idiom note → safety alert → PDF / WhatsApp / SMS / audio | Space + video, [03](03-architecture.md) |
| **Efficiency** | Smart use of the compute budget | Cost per consultation, small-model routing, VAD gating, TTS caching, scale-to-zero, final spend vs. $100 | [07](07-compute-budget-and-efficiency.md) |
| **Demo & pitch** | Clear and compelling | A human hook, a live "silent alert" moment, and a 3-min script that has been rehearsed | [09](09-pitch-and-demo.md) |

## 5. Timeline anchors

| When (Doha) | Milestone |
|---|---|
| Fri night | **Soft submission checkpoint**: Space live (even if rough) plus the README and a draft video ready for review |
| Sat 10:00 AM | Feature freeze. Only bug fixes after this |
| Sat 11:30 AM | Final demo video recorded and uploaded, link tested in incognito |
| Sat 1:00 PM | Sheet row filled. Re-test the Space from a phone |
| **Sat 2:00 PM** | **Hard deadline**. Row marked Submitted |
| Sat 2:00–3:45 PM | Judges shortlist; we rehearse the pitch |
| Sat 4:00–6:00 PM | Finalist pitches (3 min + Q&A) |

## 6. Last-hour sanity pass

- [ ] Open the Space in incognito on a phone and a laptop, and run the sample consultation end to end.
- [ ] Download the patient PDF. Check that the native script renders (no tofu boxes), that the audio plays, and that the WhatsApp and SMS links open.
- [ ] Check that the video link plays logged out.
- [ ] Run `hf jobs ps` to confirm no Job is running. Confirm Endpoints are paused or set to scale-to-zero.
- [ ] Re-read the sheet row: every link is correct and the status is **Submitted**.
