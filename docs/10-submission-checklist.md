# 10 · Submission & Rules-Compliance Checklist

> Source of truth: the official [Participant Handbook](https://huggingface.co/spaces/qai-hackathon/handbook) and [Agenda](https://huggingface.co/spaces/qai-hackathon/agenda) of the Qai × Hugging Face Hackathon O1 (Doha, 5–7 Nov 2026).
> **Hard deadline: Saturday 7 Nov 2026, 2:00 PM Doha time.** Late rows in the submission sheet cannot be judged.
> **Status column** reflects the repo on Sat 7 Nov: done / in progress / pending.

**Team ID:** `QH-129` · **Captain (HF account that owns the credits and all repos):** [`dullgrey`](https://huggingface.co/dullgrey) · Hub names use the lowercase form `team-qh-129`.

---

## 1. Hard rules (any miss = risk of disqualification)

| # | Rule (handbook wording, condensed) | How Bayan AI complies | Owner | Status |
|---|---|---|---|---|
| R1 | Build an AI system that **solves a real problem in Qatar** | Language barriers and medication safety for Qatar's migrant majority in workers' clinics, ambulance and ad hoc interpreting. See [01 · Problem & Impact](01-problem-and-impact.md) | Pitch lead | Done (docs); pitch pending |
| R2 | **Grounded in Qatar or the wider Middle East**, or disqualified | Qatar demographics and health system, the MoPH Patients' Bill of Rights languages, Gulf-specific clinical risks (heat rules), 999, PDPPL (Law No. 13 of 2016) privacy design. The Qatar grounding must be **visible in the first 15 s** of the README, the video and the pitch | Everyone | README: in progress; video and pitch: pending |
| R3 | **Built with Hugging Face** (open-source libs and/or platform) | Gradio Space; `openai/gpt-oss-120b` via Inference Providers (Cerebras, Groq); **smolagents** copilot and wrap-up agents; a private L4 GPU Space as voice worker (Whisper large-v3-turbo, VoxLingua107, IndicConformer, Indic Parler-TTS) reached with `gradio_client`; Kokoro-82M for the optional English voice; Transformers on the worker. See [04 · Models](04-models-and-languages.md) | Tech lead | Done |
| R4 | Frontier models (GPT, Claude…) only "around the edges" | **No frontier model sits in the runtime path.** A coding assistant (Claude Code) was used during the build, as the commit trailers show; say so once in the README | Tech lead | Runtime: done. README note: done |
| R5 | **Everything built during the event** | Repo history starts at the event; commits with real timestamps | Everyone | Done |
| R6 | Stay within the **$100 shared credit pool** (no top-ups) | Budget and guardrails in [07 · Compute Budget](07-compute-budget-and-efficiency.md). Sleep the GPU worker when idle; no Jobs or Endpoints are used | Captain | In progress (final spend: ⟨measure: total $ spent, from the billing page⟩) |

## 2. Deliverables

| # | Deliverable | Exact requirement | Status |
|---|---|---|---|
| D1 | **Live HF Space** | Under the **captain's account**: `dullgrey/team-qh-129-bayan-app` (lowercase, hyphens). **Running** at judging time | Running; brain and outputs integrated in the local code, **not yet deployed** |
| D2 | Space tag | `qai-hf-hackathon-2026` in the README YAML `tags:` | Done |
| D5 | **Demo video, 2–3 min** | Link viewable by anyone (YouTube unlisted or a public Drive link; test it in an incognito window). This is our backup if the live demo breaks | Pending |
| D6 | **Submission sheet row** | All links pasted, row marked **Submitted** before 2:00 PM | Pending |
| D7 | Blog post *(optional)* | HF community blog or Space article; link goes in the "Blog URL" column | Not planned |

Not shipping: a fine-tuned model (former D3, see [06](06-fine-tuning-plan.md)) and a Hub idiom dataset (former D4). The lexicon stays in [`data/idiom_lexicon.json`](../data/idiom_lexicon.json). Their links are removed from the README.

## 3. Space readiness (judges must be able to "try it")

- [ ] The Space builds from a clean state, with pinned versions in `requirements.txt`. **Check:** the brain and outputs need `smolagents==1.26.0`, `fpdf2`, `uharfbuzz`, `rapidfuzz`; the current `requirements.txt` lists only `fastrtc[vad]`, `soundfile`, `numpy`, `segno`.
- [ ] Secrets (`HF_TOKEN`, `BAYAN_ACCESS_CODE`, the Cloudflare TURN keys) are set as **Space secrets**, never committed. On Spaces, an unset `BAYAN_ACCESS_CODE` locks everyone out, so set it and give judges the code.
- [x] **Demo mode** works without a microphone: the golden path as text turns with real translation, and real voice when the worker is running.
- [x] Live mode works with the browser microphone over HTTPS (FastRTC WebRTC with our Cloudflare TURN relay).
- [ ] Cold start is known: the private L4 voice worker sleeps when idle and boots in about 99 s once hardware is assigned. **Wake it well before judging.**
- [x] The main Space runs on CPU; the only GPU is the voice worker Space.
- [ ] The README states the patient languages supported, with a clear tier: Nepali (exercised end to end), Hindi, Urdu, Bengali, Malayalam (voice, unverified), Filipino (text only).
- [ ] A clinical disclaimer is visible in the UI (decision support for licensed clinicians, not a medical device). **Not in `bayan/ui.py` yet.**

## 4. Judging criteria → where we prove each one

| Criterion | What judges look for | Our proof point | Where |
|---|---|---|---|
| **Impact & relevance** | A real, worthwhile Qatar/ME problem, solved well | The migrant majority, cited evidence on interpreter errors, Qatar heat context, personas | README §Why, [01](01-problem-and-impact.md) |
| **Use of Hugging Face** | Genuinely built with HF | Open-model cascade on Inference Providers and a private GPU Space, two **smolagents** agents (copilot and wrap-up), Gradio Space | README §Built with HF, [04](04-models-and-languages.md), [11](11-clinical-copilot-agent.md) |
| **Technical execution** | Works end to end | Voice → translation → idiom note → held sentence in the Space; rule cards, Consultation note and patient sheet PDFs from the brain (tests + live smoke run 17/17; integrated locally, not yet deployed) | Space + video, [03](03-architecture.md) |
| **Efficiency** | Smart use of the compute budget | Measured on the golden path: about $0.015 consultation brain + about $0.004 wrap-up; Groq for extraction, batched questions, skipped trivial turns, deterministic rules and gate; final spend vs. $100 | [07](07-compute-budget-and-efficiency.md) |
| **Demo & pitch** | Clear and compelling | A human hook, a live held-sentence moment, and a 3-min script that has been rehearsed | [09](09-pitch-and-demo.md) |

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

- [ ] `pytest tests` passes (269 offline tests, no paid calls) with the full requirements installed.
- [ ] `python scripts/smoke_e2e.py` prints ALL PASS (live golden path, 17 checks, about $0.02).
- [ ] Open the Space in incognito on a phone and a laptop, enter the access code, and run the demo consultation end to end.
- [ ] Open the patient PDF. Check that the native script renders (no tofu boxes), that the audio plays, and that the WhatsApp and SMS links open.
- [ ] Scan the review-screen QR with a phone: the `/plan/<id>` page opens.
- [ ] Check that the video link plays logged out.
- [ ] Put the voice worker to sleep after judging (it bills by the hour on L4).
- [ ] Re-read the sheet row: every link is correct and the status is **Submitted**.
