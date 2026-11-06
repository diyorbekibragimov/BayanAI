---
title: Bayan Voice Worker
emoji: 🎙️
colorFrom: green
colorTo: indigo
sdk: gradio
sdk_version: 5.49.1
python_version: "3.10"
app_file: app.py
pinned: false
license: apache-2.0
short_description: GPU speech backend (Indic ASR + TTS) for Bayan AI
suggested_hardware: l4x1
tags:
  - qai-hf-hackathon-2026
models:
  - ai4bharat/indic-conformer-600m-multilingual
  - ai4bharat/indic-parler-tts
  - openai/whisper-large-v3-turbo
---

# Bayan AI · GPU voice worker

A private backend for [`dullgrey/team-qh-129-bayan-app`](https://huggingface.co/spaces/dullgrey/team-qh-129-bayan-app). It hosts the speech models that no Inference Provider serves:

| Endpoint | Model | Job |
|---|---|---|
| `/hear` | `openai/whisper-large-v3-turbo` + IndicConformer | Doctor or patient? Then transcribe with the right model |
| `/transcribe` | `ai4bharat/indic-conformer-600m-multilingual` (MIT) | Patient speech → text (Nepali, Hindi, Urdu, Bengali, Malayalam…) |
| `/speak` | `ai4bharat/indic-parler-tts` (Apache-2.0) | Text → patient-language speech |
| `/benchmark` | both | Nepali TTS → ASR round-trip timing |
| `/langs` | — | ASR language codes |

Hardware: `l4x1`, with sleep after 15 min idle. Gradio is pinned to 5.x because `parler-tts` requires `transformers==4.46.1`.
