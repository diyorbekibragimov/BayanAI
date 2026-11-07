# 09 — Pitch & Demo

> **Format rules we are building for** ([handbook](https://huggingface.co/spaces/qai-hackathon/handbook), [agenda](https://huggingface.co/spaces/qai-hackathon/agenda)): a 2–3 minute demo video with a public link, due by **Saturday 2:00 PM**. It is our backup if the live demo breaks. Finalists give a **3-minute pitch plus Q&A** (Saturday 4–6 PM).
> **Judged on:** Impact & relevance · Use of Hugging Face · Technical execution · Efficiency · Demo & pitch. Every section below is tagged with the criteria it serves.
> **Scenario source:** the Golden Path in [02 Product Spec §8](02-product-spec.md#8-the-golden-path-demo-scenario), which mirrors worked example 1 in [05 §3](05-clinical-safety-and-cultural-intelligence.md#3-worked-examples-end-to-end).
> **Related docs:** [01 Problem & Impact](01-problem-and-impact.md) (every statistic) · [04 Models & Languages](04-models-and-languages.md) (model names) · [05 Clinical Safety](05-clinical-safety-and-cultural-intelligence.md) (idiom and rules) · [06 Fine-Tuning](06-fine-tuning-plan.md) · [07 Compute Budget](07-compute-budget-and-efficiency.md) (money). A value not yet measured is written `⟨measure: …⟩` (today: total spend and end-to-end voice latency). Fill it in from the billing page or the latency log before going on stage, and never improvise a number. **Measured** on the live golden path (`scripts/smoke_e2e.py`, 9 text turns): copilot agent ≈ 1.2–1.6 s per run in 1 step, extraction ≈ 1.1 s, wrap-up ≈ 6–8 s, LLM cost ≈ $0.015 for the think loop + ≈ $0.004 for the wrap-up (excludes talk-loop translation and GPU-worker hours). **Estimated:** ≈ $0.06 for a 40-turn consultation.
> **Honesty rules:** no clinician has reviewed the lexicon, the rules or this scenario yet. Every Nepali line here is a machine draft that a native speaker must verify. "Tier 1" means demo target, not verified. **Status:** the demo video is not recorded yet; the clinical brain (rules, cards, agents, PDFs) is wired into the Space UI in the local code (269 offline tests, live smoke run 17/17) but not yet deployed.

---

## Contents

1. [3-minute finalist pitch (word for word)](#1-3-minute-finalist-pitch-word-for-word)
2. [Demo video script (2–3 min)](#2-demo-video-script-23-min)
3. [Backup demo plan](#3-backup-demo-plan)
4. [Judge Q&A prep (15 questions)](#4-judge-qa-prep-15-questions)
5. [Taglines and 30-second elevator version](#5-taglines-and-30-second-elevator-version)

---

## 1. 3-minute finalist pitch (word for word)

**Cast:** **Speaker** (pitch lead, stands centre, also plays the doctor). **Operator** (runs the tablet and laptop, mirrored to the projector). A **native Nepali speaker** reads the patient lines if one is available. Otherwise replay mode plays the pre-recorded patient audio.
**Default demo mode for the pitch: the Space's no-mic demo (L1, see §3).** It plays the golden path as text turns through the real translation, rules and Nepali voice (speech recognition is skipped), because a hall PA feeding back into the tablet mic is the most likely way to fail. Use the live mic (L0) only in a quiet room.
**Time budget:** about 375 words from the Speaker (recount after any edit), leaving out the optional cascade line (25 words). At about 150 words per minute that is ≈ 2:30, plus about 25 s of patient and Bayan audio during the demo, for ≈ 2:55 in total. Rehearse with a stopwatch. If you run long, skip the optional line, then drop the "one in four" clause from the idiom line.

---

**[0:00 – 0:27] HOOK** *(Impact)*

*Stage: lights on the Speaker. Slide 1 is black, with one line of Nepali text and its English subtitle: "छाती ग्यास्ट्रिकले जस्तो पोलेको छ। · My chest is burning, like gastric." Small caption: "Illustrative story · Nepali machine draft, native-speaker check pending."*

> "Imagine an August night at a Doha workers' clinic. A twenty-nine-year-old Nepali scaffolder says his chest burns like *'gyastrik'*, and that penicillin once made his body swell. His roommate interprets: 'stomach problem.' The allergy is lost. He goes home with amoxicillin, which *is* a penicillin."

*Pause, two beats.*

> "That story is illustrative. The error isn't. One study counted thirty-one interpreter errors per visit, and almost two-thirds could have clinical consequences."

*Slide footnote: [Flores et al., Pediatrics 2003](https://pubmed.ncbi.nlm.nih.gov/12509547/): 396 errors in 13 encounters, mean 31 per encounter, 63% with potential clinical consequences. Persona: [01 §3](01-problem-and-impact.md#3-who-suffers-personas), persona 1.*

**[0:27 – 0:53] PROBLEM IN QATAR** *(Impact & relevance)*

*Slide 2: a map with language labels over Qatar. Big number: **"≈ 9 in 10 residents are not Qatari"** (estimate; Qatar publishes no nationality breakdown: [Ahmad & Hillman 2021](https://doi.org/10.1515/multi-2020-0119), see [01 §1.1](01-problem-and-impact.md#11-a-population-that-speaks-neither-clinical-language)). Second line: **"65% of 312 HMC ambulance staff face language barriers"** ([Farhat et al., Qatar Med J 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12127531/)). Bottom strip: the cover of the MoPH Patients' Bill of Rights, with its eight language editions: Arabic, English, Bengali, Filipino, Hindi, Malayalam, Nepali, Urdu ([MoPH](https://dhp.moph.gov.qa/en/Pages/FTPDownloads.aspx)). Highlight the six patient languages.*

> "Roughly nine in ten people in Qatar aren't Qatari. Doctors work in English and Arabic. Among 312 HMC ambulance staff, sixty-five percent face language barriers at least occasionally. Qatar's Patients' Bill of Rights says an interpreter can be provided when needed, and the Ministry publishes it in Nepali, Hindi, Urdu, Bengali, Malayalam and Filipino. Exactly our six patient languages. Big hospitals have interpreters. A workers' clinic at night, or an ambulance, usually has a roommate. **Bayan AI** is for that room. *Bayan* is Arabic for *clarity*."

**[0:53 – 2:06] LIVE DEMO MOMENT** *(Technical execution · Demo)*

*Stage: the Operator puts the tablet on the lectern and mirrors it to the projector. The Speaker turns slightly toward the tablet as "the doctor". Consent has already been given. Say so, don't show it. Replay mode runs on the scenario clock ([02 §8](02-product-spec.md#8-the-golden-path-demo-scenario)), so all five rule hits appear (the 10-minute ECG timer needs the scenario clock; without it, expect four).*

> "One tablet. It listens, talks and thinks. He's consented, in Nepali."

*Speaker (as doctor): "What brings you in today?" Bayan speaks Nepali. The patient line P1 plays in Nepali. The `npi-005` idiom card slides in, and the amber chest-pain card opens.*

> "The doctor sees his words and a sourced note: *'gyastrik'* usually means stomach trouble, but it can hide heart pain. In Nepal, fewer than one in four heart-attack patients thought it was their heart."

*The patient line P2 (penicillin, swelling, sore throat) plays. The allergy chip lights up. Speaker (as doctor): "Probably just gastric. Amoxicillin, and you can go home."*

*The allergy card appears and the chest-pain card turns red. Let the room notice the silence for one beat.*

> "Silence. Only the doctor sees two alerts: his penicillin allergy, and chest pain going home without an ECG or troponin. Bayan held that sentence back."

*Speaker taps "Say something else" on the held sentence and Acknowledge on both cards. Speaker (as doctor): "No amoxicillin. First, blood pressure, an ECG and troponin." Then: "Bayan, end consultation." The Operator shows the review screen, then the Nepali PDF. A teammate scans the QR with a phone and opens the care-plan page. Play three seconds of the Nepali audio.*

> "The doctor gets a consultation note for the record; the patient, a Nepali care sheet with his medicines, danger signs and 999, on his own phone, with audio if he can't read."

**[2:06 – 2:24] HOW IT WORKS ON HUGGING FACE** *(Use of Hugging Face)*

*Slide 3: the cascade diagram. VAD → language ID / ASR → LLM → rules → TTS, with model names under each box: Silero VAD · `speechbrain/lang-id-voxlingua107-ecapa` (who is speaking) · `ai4bharat/indic-conformer-600m-multilingual` (Nepali) + `openai/whisper-large-v3-turbo` (doctor) · `openai/gpt-oss-120b` (Cerebras/Groq via Inference Providers) · 81 rules in `data/safety_rules.json` · smolagents copilot · `ai4bharat/indic-parler-tts` (Nepali). Corner: Space `dullgrey/team-qh-129-bayan-app` + private L4 GPU Space for speech.*

> "All open models on Hugging Face. IndicConformer and Whisper transcribe. GPT-OSS 120B, on Inference Providers, translates and extracts facts. Eighty-one cited rules fire the alerts. A smolagents copilot suggests what to ask next. Indic Parler-TTS speaks Nepali. It all runs on two Spaces."

*No fine-tuned model and no Hub dataset shipped. Do not mention either on stage.*

> *[Optional, cut first if running long]* "Why a cascade? No open speech-to-speech model we found speaks Nepali aloud, and keeping text in the middle is what makes the safety checks possible."

**[2:24 – 2:33] EFFICIENCY** *(Efficiency)*

*Slide 4: two big numbers: ⟨measure: total $ spent, from the billing page / spend log⟩ of $100, and **≈ $0.02** of LLM calls for the golden-path consultation (measured: $0.015 think loop + $0.004 wrap-up; small print: excludes talk-loop translation and GPU-worker hours; ≈ $0.06 estimated for a 40-turn visit; [07](07-compute-budget-and-efficiency.md)).*

> "We spent ⟨measure: total $ spent⟩ of our hundred dollars. The clinical brain and wrap-up for our test visit cost about two cents, measured, because the safety rules run on CPU and the agent only runs when something new is said."

**[2:33 – 2:47] IMPACT** *(Impact & relevance)*

*Slide 5: the Nepali PDF next to a phone playing audio. Footnote: 1,460,696 patient visits in 2025 at Qatar Red Crescent's workers' health centres ([Qatar Tribune 2026](https://www.qatar-tribune.com/article/247543/nation/qrcs-medical-affairs-division-getsaccreditation-canada-diamond-tag)).*

> "Most medical AI saves doctors time. Bayan protects patients. Qatar Red Crescent's workers' clinics logged nearly one and a half million visits in 2025. Bayan gives those workers care they understand, on their own phone."

**[2:47 – 2:56] ASK**

*Slide 6: tagline, Space URL (`huggingface.co/spaces/dullgrey/team-qh-129-bayan-app`) and QR code.*

> "Our ask: introductions to a workers' clinic and QCRI's Fanar team, for a supervised pilot. Bayan AI: every patient, understood. Thank you."

*Stop. Smile. Don't add anything. Q&A starts.*

---

**Pitch rules for the Speaker**

- The idiom line must match lexicon entry `npi-005` exactly. *Gyastrik* (ग्यास्ट्रिक) is listed with "dyspepsia, gastritis or reflux" as its high-likelihood meaning and cardiac ischaemia as a low-likelihood one that it can mask ([Kohrt & Harper 2008](https://pmc.ncbi.nlm.nih.gov/articles/PMC3869091/); [AHA/ACC 2021](https://doi.org/10.1161/CIR.0000000000001029)). So say "can hide heart pain", never "usually means heart pain". The "one in four" clause comes from [Prajapati et al., JNHRC 2022](https://jnhrc.com.np/index.php/jnhrc/article/view/1217): 87.9% of STEMI patients had typical chest pain, only 23.8% thought it was cardiac. Never say that missed diagnosis kills workers in Qatar: we have no source for that.
- Every number on stage comes from [01](01-problem-and-impact.md), [05](05-clinical-safety-and-cultural-intelligence.md) or the `smoke_e2e` output: 9 in 10 (estimate), 312 staff / 65%, 31 errors / 63%, 23.8% (Prajapati), the eight Bill of Rights languages, 1,460,696 QRCS visits in 2025, and ≈ $0.02 per golden-path consultation. If a judge asks for a source, point to doc 01.
- "Eighty-one cited rules" is true, but they are **not clinician-reviewed**. Say so if asked (Q&A #14).
- Say "illustrative" out loud for the hook. Judges in Doha will know the context, so honesty earns trust.
- Never say "diagnoses", "replaces interpreters" or "100% accurate". Say "supports the doctor", "fills the gaps", "flags for the doctor".
- If the demo stalls for more than 5 s, say "Let me switch to our recorded run" and go to L2 or L3 (§3). Don't debug on stage.
- Run it with a stopwatch at least three times on Saturday before 2 PM, and once more at 3:45 PM.

---

## 2. Demo video script (2–3 min)

**Status: not recorded yet.** **Target length 2:40.** Public link (YouTube unlisted or HF-hosted MP4, viewable by anyone), linked from the Space README and the submission sheet. Shot on a phone in landscape, 1080p. A quiet room dressed as a clinic (desk, tablet, a stethoscope as a prop). Two people: **Doctor** (team member) and **Patient** (a native Nepali speaker if at all possible). Screen-record the tablet at the same time and cut between the room and the screen.

**Honesty captions (required on screen):** "Illustrative scenario · synthetic patient · not medical advice · clinical content not yet clinician-reviewed". Plus "Patient voice: [native speaker | synthetic TTS]", whichever is true.

**Record in replay mode (L1) on the scenario clock** ([02 §8](02-product-spec.md#8-the-golden-path-demo-scenario)). The video then represents a consultation of about 12 minutes, plus a later results turn, so the "no ECG within 10 minutes" item (`WORK-CHEST-01`) appears as it would in real time. Show a small caption "scenario time hh:mm" in the corner, so the compression is visible and honest.

### 2.1 Shot list

| Time | Shot / visual | Narration (voice-over) | On-screen caption |
|---|---|---|---|
| 0:00–0:08 | **Cold open.** Close-up of the patient's face, speaking Nepali (P1). Subtitles in English. | — (patient audio only) | "My chest is burning, like *gyastrik* (gastric)…" |
| 0:08–0:25 | Wide shot: the doctor looks unsure. Cut to a title card with the stats. | "Roughly nine in ten people in Qatar aren't Qatari, and many speak neither English nor Arabic. Their Bill of Rights says an interpreter can be provided. Where none is in the room, errors follow: one study counted 31 interpreter errors per visit, almost two-thirds potentially consequential." | "≈ 9 in 10 not Qatari (estimate) · Ahmad & Hillman 2021" · "MoPH Patients' Bill of Rights: Nepali, Hindi, Urdu, Bengali, Malayalam, Filipino" · "Flores et al., Pediatrics 2003" |
| 0:25–0:35 | Tablet on the desk. The doctor taps **Start** and picks **Nepali**. The tablet speaks consent in Nepali. The patient says "हो" (yes). | "This is Bayan AI. One tablet. It listens, it talks, and it thinks. First, it asks the patient's consent, in their language." | "Consent in Nepali" |
| 0:35–0:50 | D1 → Bayan speaks Nepali. P1 plays. **Screen recording:** Nepali script, literal line, the `npi-005` *gyastrik* idiom card sliding in, and the amber chest-pain card opening (`WORK-CHEST-04`). | "The doctor sees what was literally said, and a sourced note: 'gyastrik' usually means stomach trouble, but it can hide heart pain." | "Literal translation + idiom card (never spoken) · source: lexicon npi-005" |
| 0:50–1:05 | D2 (Arabic variant if S1 is done) → P2. **Screen:** allergy chip "PENICILLIN (body swelling · severe)", state panel ticks. The scenario clock passes 10 minutes and "no ECG within 10 min" (`WORK-CHEST-01`) joins the amber card. | "In the background, Bayan keeps track of allergies, medicines, vitals and tests." | "Doctor can speak English or Arabic" |
| 1:05–1:25 | D3: the doctor prescribes amoxicillin and says "go home". **Screen:** the 🔴 allergy card (`ALG-PEN-01`) appears, the chest-pain card turns 🔴 (`WORK-CHEST-02`, `-03`), and the held-turn banner shows. **Room shot:** the patient waits and hears nothing. | "The doctor is about to prescribe a penicillin, and send chest pain home without an ECG or a troponin test. Bayan says nothing aloud. It alerts only the doctor, and holds that sentence back." | "Silent alerts · doctor only · 2 cards, 5 rule hits" |
| 1:25–1:40 | The doctor reads, taps **Acknowledge** on both cards, then says D4. Bayan speaks Nepali. The patient nods. Cut, then D5 (results). | "The doctor stays in control, and corrects the plan." | "Doctor decides · Bayan supports" · on D5: "Later: results" |
| 1:40–1:48 | D6 (plan and red flags) → Nepali. D7: "Bayan, end consultation." | — | "Voice command: end consultation" |
| 1:48–2:05 | **Screen:** review → consultation note (plain text to copy into the EMR). Then the Nepali PDF full-screen: Your medicines, Do not take, Call 999 or come back now if. The doctor taps **Approve & send**. | "The doctor gets an English consultation note for the record. Nothing reaches the patient until the doctor approves it." | "English consultation note · every line traceable to the transcript" |
| 2:05–2:18 | **Phone close-up:** the patient scans the on-screen QR and the care-plan page opens in Nepali. The prefilled WhatsApp message (PDF and audio links) is ready to send. The Nepali audio plays, with subtitles. | "The patient leaves with a care plan in Nepali on his own phone, with audio for anyone who can't read." | "PDF · WhatsApp/SMS link · audio" |
| 2:18–2:35 | **Animated diagram:** VAD → LID/ASR → LLM → rules → TTS, with HF logos and model names. Then two big numbers. | "Built on open models on Hugging Face: IndicConformer, Whisper, GPT-OSS 120B on Inference Providers with a smolagents copilot, and Indic Parler-TTS, served from two Spaces. Total spend: ⟨measure: total $ spent, billing page⟩. About two cents of LLM calls for this visit, measured." | "Silero VAD · voxlingua107 · indic-conformer-600m · whisper-large-v3-turbo · gpt-oss-120b (Cerebras/Groq) · smolagents · indic-parler-tts" · "Measured: ≈ $0.02 LLM cost, golden path (excl. translation, GPU hours)" |
| 2:35–2:42 | Closing card: Bayan logo, tagline, Space URL. | "Bayan AI. Every patient, understood." | `huggingface.co/spaces/dullgrey/team-qh-129-bayan-app` · `qai-hf-hackathon-2026` |

### 2.2 Exact lines

**Recording markers:**
**🎙 NATIVE** means a native speaker must record or perform the line, and verify the wording first.
**🤖 GEN** means Bayan generates the line live. A native speaker must back-check the output in rehearsal, and we re-record if it is wrong.
**✅ EN/AR** means the team speaks it.

> The Nepali text below is a **machine draft for the native speaker to correct**. It is not final copy. If no native Nepali speaker can be found by Saturday 09:00, synthesise the patient lines with the Nepali TTS, `ai4bharat/indic-parler-tts` (Nepali has one named voice, "Amrita"; it is the only patient voice in the runtime), and caption the video "synthetic patient voice". Do not present it as a real person.

| # | Speaker | Lang | Line as spoken | English meaning | Marker |
|---|---|---|---|---|---|
| C1 | Bayan | NE | *(consent script, [02 §3.3](02-product-spec.md#33-consent-script-fixed-text-pre-verified-per-language))* | "Hello. I am Bayan, a computer interpreter… Do you agree? Please say yes or no." | 🎙 NATIVE verifies text, then cached TTS |
| C2 | Patient | NE | हो, म सहमत छु। | "Yes, I agree." | 🎙 NATIVE |
| D1 | Doctor | EN | "Hello, I'm Dr Sara. What brings you in today?" | — | ✅ EN |
| B1 | Bayan | NE | *(translation of D1)* | — | 🤖 GEN |
| P1 | Patient | NE | मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ। खाना खाएपछि सुरु भयो, अनि रिँगटा लागेको छ। | "My chest is burning, like *gyastrik* (gastric). It started after lunch, and I feel dizzy." Must trigger lexicon entry `npi-005` (ग्यास्ट्रिक, *gyastrik*). | 🎙 NATIVE |
| D2 | Doctor | AR *(S1)* / EN fallback | هل تعمل في الخارج؟ وهل عندك حساسية من أي دواء؟ / "Do you work outdoors? Are you allergic to any medicine?" | — | ✅ AR (Arabic-speaking teammate) or EN |
| P2 | Patient | NE | हो, म बाहिर साइटमा काम गर्छु। एक पटक पेनिसिलिनको सुई लगाउँदा मेरो जिउ सुन्निएको थियो। अनि तीन दिनदेखि घाँटी दुखेको छ। | "Yes, I work outside on a site. Once, after a penicillin injection, my body swelled up. And my throat has hurt for three days." | 🎙 NATIVE |
| D3 | Doctor | EN | "It's probably just gastric, and a throat infection. I'll give you amoxicillin five hundred milligrams three times a day for your throat, and you can go home." | — | ✅ EN → **held by Bayan, never spoken in Nepali**. Do **not** say "the heat": a heat-illness assessment would add `WORK-HEAT-03` ([02 §8](02-product-spec.md#8-the-golden-path-demo-scenario), note 3). |
| — | *(screen)* | — | 🔴 ALLERGY CONFLICT (`ALG-PEN-01`: "Penicillin allergy reported ('…my body swelled'). Amoxicillin is a penicillin.") · 🔴 CHEST-PAIN WORKUP (`WORK-CHEST-02` no ECG, `-03` no troponin, `-01` no ECG within 10 min, `-04` *gyastrik* can mask cardiac pain) | — | silent |
| D4 | Doctor | EN | "Actually, no amoxicillin. Your throat looks viral. Before you go, we'll check your blood pressure, do a heart tracing, and a blood test for the heart called troponin." | — | ✅ EN (orders ECG + troponin, which clears `WORK-CHEST-01…04`) |
| D5 | Doctor | EN | *(later)* "Your blood pressure is one twenty-eight over eighty-two, your heart tracing is normal, and the troponin test is normal." | — | ✅ EN (fills BP, ECG and troponin in the state panel, as stated by the clinician) |
| D6 | Doctor | EN | "Take paracetamol, one gram, up to three times a day, for your throat. Drink plenty of water and rest out of the sun for two days. If the chest pain comes back, spreads to your arm or jaw, you feel faint or sweaty, or you vomit blood or pass black stools, call 999 or come straight back." | — | ✅ EN. **Dose checked against the rules:** 1 g × 3 = 3 g/day passes `DOSE-PARA-01` (max 1 g/dose, 4 g/day), `DOSE-PARA-03` (no weight recorded) and `DOSE-PARA-04` (caution above 3 g/day with heat illness or a hepatic risk factor). "Four times a day" is avoided on purpose. Red flags come from `npi-005`'s clarifying questions (radiation to the arm or jaw, sweating, black stools or vomiting blood). **Not clinician-reviewed.** |
| P3 | Patient | NE | हुन्छ, धन्यवाद डाक्टर। | "Okay, thank you, doctor." | 🎙 NATIVE |
| D7 | Doctor | EN | "Bayan, end consultation." | — | ✅ EN (command, not translated) |

**Expected outputs to show in the video (checked before filming):**
- **Consultation note (PDF + plain text):** Allergies (penicillin, body swelling, per patient), Presenting complaint, History, Observations and investigations (BP 128/82, ECG and troponin as stated by the clinician), Assessment in the clinician's own words only, Plan, Medication changes (amoxicillin withdrawn), Information given to patient, Safety alerts in plain sentences (5 rule hits: `ALG-PEN-01`, `WORK-CHEST-01…04`, acknowledged), sign-off, transcript appendix.
- **Nepali PDF (English beneath each line):** Your medicines (paracetamol 1 g, only if needed, up to 3 times a day; no daily schedule table because it is as-needed), Do not take (penicillin), Other instructions (water, rest out of the sun), Call 999 or come back now if (chest pain returns or spreads to the arm or jaw, fainting, sweating, vomiting blood or black stools). No QR on the PDF.
- **No other alert** appears after D4–D6 (checked by `scripts/smoke_e2e.py`: "all rule cards resolved after the corrected plan").
- **WhatsApp:** a prefilled `wa.me` click-to-chat link with the Nepali title, the PDF link and the audio link; a person taps Send (no business API).
- **SMS:** a prefilled `sms:` link, ≤ 2 UCS-2 segments with the link.
- **Audio:** a WAV of the plan read aloud in Nepali (Indic Parler-TTS); built, off by default in the Space (`BAYAN_PLAN_AUDIO=1`).

---

## 3. Backup demo plan

Three things are most likely to fail on the day: the venue Wi-Fi, provider cold starts, and the hall PA feeding back into the tablet mic. Each fallback level is one tap away, and **the operator switches without apologising**.

| Level | What runs | When to use | What the Speaker says |
|---|---|---|---|
| **L0: Fully live** | Live mic, live speakers, real pipeline | Booth demos, Q&A, quiet rooms | — |
| **L1: No-mic demo (default for the pitch)** | **Built:** the start screen's demo button plays the golden path as text turns through the real translation, held-sentence check and Nepali voice (worker TTS when the worker is up; text only otherwise). Speech recognition is skipped. *Designed, not built:* WAV replay through ASR. | Pitch stage, noisy rooms, no native speaker present | "This is the real system running on our scripted consultation." |
| **L2: Cached run** *(not built)* | Pre-computed pipeline outputs from a successful Saturday-morning run, replayed with the original timings. No network needed. Today's stand-in: the PDFs and page images saved by `scripts/smoke_e2e.py`. | Provider outage, or Wi-Fi down | "The network's down, so here's the recorded run from this morning, same system." |
| **L3: Demo video** | The 2–3 min video, cued at 0:35 | Laptop or tablet dies | "Let me show you the video." |

**Build requirements (Must M12 in [02](02-product-spec.md#7-mvp-scope-for-saturday-2-pm-moscow); designed, superseded for now by the built no-mic demo):**
- Replay mode takes a folder of `turn_NN_<speaker>_<lang>.wav` files plus a manifest (order, expected route, and a `t_scenario` timestamp per turn that drives the rule engine's clock, so the 10-minute ECG timer behaves as in a real consultation) and feeds them through the normal audio entry point. It must not shortcut ASR.
- The cached run is a JSONL of pipeline events (transcript, translation, alerts, timings) plus the final PDFs, audio and note.
- The operator's control is off-screen (a laptop keyboard shortcut, or a hidden button on the tablet edge).

**Pre-flight checklist (T-30 min before pitch, and before filming)**

- [ ] Wake the GPU voice worker Space (boot ≈ 99 s) and send one request each to `/hear` and `/speak_stream`. Check the main Space is awake and the access code works.
- [ ] Phone hotspot ready as a Wi-Fi fallback. Tablet and laptop charged above 80%.
- [ ] Tablet audio goes **direct to the venue PA by cable** if possible. Tablet mic not facing the speakers.
- [ ] Demo phone has WhatsApp logged in and can scan the on-screen QR.
- [ ] A Golden Path dry run in replay mode passes: exactly two cards appear (`ALG-PEN-01`; chest-pain workup with `WORK-CHEST-01…04`), nothing else fires after the corrected plan, the PDFs render, and the QR opens the care-plan page.
- [ ] The billing page has been read and the `⟨measure⟩` total-spend value in §1 is filled in. Re-run `python scripts/smoke_e2e.py` (≈ $0.02) and check it says ALL PASS.
- [ ] Cached run (L2) loaded locally. Video (L3) downloaded locally, not streamed.
- [ ] Session cleared, so no leftover transcript is on screen.

---

## 4. Judge Q&A prep (15 questions)

Answer in ≤ 20 seconds, then stop. Lead with the honest limit and follow with the mitigation.

| # | Question | Answer |
|---|---|---|
| 1 | **How accurate is it? What about hallucinations?** | "We don't claim an accuracy number. We haven't run per-language speech or translation benchmarks yet, and no native speaker has reviewed the output. Four built choices limit hallucination. Only deterministic rules can raise a critical alert, never the model. Idiom notes come straight from a cited lexicon. The note's assessment holds only the doctor's own words: code drops any diagnosis nobody said. And every medicine on the patient's sheet is re-checked against the rules, with numbers the doctor didn't say rejected." |
| 2 | **If the translation is wrong and a patient is harmed, who is liable?** | "The doctor stays the decision-maker. Bayan supports decisions and doesn't make them, and nothing reaches the patient without the doctor approving it. Every session leaves an audit trail of what was said, what Bayan showed, and what the doctor did. A real deployment would go through the hospital's clinical governance and medico-legal review before any pilot. We don't claim to have settled liability this weekend." |
| 3 | **Where does patient audio go? Privacy?** | "Our Space keeps no audio: each utterance goes to our private GPU worker and the temporary file is deleted. The worker deletes each upload right after loading it. Sessions live in memory, output files sit in a per-consultation temp folder deleted on reset or after 24 hours, and the patient's plan link expires after 24 hours. Qatar's data protection law, Law 13 of 2016, treats health data as a special category, so consent is spoken in the patient's own language before anything else happens. This weekend we use synthetic data only. In production, the open models run on in-country infrastructure." |
| 4 | **Why not just use Google Translate?** | "A translator app isn't an interpreter in the room. Someone has to hold the phone and press buttons. It doesn't know that a Nepali worker's 'gyastrik' in the chest can hide heart pain, it doesn't notice the penicillin allergy, and it doesn't write the consultation note or the care plan. It's also a consumer service: a hospital can't host it, audit it, or keep the data in Qatar. Bayan's value is the safety layer and the outputs, not only the translation." |
| 5 | **Why not a human interpreter?** | "Professional interpreters are the gold standard, and the research shows they make fewer consequential errors than ad hoc interpreters. In Flores 2003, 77% of ad hoc interpreters' errors had potential clinical consequences, against 53% for hospital interpreters. HMC and Sidra offer them, Sidra around the clock in 66 languages. Bayan is for the rooms they don't reach: workers' clinics at night, ambulances, walk-ins. If the patient declines, Bayan switches off and the doctor calls the interpreter service." |
| 6 | **What does it cost?** | "Measured on our test consultation: about one and a half cents for extraction and the copilot agent, plus under half a cent for the wrap-up. We estimate about six cents for a 40-turn visit. Translation calls and the GPU voice worker, $0.80 an hour while awake, come on top. We built and demoed everything for ⟨measure: total $ spent, billing page⟩ of the $100 budget. At hospital scale, a dedicated GPU with many concurrent consultations changes the cost curve, but we haven't benchmarked that yet. See doc 07." |
| 7 | **What about languages with no good text-to-speech, or weak speech recognition?** | "We're honest about tiers. Tier 1 is Nepali, Hindi, Urdu, Bengali, Malayalam and Tagalog, the same six patient languages as the MoPH Bill of Rights. Nepali is the one we've tested most. Hindi, Urdu, Bengali and Malayalam run through the same models with voice in and out, but with less testing. Filipino has speech recognition and text, no voice yet. Other languages are on the roadmap. Where there's no adequate TTS, the wrap-up warns 'audio not available, explain verbally', and the PDF still goes out. Sinhala and Pashto only have a non-commercial voice today, and Tagalog's voice is non-commercial too. We chose not to fine-tune TTS this weekend: it needs many GPU-hours and native listening tests. Indic Parler-TTS already speaks Nepali." |
| 8 | **Dialects? Sylheti vs standard Bengali, or Nepali spoken in the hills vs the Terai?** | "This is a real limit. ASR is weaker on dialects and code-switching. Today the doctor sees the patient's own transcript next to the English, a sentence can be repeated more slowly with one tap, and a prescribing sentence that conflicts with an allergy is held. Confidence scores and 'did you mean…?' confirm-back are designed, not built. We deliberately didn't fine-tune ASR this weekend, because without a native-transcribed clinical test set we couldn't measure the gain. Dialect coverage is the main fine-tuning target after the hackathon, ideally with recordings collected with consent from Qatar's communities." |
| 9 | **Is this a regulated medical device?** | "The interpretation and note parts are communication and documentation tools. The safety sentinel is clinical decision support, and we'd expect regulators to look at it. We haven't verified the exact Ministry of Public Health pathway, and we'd do that with a clinical partner before any pilot. It's designed for this: deterministic, auditable rules with cited sources, and the doctor always decides." |
| 10 | **Who pays? What's the business model?** | "The buyers are providers and payers who carry the cost of miscommunication: HMC and PHCC for public clinics, private hospitals and clinics that serve worker populations, and employers and insurers who pay for workers' care. The model is per-clinic or per-tablet licensing, with a hosted or on-premise option. We have not validated pricing. That's what a pilot is for." |
| 11 | **Can it run sovereign, inside Qatar, with no data leaving?** | "Yes, by design. Every model is open-weight from the Hugging Face Hub, so the whole cascade can run on a dedicated Inference Endpoint in a suitable region, or on a hospital's own GPUs. Our four speech models already run together on one 24 GB L4 GPU in our own Space. Fanar, Qatar's own model from QCRI, is an option for Arabic we haven't integrated. We haven't yet sized self-hosting the 120B model, or how many consultations one GPU can serve at once." |
| 12 | **How exactly did you use Hugging Face?** | "The app is a Gradio Space with FastRTC. `gpt-oss-120b` runs through Inference Providers: Cerebras for translation and our two smolagents agents, Groq for background fact extraction. Kokoro gives an optional English voice for the doctor. The speech models no provider serves, Whisper large-v3-turbo, VoxLingua107 language ID, IndicConformer and Indic Parler-TTS, run on a private L4 GPU Space we call with `gradio_client`. We did not ship a fine-tune or publish a dataset. No closed frontier model is in the loop." |
| 13 | **Efficiency: how did you spend your $100?** | "⟨measure: final spend-log line, actual $ by item⟩. The big items are the L4 voice worker while awake and LLM calls, which we measured at about two cents for the golden-path consultation. Five choices save money. Alerts are rules on CPU, not LLM calls. Extraction runs on Groq, same model, cheaper input. A doctor's plain question is extracted together with the patient's answer, in one call. Courtesy turns are skipped. And the agent only runs when something new appeared." |
| 14 | **No one on your team is a clinician. How do you trust the clinical content?** | "We didn't invent any medicine, and we haven't had a clinician review it yet. All 98 idiom entries and all 81 rules cite sources: FDA labels, NICE, AHA/ACC and ESC guidelines, and peer-reviewed papers. Forty-three idioms are honestly marked 'community-reported'. The rules are deterministic and simple: a penicillin allergy against a penicillin, or chest pain discharged without an ECG or troponin. Everything is framed as a flag for the doctor, never a diagnosis. Clinical and pharmacist review of the rule set is step one of any pilot." |
| 15 | **What's next?** | "Three things. A supervised pilot in one clinic that serves workers, alongside professional interpreters, measuring errors caught and patient understanding. Dialect fine-tuning with community recordings. And Arabic grounding, possibly with Fanar, plus sovereign hosting. We'd love introductions to HMC, PHCC and QCRI." |

**Backup answers (if asked):**
- *Alert fatigue?* "Only the rules can raise a red alert, and every alert quotes its evidence. Related rules are grouped: the Golden Path's five rule hits show up as two cards. Only a critical prescribing alert adds friction, by holding the sentence. Overriding an alert takes one tap with a reason, and that is logged. Override rates for drug alerts are documented between 49% and 96%, which is why we keep the number of alerts low." ([van der Sijs et al. 2006](https://pubmed.ncbi.nlm.nih.gov/16357358/), via [05 §2.7](05-clinical-safety-and-cultural-intelligence.md#27-alert-ux-silent-evidenced-accountable))
- *What if a family member speaks?* "Bayan interprets them too, so the patient hears everything said about them. Labelling a line as 'companion' is designed, not built."
- *What if the patient speaks Arabic?* "Then language stops being a speaker signal. Today Arabic is routed as the doctor's side, so this case isn't supported yet. A manual speaker toggle is designed; automatic diarization is a stretch goal."

---

## 5. Taglines and 30-second elevator version

### Taglines (pick one for the closing slide; the recommended one is first)

1. **"Every patient, understood."**
2. **"It listens. It talks. It thinks, so no one is lost in translation."**
3. **"Clarity at the bedside, in every language spoken in Qatar."**
4. **"The interpreter that also watches the patient's back."**
5. **"Your language. Your care plan. Your phone."**

### 30-second elevator version (≈ 80 words)

> "In Qatar, many patients speak neither English nor Arabic, and their doctors don't speak Nepali, Bengali or Tagalog. Interpretation errors are common, and some are dangerous, like a penicillin allergy that never gets translated. Bayan AI is one tablet that listens to the consultation, interprets out loud in both directions, and quietly alerts the doctor to risks like allergy conflicts. At the end, the patient gets a care plan in their own language, as a PDF, a link to send by WhatsApp or SMS, and audio. It's built on open models on Hugging Face."
