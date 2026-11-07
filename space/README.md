---
title: Bayan AI
emoji: 🩺
colorFrom: green
colorTo: indigo
sdk: gradio
sdk_version: 5.49.1
python_version: "3.10"
app_file: app.py
pinned: true
license: apache-2.0
short_description: Ambient medical interpreter & safety net for Qatar clinics
suggested_hardware: cpu-upgrade
tags:
  - qai-hf-hackathon-2026
  - medical
  - healthcare
  - speech-to-speech
  - translation
  - smolagents
  - agents
  - clinical-decision-support
  - qatar
  - nepali
  - health-equity
models:
  - openai/gpt-oss-120b
  - openai/whisper-large-v3-turbo
  - speechbrain/lang-id-voxlingua107-ecapa
  - ai4bharat/indic-conformer-600m-multilingual
  - ai4bharat/indic-parler-tts
  - hexgrad/Kokoro-82M
---

# Bayan AI · بيان

A clinical AI system that interprets between doctors and patients in Qatar, reasons about the consultation, and flags what gets missed.

The doctor speaks English or Arabic; the patient speaks one of 37 languages. Tap the pearl, speak, tap again. Bayan translates each turn aloud, keeps a running case summary, and puts flags and one suggested next question on the doctor's screen only. A rule-based prescription gate holds a dangerous instruction (for example amoxicillin after a reported penicillin allergy) before the patient hears it. At the end it writes the doctor's note and a care plan in the patient's language, as PDFs and a QR-code phone page.

Add `?demo=1` to the app URL for a scripted Nepali consultation.

| | |
|---|---|
| Interpretation | Speech via a private GPU Space (`dullgrey/team-qh-129-bayan-voice`): VoxLingua107, Whisper, IndicConformer, MMS, Indic Parler-TTS, Supertonic, Piper |
| Reasoning | `openai/gpt-oss-120b` via Inference Providers (Cerebras, Groq); two smolagents agents (clinical review, wrap-up) |
| Safety | 83 cited rules and a 98-entry idiom lexicon, deterministic, no LLM in the hold path |

Source, documentation and results: https://github.com/diyorbekibragimov/BayanAI

Built by Team QH-129 for the Qai × Hugging Face Hackathon O1, Doha, 5–7 Nov 2026. Decision support, not a medical device; not clinically validated. Machine translation is not certified interpreting.
