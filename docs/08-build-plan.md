# 08 · Build Plan: From Zero to Submitted by Sat 2:00 PM

> Nothing is built yet. This plan turns the docs into a shippable Space in roughly 20 working hours.
> Rule of thumb: **the golden path must work end to end before any feature is widened.** One perfect consultation beats ten half-working languages.

---

## 1. The golden path (what must work no matter what)

A Nepali-speaking construction worker with heat exposure says his chest "burns like gas" and mentions a penicillin allergy. The doctor (English, then Arabic) is about to prescribe amoxicillin and discharge him.

1. Bayan speaks the consent line in Nepali, and the patient agrees.
2. Two-way voice interpretation, with no push-to-talk.
3. An **idiom card** appears: *"burning like gas" → may be cardiac or GI; ask about exertion, radiation, sweating.*
4. **Silent alerts** appear on screen, never spoken: penicillin allergy vs. amoxicillin, and chest pain with discharge but no ECG or troponin.
5. The doctor corrects course, and Bayan acknowledges it.
6. "Bayan, end consultation" produces:
   - an English SOAP note
   - a **Nepali PDF care plan**
   - an MP3 of the plan read aloud
   - a WhatsApp link and an SMS

The full scenario script lives in [09 · Pitch & Demo](09-pitch-and-demo.md).

## 2. Team roles (works for 2–4 people)

| Role | Owns | If the team has only 2 people |
|---|---|---|
| **A · Voice** | Mic capture, VAD, language routing, ASR, TTS router, echo/self-hearing guard | A + C |
| **B · Brain** | Translation prompts, idiom RAG, state extractor, safety rules engine, notes and care-plan generation | B + D |
| **C · Product** | Single-screen UI, the PDF (complex-script fonts), WhatsApp/SMS/audio delivery, Space deployment | A + C |
| **D · Story** | Golden-path audio recordings (native speakers), demo video, pitch, README, dataset card, cost tracking | B + D |

The captain holds the $100 pool, creates teammate tokens, and owns the Space and model namespaces (see [10 · Checklist](10-submission-checklist.md)).

## 3. Proposed repo layout

```
BayanAI/
├── app.py                  # Gradio/FastAPI entry point (HF Space)
├── requirements.txt        # pinned
├── bayan/
│   ├── audio/   vad.py · lid.py · asr.py · tts.py · echo_guard.py
│   ├── brain/   translate.py · idioms.py · extractor.py · sentinel.py · notes.py · careplan.py
│   ├── outputs/ pdf.py · whatsapp.py · sms.py · audio_export.py
│   ├── prompts/ *.md        # versioned prompt files
│   └── session.py           # in-memory consultation state (no audio retention)
├── data/    idiom_lexicon.json · safety_rules.json
├── demo/    golden_path/*.wav   # pre-recorded backup audio
├── assets/fonts/            # Noto Sans Devanagari / Bengali / Malayalam / Arabic …
├── training/ (optional)     # gen_data.py · train.py · eval.py  → see 06
└── docs/
```

## 4. Hour-by-hour plan

Times are Doha time. Shift the whole schedule if you start later, but **never move the Saturday anchors.**

### Phase 0 · Setup (first hour)
- [ ] Captain: claim the $100 coupon and create a token per teammate. Everyone runs `hf auth login --token …`.
- [ ] Create the Space `dullgrey/team-qh-129-bayan-app` (Gradio SDK, hardware `cpu-upgrade`) and push a hello-world.
- [ ] Smoke-test one call to each provider: ASR (Whisper), LLM chat, TTS. Write down the latency and cost of each.
- [ ] Captain: accept the gated licences for `ai4bharat/indic-conformer-600m-multilingual` and `ai4bharat/indic-parler-tts` (they are gated, so access must be requested on the Hub).
- [ ] A: stand up the **GPU voice worker** (IndicConformer + Indic Parler-TTS + MMS-TTS) as an L4 Endpoint with scale-to-zero, or as a ZeroGPU/GPU Space. Measure Nepali TTS speed on it right away, because it is the biggest unknown in [07](07-compute-budget-and-efficiency.md).
- [ ] D: book native speakers (Nepali first, Hindi second) to record the golden-path lines and to review translations.

### Phase 1 · Skeleton pipeline (hours 1–5)
- [ ] A: browser mic → VAD-segmented utterances → server; ASR (Whisper via Providers for English; IndicConformer on the GPU voice worker for Nepali); language routing for doctor-side vs. patient-side.
- [ ] B: translation call with JSON output `{translation, role, idiom_candidates, needs_clarification}`.
- [ ] A: TTS router by language, with a fallback table from [04](04-models-and-languages.md).
- [ ] C: single-screen UI showing the live transcript (literal + translation) and audio playback.
- **Checkpoint:** one spoken English sentence comes out as Nepali audio, and one Nepali sentence comes out as English text and audio.

### Phase 2 · The "thinking" layer (hours 5–10)
- [ ] B: idiom retrieval from `data/idiom_lexicon.json` → idiom cards in the UI.
- [ ] B: state extractor (allergies, meds and doses, symptoms, vitals, investigations, disposition) running in the background every turn.
- [ ] B: deterministic sentinel over `data/safety_rules.json` → silent alert tray, with acknowledge/override and a reason.
- [ ] A: echo guard (stop the agent from translating its own TTS) and a spoken repeat/clarify prompt.
- **Checkpoint (Friday-night soft submission):** golden path steps 1–5 work live. Space is up. README and a draft video are ready.

### Phase 3 · Outputs (hours 10–14)
- [ ] B: SOAP note generator (English) and care-plan generator (simple English → native language, plus a back-translation check).
- [ ] C: PDF with correct complex-script shaping (HarfBuzz-based renderer such as WeasyPrint, plus Noto fonts). Include a medication-time grid (sun/moon pictograms), a red-flag section, and a QR code to the audio.
- [ ] C: MP3 export of the care plan; a WhatsApp click-to-chat link with the PDF link; SMS with a short native-script summary and the link.
- [ ] **Optional fine-tune track** (only if Phase 2 is green): see [06 · Fine-Tuning Plan](06-fine-tuning-plan.md) for the go/no-go gates.

### Phase 4 · Widen, harden, and record (Sat, until 11:30 AM)
- [ ] Add the Tier-1 languages one by one, each verified by a native speaker or flagged "unverified."
- [ ] Demo mode: a "Play sample consultation" button that runs the pre-recorded audio through the real pipeline.
- [ ] Cost meter in the UI footer (provider seconds, tokens, characters, and $ per consultation) for the efficiency story.
- [ ] **10:00 AM feature freeze.** Record the demo video by 11:30.

### Phase 5 · Submit (Sat 11:30 AM – 2:00 PM)
- [ ] Final README, model and dataset cards, tags, and links. Fill the sheet row by 1:00 PM and mark it **Submitted**.
- [ ] Run the last-hour sanity pass in [10](10-submission-checklist.md).

## 5. Go / no-go gates

| Gate | When | If red… |
|---|---|---|
| Live voice round-trip under ~4 s | End of Phase 1 | Fall back to "tap to translate" on the same screen. Keep the ambient mode for the video only |
| Nepali TTS quality is acceptable to a native speaker | Phase 1 | Use Hindi as the golden-path language and keep Nepali as text plus best-effort audio |
| Safety alerts fire reliably on the scripted consultation | Phase 2 | Narrow to the 2 golden-path rules, and polish those |
| Fine-tune eval beats the base prompt | Phase 3 | Ship inference-only. Still publish the dataset (Use-of-HF points) |
| PDF renders native scripts correctly | Phase 3 | Render the native text as images from the browser, or ship the HTML care plan plus a print-to-PDF button |

## 6. Definition of done

- The golden path runs live in the Space **and** in the recorded video.
- Every patient-facing sentence in the demo has been checked by a native speaker, or is clearly marked as machine-generated.
- Spend is under $100, with at least $15 kept back for judging day, and the number appears in the pitch.
- All deliverables in [10](10-submission-checklist.md) are ticked.
