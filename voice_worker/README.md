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
  - openai/whisper-large-v3-turbo
  - speechbrain/lang-id-voxlingua107-ecapa
  - ai4bharat/indic-conformer-600m-multilingual
  - ai4bharat/indic-parler-tts
---

# Bayan AI · GPU voice worker

A private backend for [`dullgrey/team-qh-129-bayan-app`](https://huggingface.co/spaces/dullgrey/team-qh-129-bayan-app), called with `gradio_client` and an `HF_TOKEN`. It hosts the speech models that no Inference Provider serves. It is a GPU Space, not an Inference Endpoint.

| Model | Job |
|---|---|
| `speechbrain/lang-id-voxlingua107-ecapa` (Apache-2.0) | Who is speaking: language ID scored over {en, ar, patient language} only |
| `openai/whisper-large-v3-turbo` (MIT) | Doctor speech (English, Arabic); patient languages IndicConformer lacks (e.g. Filipino) |
| `ai4bharat/indic-conformer-600m-multilingual` (MIT, gated) | Patient speech in Indic languages (Nepali, Hindi, Urdu, Bengali, Malayalam…) |
| `ai4bharat/indic-parler-tts` (Apache-2.0, gated) | Patient-language speech (ne, hi, ur, bn, ml, ta, te) |

| Endpoint | Returns |
|---|---|
| `/hear(audio, patient_lang)` | `{role, lang, text, engine, lid, lid_whisper, timings}`: doctor or patient, then ASR with the right model |
| `/transcribe(audio, lang, decoding)` | IndicConformer text (`ctc` or `rnnt`) |
| `/speak(text, lang, description)` | One WAV + stats |
| `/speak_stream(text, lang, description)` | Generator of `{sr, pcm}` chunks (base64 int16), then `{done: true, …stats}` |
| `/speak_stream_opts`, `/tts_probe` | Latency experiments (debug) |
| `/benchmark` | Nepali and English TTS → `/hear` round trip |
| `/langs` | ASR language codes |

`/speak_stream` cuts the text into short segments and generates them in one batched Parler call (a decoding step for several segments costs about the same as for one), so the first audio waits only for the first short segment. If batched streaming fails it falls back to the one-sentence path. Measured from Doha (commit `474e406`): first audio ~2.2 s for a 3-sentence answer and ~3.1 s for a short question; boot ~99 s (was ~137 s). Boot logs print a timestamp per download and load step, and a TTS warm-up runs before serving.

Hardware: `l4x1` ($0.80/h), one GPU job at a time (`default_concurrency_limit=1`). Gradio is pinned to 5.x because `parler-tts` requires `transformers==4.46.1`.

**Privacy:** `/hear` and `/transcribe` delete the uploaded audio right after loading it, and `gr.Blocks(delete_cache=(600, 600))` removes other cached files (e.g. synthesised speech) once they are 10 minutes old.
