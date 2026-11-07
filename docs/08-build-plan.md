# 08 · Build Plan: From Zero to Submitted by Sat 2:00 PM

> **Status (Sat 7 Nov):** the plan below was written before coding. Each item is now marked **done**, **in progress** or **not done**, from the code in this repo.
> Rule of thumb: **the golden path must work end to end before any feature is widened.** One perfect consultation beats ten half-working languages.

---

## 1. The golden path (what must work no matter what)

A Nepali-speaking construction worker with heat exposure says his chest "burns like *gyastrik*" and mentions a penicillin allergy. The doctor is about to prescribe amoxicillin and discharge him.

| Step | Status |
|---|---|
| 1. Bayan speaks the consent line in Nepali, and the patient agrees. | Done (spoken consent, tap Yes / No; Nepali text not native-verified) |
| 2. Two-way voice interpretation, with no push-to-talk. | Done (FastRTC, server-side VAD) |
| 3. An **idiom card**: *gyastrik* may be cardiac or GI; ask about exertion, radiation, sweating. | Done: brain idiom card plus one red-flag-first "Ask next" (wired in the local code) |
| 4. **Silent alerts** on screen, never spoken: penicillin allergy vs. amoxicillin, and chest pain with discharge but no ECG or troponin. | Done in the local code: the rule-engine gate holds the sentence; rule cards (incl. the grouped chest-pain card) show as red alerts in the Notes panel |
| 5. The doctor corrects course. | Done ("Say something else" / "Speak it anyway") |
| 6. "End consultation" produces an English Consultation note (PDF + text), a Nepali patient sheet PDF, a WAV of the plan read aloud, and WhatsApp and SMS links. | Done in the local code: wrap-up agent → review screen (care plan + editable "Doctor's note"), both PDFs at `/files/<token>/`, `/plan/<id>` with PDF download, WhatsApp link. WAV: built, off by default (`BAYAN_PLAN_AUDIO=1`) |

The full scenario script lives in [09 · Pitch & Demo](09-pitch-and-demo.md). The brain's version of it is `GOLDEN_TURNS` in `tests/test_copilot.py`, run live by `scripts/smoke_e2e.py`.

## 2. Team roles (works for 2–4 people)

| Role | Owns | If the team has only 2 people |
|---|---|---|
| **A · Voice** | Mic capture, VAD, language routing, ASR, TTS, echo/self-hearing guard, GPU voice worker | A + C |
| **B · Brain** | Translation prompts, idiom matching, state extractor, rules engine, copilot and wrap-up agents, note and care-plan generation | B + D |
| **C · Product** | UI shell, PDFs (complex-script fonts), WhatsApp/SMS/audio delivery, Space deployment | A + C |
| **D · Story** | Demo video, pitch, README, cost tracking, native-speaker review | B + D |

Team names and roles for the README: pending.

## 3. Repo layout (as built)

```
BayanAI/
├── app.py                  # Space entry: FastAPI + Gradio, access gate, FastRTC stream, /plan/<id>
├── requirements.txt
├── bayan/
│   ├── ui.py               # screens (Duet design), static stage driven by JSON views
│   ├── consult.py          # consultation state machine, held sentences, demo script, end of visit
│   ├── talk.py             # voice worker client, gpt-oss-120b translation, TTS routing
│   ├── copilot.py          # Notes-panel suggestions; adapter for brain cards
│   ├── careplan.py         # care plan text, QR, expiring /plan/<id> page
│   ├── brain/              # agentkit · cards · checklist · copilot · extract · idioms · llm · merge
│   │                       # rules · state · vocab · wrapup
│   └── outputs/            # report (PDFs) · delivery (wa.me, sms:, WAV) · retention (temp files)
├── voice_worker/           # private L4 GPU Space: app.py, requirements.txt, README.md
├── data/                   # idiom_lexicon.json · safety_rules.json
├── assets/fonts/           # Noto fonts for the PDFs
├── tests/                  # conftest.py (blocks paid calls) + 7 test files, 269 tests
├── scripts/                # smoke_e2e.py (live golden path) · smoke_copilot.py
└── docs/
```

Not created: `bayan/audio/`, `bayan/prompts/`, `demo/golden_path/*.wav`, `training/`.

## 4. Hour-by-hour plan (with status)

### Phase 0 · Setup
- [x] Tokens and the $100 pool.
- [x] Space `dullgrey/team-qh-129-bayan-app` (Gradio SDK), behind an access code.
- [x] Gated licences for `ai4bharat/indic-conformer-600m-multilingual` and `ai4bharat/indic-parler-tts`.
- [x] **GPU voice worker** as a private Space on an L4 GPU (`dullgrey/team-qh-129-bayan-voice`, reached with `gradio_client`; not an Inference Endpoint, not ZeroGPU): Whisper large-v3-turbo, VoxLingua107 language ID, IndicConformer, Indic Parler-TTS. Boot about 99 s once hardware is assigned; streaming first audio about 2.2–3.1 s from Doha (commit `474e406`).
- [ ] Native speakers booked for review: **not done**.

### Phase 1 · Skeleton pipeline
- [x] Mic → FastRTC (WebRTC) → Silero VAD on the server → `/hear` on the worker (who is speaking + ASR).
- [x] Translation call with JSON output (`translation`, `english`, `drugs`, `allergies`, `tests`) on `gpt-oss-120b` via Cerebras, reasoning low.
- [x] TTS routing: Indic Parler (streamed) for ne, hi, ur, bn, ml; optional Kokoro for English; text only otherwise.
- [x] UI shell: Duet view, caption mode, Notes panel, held sentence, review and QR hand-off.
- **Checkpoint:** English speech → Nepali audio, Nepali speech → English text: done.

### Phase 2 · The "thinking" layer
- [x] Deterministic idiom matching over `data/idiom_lexicon.json` (59 entries).
- [x] State extractor (Groq, background), merge with utterance evidence.
- [x] Rule engine over all 81 rules in `data/safety_rules.json`, card store with acknowledge / override / dismiss / wrong fact and an append-only audit.
- [x] Prescription gate (synchronous, no LLM, about 3 ms).
- [x] **Clinical copilot agent** (smolagents 1.26.0) per [11](11-clinical-copilot-agent.md), with deterministic fallback.
- [x] Echo guard: mic held while Bayan speaks plus a 300 ms tail. Self-match filter and spoken clarify prompt: not done.
- [x] Wiring the brain into the Space UI: **done** in the local code; not yet deployed to the Space.

### Phase 3 · Outputs
- [x] Wrap-up agent (smolagents: `draft_outputs`, `render_outputs`) with a deterministic fallback order.
- [x] Consultation note (English) with the Assessment guard; plain-text copy for the EMR.
- [x] Patient sheet PDF: fpdf2 + HarfBuzz shaping + Noto fonts, native first, English beneath, schedule table, Do not take, Call 999. No QR on the PDF. Back-translation check: not done.
- [x] Care-plan WAV; `wa.me` and `sms:` links (prefilled, a person taps Send).
- [x] Outputs wired into the Space review screen: **done** in the local code; not yet deployed.
- [ ] Optional fine-tune track ([06](06-fine-tuning-plan.md)): **not done**; nothing shipped.

### Phase 4 · Widen, harden, and record
- [ ] Tier-1 languages verified by native speakers: **not done** (Hindi, Urdu, Bengali, Malayalam wired but unverified; Filipino text only).
- [x] Demo mode: no-mic golden path as text turns, real translation, real voice when the worker is up.
- [x] Measured cost per call in `llm.USAGE` and per-run metrics (golden path: about $0.015 consultation brain + about $0.004 wrap-up). A cost meter in the UI: not done.
- [x] Tests: `pytest tests` (269 offline, fake models) and `scripts/smoke_e2e.py` (live, 17/17 on the merged code, about $0.02).
- [ ] Demo video: **pending**.

### Phase 5 · Submit
- [ ] Final README, tags and links; sheet row marked **Submitted**: pending.
- [ ] Last-hour sanity pass in [10](10-submission-checklist.md): pending.

## 5. Go / no-go gates

| Gate | When | Result |
|---|---|---|
| Live voice round-trip under ~4 s | End of Phase 1 | Not measured end to end. Worker streaming first audio about 2.2–3.1 s from Doha (TTS only) |
| Nepali TTS quality is acceptable to a native speaker | Phase 1 | Pending (no native-speaker review yet) |
| Safety alerts fire reliably on the scripted consultation | Phase 2 | Green in the offline golden-path test and the live smoke run (text turns); not yet in the Space |
| Fine-tune eval beats the base prompt | Phase 3 | Not run. Shipped inference-only; no dataset published |
| PDF renders native scripts correctly | Phase 3 | Rendered page correct by eye for Nepali; copying Nepali text out of the PDF gives broken text (known limitation) |

## 6. Definition of done

- [ ] The golden path runs live in the Space **and** in the recorded video (integration done locally; deployment and video pending).
- [ ] Every patient-facing sentence in the demo has been checked by a native speaker, or is clearly marked as machine-generated.
- [ ] Spend is under $100, with at least $15 kept back for judging day, and the number appears in the pitch.
- [ ] All deliverables in [10](10-submission-checklist.md) are ticked.
