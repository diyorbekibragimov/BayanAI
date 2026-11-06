# 09 — Pitch & Demo

> **Format rules we are building for** ([handbook](https://huggingface.co/spaces/qai-hackathon/handbook), [agenda](https://huggingface.co/spaces/qai-hackathon/agenda)): a 2–3 minute demo video with a public link, due by **Saturday 2:00 PM**. It is our backup if the live demo breaks. Finalists give a **3-minute pitch plus Q&A** (Saturday 4–6 PM).
> **Judged on:** Impact & relevance · Use of Hugging Face · Technical execution · Efficiency · Demo & pitch. Every section below is tagged with the criteria it serves.
> **Scenario source:** the Golden Path in [02 Product Spec §8](02-product-spec.md#8-the-golden-path-demo-scenario), which mirrors worked example 1 in [05 §3](05-clinical-safety-and-cultural-intelligence.md#3-worked-examples-end-to-end).
> **Related docs:** [01 Problem & Impact](01-problem-and-impact.md) (every statistic) · [04 Models & Languages](04-models-and-languages.md) (model names) · [05 Clinical Safety](05-clinical-safety-and-cultural-intelligence.md) (idiom and rules) · [06 Fine-Tuning](06-fine-tuning-plan.md) · [07 Compute Budget](07-compute-budget-and-efficiency.md) (money). A value that can only be measured is written `⟨measure: …⟩`. Fill it in from the cost meter, the billing page or the latency log before going on stage, and never improvise a number. Doc-07 cost figures are **estimates** and must be called that until they are measured.
> **Honesty rules:** no clinician has reviewed the lexicon, the rules or this scenario yet. Every Nepali line here is a machine draft that a native speaker must verify. "Tier 1" means demo target, not verified.

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
**Default demo mode for the pitch: replay mode (L1, see §3).** The real pipeline runs live on pre-recorded patient audio, because a hall PA feeding back into the tablet mic is the most likely way to fail. The doctor lines are spoken live if the room is quiet enough. Otherwise they are replayed too.
**Time budget:** 376 words from the Speaker, counting the doctor lines and the two `⟨measure⟩` values (as about three words each) and leaving out the optional cascade line (25 words). At about 150 words per minute that is ≈ 2:30, plus about 25 s of patient and Bayan audio during the demo, for ≈ 2:55 in total. Rehearse with a stopwatch. If you run long, skip the optional line (not in the count), then drop the Pradhan clause from the idiom line.

---

**[0:00 – 0:27] HOOK** *(Impact)*

*Stage: lights on the Speaker. Slide 1 is black, with one line of Nepali text and its English subtitle: "छाती ग्यास्ट्रिकले जस्तो पोलेको छ। · My chest is burning, like gastric." Small caption: "Illustrative story · Nepali machine draft, native-speaker check pending."*

> "Imagine an August night at a Doha workers' clinic. A twenty-nine-year-old Nepali scaffolder says his chest burns like *'gyastrik'*, and that penicillin once made his body swell. His roommate interprets: 'stomach problem.' The allergy is lost. He goes home with amoxicillin, which *is* a penicillin."

*Pause, two beats.*

> "That story is illustrative. The error isn't. One study counted thirty-one interpreter errors per visit, and almost two-thirds could have clinical consequences."

*Slide footnote: [Flores et al., Pediatrics 2003](https://pubmed.ncbi.nlm.nih.gov/12509547/): 396 errors in 13 encounters, mean 31 per encounter, 63% with potential clinical consequences. Persona: [01 §3](01-problem-and-impact.md#3-who-suffers-personas), persona 1.*

**[0:27 – 0:53] PROBLEM IN QATAR** *(Impact & relevance)*

*Slide 2: a map with language labels over Qatar. Big number: **"≈ 9 in 10 residents are not Qatari"** (estimate; Qatar publishes no nationality breakdown: [Ahmad & Hillman 2021](https://doi.org/10.1515/multi-2020-0119), see [01 §1.1](01-problem-and-impact.md#11-a-population-that-speaks-neither-clinical-language)). Second line: **"65% of 312 HMC ambulance staff face language barriers"** ([Farhat et al., Qatar Med J 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12127531/)). Bottom strip: the cover of the MoPH Patients' Bill of Rights, with its eight language editions: Arabic, English, Bengali, Filipino, Hindi, Malayalam, Nepali, Urdu ([MoPH](https://dhp.moph.gov.qa/en/Pages/FTPDownloads.aspx)). Highlight the six patient languages.*

> "Roughly nine in ten people in Qatar aren't Qatari. Doctors work in English and Arabic. Among 312 HMC ambulance staff, sixty-five percent face language barriers at least occasionally. Qatar's Patients' Bill of Rights promises an interpreter, and the Ministry publishes it in Nepali, Hindi, Urdu, Bengali, Malayalam and Filipino. Exactly our six patient languages. **Bayan AI** delivers that right. *Bayan* is Arabic for *clarity*."

**[0:53 – 2:06] LIVE DEMO MOMENT** *(Technical execution · Demo)*

*Stage: the Operator puts the tablet on the lectern and mirrors it to the projector. The Speaker turns slightly toward the tablet as "the doctor". Consent has already been given. Say so, don't show it. Replay mode runs on the scenario clock ([02 §8](02-product-spec.md#8-the-golden-path-demo-scenario)), so all five rule hits appear.*

> "One tablet. It listens, talks and thinks. He's consented, in Nepali."

*Speaker (as doctor): "What brings you in today?" Bayan speaks Nepali. The patient line P1 plays in Nepali. The `npi-005` idiom card slides in, and the amber chest-pain card opens.*

> "The doctor sees his words and a sourced note: *'gyastrik'* usually means stomach trouble, but it can hide heart pain, and heart disease dominates recorded deaths of Nepali workers here."

*The patient line P2 (penicillin, swelling, sore throat) plays. The allergy chip lights up. Speaker (as doctor): "Probably just gastric. Amoxicillin, and you can go home."*

*The allergy card appears and the chest-pain card turns red. Let the room notice the silence for one beat.*

> "Silence. Only the doctor sees two alerts: his penicillin allergy, and chest pain going home without an ECG or troponin. Bayan held that sentence back."

*Speaker taps Acknowledge on both cards. Speaker (as doctor): "No amoxicillin. First, blood pressure, an ECG and troponin." Then: "Bayan, end consultation." The Operator shows the review screen, then the Nepali PDF. A teammate holds up a phone with the WhatsApp message. Play three seconds of the Nepali audio.*

> "The doctor gets a SOAP note; the patient, a Nepali care plan with medicine times, danger signs and 999, on WhatsApp, with audio if he can't read."

**[2:06 – 2:24] HOW IT WORKS ON HUGGING FACE** *(Use of Hugging Face)*

*Slide 3: the cascade diagram. VAD → language ID / ASR → LLM → rules → TTS, with model names under each box: Silero VAD · `ai4bharat/indic-conformer-600m-multilingual` (Nepali) + `openai/whisper-large-v3-turbo` (doctor) · `openai/gpt-oss-120b` (Cerebras/Groq via Inference Providers) · 81 rules in `data/safety_rules.json` · `ai4bharat/indic-parler-tts` (Nepali) + Kokoro-82M (English). Corner: `dullgrey/team-qh-129-bayan` (Qwen3-4B LoRA, HF Jobs) · dataset `dullgrey/team-qh-129-bayan-idioms` · Space `dullgrey/team-qh-129-bayan-app`.*

> "All open Hugging Face models. IndicConformer and Whisper transcribe. GPT-OSS 120B, on Inference Providers, translates and extracts facts. Eighty-one cited rules fire the alerts. Indic Parler-TTS speaks Nepali. A Qwen model we fine-tuned on HF Jobs tracks the clinical state. It all runs in a Space."

*If the fine-tune missed its ship bars (gate G3 in [06 §10](06-fine-tuning-plan.md#10-timeline-with-gono-go-gates)), replace the fine-tune sentence with: "We published our idiom dataset on the Hub, with a fine-tune trained on HF Jobs as an experiment." Same length.*

> *[Optional, cut first if running long]* "Why a cascade? No open speech-to-speech model we found speaks Nepali aloud, and keeping text in the middle is what makes the safety checks possible."

**[2:24 – 2:33] EFFICIENCY** *(Efficiency)*

*Slide 4: two big numbers, both measured: ⟨measure: total $ spent, from the billing page / spend log⟩ of $100, and ⟨measure: $ per consultation, from the UI cost meter⟩. Small print: doc-07 **estimate** ≈ $0.015 marginal API cost per consultation vs ≈ $0.047 for a naive build, from list prices ([07 §3](07-compute-budget-and-efficiency.md#3-cost-per-consultation)).*

> "We spent ⟨measure: total $ spent⟩ of our hundred dollars. A consultation costs about ⟨measure: $ per consultation, UI cost meter⟩, three times less than a naive build."

*Say "three times" only if the cost meter confirms it. Otherwise say "by our estimate, about one and a half cents, three times less than a naive build."*

**[2:33 – 2:47] IMPACT** *(Impact & relevance)*

*Slide 5: the Nepali PDF next to a phone playing audio. Footnote: 1,460,696 patient visits in 2025 at Qatar Red Crescent's workers' health centres ([Qatar Tribune 2026](https://www.qatar-tribune.com/article/247543/nation/qrcs-medical-affairs-division-getsaccreditation-canada-diamond-tag)); cardiovascular causes dominated recorded deaths of Nepali workers in Qatar, 2009–2017 ([Pradhan et al., Cardiology 2019](https://doi.org/10.1159/000500853)).*

> "Most medical AI saves doctors time. Bayan protects patients. Qatar Red Crescent's workers' clinics logged nearly one and a half million visits in 2025. Bayan gives those workers care they understand, on their own phone."

**[2:47 – 2:56] ASK**

*Slide 6: tagline, Space URL (`huggingface.co/spaces/dullgrey/team-qh-129-bayan-app`) and QR code.*

> "Our ask: introductions to a workers' clinic and QCRI's Fanar team, for a supervised pilot. Bayan AI: every patient, understood. Thank you."

*Stop. Smile. Don't add anything. Q&A starts.*

---

**Pitch rules for the Speaker**

- The idiom line must match lexicon entry `npi-005` exactly. *Gyastrik* (ग्यास्ट्रिक) is listed with "dyspepsia, gastritis or reflux" as its high-likelihood meaning and cardiac ischaemia as a low-likelihood one that it can mask ([Kohrt & Harper 2008](https://pmc.ncbi.nlm.nih.gov/articles/PMC3869091/); [AHA/ACC 2021](https://doi.org/10.1161/CIR.0000000000001029)). So say "can hide heart pain", never "usually means heart pain". The deaths clause comes from [Pradhan et al. 2019](https://pubmed.ncbi.nlm.nih.gov/31302648/).
- Every number on stage comes from [01](01-problem-and-impact.md) or the cost meter: 9 in 10 (estimate), 312 staff / 65%, 31 errors / 63%, the eight Bill of Rights languages, and 1,460,696 QRCS visits in 2025. If a judge asks for a source, point to doc 01.
- "Eighty-one cited rules" is true, but they are **not clinician-reviewed**. Say so if asked (Q&A #14).
- Say "illustrative" out loud for the hook. Judges in Doha will know the context, so honesty earns trust.
- Never say "diagnoses", "replaces interpreters" or "100% accurate". Say "supports the doctor", "fills the gaps", "flags for the doctor".
- If the demo stalls for more than 5 s, say "Let me switch to our recorded run" and go to L2 or L3 (§3). Don't debug on stage.
- Run it with a stopwatch at least three times on Saturday before 2 PM, and once more at 3:45 PM.

---

## 2. Demo video script (2–3 min)

**Target length 2:40.** Public link (YouTube unlisted or HF-hosted MP4, viewable by anyone), linked from the Space README and the submission sheet. Shot on a phone in landscape, 1080p. A quiet room dressed as a clinic (desk, tablet, a stethoscope as a prop). Two people: **Doctor** (team member) and **Patient** (a native Nepali speaker if at all possible). Screen-record the tablet at the same time and cut between the room and the screen.

**Honesty captions (required on screen):** "Illustrative scenario · synthetic patient · not medical advice · clinical content not yet clinician-reviewed". Plus "Patient voice: [native speaker | synthetic TTS]", whichever is true.

**Record in replay mode (L1) on the scenario clock** ([02 §8](02-product-spec.md#8-the-golden-path-demo-scenario)). The video then represents a consultation of about 12 minutes, plus a later results turn, so the "no ECG within 10 minutes" item (`WORK-CHEST-01`) appears as it would in real time. Show a small caption "scenario time hh:mm" in the corner, so the compression is visible and honest.

### 2.1 Shot list

| Time | Shot / visual | Narration (voice-over) | On-screen caption |
|---|---|---|---|
| 0:00–0:08 | **Cold open.** Close-up of the patient's face, speaking Nepali (P1). Subtitles in English. | — (patient audio only) | "My chest is burning, like *gyastrik* (gastric)…" |
| 0:08–0:25 | Wide shot: the doctor looks unsure. Cut to a title card with the stats. | "Roughly nine in ten people in Qatar aren't Qatari, and many speak neither English nor Arabic. Their Bill of Rights promises an interpreter. Without one, errors follow: one study counted 31 interpreter errors per visit, almost two-thirds potentially consequential." | "≈ 9 in 10 not Qatari (estimate) · Ahmad & Hillman 2021" · "MoPH Patients' Bill of Rights: Nepali, Hindi, Urdu, Bengali, Malayalam, Filipino" · "Flores et al., Pediatrics 2003" |
| 0:25–0:35 | Tablet on the desk. The doctor taps **Start** and picks **Nepali**. The tablet speaks consent in Nepali. The patient says "हो" (yes). | "This is Bayan AI. One tablet. It listens, it talks, and it thinks. First, it asks the patient's consent, in their language." | "Consent in Nepali · no audio stored" |
| 0:35–0:50 | D1 → Bayan speaks Nepali. P1 plays. **Screen recording:** Nepali script, literal line, the `npi-005` *gyastrik* idiom card sliding in, and the amber chest-pain card opening (`WORK-CHEST-04`). | "The doctor sees what was literally said, and a sourced note: 'gyastrik' usually means stomach trouble, but it can hide heart pain." | "Literal translation + idiom card (never spoken) · source: lexicon npi-005" |
| 0:50–1:05 | D2 (Arabic variant if S1 is done) → P2. **Screen:** allergy chip "PENICILLIN (body swelling · severe)", state panel ticks. The scenario clock passes 10 minutes and "no ECG within 10 min" (`WORK-CHEST-01`) joins the amber card. | "In the background, Bayan keeps track of allergies, medicines, vitals and tests." | "Doctor can speak English or Arabic" |
| 1:05–1:25 | D3: the doctor prescribes amoxicillin and says "go home". **Screen:** the 🔴 allergy card (`ALG-PEN-01`) appears, the chest-pain card turns 🔴 (`WORK-CHEST-02`, `-03`), and the held-turn banner shows. **Room shot:** the patient waits and hears nothing. | "The doctor is about to prescribe a penicillin, and send chest pain home without an ECG or a troponin test. Bayan says nothing aloud. It alerts only the doctor, and holds that sentence back." | "Silent alerts · doctor only · 2 cards, 5 rule hits" |
| 1:25–1:40 | The doctor reads, taps **Acknowledge** on both cards, then says D4. Bayan speaks Nepali. The patient nods. Cut, then D5 (results). | "The doctor stays in control, and corrects the plan." | "Doctor decides · Bayan supports" · on D5: "Later: results" |
| 1:40–1:48 | D6 (plan and red flags) → Nepali. D7: "Bayan, end consultation." | — | "Voice command: end consultation" |
| 1:48–2:05 | **Screen:** review → SOAP note → **Copy**. Then the Nepali PDF full-screen: pictograms, red box, 999, QR. The doctor taps **Approve & send**. | "The doctor gets an English SOAP note for the record. Nothing reaches the patient until the doctor approves it." | "English SOAP note · every line traceable to the transcript" |
| 2:05–2:18 | **Phone close-up:** WhatsApp message with the PDF link. SMS arriving. The patient scans the QR and the Nepali audio plays, with subtitles. | "The patient leaves with a care plan in Nepali, on WhatsApp and SMS, with audio for anyone who can't read." | "PDF · WhatsApp · SMS · audio" |
| 2:18–2:35 | **Animated diagram:** VAD → LID/ASR → LLM → rules → TTS, with HF logos and model names. Then two big numbers. | "Built on open Hugging Face models: IndicConformer, Whisper, GPT-OSS 120B on Inference Providers, and Indic Parler-TTS, plus our Qwen fine-tune from HF Jobs, served from a Space. Total spend: ⟨measure: total $ spent, billing page⟩. About ⟨measure: $ per consultation, UI cost meter⟩ per visit." | "Silero VAD · indic-conformer-600m · whisper-large-v3-turbo · gpt-oss-120b (Cerebras/Groq) · indic-parler-tts · `dullgrey/team-qh-129-bayan` · `dullgrey/team-qh-129-bayan-idioms`" · "Estimate before measuring: ≈ $0.015 per consultation (doc 07)" |
| 2:35–2:42 | Closing card: Bayan logo, tagline, Space URL. | "Bayan AI. Every patient, understood." | `huggingface.co/spaces/dullgrey/team-qh-129-bayan-app` · `qai-hf-hackathon-2026` |

### 2.2 Exact lines

**Recording markers:**
**🎙 NATIVE** means a native speaker must record or perform the line, and verify the wording first.
**🤖 GEN** means Bayan generates the line live. A native speaker must back-check the output in rehearsal, and we re-record if it is wrong.
**✅ EN/AR** means the team speaks it.

> The Nepali text below is a **machine draft for the native speaker to correct**. It is not final copy. If no native Nepali speaker can be found by Saturday 09:00, synthesise the patient lines with the Nepali TTS, `ai4bharat/indic-parler-tts` (Nepali has one named voice, "Amrita"; fallbacks `kenpath/svara-tts-v1` or OmniVoice, per [04 §3](04-models-and-languages.md#3-language-coverage-matrix)), and caption the video "synthetic patient voice". Do not present it as a real person.

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
- **SOAP note:** includes "Allergy: penicillin (body swelling, per patient; recorded as severe)", BP 128/82, "ECG: normal; troponin: normal (as stated by clinician)", a decision-support log with both cards (5 rule hits: `ALG-PEN-01`, `WORK-CHEST-01…04`) acknowledged and the amoxicillin withdrawn, and the plan exactly as said.
- **Nepali PDF:** paracetamol 1 g with ☀️ 🌤 🌙 (up to 3×/day), water, rest out of the sun, red-flag box (chest pain returns or spreads to the arm or jaw, fainting, sweating, vomiting blood or black stools → 999), "PENICILLIN: do not take", QR to audio.
- **No other alert** appears after D4–D6 (checked by the rule-engine unit test in [02 §8](02-product-spec.md#8-the-golden-path-demo-scenario)).
- **WhatsApp:** click-to-chat with a Nepali line, the PDF link and the audio link (stretch: sandbox attachment).
- **SMS:** ≤ 2 UCS-2 segments with the link.
- **MP3:** Nepali, slower rate, ≤ 2 min.

---

## 3. Backup demo plan

Three things are most likely to fail on the day: the venue Wi-Fi, provider cold starts, and the hall PA feeding back into the tablet mic. Each fallback level is one tap away, and **the operator switches without apologising**.

| Level | What runs | When to use | What the Speaker says |
|---|---|---|---|
| **L0: Fully live** | Live mic, live speakers, real pipeline | Booth demos, Q&A, quiet rooms | — |
| **L1: Replay mode (default for the pitch)** | Pre-recorded WAVs per turn (C2, D1–D7, P1–P3), fed by a hidden **"Next turn ▶"** control into the **same** pipeline (VAD → ASR → LLM → rules → TTS). Real models, real outputs. | Pitch stage, noisy rooms, no native speaker present | "This is the real pipeline running on our recorded patient audio." |
| **L2: Cached run** | Pre-computed pipeline outputs from a successful Saturday-morning run, replayed with the original timings. No network needed. | Provider outage, or Wi-Fi down | "The network's down, so here's the recorded run from this morning, same system." |
| **L3: Demo video** | The 2–3 min video, cued at 0:35 | Laptop or tablet dies | "Let me show you the video." |

**Build requirements (Must M12 in [02](02-product-spec.md#7-mvp-scope-for-saturday-2-pm-moscow)):**
- Replay mode takes a folder of `turn_NN_<speaker>_<lang>.wav` files plus a manifest (order, expected route, and a `t_scenario` timestamp per turn that drives the rule engine's clock, so the 10-minute ECG timer behaves as in a real consultation) and feeds them through the normal audio entry point. It must not shortcut ASR.
- The cached run is a JSONL of pipeline events (transcript, translation, alerts, timings) plus the final PDF, MP3 and note.
- The operator's control is off-screen (a laptop keyboard shortcut, or a hidden button on the tablet edge).

**Pre-flight checklist (T-30 min before pitch, and before filming)**

- [ ] Warm up every model endpoint with one dummy request each (ASR, LLM, TTS) to avoid cold starts. Check the Space is awake.
- [ ] Phone hotspot ready as a Wi-Fi fallback. Tablet and laptop charged above 80%.
- [ ] Tablet audio goes **direct to the venue PA by cable** if possible. Tablet mic not facing the speakers.
- [ ] Demo phone has WhatsApp logged in (and joined the Twilio sandbox within its expiry window, if C2 is used). SMS number verified on the Twilio trial (if S2 is used).
- [ ] A Golden Path dry run in replay mode passes: exactly two cards appear (`ALG-PEN-01`; chest-pain workup with `WORK-CHEST-01…04`), nothing else fires after the corrected plan, the PDF renders, and the QR opens audio.
- [ ] The cost meter and the billing page have been read, and every `⟨measure⟩` value in §1 is filled in.
- [ ] Cached run (L2) loaded locally. Video (L3) downloaded locally, not streamed.
- [ ] Session cleared, so no leftover transcript is on screen.

---

## 4. Judge Q&A prep (15 questions)

Answer in ≤ 20 seconds, then stop. Lead with the honest limit and follow with the mitigation.

| # | Question | Answer |
|---|---|---|
| 1 | **How accurate is it? What about hallucinations?** | "We don't claim a clinical accuracy number yet. We measured ⟨measure: per-language ASR WER/CER on 20 FLEURS utterances and chrF++ on 50 FLORES+ sentences, from the [04 §9](04-models-and-languages.md#9-verification-plan-cheap-and-it-doubles-as-an-efficiency-talking-point) mini-benchmarks⟩, and our native-speaker smoke tests. Three design choices limit hallucination. Every line of the doctor's note links back to the exact transcript turn it came from. The assessment and plan come only from the doctor's own words. Numbers, doses and drug names are 'critical tokens': if they change between speech and translation, Bayan asks 'did you mean…?' instead of guessing." |
| 2 | **If the translation is wrong and a patient is harmed, who is liable?** | "The doctor stays the decision-maker. Bayan supports decisions and doesn't make them, and nothing reaches the patient without the doctor approving it. Every session leaves an audit trail of what was said, what Bayan showed, and what the doctor did. A real deployment would go through the hospital's clinical governance and medico-legal review before any pilot. We don't claim to have settled liability this weekend." |
| 3 | **Where does patient audio go? Privacy?** | "Audio is processed in memory and never stored. The transcript is wiped when the session ends, and patient links expire. Qatar's data protection law, Law 13 of 2016, treats health data as a special category, so consent is spoken in the patient's own language before anything else happens. This weekend we use synthetic data only. In production, the open models run on in-country infrastructure." |
| 4 | **Why not just use Google Translate?** | "A translator app isn't an interpreter in the room. Someone has to hold the phone and press buttons. It doesn't know that a Nepali worker's 'gyastrik' in the chest can hide heart pain, it doesn't notice the penicillin allergy, and it doesn't write the SOAP note or the care plan. It's also a consumer service: a hospital can't host it, audit it, or keep the data in Qatar. Bayan's value is the safety layer and the outputs, not only the translation." |
| 5 | **Why not a human interpreter?** | "Professional interpreters are the gold standard, and the research shows they make fewer consequential errors than ad hoc interpreters. In Flores 2003, 77% of ad hoc interpreters' errors had potential clinical consequences, against 53% for hospital interpreters. Bayan fills the gaps: nights, walk-in clinics, rarer languages. When the patient declines or Bayan is unsure, it tells the doctor to call a human interpreter." |
| 6 | **What does it cost?** | "About ⟨measure: $ per consultation, UI cost meter⟩ per consultation in our current setup. Our list-price estimate was about $0.015 of marginal API cost, against $0.047 for a naive build, so about three times cheaper. Self-hosted Nepali TTS GPU time comes on top of that. We built and demoed everything for ⟨measure: total $ spent, billing page⟩ of the $100 budget, against a plan of about $32 and a $25 reserve we set aside not to touch. At hospital scale, a dedicated GPU with many concurrent consultations changes the cost curve, but we haven't benchmarked that yet. See doc 07." |
| 7 | **What about languages with no good text-to-speech, or weak speech recognition?** | "We're honest about tiers. Tier 1 is Nepali, Hindi, Urdu, Bengali, Malayalam and Tagalog, the same six patient languages as the MoPH Bill of Rights. Those are demo targets: ⟨measure: which Tier-1 languages passed the doc-04 smoke test⟩ are verified end to end today. Tier 2 and 3, such as Tamil, Sinhala, Swahili, Somali and Pashto, have a model for each stage but no verification. Where there's no adequate TTS, the review screen says 'audio not available', and the PDF still goes out. Sinhala and Pashto only have a non-commercial voice today, and Tagalog's voice is non-commercial too. We chose not to fine-tune TTS this weekend: it needs many GPU-hours and native listening tests. Indic Parler-TTS already speaks Nepali." |
| 8 | **Dialects? Sylheti vs standard Bengali, or Nepali spoken in the hills vs the Terai?** | "This is a real limit. ASR is weaker on dialects and code-switching. We mitigate with confidence scores and confirm-back ('did you mean…?'), and we never guess on numbers or drugs. We deliberately didn't fine-tune ASR this weekend, because without a native-transcribed clinical test set we couldn't measure the gain. Dialect coverage is the main fine-tuning target after the hackathon, ideally with recordings collected with consent from Qatar's communities." |
| 9 | **Is this a regulated medical device?** | "The interpretation and note parts are communication and documentation tools. The safety sentinel is clinical decision support, and we'd expect regulators to look at it. We haven't verified the exact Ministry of Public Health pathway, and we'd do that with a clinical partner before any pilot. It's designed for this: deterministic, auditable rules with cited sources, and the doctor always decides." |
| 10 | **Who pays? What's the business model?** | "The buyers are providers and payers who carry the cost of miscommunication: HMC and PHCC for public clinics, private hospitals and clinics that serve worker populations, and employers and insurers who pay for workers' care. The model is per-clinic or per-tablet licensing, with a hosted or on-premise option. We have not validated pricing. That's what a pilot is for." |
| 11 | **Can it run sovereign, inside Qatar, with no data leaving?** | "Yes, by design. Every model is open-weight from the Hugging Face Hub, so the whole cascade can run on a dedicated Inference Endpoint in a suitable region, or on a hospital's own GPUs. For Arabic we can use Fanar, Qatar's own model from QCRI. Our rough estimate is that the voice models fit on one 24 GB L4 GPU, tightly, or comfortably on a 48 GB L40S. Our 4B fine-tune runs on one GPU, or as a GGUF on CPU for an offline box. We haven't yet sized self-hosting the 120B model, or how many consultations one GPU can serve at once." |
| 12 | **How exactly did you use Hugging Face?** | "The app is a Hugging Face Space. Every model is an open model from the Hub. The ones a provider serves are called through Inference Providers: `gpt-oss-120b` on Cerebras and Groq, Whisper large-v3-turbo, Kokoro and Chatterbox for the doctor-side voice, and Fanar-1-9B on featherless-ai. The Nepali speech models, IndicConformer and Indic Parler-TTS, aren't served by any provider, so they run on one GPU worker we host on HF. We fine-tuned a LoRA on Qwen3-4B-Instruct with TRL and PEFT on HF Jobs, and published it as `dullgrey/team-qh-129-bayan` with a model card, next to the dataset `dullgrey/team-qh-129-bayan-idioms`. The cascade design follows Hugging Face's open speech-to-speech pipeline pattern. No frontier closed model is in the core loop." |
| 13 | **Efficiency: how did you spend your $100?** | "⟨measure: final spend-log line, actual $ by item⟩. The plan was about $32: about $5.50 for build-time APIs and synthetic data, $5 for fine-tuning and evaluation on HF Jobs, about $19 for GPU serving (the Nepali voice worker and the fine-tuned model, scale-to-zero), and $3 for judging-day traffic, with $25 kept as an untouchable reserve. Three choices saved money. Alerts are rules, not extra LLM calls. Consent and fixed prompts are cached audio. We picked the smallest model that passed our Golden Path checks at each stage." |
| 14 | **No one on your team is a clinician. How do you trust the clinical content?** | "We didn't invent any medicine, and we haven't had a clinician review it yet. All 59 idiom entries and all 81 rules cite sources: FDA labels, NICE, AHA/ACC and ESC guidelines, and peer-reviewed papers. Twenty idioms are honestly marked 'community-reported'. The rules are deterministic and simple: a penicillin allergy against a penicillin, or chest pain discharged without an ECG or troponin. Everything is framed as a flag for the doctor, never a diagnosis. Clinical and pharmacist review of the rule set is step one of any pilot." |
| 15 | **What's next?** | "Three things. A supervised pilot in one clinic that serves workers, alongside professional interpreters, measuring errors caught and patient understanding. Dialect fine-tuning with community recordings. And deeper Arabic support with Fanar, plus sovereign hosting. We'd love introductions to HMC, PHCC and QCRI." |

**Backup answers (if asked):**
- *Alert fatigue?* "There are only two alert colours, and every alert quotes its evidence. Related rules are grouped: the Golden Path's five rule hits show up as two cards. Only a critical prescribing alert adds friction, by holding the sentence. Overriding an alert takes one tap with a reason, and that is logged. Override rates for drug alerts are documented between 49% and 96%, which is why we keep the number of alerts low." ([van der Sijs et al. 2006](https://pubmed.ncbi.nlm.nih.gov/16357358/), via [05 §2.7](05-clinical-safety-and-cultural-intelligence.md#27-alert-ux-silent-evidenced-accountable))
- *What if a family member speaks?* "Bayan interprets them too, so the patient hears everything said about them, and the doctor can label the line as 'companion'."
- *What if the patient speaks Arabic?* "Language stops being a speaker signal, so the doctor flips a toggle and labels lines. Automatic diarization is a stretch goal."

---

## 5. Taglines and 30-second elevator version

### Taglines (pick one for the closing slide; the recommended one is first)

1. **"Every patient, understood."**
2. **"It listens. It talks. It thinks, so no one is lost in translation."**
3. **"Clarity at the bedside, in every language spoken in Qatar."**
4. **"The interpreter that also watches the patient's back."**
5. **"Your language. Your care plan. Your phone."**

### 30-second elevator version (≈ 80 words)

> "In Qatar, many patients speak neither English nor Arabic, and their doctors don't speak Nepali, Bengali or Tagalog. Interpretation errors are common, and some are dangerous, like a penicillin allergy that never gets translated. Bayan AI is one tablet that listens to the consultation, interprets out loud in both directions, and quietly alerts the doctor to risks like allergy conflicts. At the end, the patient gets a care plan in their own language, as a PDF, on WhatsApp and SMS, and as audio. It's built on open Hugging Face models."
