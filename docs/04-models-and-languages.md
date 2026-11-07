# 04 · Models & Languages: What Runs Where, for Which Language, and Why

> **One-line answer:** Bayan AI is a **cascade** of open Hugging Face models: VAD → language/role ID → ASR → LLM "clinical brain" → TTS. No single open speech-to-speech model can *speak* Nepali or Malayalam, and none gives us the text we need for safety checks and notes. The brain is **`openai/gpt-oss-120b` via HF Inference Providers** (Cerebras for translation and the agents, Groq for background extraction). All speech models run on **one private GPU Space** (L4, `l4x1`, $0.80/h) that the app calls with `gradio_client`: Whisper large-v3-turbo, VoxLingua107 language ID, IndicConformer and Indic Parler-TTS. The app Space itself runs on `cpu-upgrade`.
>
> **What is in the runtime vs what was researched:** §0 lists the models the code actually calls. Everything else in this doc (Fanar, Voxtral, Omnilingual ASR, MMS-TTS, OmniVoice, Chatterbox, pyannote, IndicTrans2, NLLB, a Qwen3-4B fine-tune, and others) is an **alternative considered or roadmap**, not part of the hackathon build.
>
> **Read with:** [03 Architecture](03-architecture.md) (the loops) · [06 Fine-Tuning Plan](06-fine-tuning-plan.md) · [07 Compute Budget](07-compute-budget-and-efficiency.md) · [08 Build Plan](08-build-plan.md)
>
> **Verification note:** every model ID, license and provider mapping below was checked against the Hugging Face Hub API (`/api/models/<id>?expand[]=inferenceProviderMapping&expand[]=cardData`) or the model card on **2026-11-06**. Provider speed and price numbers come from a snapshot of `https://router.huggingface.co/v1/models` taken the same day, and they change over time. Anything marked *(estimate)* or *(unverified)* still needs to be measured.

---

## 0. Models actually used (runtime)

These are the only models the code calls today (`bayan/talk.py`, `bayan/brain/`, `voice_worker/app.py`).

| Stage | Model | Where it runs | Notes |
|---|---|---|---|
| **VAD / end of turn** | [Silero VAD](https://github.com/snakers4/silero-vad) (MIT) inside [FastRTC](https://github.com/gradio-app/fastrtc) `ReplyOnPause` | App Space, **server side** (not in the browser) | Threshold 0.5, 600 ms minimum silence; utterances under 0.3 s are dropped |
| **Who is speaking** | [speechbrain/lang-id-voxlingua107-ecapa](https://huggingface.co/speechbrain/lang-id-voxlingua107-ecapa) (Apache-2.0) | GPU voice worker (`/hear`) | Language ID restricted to {en, ar, the session's patient language}: en/ar = doctor, otherwise patient |
| **ASR, doctor (English, Arabic)** | [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) (MIT) | GPU voice worker (not via Providers) | Also the fallback ASR for patient languages IndicConformer lacks (e.g. Tagalog) |
| **ASR, patient (Indic)** | [ai4bharat/indic-conformer-600m-multilingual](https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual) (MIT, gated) | GPU voice worker | CTC decoding |
| **Translation (talk loop)** | [openai/gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b) (Apache-2.0) | Inference Providers, **Cerebras**, reasoning `low` | JSON out: translation, literal English, drugs, allergies, tests |
| **Clinical-fact extraction (think loop)** | gpt-oss-120b | Inference Providers, **Groq** (falls back to Cerebras), reasoning `medium`, `json_schema` output | Same model, cheaper input on Groq ($0.15 vs $0.35 per 1M) |
| **Copilot agent + wrap-up agent** | gpt-oss-120b through **smolagents 1.26.0** `ToolCallingAgent` | Inference Providers, **Cerebras only**, reasoning `medium` | On Groq, gpt-oss called a nonexistent `json` tool, so the agents never use Groq ([11](11-clinical-copilot-agent.md)) |
| **Wrap-up writing (note + care plan)** | gpt-oss-120b | Inference Providers, Cerebras (Groq fallback), reasoning `medium` | Two calls in parallel; long consultations add map-reduce calls |
| **Patient voice** | [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts) (Apache-2.0, gated) | GPU voice worker (`/speak_stream`) | Streaming speech for ne, hi, ur, bn, ml, ta, te |
| **Doctor voice (optional)** | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0) | Inference Providers (`provider="auto"`) | English only; off by default (`BAYAN_DOCTOR_VOICE=1`) |

**Measured behaviour that shaped the choices.** Reasoning `high` failed (empty replies, about 12 s), so nothing uses it. Tool calling with gpt-oss through Groq failed, so the agents are Cerebras-only.

**Not voiced today:** Filipino/Tagalog and Arabic (text only on screen and in the PDF). Doctor side: English and Arabic speech in; the patient's words are always shown to the doctor in English.

**The GPU voice worker** is a private Gradio Space, `dullgrey/team-qh-129-bayan-voice`, on an L4 (`l4x1`, $0.80/h, sleeps when idle), called with `gradio_client`. It is **not** an Inference Endpoint and not ZeroGPU. See [voice_worker/README.md](../voice_worker/README.md) for its endpoints.

### 0.1 Design-time comparison (alternatives considered / roadmap)

The table below is the plan we researched on 2026-11-06. The **Status** column says what happened. Only the rows marked **used** are in the runtime.

| Stage | Primary | Fallback | Status | Why |
|---|---|---|---|---|
| **Audio transport + VAD** | [Silero VAD](https://github.com/snakers4/silero-vad) (MIT) via [FastRTC](https://github.com/gradio-app/fastrtc) `ReplyOnPause` (MIT, uses Silero) | [pipecat-ai/smart-turn-v3](https://huggingface.co/pipecat-ai/smart-turn-v3) (BSD-2, 8M params, semantic end-of-turn) | **Used** (Silero in FastRTC, server side). Smart Turn: roadmap | Ambient mode: only utterances go to the GPU worker, and silence costs nothing |
| **Role + language ID** | Session-pinned patient language, plus [speechbrain/lang-id-voxlingua107-ecapa](https://huggingface.co/speechbrain/lang-id-voxlingua107-ecapa) (Apache-2.0) to tell doctor-side (en/ar) from patient-side speech | Whisper's built-in LID; [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) (CC-BY-4.0) when both people speak Arabic | **Used** (VoxLingua107 on the worker; Whisper LID logged for diagnostics only). pyannote: roadmap | Language doubles as diarization for free. Hindi/Urdu/Nepali confusion is avoided by pinning the language |
| **ASR, doctor (English)** | [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) (MIT) | [openai/whisper-large-v3](https://huggingface.co/openai/whisper-large-v3) | **Used**, on the GPU worker (not via Providers) | Strong English; one worker call does role ID and ASR |
| **ASR, doctor (Arabic incl. Gulf)** | [mistralai/Voxtral-Mini-4B-Realtime-Arabic](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-Arabic) (Apache-2.0; MSA + **Gulf `afb`**, Egyptian, Sudanese, Levantine, …; code-switching) | whisper-large-v3-turbo | **Roadmap.** Arabic goes through Whisper turbo on the worker today | The only open model found that lists Gulf Arabic and is built for streaming |
| **ASR, patient (Indic: ne, hi, ur, bn, ml, ta, te, pa)** | [ai4bharat/indic-conformer-600m-multilingual](https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual) (MIT, gated, 22 languages, CTC/RNNT) | [facebook/omniASR-LLM-7B / CTC-1B](https://huggingface.co/facebook/omniASR-LLM-7B) (Apache-2.0) | **Used** (IndicConformer). Omnilingual: roadmap | Whisper large-v2's FLEURS WER is **≥99% on Bengali, Malayalam, Telugu, Punjabi** (104.1, 100.7, 99.0, 102.4) (Whisper paper, Table 13) |
| **ASR, patient (fil, id)** | whisper-large-v3(-turbo) | [Qwen/Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) (Apache-2.0, `deepinfra`) | **Used** for Tagalog (Whisper turbo on the worker). Indonesian and Qwen3-ASR: roadmap | Whisper is reasonable on Tagalog (13.8 WER) and Indonesian (7.1) |
| **ASR, patient (si, sw, am, ti, so, om, ps)** | [facebook/omniASR-LLM-7B](https://huggingface.co/facebook/omniASR-LLM-7B) or `CTC-1B` (Apache-2.0, 1,600+ languages) | Whisper (si, sw, am, so, ps only) | **Roadmap** (these languages are not in the app) | Meta reports CER under 10 for all of these except Pashto (`pus`, 12.6) |
| **Clinical brain (translate + extraction + agents + notes)** | [openai/gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b) (Apache-2.0) via Cerebras / Groq | [Qwen/Qwen3.5-397B-A17B](https://huggingface.co/Qwen/Qwen3.5-397B-A17B) (201 languages claimed) · [google/gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it) (Apache-2.0) · [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) (`:cerebras`, ~709 tok/s) | **Used** (gpt-oss-120b only; the alternatives were not wired in) | Fastest large open model on HF Providers, with structured output and tool calling |
| **Arabic grounding (Qatar)** | [QCRI/Fanar-1-9B-Instruct](https://huggingface.co/QCRI/Fanar-1-9B-Instruct) (Apache-2.0, `featherless-ai`) to polish Arabic-side text and patient material | [QCRI/Fanar-2-27B-Instruct](https://huggingface.co/QCRI/Fanar-2-27B-Instruct) (Apache-2.0; no provider, so an Endpoint or a GGUF build with llama.cpp) | **Roadmap** (not in the runtime) | Qatar's national Arabic LLM covers MSA, Gulf, Levantine and Egyptian |
| **MT second opinion** | [ai4bharat/indictrans2-en-indic-1B](https://huggingface.co/ai4bharat/indictrans2-en-indic-1B) + [indic-en-1B](https://huggingface.co/ai4bharat/indictrans2-indic-en-1B) (MIT) | [facebook/nllb-200-distilled-600M](https://huggingface.co/facebook/nllb-200-distilled-600M) (CC-BY-NC-4.0; covers Tigrinya, Oromo, Somali, Sinhala…) | **Roadmap** (no back-translation check today) | Back-translation check on safety-critical sentences (drugs, doses, allergies) |
| **TTS, patient (Indic incl. Nepali)** | [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts) (Apache-2.0, gated) | [facebook/mms-tts-*](https://huggingface.co/facebook/mms-tts-hin) (CC-BY-NC-4.0; no Nepali) · [kenpath/svara-tts-v1](https://huggingface.co/kenpath/svara-tts-v1) (Apache-2.0) | **Used** (Indic Parler, streaming). MMS-TTS and svara: not used | The only permissively licensed open TTS found that speaks Nepali, Malayalam, Bengali, Urdu, Tamil and Telugu in one model |
| **TTS, patient (fil, id, sw, am, ti, so, om)** | `facebook/mms-tts-{tgl,ind,swh,amh,tir,som,orm}` (CC-BY-NC-4.0, ~36M params each, VITS) | [k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice) (weights CC-BY-NC; 600+ languages) | **Roadmap.** Tagalog is text only today | Tiny and fast; Amharic and Tigrinya need `uroman` romanization |
| **TTS, gap languages (si, ps)** | [k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice) (lists `si`, `pbt`, `pst`) | Large native-script text + PDF (per [03 §9](03-architecture.md)) | **Roadmap** | MMS-TTS has no Sinhala, Pashto or Nepali checkpoint |
| **TTS, doctor side** | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0; `fal-ai`, `deepinfra`) for English; [ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox) Multilingual (MIT; `fal-ai`, `replicate`, `deepinfra`) for Arabic | `facebook/mms-tts-ara` | **Used** for English (Kokoro, optional, off by default). Chatterbox / Arabic voice: roadmap | Serverless |

**Two rules that make this stack work:**
1. **Providers for the LLM** (gpt-oss-120b, plus the optional Kokoro doctor voice). This is pay-per-token, with no idle GPU.
2. **One GPU Space for all speech models** (Whisper turbo, VoxLingua107, IndicConformer, Indic Parler). Today **no Inference Provider serves any TTS model that speaks Nepali, Malayalam, Bengali, Tagalog or Urdu**. The full provider-served TTS list on 2026-11-06 is Kokoro-82M, chatterbox, chatterbox-turbo, Qwen3-TTS-CustomVoice and sesame/csm-1b. Provider-served ASR is limited to Whisper v3/turbo, Qwen3-ASR, Cohere Transcribe and NVIDIA Nemotron 3.5 ASR. We run Whisper on the worker too, so one `/hear` call does role ID and ASR.

---

## 1. Why a cascade beats end-to-end speech-to-speech

### 1.1 The evidence: language coverage for *speech output*

| Model (HF repo) | License | Speech **in** | Speech **out** | Speaks Nepali / Malayalam / Tagalog? | On Providers? |
|---|---|---|---|---|---|
| [facebook/seamless-m4t-v2-large](https://huggingface.co/facebook/seamless-m4t-v2-large) | CC-BY-NC-4.0 | ~101 languages | 35 languages incl. arb, ben, hin, urd, tel, **tgl**, ind, swh | **No** npi, mal, tam, amh, som, pan, pbt (text target only); no sin, tir | No |
| [facebook/seamless-streaming](https://huggingface.co/facebook/seamless-streaming) | CC-BY-NC-4.0 | Same family | Same family | Same gaps | No |
| [facebook/seamless-expressive](https://huggingface.co/facebook/seamless-expressive) | other, manually gated | en, es, it, de, zh, fr | Same 6 | No | No |
| [Qwen/Qwen3-Omni-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct) | Apache-2.0 | 19 (incl. ar, ur, id, ms; **not** hi) | **10** (en, zh, fr, de, ru, it, es, pt, ja, ko) | No | No |
| [Qwen/Qwen2.5-Omni-7B](https://huggingface.co/Qwen/Qwen2.5-Omni-7B) | Apache-2.0 | Multilingual | 2 voices; output languages beyond en/zh not documented *(unverified)* | No evidence | No |
| [kyutai/hibiki-zero-3b-pytorch-bf16](https://huggingface.co/kyutai/hibiki-zero-3b-pytorch-bf16) | CC-BY-NC-SA-4.0 | fr, es, pt, de | en only | No | No |
| [kyutai/moshiko-pytorch-bf16](https://huggingface.co/kyutai/moshiko-pytorch-bf16) (Moshi) | CC-BY-4.0 | en | en | No | No |
| [mistralai/Voxtral-Small-24B-2507](https://huggingface.co/mistralai/Voxtral-Small-24B-2507) / [Mini-3B](https://huggingface.co/mistralai/Voxtral-Mini-3B-2507) | Apache-2.0 | 8 (en, fr, de, es, it, pt, nl, hi) | Text only | n/a | No |
| [google/gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it) (successor to Gemma 3n audio) | Apache-2.0 | ASR + speech→text translation, max 30 s clips | Text only | n/a | No |
| [microsoft/Phi-4-multimodal-instruct](https://huggingface.co/microsoft/Phi-4-multimodal-instruct) | MIT | 8 (en, zh, de, fr, it, ja, es, pt) | Text only | n/a | No |
| [fixie-ai/ultravox-v0_6-llama-3_3-70b](https://huggingface.co/fixie-ai/ultravox-v0_6-llama-3_3-70b) | MIT | Whisper-turbo encoder; v0.6 adds Hindi data | Text only | n/a | No |

**Conclusion.** No open end-to-end model on the Hub produces speech in Nepali or Malayalam, the two languages Bayan most needs to prove. Seamless comes closest, with Tagalog, Bengali, Urdu, Hindi, Telugu, Indonesian and Swahili speech out, but it is non-commercial and not served by any provider.

### 1.2 The second reason: the text in the middle is the product

- **Safety sentinel needs text.** Drug–allergy and dose checks run on a structured state built from transcripts ([03 §4](03-architecture.md)). A speech-token-to-speech-token model gives us nothing to check.
- **Audit and notes need text.** The SOAP note, the patient PDF and the alert log all come from the bilingual transcript.
- **Per-stage error control.** In a cascade we can show the doctor an ASR confidence score, back-translate a dose sentence, or ask "Did you say…?" End-to-end models fail silently.
- **Per-language best of breed.** Each stage picks the best model for each language (IndicConformer for Malayalam, Whisper for English; Voxtral for Gulf Arabic is on the roadmap), which no single model can match today.
- **Efficiency.** The expensive reasoning runs on a provider by the token. The speech models are small (36M–7B parameters).

### 1.3 Where end-to-end *can* help (fallback only; not implemented)

- **SeamlessM4T v2 as a "one-model" fallback** for languages where it has speech output (Tagalog, Bengali, Urdu, Hindi, Telugu, Indonesian, Swahili, Arabic). If our TTS for one of these fails during the demo, `SeamlessM4Tv2Model` can produce text and speech in one call in Transformers. It is non-commercial, so it is for the demo only.
- **Gemma 4 E4B** (Apache-2.0) can do speech→English text translation in one pass. It is a candidate cross-check for ASR+MT on ≤30 s clips, not a primary path.

---

## 2. Which languages actually matter in Qatar

Qatar does not publish population by nationality, so all figures are **unofficial estimates** (embassy-derived) and are used here only for prioritization. Sources: [Wikipedia, Demographics of Qatar](https://en.wikipedia.org/wiki/Demographics_of_Qatar) (2019 compilation) and the [Gulf Labour Markets & Migration programme (GLMM)](https://gulfmigration.grc.net/qatar-estimates-of-foreign-nationals-residing-in-qatar-by-country-of-citizenship-selected-countries-2014/) (2014).

| Community (est.) | Languages Bayan must cover | Priority |
|---|---|---|
| India, ~700k (2019) | Malayalam, Tamil, Hindi, Telugu (plus others) | **Tier 1**: Hindi, Malayalam. Tier 2: Tamil, Telugu. *(No reliable per-state breakdown found. That Malayalam is the largest Indian language group is widely assumed but unverified.)* |
| Nepal, ~400k (2019) | Nepali | **Tier 1** |
| Bangladesh, ~400k (2019) | Bengali | **Tier 1** |
| Egypt, ~300k (brief estimate) | Egyptian Arabic | Doctor-side Arabic covers this, but Arabic–Arabic visits would need speaker diarization (roadmap; pyannote is the candidate) |
| Philippines, ~236k (2019) | Tagalog/Filipino (many also speak English) | **Tier 1** |
| Pakistan, ~150–180k (2019) | Urdu, Punjabi (Shahmukhi script), Pashto | **Tier 1**: Urdu. Tier 2: Punjabi. Tier 3: Pashto |
| Sri Lanka, ~140k (2019) | Sinhala, Tamil | Tier 2 (large domestic-worker community) |
| Kenya, ~30k (2019 compilation) | Swahili (plus English) | Tier 2 |
| Ethiopia, ~21k (2014) | Amharic, Oromo, Tigrinya | Tier 2: Amharic. Tier 3: Oromo, Tigrinya |
| Indonesia, Eritrea, Somalia, Sudan, Uganda | Indonesian, Tigrinya, Somali, Sudanese Arabic, Luganda | No reliable figure found; Indonesian Tier 2, others Tier 3 |

---

## 3. Language coverage matrix

**Tier legend.** **T1** = demo target: the full speech-in/speech-out path must pass the smoke test in §9 before we call it "demo-verified". **T2** = a model exists for every stage, but there is no demo verification. **T3** = experimental speech; the default is on-screen native text, the PDF, and English/Arabic audio for staff.

**Status today.** The app's language picker offers Nepali, Hindi, Urdu, Bengali, Malayalam and Filipino. Nepali is the golden-path language. None of the languages has had a native-speaker review yet. The **In the app today** column names the models the code actually uses; the columns to its right are the design-time research (alternatives considered / roadmap).

ASR numbers are as published: **W** = Whisper large-v2 FLEURS WER % ([Whisper paper, Table 13](https://ar5iv.labs.arxiv.org/html/2212.04356)); **O** = Omnilingual ASR LLM-7B CER % from [Meta's per-language table](https://github.com/facebookresearch/omnilingual-asr/blob/main/per_language_results_table_7B_llm_asr.csv) (Meta's own eval sets). WER and CER are **not comparable** with each other. WER above 100% usually means output in the wrong script, or garbage. Large-v3 is said to cut errors by 10–20% compared with v2 ([model card](https://huggingface.co/openai/whisper-large-v3)), but OpenAI publishes no per-language table for v3.

| Language (code) | Role | **In the app today** (ASR · translation · voice) | ASR: best → fallback (research) | Text translation (to/from en) (research) | TTS: best → fallback (research) | Tier |
|---|---|---|---|---|---|---|
| English (en) | Doctor | Whisper turbo (worker) · gpt-oss-120b · Kokoro, optional (off by default) | whisper-large-v3-turbo → Voxtral-Realtime-2602 | — | Kokoro-82M (Providers) | **T1** |
| Arabic MSA + Gulf + Egyptian (ar, afb, arz) | Doctor (and Arab patients) | Whisper turbo (worker) · gpt-oss-120b · **no voice (text only)** | Voxtral-Mini-4B-Realtime-Arabic (avg CER 8.82% at 480 ms over 7 Arabic benchmarks) → whisper-large-v3 (W 16.0) | gpt-oss-120b; Fanar-1-9B / Fanar-2-27B for Arabic polish (roadmap) | Chatterbox Multilingual `ar` (Providers) → mms-tts-ara | **T1** |
| Hindi (hi) | Patient | IndicConformer · gpt-oss-120b · Indic Parler-TTS (less tested than Nepali) | IndicConformer → Whisper (W 21.5) / Nemotron 3.5 Transcribe (FLEURS 7.47, `deepinfra`) | gpt-oss-120b; IndicTrans2 check | Indic Parler-TTS → Chatterbox `hi` (Providers) / MMS-TTS hin / Kokoro `h` | **T1** |
| Urdu (ur) | Patient | IndicConformer · gpt-oss-120b · Indic Parler-TTS (less tested) | IndicConformer → Whisper (W 22.6) / Omni (O 3.5) | gpt-oss-120b; IndicTrans2 check | Indic Parler-TTS (no named Urdu speaker listed) → mms-tts-urd-script_arabic / Seamless | **T1** |
| Nepali (ne/npi) | Patient | IndicConformer · gpt-oss-120b · Indic Parler-TTS, streaming (golden path) | IndicConformer → Omni (O 12.3 `npi`; 6.5 `nep`); Whisper weak (W 47.1) | gpt-oss-120b; IndicTrans2 check | Indic Parler-TTS (1 speaker, "Amrita") → svara-tts-v1 / OmniVoice | **T1** |
| Bengali (bn) | Patient | IndicConformer · gpt-oss-120b · Indic Parler-TTS (less tested) | IndicConformer → Omni (O 2.8); **Whisper fails (W 104.1)** | gpt-oss-120b; IndicTrans2 check | Indic Parler-TTS → mms-tts-ben / Seamless | **T1** |
| Malayalam (ml) | Patient | IndicConformer · gpt-oss-120b · Indic Parler-TTS (less tested) | IndicConformer → Omni (O 5.3); **Whisper fails (W 100.7)** | gpt-oss-120b; IndicTrans2 check | Indic Parler-TTS → mms-tts-mal / svara | **T1** |
| Tagalog/Filipino (tl/fil) | Patient | Whisper turbo (worker) · gpt-oss-120b · **no voice (text only)** | whisper-large-v3 (W 13.8) → Qwen3-ASR-1.7B (`deepinfra`) / Omni (O 1.6) | gpt-oss-120b | mms-tts-tgl → Seamless (tgl) / OmniVoice. **All non-commercial** | **T1** |
| Tamil (ta) | Patient | Worker can do ASR + voice; not in the app's language picker | IndicConformer → Whisper (W 17.5) / Omni (O 5.2) | gpt-oss-120b; IndicTrans2 | Indic Parler-TTS → mms-tts-tam | T2 |
| Telugu (te) | Patient | Worker can do ASR + voice; not in the app's language picker | IndicConformer → Omni (O 6.5); Whisper fails (W 99.0) | gpt-oss-120b; IndicTrans2 | Indic Parler-TTS → mms-tts-tel / Seamless | T2 |
| Punjabi (pa) | Patient | Roadmap | IndicConformer (Gurmukhi) → Omni (O 4.3); Whisper fails (W 102.4) | gpt-oss-120b; IndicTrans2 (Gurmukhi only) | Indic Parler (unofficial) → mms-tts-pan / svara. **Pakistani patients read Shahmukhi; the PDF needs that script** | T2 |
| Sinhala (si) | Patient | Roadmap | Omni (O 7.2) → Whisper (no FLEURS figure in Table 13) | gpt-oss-120b; NLLB check | OmniVoice (NC) → community [chan4lk/piper-tts-sinhala](https://huggingface.co/chan4lk/piper-tts-sinhala) (MIT, quality unknown) | T2 |
| Indonesian (id) | Patient | Roadmap | whisper-large-v3 (W 7.1) → Qwen3-ASR / Omni (O 1.8) | gpt-oss-120b | mms-tts-ind → Seamless / OmniVoice | T2 |
| Swahili (sw) | Patient | Roadmap | Omni (O 2.8) → Whisper (W 39.3) | gpt-oss-120b; NLLB check | Chatterbox `sw` (Providers, MIT) → mms-tts-swh | T2 |
| Amharic (am) | Patient | Roadmap | Omni (O 5.7); **Whisper fails (W 140.3)** | gpt-oss-120b; NLLB check | mms-tts-amh (needs `uroman`) → OmniVoice | T2 |
| Somali (so) | Patient | Roadmap | Omni (O 6.1); Whisper fails (W 102.9) | gpt-oss-120b; NLLB check | mms-tts-som → OmniVoice | T3 |
| Tigrinya (ti) | Patient | Roadmap | Omni (O 9.8); no Whisper support | NLLB-200 (has `tir`); LLM quality unknown | mms-tts-tir (needs `uroman`) → OmniVoice | T3 |
| Oromo (om) | Patient | Roadmap | Omni (O 7.8); no Whisper support | NLLB-200 (has `gaz`); LLM quality unknown | mms-tts-orm → OmniVoice | T3 |
| Pashto (ps) | Patient | Roadmap | Omni (O 8.8 `pbt` / 12.6 `pus`); Whisper fails (W 93.7) | gpt-oss-120b; NLLB check | **OmniVoice only** (NC). Otherwise text | T3 |

**Honest gaps.**
- **No commercial-safe TTS was found for Tagalog, Indonesian, Amharic, Tigrinya, Somali, Oromo or Pashto.** Every option is CC-BY-NC (MMS-TTS, Seamless, OmniVoice).
- **Translation quality for Nepali, Malayalam, Sinhala, Tigrinya, Oromo and Pashto has not been measured for gpt-oss-120b**, and there is no published per-language evaluation we could find. §9 adds a $1-scale measurement.
- **Dialect and register.** All ASR numbers come from read or clean speech. Clinic audio (accented, emotional, code-switched, noisy) will be worse *(unverified, expected)*.
- **No native-speaker review yet** of any translation, voice or patient sheet in the app.

---

## 4. Stage deep dives

### 4.1 VAD, turn-taking, role and language ID (ambient, no push-to-talk)

| Model | License | Size | What it gives us | Notes |
|---|---|---|---|---|
| **Silero VAD** ([GitHub](https://github.com/snakers4/silero-vad), [onnx-community/silero-vad](https://huggingface.co/onnx-community/silero-vad)) | MIT | ~2 MB ONNX | Speech/non-speech frames | **Used**: inside FastRTC `ReplyOnPause` ([source](https://github.com/gradio-app/fastrtc)) on the app Space, server side. Could also run in the browser via ONNX (not done) |
| [pipecat-ai/smart-turn-v3](https://huggingface.co/pipecat-ai/smart-turn-v3) | BSD-2 | 8M params (Whisper-tiny encoder) | "Has the speaker *finished*?" from the waveform, ≤8 s window | 23 languages incl. **Arabic, Bengali, Hindi, Indonesian** ([repo](https://github.com/pipecat-ai/smart-turn)). "~10 ms on some CPUs, <100 ms on most cloud instances." Not trained on Nepali/Malayalam, so use it only as a hint |
| [speechbrain/lang-id-voxlingua107-ecapa](https://huggingface.co/speechbrain/lang-id-voxlingua107-ecapa) | Apache-2.0 | ECAPA-TDNN (small) | LID over 107 languages; covers every target except **Tigrinya, Oromo** ([label list](https://huggingface.co/speechbrain/lang-id-voxlingua107-ecapa/blob/main/label_encoder.txt)) | **Used** (role ID on the worker). 6.7% error on the VoxLingua107 dev set. The card warns it "doesn't work well on speech with a foreign accent" |
| Whisper LID (any Whisper) | Apache/MIT | — | Free byproduct of ASR | 99 languages; no Tigrinya/Oromo. Logged on the worker for diagnostics only |
| [facebook/mms-lid-126 / 256 / 4017](https://huggingface.co/facebook/mms-lid-256) | CC-BY-NC-4.0 | ~1B | LID for up to 4,017 languages | Heavy; use only if we must detect Tigrinya/Oromo automatically |
| [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) | CC-BY-4.0, gated | — | Who spoke when; **exclusive** (non-overlapping) mode for aligning with ASR | Not used (roadmap). DER better than 3.1 on most sets (e.g., AMI-IHM 17.0 vs 18.8). Needs pyannote.audio 4.x |
| [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) | MIT, gated | — | Older and stable | Not used. Fallback if 4.x dependencies clash |

**Design as built (in line with [03 §3.1](03-architecture.md)).**
1. **The patient language is pinned at session start** with one tap on the start screen. This is not push-to-talk. Spoken Hindi and Urdu are close to mutually intelligible and differ mainly in script, and Nepali and Hindi share Devanagari and a great deal of vocabulary, so free-running LID would flip between them. The pinned language decides the ASR model, the TTS voice and the PDF script.
2. **LID answers only the role question**: VoxLingua107 scores just {en, ar, patient language}; en/ar means doctor, otherwise patient. That is a far easier decision than 107-way LID.
3. **Arabic–Arabic visits** (Egyptian or Sudanese patients): roadmap. The plan is pyannote community-1, with the doctor enrolled by speaking a sentence at consent time.
4. **Echo guard (built):** `ReplyOnPause(can_interrupt=False)`, and the mic stays held until Bayan's playback ends plus a 300 ms tail ([03 §3.2](03-architecture.md)). Without this the agent would translate itself.

### 4.2 ASR per language

**Used today:** whisper-large-v3-turbo (on the GPU worker, not via Providers) and IndicConformer. Every other row is an alternative considered.

| Model | License | Params | Languages relevant to Bayan | Providers | Quality notes (cited) |
|---|---|---|---|---|---|
| [openai/whisper-large-v3](https://huggingface.co/openai/whisper-large-v3) | Apache-2.0 | 1.55B | 99 incl. all targets except ti, om | `fal-ai`, `replicate`, `hf-inference`, `deepinfra` | v2 FLEURS WER: ar 16.0, hi 21.5, ur 22.6, ta 17.5, tl 13.8, id 7.1, ne 47.1, sw 39.3. **bn 104.1, ml 100.7, te 99.0, pa 102.4, so 102.9, am 140.3, ps 93.7** ([paper, Table 13](https://ar5iv.labs.arxiv.org/html/2212.04356)). ~1% of transcripts contain hallucinated phrases, and 38% of those include explicit harms ([Koenecke et al., 2024](https://arxiv.org/abs/2402.08021)) |
| [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | MIT | 809M | Same | `hf-inference`, `deepinfra` | 4 decoder layers instead of 32: "way faster… minor quality degradation" (card) |
| [ai4bharat/indic-conformer-600m-multilingual](https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual) | MIT, gated | 600M | 22 Indic incl. **ne, hi, ur, bn, ml, ta, te, pa** | none | Hindi WER 13.2 on Vaani-Benchmark-V1.0 (card). Needs `trust_remote_code`; call `model(wav, "ml", "ctc")`. The card now points to a newer "Indic-Transcribe" ([bodhan-ai/indic-transcribe-flex](https://huggingface.co/bodhan-ai/indic-transcribe-flex), license "other", gated, not evaluated by us) |
| [facebook/omniASR-LLM-7B](https://huggingface.co/facebook/omniASR-LLM-7B) (+ CTC-300M/1B/3B/7B, LLM-300M/1B/3B) | Apache-2.0 | 0.3–7.8B | 1,600+ incl. **every** target | none | CER <10 for 78% of languages (Meta). **CTC-1B: ~3 GiB VRAM, 48× faster than LLM-7B; LLM-7B: ~17 GiB, RTF 0.092 on A100** (card). Uses the `omnilingual-asr` package (fairseq2), not Transformers |
| [mistralai/Voxtral-Mini-4B-Realtime-Arabic](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-Arabic) | Apache-2.0 | 4.4B | MSA + 15 dialects incl. **Gulf (`afb`), Najdi, Egyptian, Sudanese, Levantine, Iraqi** | none | Avg CER 8.82% at 480 ms delay (7 benchmarks; the card warns normalization affects scores). Transformers ≥5.2 or vLLM `/v1/realtime`. WebGPU demo Space exists |
| [mistralai/Voxtral-Mini-4B-Realtime-2602](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602) | Apache-2.0 | 4.4B | 13 incl. en, ar, hi | none | FLEURS at 480 ms: en 4.90, hi 12.88, ar 22.53. Configurable 80 ms–2.4 s delay |
| [CohereLabs/cohere-transcribe-arabic-07-2026](https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026) | Apache-2.0, gated | 2B | Arabic + dialects + English code-switch | none | Best average on the Open Universal Arabic ASR Leaderboard per its card (25.87 WER / 11.80 CER; SADA, Saudi, 37.47 WER). The card says code-switching is "inconsistent" |
| [CohereLabs/cohere-transcribe-03-2026](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026) | Apache-2.0, gated | 2B | 14 incl. en, ar (no South Asian) | `fal-ai` | Doctor-side alternative only |
| [Qwen/Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) / [0.6B](https://huggingface.co/Qwen/Qwen3-ASR-0.6B) | Apache-2.0 | 2.3B / 0.9B | 30 incl. en, ar, hi, **fil**, id, ms. **No** ur, bn, ne, ml, ta | `deepinfra` | Has streaming mode and built-in LID |
| [nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B) | OpenMDW-1.1 | 30B MoE (~4.3B active) | 40 incl. en, ar, hi, **bn, ta, te, tl**, id | `deepinfra` | FLEURS WER: ar 6.35, hi 7.47, fil 18.28, id 14.51. **Offline model**, not real-time streaming. No ur, ne, ml |
| [microsoft/VibeVoice-ASR](https://huggingface.co/microsoft/VibeVoice-ASR) | MIT | 8.7B | 51 incl. ne, ur, hi, ar, tl, sw | none | Joint ASR + diarization + timestamps over 60-min audio. A candidate for an **end-of-visit re-transcription** pass, not the live loop |
| [facebook/mms-1b-all](https://huggingface.co/facebook/mms-1b-all) | CC-BY-NC-4.0 | 1B | 1,162 (adapters) | none | Native in Transformers; superseded by Omnilingual |
| [nvidia/canary-1b-v2](https://huggingface.co/nvidia/canary-1b-v2), [parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | CC-BY-4.0 | 1B / 0.6B | 25 European languages only | none | **Not relevant** to patient side |

**Arabic dialect notes (research; Arabic goes through Whisper turbo today).** Voxtral-Arabic is the only model found that explicitly lists Gulf Arabic and streams. Omnilingual's Gulf (`afb`) CER is **41.8** and Najdi (`ars`) **38.9**, so do not use it for Gulf speech. Egyptian (`arz` 9.9) and Sudanese (`apd` 14.9) are better. A Hub search also returns community Egyptian Whisper fine-tunes (e.g., [AbdelrahmanHassan/whisper-large-v3-egyptian-arabic](https://huggingface.co/AbdelrahmanHassan/whisper-large-v3-egyptian-arabic)), which we have not evaluated.

**Fanar Aura (QCRI) speech.** The Fanar API exposes `Fanar-3.0-Aura-Transcribe`, `Fanar-Aura-TTS-2`, diarization and `Fanar-3.0-Shaheen-Translate` (en↔ar only) ([OpenAPI spec](https://api.fanar.qa/openapi.json)). Access is by request ([api.fanar.qa](https://api.fanar.qa/request/en)), and **we found no Aura weights on the Hub**. It could be an optional "around the edges" integration for the Arabic side (not done). It does not count as HF usage.

### 4.3 Translation + reasoning LLM (the clinical brain)

Live router snapshot, 2026-11-06 (`/v1/models`). "tok/s" = provider throughput, "TTFT" = first-token latency, prices in $ per 1M tokens (input / output).

| Model | License | Providers (live) | Fastest observed | Structured output | Multilingual notes |
|---|---|---|---|---|---|
| **[openai/gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b)** | Apache-2.0 | groq, cerebras, novita, together, fireworks-ai, featherless-ai, scaleway, baseten, ovhcloud, deepinfra | **Cerebras ~1,174 tok/s, TTFT ~294 ms, $0.35/$0.75**; Groq ~423 tok/s, ~320 ms, $0.15/$0.75 | Yes (router flag); native function calling; reasoning effort low/medium/high | No published per-language eval for our languages → measure (§9) |
| [openai/gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) | Apache-2.0 | groq, deepinfra, ovhcloud, featherless-ai | Groq ~678 tok/s, ~413 ms | Yes | Cheaper fallback for the think loop |
| [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) | Apache-2.0 | cerebras, novita, nscale, deepinfra, ovhcloud, featherless-ai | Cerebras ~709 tok/s, ~279 ms | **Not on Cerebras** (yes on nscale) | Built on Qwen3.5; language count not stated in its card |
| [Qwen/Qwen3.5-397B-A17B](https://huggingface.co/Qwen/Qwen3.5-397B-A17B) | Apache-2.0 | novita, deepinfra, scaleway, ovhcloud, featherless-ai | ~61 tok/s, TTFT 0.35–1.2 s | Not flagged on the providers listed | "201 languages and dialects" (card). Best candidate for low-resource quality, too slow for the talk loop |
| [google/gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it) / [26B-A4B](https://huggingface.co/google/gemma-4-26B-A4B-it) | **Apache-2.0** | novita, deepinfra, featherless-ai (+ scaleway for 26B) | 26B-A4B on DeepInfra ~111 tok/s, ~271 ms | Yes | Pretrained on 140+ languages, "35+ out of the box" (card) |
| [Qwen/Qwen3-235B-A22B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507) | Apache-2.0 | deepinfra, scaleway | ~24 tok/s | Yes | Superseded by Qwen3.5 |
| [Qwen/Qwen3-Next-80B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Instruct) | Apache-2.0 | featherless-ai, deepinfra | — | — | Superseded |
| [meta-llama/Llama-3.3-70B-Instruct](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct) | Llama 3.3 | novita, featherless-ai, scaleway, ovhcloud (**groq mapping in error state**) | ~51 tok/s | Varies | Officially 8 languages (en, fr, it, pt, hi, es, th, de). **Not a fit** |
| [QCRI/Fanar-1-9B-Instruct](https://huggingface.co/QCRI/Fanar-1-9B-Instruct) | Apache-2.0 | featherless-ai | — | — | ar + en only; Qatar-built |
| [QCRI/Fanar-2-27B-Instruct](https://huggingface.co/QCRI/Fanar-2-27B-Instruct) | Apache-2.0 | **none** | — | Tool calling | ar + en; MSA, Gulf, Levantine, Egyptian; Gemma-3-27B base; 32K context; Belebele (dialectal Arabic) 86.81 (card). GGUF builds exist (e.g., [mradermacher/Fanar-2-27B-Instruct-GGUF](https://huggingface.co/mradermacher/Fanar-2-27B-Instruct-GGUF)) for llama.cpp |
| [google/medgemma-27b-text-it](https://huggingface.co/google/medgemma-27b-text-it) | HAI-DEF terms, gated | featherless-ai | — | — | English medical text; a candidate second opinion for the sentinel, not for translation |
| [ai4bharat/indictrans2-en-indic-1B](https://huggingface.co/ai4bharat/indictrans2-en-indic-1B) / [indic-en-1B](https://huggingface.co/ai4bharat/indictrans2-indic-en-1B) | MIT, gated | none | — | n/a (MT) | 22 Indic languages incl. ne, ur, bn, ml, ta, te, pa |
| [facebook/nllb-200-3.3B](https://huggingface.co/facebook/nllb-200-3.3B) / [distilled-600M](https://huggingface.co/facebook/nllb-200-distilled-600M) | CC-BY-NC-4.0 | none | — | n/a | 200 languages incl. tir, gaz (Oromo), som, sin, pbt |
| [google/translategemma-27b-it](https://huggingface.co/google/translategemma-27b-it) (4B/12B too) | Gemma terms, gated | none | — | Fixed chat template with `source_lang_code`/`target_lang_code` | 55 languages (WMT24++); 27B MetricX 3.09. The list of languages is not on the card |
| [sarvamai/sarvam-translate](https://huggingface.co/sarvamai/sarvam-translate) | **GPL-3.0** | none | — | — | 22 Indic + en. License is awkward for products |
| [CohereLabs/command-a-translate-08-2025](https://huggingface.co/CohereLabs/command-a-translate-08-2025), [aya-expanse-32b](https://huggingface.co/CohereLabs/aya-expanse-32b) | CC-BY-NC-4.0 | cohere | ~70 / ~42 tok/s | Yes / No | **Only 23 languages**: no Nepali, Bengali, Urdu, Malayalam, Tagalog |
| [CohereLabs/tiny-aya-global](https://huggingface.co/CohereLabs/tiny-aya-global) | CC-BY-NC-4.0 | cohere | ~134 tok/s | No | 67 languages incl. ne, tl, bn, ur, ta, te, pa, am, sw. **No ml, si, so, ti, om, ps** |

**What we run (only gpt-oss-120b; the other rows are alternatives considered).**
- **Talk loop (translation):** gpt-oss-120b on Cerebras, `reasoning_effort="low"`, temperature 0. Output is one JSON object: the translation, a literal English rendering, and the drugs, allergies and tests mentioned. There is no provider fallback in the talk loop yet: a failed call shows "Could not translate that. Please say it again."
- **Think loop (clinical-fact extraction):** the same model on **Groq** at `medium`, with `json_schema` output, falling back to Cerebras. It runs in the background and never blocks speech. The fine-tuned Qwen3-4B from [06](06-fine-tuning-plan.md) was **not** trained or shipped.
- **Agents:** the smolagents copilot agent and wrap-up agent run gpt-oss-120b on **Cerebras only**, at `medium` ([11](11-clinical-copilot-agent.md)).
- **Wrap-up (SOAP note + care plan):** gpt-oss-120b on Cerebras at `medium`, note and care plan in parallel. No Qwen3.5 fallback and no Fanar polishing in the build.
- **Never `high`:** measured to return empty replies after about 12 s.
- **Roadmap:** an independent back-translation (IndicTrans2 for Indic, NLLB for the rest) of safety-critical sentences (allergy, drug, dose, red flags), shown to the doctor; spelling out numbers for TTS.

### 4.4 TTS per language

**Used today:** Indic Parler-TTS (GPU worker, streaming) and Kokoro-82M (optional English doctor voice via Providers). Every other row is an alternative considered.

| Model | License | Params | Languages relevant to Bayan | Providers | Notes |
|---|---|---|---|---|---|
| [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts) | Apache-2.0 (gated, auto) | ~0.9B | Official: **ne, hi, ur, bn, ml, ta, te** (+ 14 more). Unofficial: Punjabi | none | 69 speakers; Nepali has only **1** ("Amrita"). Native-speaker score after fine-tuning: ne 80.0, bn 86.2, ml 86.5, hi 84.8, ta 75.5, te 88.5, ur 77.8 (card). Streaming via the parler-tts [INFERENCE guide](https://github.com/huggingface/parler-tts/blob/main/INFERENCE.md). The card now points to a newer `bodhan-ai/indic-speak` (not evaluated) |
| [facebook/mms-tts-*](https://huggingface.co/facebook/mms-tts-hin) | CC-BY-NC-4.0 | ~36M each (VITS) | hin, ben, mal, tam, tel, pan, urd-script_arabic, tgl, ind, swh, amh, tir, som, orm, ara. **No npi/nep, sin, pus/pbt** (repos do not exist) | none | Very fast, single voice, flat prosody. `amh`/`tir` need `uroman` romanization (`is_uroman: true`) |
| [k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice) | Code Apache-2.0; **weights CC-BY-NC** (training data) | ~0.6B (Qwen3-0.6B base) | 646 language codes incl. **si, pbt/pst, npi, fil, ml, ta, te, so, ti, om, am, ur, bn, hi** | none | Zero-shot cloning/voice design; "RTF as low as 0.025" (card). Supported backend in huggingface/speech-to-speech. **Only option found for Sinhala and Pashto.** Quality on low-resource languages is unknown → listen-test |
| [kenpath/svara-tts-v1](https://huggingface.co/kenpath/svara-tts-v1) | Apache-2.0 | 3.3B | 19: hi, bn, ml, ta, te, pa, **ne**, … | none | Emotion tags; heavier. Backup for Indic |
| [ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox) (Multilingual V3, 0.5B) | MIT | 0.5B | 23 incl. **ar, hi, sw, ms** (no Indic beyond Hindi) | `fal-ai`, `replicate`, `deepinfra` | Voice cloning. Which variant (EN-only or multilingual) each provider serves is **unverified** → test `language_id` |
| [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | Apache-2.0 | 82M | en (+ hi, ja, zh, es, fr, it, pt voices) | `fal-ai`, `deepinfra` | Doctor-side English |
| [Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) | Apache-2.0 | 1.9B | 10 (zh, en, ja, ko, de, fr, ru, pt, es, it) | `together` | 97 ms streaming claim. **No South Asian languages** |
| [mistralai/Voxtral-4B-TTS-2603](https://huggingface.co/mistralai/Voxtral-4B-TTS-2603) | CC-BY-NC-4.0 | 4B | 9 incl. ar, hi | none | Not needed |
| SeamlessM4T v2 (T2ST) | CC-BY-NC-4.0 | 2.3B | Speech out: ben, hin, urd, tel, tgl, ind, swh, arb | none | One-model fallback (§1.3) |
| [coqui/XTTS-v2](https://huggingface.co/coqui/XTTS-v2), [SWivid/F5-TTS](https://huggingface.co/SWivid/F5-TTS), [FunAudioLLM/CosyVoice2-0.5B](https://huggingface.co/FunAudioLLM/CosyVoice2-0.5B) | other (Coqui CPML) / CC-BY-NC / Apache-2.0 | — | XTTS: 17 languages incl. ar, hi; CosyVoice: 9 (no South Asian) | none | **Not useful** for our patient languages |

**Gap fallbacks.** Today: native-script text on screen and the PDF ([03 §9](03-architecture.md)); this is what Tagalog patients get, and there is no Arabic voice either. Roadmap, in order: (1) OmniVoice. (2) Seamless where it has speech output. The audio file for illiterate patients is the hardest gap for Sinhala and Pashto. Be upfront about it in the pitch.

---

## 5. Hugging Face tooling that applies

| Tool | How Bayan uses it | Notes |
|---|---|---|
| **Inference Providers** (`huggingface_hub.InferenceClient`) | **Used:** `chat_completion` for gpt-oss-120b (Cerebras, Groq); `text_to_speech` for the optional Kokoro doctor voice | Provider pinned per call (`provider="cerebras"` / `"groq"`) ([docs](https://huggingface.co/docs/inference-providers/index)). Provider ASR and other models are not used |
| **smolagents** (1.26.0) | **Used:** `ToolCallingAgent` + `InferenceClientModel` for the copilot agent and the wrap-up agent ([11](11-clinical-copilot-agent.md)) | Cerebras only; our 2-line system template replaces the 3.8k-char default |
| **Spaces** | **Used:** the app Space (Gradio + FastAPI + FastRTC, `cpu-upgrade`) and the private voice-worker Space (`l4x1`, $0.80/h), called with `gradio_client` | Per-minute billing; set a **sleep time** ([docs](https://huggingface.co/docs/hub/spaces-gpus)) |
| **Inference Endpoints** | Not used. The voice worker is a GPU Space instead | L4 $0.80/h, L40S $1.80/h, A100 $2.50/h ([pricing](https://huggingface.co/docs/inference-endpoints/en/pricing)). Possible production host |
| **ZeroGPU** | Not used | Half RTX Pro 6000 (48 GB). **Gradio SDK only, no `torch.compile`**, daily quota (free 5 min, PRO 40 min), then $1 per 10 min ([docs](https://huggingface.co/docs/hub/spaces-zerogpu)). Each call waits for a GPU allocation, which is risky for the talk loop |
| **Transformers / parler-tts / speechbrain** | **Used** on the worker: Whisper turbo (`WhisperForConditionalGeneration`), IndicConformer (`trust_remote_code`), Indic Parler (`parler-tts`), VoxLingua107 (`speechbrain`) | Transformers pinned to 4.46.1 because `parler-tts` needs it |
| **[FastRTC](https://github.com/gradio-app/fastrtc)** (MIT) | **Used:** WebRTC audio into Python; `ReplyOnPause` gives Silero-based turn-taking | Own Cloudflare TURN relay for the WebRTC connection |
| **[huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech)** | Reference only | Reference cascade (Apache-2.0): Silero VAD → STT → LLM → TTS |
| **llama.cpp** | Roadmap: Fanar-2-27B or a small model as GGUF for an on-prem story | Matches the hackathon's local-models workshop |
| **HF Jobs** | Roadmap: the §9 eval and the LoRA in [06](06-fine-tuning-plan.md). Not part of the shipped build | Save results to a Hub dataset from inside the job |

Minimal call sketch of what the code does (see `bayan/talk.py`, `bayan/brain/llm.py`):

```python
from gradio_client import Client, handle_file
from huggingface_hub import InferenceClient

worker = Client("dullgrey/team-qh-129-bayan-voice", hf_token=HF_TOKEN)   # private GPU Space
heard = worker.predict(handle_file(wav_path), "ne", api_name="/hear")       # {"role", "lang", "text", ...}

llm = InferenceClient(provider="cerebras", api_key=HF_TOKEN)
out = llm.chat.completions.create(
    model="openai/gpt-oss-120b", messages=messages, temperature=0, max_tokens=700,
    extra_body={"reasoning_effort": "low"},
)

for chunk in worker.submit(translation, "ne", "", api_name="/speak_stream"):   # ~0.5 s PCM chunks
    ...
```

---

## 6. Licensing: what is fine for the demo and what blocks a product

A hackathon research demo can use CC-BY-NC models. A hospital deployment cannot without separate licensing.

**The runtime uses no CC-BY-NC model.** Its licences: gpt-oss-120b (Apache-2.0), whisper-large-v3-turbo (MIT), VoxLingua107 (Apache-2.0), IndicConformer (MIT, gated), Indic Parler-TTS (Apache-2.0, gated), Kokoro-82M (Apache-2.0), Silero VAD (MIT). The table below covers the alternatives we researched.

| Stage | Commercial-safe (as published) | Non-commercial (demo only) |
|---|---|---|
| VAD / LID / diarization | Silero (MIT), Smart Turn (BSD-2), VoxLingua107 (Apache-2.0), pyannote 3.1 (MIT), community-1 (CC-BY-4.0, attribution) | MMS-LID (CC-BY-NC-4.0) |
| ASR | Whisper (Apache/MIT), IndicConformer (MIT), Omnilingual (Apache-2.0), Voxtral (Apache-2.0), Qwen3-ASR (Apache-2.0), Cohere Transcribe (Apache-2.0), VibeVoice-ASR (MIT); Nemotron (OpenMDW-1.1, read the terms) | MMS-1b-all, SeamlessM4T v2 |
| LLM / MT | gpt-oss (Apache-2.0), Qwen3.x (Apache-2.0), **Gemma 4 (Apache-2.0)**, Fanar (Apache-2.0), IndicTrans2 (MIT). Custom terms: Llama 3.3, Gemma 3/TranslateGemma (Gemma terms), MedGemma (HAI-DEF) | NLLB-200, Aya/Command-A-Translate/Tiny-Aya; sarvam-translate is GPL-3.0 |
| TTS | Indic Parler (Apache-2.0), svara (Apache-2.0), Chatterbox (MIT), Kokoro (Apache-2.0), Qwen3-TTS (Apache-2.0) | **MMS-TTS, OmniVoice weights, Seamless, Voxtral-TTS, F5-TTS**; XTTS-v2 (Coqui CPML) |

**Commercial gap to state in the pitch.** A commercial path exists today for Hindi, Urdu, Nepali, Bengali, Malayalam, Tamil and Telugu (IndicConformer + gpt-oss + Indic Parler), and on paper for Arabic, English and Swahili. Voice for Tagalog, Indonesian, Sinhala, Amharic, Tigrinya, Somali, Oromo and Pashto would need NC models replaced or licensed. Training permissive voices is post-hackathon work ([06 §2](06-fine-tuning-plan.md)).

---

## 7. Latency per turn (target: end of speech → first translated audio ≤ 3 s, not yet measured end to end)

| Step | Number | Basis | How to shrink it |
|---|---|---|---|
| End-of-turn detection | 600 ms minimum silence | FastRTC `SileroVadOptions(min_silence_duration_ms=600)` in `app.py` (configured, not measured) | Smart Turn (roadmap) would allow a shorter silence threshold without cutting people off |
| Upload utterance + role ID + ASR (`/hear` on the worker) | not yet measured in isolation | The worker returns per-call `lid_seconds`, `asr_seconds`, `seconds` | Keep models resident on the GPU; CTC decoding |
| LLM translation (gpt-oss-120b, Cerebras) | not yet measured in isolation; router snapshot 294 ms TTFT, ~1,174 tok/s | `reasoning_effort=low`, `max_tokens` 700 | Shorter prompt; stream and cut at the first sentence (not done) |
| TTS first audio (`/speak_stream`, Indic Parler) | **measured: ~2.2 s for a 3-sentence answer, ~3.1 s for a short question**, from Doha (was 9.9 s and 3.5 s) | Teammate measurement, commit 474e406. TTS only, not end to end | Short first segment; all segments in one batched Parler call |
| Prescription gate (allergy/dose rules on a prescribing sentence) | **~3 ms** | Deterministic code, no LLM | n/a |
| **Total** | **not yet measured end to end** | | The doctor sees the **transcript immediately**. Speech follows |

**Worker boot:** ~137 s → ~99 s after parallel downloads (commit 474e406). The worker sleeps when idle, so the first call after a sleep waits for a boot. The app's no-mic demo mode keeps working in text if the worker is down.

**Background loops (never block speech), measured live on the 9-turn golden path:** extraction ~1.1 s per call; copilot agent ~1.2–1.6 s per run, 1 step; wrap-up ~6–8 s once at the end ([07](07-compute-budget-and-efficiency.md), [11](11-clinical-copilot-agent.md)).

**Streaming as built.** (1) The literal ASR text appears on screen as soon as `/hear` returns. (2) The full utterance is translated in one call (the JSON is not streamed). (3) `/speak_stream` cuts the translation into short segments, generates them in one batched Parler call and streams ~0.5 s PCM chunks, so playback starts before the rest is synthesized. (4) The think loop (idioms, rules, copilot) runs in parallel and only updates the doctor's screen. **Silent alerts are never spoken**, and a held prescribing sentence is not spoken until the doctor chooses.

---

## 8. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ASR errors in low-resource languages (Whisper ≥99% WER on bn/ml/te/pa) | Wrong translation, possible clinical harm | **Built:** route by pinned language to IndicConformer; Whisper only for en/ar and for patient languages IndicConformer lacks. **Planned:** show ASR confidence; "Did you say…?" clarification |
| Whisper hallucinations (~1% of transcripts; [Koenecke et al.](https://arxiv.org/abs/2402.08021)) | Invented content in the record | **Built:** VAD gating (no silence sent); utterances under 0.3 s dropped. **Planned:** `no_speech` threshold; mark low-confidence text |
| Hindi/Urdu/Nepali LID confusion | Wrong voice, wrong PDF script | Session-pinned patient language (§4.1) |
| Bayan hears itself | Feedback loops | **Built:** `can_interrupt=False`; mic held until playback ends + 300 ms ([03 §3.2](03-architecture.md)) |
| Dose/drug mistranslation | Patient harm | **Built:** a prescribing sentence that hits a critical rule is held before it is spoken; the care plan re-checks every medicine and its numbers against the doctor's words. **Planned:** back-translation shown to the doctor; numbers spelled out for TTS |
| LLM quality unknown for ne/ml/si/ti/om/ps | Unnatural or wrong care plan | **Planned:** §9 eval; native-speaker review; IndicTrans2/NLLB cross-check. The patient sheet shows English beneath every native line |
| Provider outage or rate limit | Talk loop stalls | **Built:** brain calls fall back Cerebras ↔ Groq; agent failure → deterministic fallback. Talk-loop translation is Cerebras-only today (a failure asks the speaker to repeat) |
| GPU worker cold start | ~99 s boot after a sleep | Keep the worker awake during the judging window; the no-mic demo mode runs in text if voice is down ([03 §9](03-architecture.md)) |
| Gated models (IndicConformer, Indic Parler) | Build blocked | Gates accepted; `HF_TOKEN` in Space secrets |
| VRAM pressure on one GPU | OOM | The worker loads four models (Parler, Whisper turbo, VoxLingua107, IndicConformer) on one L4 (24 GB) |
| NC licenses | Cannot ship commercially | No NC model in the runtime (§6) |
| Patient data leaving the clinic | Privacy (PDPPL) | Audio goes only to our own worker Space; only text goes to the LLM providers. Demo uses synthetic scripts only. The production path is self-hosted / on-prem ([03 §7](03-architecture.md)) |

---

## 9. Verification plan (cheap, and it doubles as an "Efficiency" talking point)

**Known limitation (live check).** In one test, `gpt-oss-120b` translated the Nepali "जिउ सुन्निएको थियो" ("my body swelled") as "my tongue swelled". Nepali → English quality is unverified; the patient's own words and the literal English are always shown to the doctor, a native-speaker review is needed before any real use, and a dedicated MT model such as AI4Bharat IndicTrans2 is a roadmap option.

**Status (2026-11-07).** Done: the offline suite (`pytest tests`, 269 tests with fake models; `tests/conftest.py` blocks every paid call) and a live golden-path run on the merged code (`python scripts/smoke_e2e.py`, 17/17, about $0.02; it uses text turns, so the voice worker is not involved). Not done yet: the per-language smoke test (item 1) beyond Nepali, the benchmarks (items 2–3), any native-speaker review, and p50/p95 latency (item 4).

1. **Smoke test per Tier-1 language (must pass before calling it "demo-verified").** Speak 5 scripted golden-path sentences. Check that ASR matches the script at a glance, that the translation is accepted by a native-speaker teammate or volunteer where available, that TTS is intelligible, and that the PDF renders the script correctly. Record pass/fail in the README.
2. **Translation mini-benchmark (HF Jobs or a laptop, ~$1).** Take 50 sentences per language from [openlanguagedata/flores_plus](https://huggingface.co/datasets/openlanguagedata/flores_plus) (CC-BY-SA-4.0, gated, auto). Translate en→X and X→en with gpt-oss-120b, Qwen3.5-397B, Gemma-4-31B, and IndicTrans2/NLLB, and score with chrF++. Choose the LLM per language from the results instead of guessing.
3. **ASR mini-benchmark.** 20 utterances per Tier-1 language from [google/fleurs](https://huggingface.co/datasets/google/fleurs) (CC-BY-4.0), comparing Whisper-v3, IndicConformer and Omnilingual CTC-1B on WER/CER plus latency on our GPU.
4. **Latency log.** Per-stage timestamps on every turn, with p50/p95 shown in a debug panel. Use these numbers in the pitch instead of the estimates in §7. (The worker already returns per-call timings; the brain records per-run latency, tokens and cost.)

---

## 10. Sources

- Whisper paper (FLEURS WER, Table 13): https://ar5iv.labs.arxiv.org/html/2212.04356 · large-v3 card: https://huggingface.co/openai/whisper-large-v3 · turbo card: https://huggingface.co/openai/whisper-large-v3-turbo
- Whisper hallucinations: Koenecke et al., "Careless Whisper", https://arxiv.org/abs/2402.08021
- Omnilingual ASR card: https://huggingface.co/facebook/omniASR-LLM-7B · per-language CER: https://github.com/facebookresearch/omnilingual-asr/blob/main/per_language_results_table_7B_llm_asr.csv · coverage summary: https://the-decoder.com/metas-omnilingual-asr-brings-speech-recognition-to-1600-languages/
- IndicConformer: https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual
- Voxtral Realtime (Arabic): https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-Arabic · Voxtral Realtime 2602: https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602
- Cohere Transcribe Arabic: https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026
- Qwen3-ASR: https://huggingface.co/Qwen/Qwen3-ASR-1.7B · Qwen3-Omni: https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct · Qwen3.5: https://huggingface.co/Qwen/Qwen3.5-397B-A17B · Qwen3.8-27B: https://huggingface.co/Qwen/Qwen3.8-27B
- NVIDIA Nemotron 3.5 Transcribe: https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B
- VibeVoice-ASR: https://huggingface.co/microsoft/VibeVoice-ASR
- SeamlessM4T v2: https://huggingface.co/facebook/seamless-m4t-v2-large · Hibiki-Zero: https://huggingface.co/kyutai/hibiki-zero-3b-pytorch-bf16 · Gemma 4: https://huggingface.co/google/gemma-4-E4B-it · Phi-4-multimodal: https://huggingface.co/microsoft/Phi-4-multimodal-instruct · Ultravox: https://huggingface.co/fixie-ai/ultravox-v0_6-llama-3_3-70b
- gpt-oss-120b: https://huggingface.co/openai/gpt-oss-120b · Fanar-2-27B: https://huggingface.co/QCRI/Fanar-2-27B-Instruct · Fanar 2.0 report: https://arxiv.org/abs/2603.16397 · Fanar API spec: https://api.fanar.qa/openapi.json
- IndicTrans2: https://huggingface.co/ai4bharat/indictrans2-en-indic-1B · NLLB-200: https://huggingface.co/facebook/nllb-200-3.3B · TranslateGemma: https://huggingface.co/google/translategemma-27b-it · Tiny Aya: https://huggingface.co/CohereLabs/tiny-aya-global
- Indic Parler-TTS: https://huggingface.co/ai4bharat/indic-parler-tts · Parler inference/streaming: https://github.com/huggingface/parler-tts/blob/main/INFERENCE.md · MMS-TTS: https://huggingface.co/facebook/mms-tts-hin · OmniVoice: https://huggingface.co/k2-fsa/OmniVoice (paper https://huggingface.co/papers/2604.00688) · svara-TTS: https://huggingface.co/kenpath/svara-tts-v1 · Chatterbox: https://huggingface.co/ResembleAI/chatterbox · Kokoro voices: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md · Qwen3-TTS: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
- Silero VAD: https://github.com/snakers4/silero-vad · Smart Turn: https://huggingface.co/pipecat-ai/smart-turn-v3, https://github.com/pipecat-ai/smart-turn · VoxLingua107 LID: https://huggingface.co/speechbrain/lang-id-voxlingua107-ecapa · pyannote community-1: https://huggingface.co/pyannote/speaker-diarization-community-1
- HF Inference Providers: https://huggingface.co/docs/inference-providers/index · router model list (live prices/throughput): https://router.huggingface.co/v1/models · Endpoints pricing: https://huggingface.co/docs/inference-endpoints/en/pricing · Spaces GPUs: https://huggingface.co/docs/hub/spaces-gpus · ZeroGPU: https://huggingface.co/docs/hub/spaces-zerogpu
- huggingface/speech-to-speech: https://github.com/huggingface/speech-to-speech · FastRTC: https://github.com/gradio-app/fastrtc
- Qatar population estimates: https://en.wikipedia.org/wiki/Demographics_of_Qatar · GLMM: https://gulfmigration.grc.net/qatar-estimates-of-foreign-nationals-residing-in-qatar-by-country-of-citizenship-selected-countries-2014/
- Eval datasets: https://huggingface.co/datasets/openlanguagedata/flores_plus · https://huggingface.co/datasets/google/fleurs
