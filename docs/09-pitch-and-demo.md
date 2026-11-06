# 09 — Pitch & Demo

> **Format rules we are building for** ([handbook](https://huggingface.co/spaces/qai-hackathon/handbook), [agenda](https://huggingface.co/spaces/qai-hackathon/agenda)): a 2–3 minute demo video with a public link, due by **Saturday 2:00 PM**. It is our backup if the live demo breaks. Finalists give a **3-minute pitch plus Q&A** (Saturday 4–6 PM).
> **Judged on:** Impact & relevance · Use of Hugging Face · Technical execution · Efficiency · Demo & pitch. Every section below is tagged with the criteria it serves.
> **Scenario source:** the Golden Path in [02 Product Spec §8](02-product-spec.md#8-the-golden-path-demo-scenario). **Placeholders** `[[from NN]]` are filled in from the named doc. Never improvise a number on stage.

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
**Time budget:** about 360 words from the Speaker, counting the doctor lines and leaving out the optional cascade line. At about 150 words per minute that is ≈ 2:25, plus about 25 s of patient and Bayan audio during the demo, for ≈ 2:50 in total. Rehearse with a stopwatch. If you run long, cut the optional line first.

---

**[0:00 – 0:22] HOOK** *(Impact)*

*Stage: lights on the Speaker. Slide 1 is black, with one line of Nepali text and its English subtitle: "My chest burns like gas." Small caption: "Illustrative story."*

> "Imagine a summer evening in Doha. A twenty-nine-year-old Nepali construction worker tells a clinic his chest *burns like gas*, and that penicillin once made him swell. His roommate interprets, and leaves out the allergy. He goes home with amoxicillin, which *is* a penicillin."

*Pause, two beats.*

> "That story is illustrative. The error isn't. One study found thirty-one interpreter errors per visit, including skipped allergy questions."

*Slide footnote: [Flores et al., Pediatrics 2003](https://pubmed.ncbi.nlm.nih.gov/12509547/).*

**[0:22 – 0:40] PROBLEM IN QATAR** *(Impact & relevance)*

*Slide 2: a map with language labels over Qatar. Big number: `[[from 01: expatriate share of population]]`. Footnote: `[[from 01: Qatar-specific evidence, e.g. HGH language-barrier study]]`.*

> "`[[from 01: expat share]]` of Qatar's residents are expatriates, many speaking Nepali, Hindi, Bengali, Urdu, Malayalam or Tagalog. Doctors work in English and Arabic. Professional interpreters can't be in every room at every hour, so a roommate or a phone fills the gap. We built **Bayan AI**. *Bayan* is Arabic for *clarity*."

**[0:40 – 1:45] LIVE DEMO MOMENT** *(Technical execution · Demo)*

*Stage: the Operator puts the tablet on the lectern and mirrors it to the projector. The Speaker turns slightly toward the tablet as "the doctor". Consent has already been given. Say so, don't show it.*

> "One tablet. No buttons to hold. It listens, it talks, it thinks. The patient has already consented, in Nepali."

*Speaker (as doctor): "What brings you in today?" Bayan speaks Nepali. The patient line P1 plays in Nepali.*

> "The doctor sees his exact words, 'burning like gas', and a note: in this community, 'gas' can describe chest pain, so ask whether it spreads."

*The patient line P2 (penicillin, sore throat) plays. The allergy chip lights up. Speaker (as doctor): "I'll give you amoxicillin, and you can go home."*

*Two alerts slide into the tray. Let the room notice the silence for one beat.*

> "Silence. Bayan said nothing to the patient. Only the doctor sees two alerts: amoxicillin conflicts with his penicillin allergy, and chest pain is going home without an ECG. Bayan held that sentence back."

*Speaker taps Acknowledge. Speaker: "No amoxicillin. Let's check your heart first." Then: "Bayan, end consultation." The Operator shows the review screen, then the Nepali PDF. A teammate holds up a phone with the WhatsApp message. Play three seconds of the Nepali audio.*

> "The doctor gets an English SOAP note. The patient gets a Nepali care plan with medicine times, danger signs and 999, plus audio for anyone who can't read, on WhatsApp and SMS."

**[1:45 – 2:10] HOW IT WORKS ON HUGGING FACE** *(Use of Hugging Face)*

*Slide 3: the cascade diagram. VAD → language ID / ASR → LLM → rules → TTS, with model names under each box.*

> "It's a cascade, built entirely on Hugging Face. `[[from 04: ASR model]]` transcribes and identifies the language, which also tells us who's speaking. `[[from 04: LLM]]`, on Inference Providers, translates and extracts allergies, doses and plans. Plain rules, not a chatbot, fire the alerts. `[[from 04: TTS model]]` speaks Nepali. `[[from 06: one short sentence on the fine-tuned model, trained on HF Jobs, on the Hub]]`. It all runs in a Space."

> *[Optional, cut first if running long]* "Why a cascade? No open speech-to-speech model we found speaks Nepali aloud, and keeping text in the middle is what makes the safety checks possible."

**[2:10 – 2:22] EFFICIENCY** *(Efficiency)*

*Slide 4: two big numbers.*

> "We built all of this on `[[from 07: total $ spent]]` of our hundred dollars. One consultation costs about `[[from 07: cost per consultation]]`. Alerts are rules rather than extra model calls, and fixed prompts are cached audio."

**[2:22 – 2:45] IMPACT** *(Impact & relevance)*

*Slide 5: the Nepali PDF next to a phone playing audio.*

> "Most medical AI saves doctors time. Bayan protects patients. It gives the workers who build Qatar instructions in their own language, on their own phone, that they can *listen to* even if they can't read."

**[2:45 – 3:00] ASK**

*Slide 6: tagline, Space URL and QR code.*

> "Our ask: introductions to one clinic that serves workers, and to the Fanar team at QCRI, for a supervised pilot. Bayan AI: every patient, understood. Thank you."

*Stop. Smile. Don't add anything. Q&A starts.*

---

**Pitch rules for the Speaker**

- The claim that "'gas' can describe chest pain" must match the cited lexicon entry `[[from 05: source for the 'gas' chest-pain idiom]]`. If 05 cannot source it, change the line to "Bayan flags 'gas' in the chest as worth checking".
- Say "illustrative" out loud for the hook. Judges in Doha will know the context, so honesty earns trust.
- Never say "diagnoses", "replaces interpreters" or "100% accurate". Say "supports the doctor", "fills the gaps", "flags for the doctor".
- If the demo stalls for more than 5 s, say "Let me switch to our recorded run" and go to L2 or L3 (§3). Don't debug on stage.
- Run it with a stopwatch at least three times on Saturday before 2 PM, and once more at 3:45 PM.

---

## 2. Demo video script (2–3 min)

**Target length 2:40.** Public link (YouTube unlisted or HF-hosted MP4, viewable by anyone), linked from the Space README and the submission sheet. Shot on a phone in landscape, 1080p. A quiet room dressed as a clinic (desk, tablet, a stethoscope as a prop). Two people: **Doctor** (team member) and **Patient** (a native Nepali speaker if at all possible). Screen-record the tablet at the same time and cut between the room and the screen.

**Honesty captions (required on screen):** "Illustrative scenario · synthetic patient · not medical advice". Plus "Patient voice: [native speaker | synthetic TTS]", whichever is true.

### 2.1 Shot list

| Time | Shot / visual | Narration (voice-over) | On-screen caption |
|---|---|---|---|
| 0:00–0:08 | **Cold open.** Close-up of the patient's face, speaking Nepali (P1). Subtitles in English. | — (patient audio only) | "My chest is burning like gas…" |
| 0:08–0:25 | Wide shot: the doctor looks unsure. Cut to a title card with the stats. | "In Qatar, `[[from 01: expat share]]` of people are expatriates. Many speak neither English nor Arabic. When interpretation fails, errors follow: one study counted 31 interpreter errors per visit, including skipped allergy questions." | "`[[from 01]]`" · "Flores et al., Pediatrics 2003" |
| 0:25–0:35 | Tablet on the desk. The doctor taps **Start** and picks **Nepali**. The tablet speaks consent in Nepali. The patient says "हो" (yes). | "This is Bayan AI. One tablet. It listens, it talks, and it thinks. First, it asks the patient's consent, in their language." | "Consent in Nepali · no audio stored" |
| 0:35–0:50 | D1 → Bayan speaks Nepali. P1 plays. **Screen recording:** Nepali script, literal line, idiom card sliding in. | "The doctor sees what was literally said, and a note on what it may mean." | "Literal translation + idiom card (never spoken)" |
| 0:50–1:05 | D2 (Arabic variant if S1 is done) → P2. **Screen:** allergy chip "PENICILLIN (swelling)", state panel ticks. | "In the background, Bayan keeps track of allergies, medicines and vitals." | "Doctor can speak English or Arabic" |
| 1:05–1:25 | D3: the doctor prescribes amoxicillin and says "go home". **Screen:** 🔴 and 🟠 alerts appear, and the held-turn banner shows. **Room shot:** the patient waits and hears nothing. | "The doctor is about to prescribe a penicillin and discharge chest pain without an ECG. Bayan says nothing aloud. It alerts only the doctor, and holds that sentence back." | "Silent alerts · doctor only" |
| 1:25–1:40 | The doctor reads, taps **Acknowledge**, then says D4 and D5. Bayan speaks Nepali. The patient nods. | "The doctor stays in control, and corrects the plan." | "Doctor decides · Bayan supports" |
| 1:40–1:48 | D6 (plan and red flags) → Nepali. D7: "Bayan, end consultation." | — | "Voice command: end consultation" |
| 1:48–2:05 | **Screen:** review → SOAP note → **Copy**. Then the Nepali PDF full-screen: pictograms, red box, 999, QR. The doctor taps **Approve & send**. | "The doctor gets an English SOAP note for the record. Nothing reaches the patient until the doctor approves it." | "English SOAP note · every line traceable to the transcript" |
| 2:05–2:18 | **Phone close-up:** WhatsApp message with the PDF link. SMS arriving. The patient scans the QR and the Nepali audio plays, with subtitles. | "The patient leaves with a care plan in Nepali, on WhatsApp and SMS, with audio for anyone who can't read." | "PDF · WhatsApp · SMS · audio" |
| 2:18–2:35 | **Animated diagram:** VAD → LID/ASR → LLM → rules → TTS, with HF logos and model names. Then two big numbers. | "Built entirely on Hugging Face: `[[from 04: model names]]` through Inference Providers, `[[from 06: fine-tune line]]`, served from a Space. Total spend: `[[from 07: $]]`. About `[[from 07: cost per consultation]]` per visit." | "`[[from 04]]` · `[[from 06]]` · `[[from 07]]`" |
| 2:35–2:42 | Closing card: Bayan logo, tagline, Space URL. | "Bayan AI. Every patient, understood." | Space URL · `qai-hf-hackathon-2026` |

### 2.2 Exact lines

**Recording markers:**
**🎙 NATIVE** means a native speaker must record or perform the line, and verify the wording first.
**🤖 GEN** means Bayan generates the line live. A native speaker must back-check the output in rehearsal, and we re-record if it is wrong.
**✅ EN/AR** means the team speaks it.

> The Nepali text below is a **machine draft for the native speaker to correct**. It is not final copy. If no native Nepali speaker can be found by Saturday 09:00, synthesise the patient lines with the Nepali TTS `[[from 04: Nepali TTS]]` and caption the video "synthetic patient voice". Do not present it as a real person.

| # | Speaker | Lang | Line as spoken | English meaning | Marker |
|---|---|---|---|---|---|
| C1 | Bayan | NE | *(consent script, [02 §3.3](02-product-spec.md#33-consent-script-fixed-text-pre-verified-per-language))* | "Hello. I am Bayan, a computer interpreter… Do you agree? Please say yes or no." | 🎙 NATIVE verifies text, then cached TTS |
| C2 | Patient | NE | हो, म सहमत छु। | "Yes, I agree." | 🎙 NATIVE |
| D1 | Doctor | EN | "Hello, I'm Dr Sara. What brings you in today?" | — | ✅ EN |
| B1 | Bayan | NE | *(translation of D1)* | — | 🤖 GEN |
| P1 | Patient | NE | मेरो छाती ग्यास जस्तै पोलिरहेको छ। खाना खाएपछि सुरु भयो, अनि रिँगटा लागेको छ। | "My chest is burning like gas. It started after lunch, and I feel dizzy." | 🎙 NATIVE |
| D2 | Doctor | AR *(S1)* / EN fallback | هل تعمل في الخارج؟ وهل عندك حساسية من أي دواء؟ / "Do you work outdoors? Are you allergic to any medicine?" | — | ✅ AR (Arabic-speaking teammate) or EN |
| P2 | Patient | NE | हो, म बाहिर साइटमा काम गर्छु। एक पटक पेनिसिलिनको सुई लगाउँदा मेरो जिउ सुन्निएको थियो। अनि तीन दिनदेखि घाँटी दुखेको छ। | "Yes, I work outside on a site. Once, after a penicillin injection, my body swelled up. And my throat has hurt for three days." | 🎙 NATIVE |
| D3 | Doctor | EN | "It's probably the heat and some gastritis. I'll give you amoxicillin five hundred milligrams three times a day for your throat, and you can go home." | — | ✅ EN → **held by Bayan, never spoken in Nepali** |
| — | *(screen)* | — | 🔴 ALLERGY CONFLICT · 🟠 MISSING WORKUP | — | silent |
| D4 | Doctor | EN | "Actually, no amoxicillin. Your throat looks viral. Before you go, we'll check your blood pressure and do a heart tracing." | — | ✅ EN |
| D5 | Doctor | EN | "Your blood pressure is one twenty-eight over eighty-two, and your heart tracing is normal." | — | ✅ EN (fills BP and ECG in the state panel) |
| D6 | Doctor | EN | "Take paracetamol, one gram, up to four times a day, for your throat. Drink plenty of water and rest out of the sun for two days. If the chest pain comes back, spreads to your arm or jaw, or you feel faint or sweaty, call 999 or come straight back." | — | ✅ EN. Dosing and red flags must be confirmed against `[[from 05]]` before recording. |
| P3 | Patient | NE | हुन्छ, धन्यवाद डाक्टर। | "Okay, thank you, doctor." | 🎙 NATIVE |
| D7 | Doctor | EN | "Bayan, end consultation." | — | ✅ EN (command, not translated) |

**Expected outputs to show in the video (checked before filming):**
- **SOAP note:** includes "Allergy: penicillin (body swelling, per patient)", BP 128/82, "ECG: normal (as stated by clinician)", a decision-support log with both alerts acknowledged and the amoxicillin withdrawn, and the plan exactly as said.
- **Nepali PDF:** paracetamol 1 g with ☀️ 🌤 🌆 🌙 (up to 4×/day), water, rest out of the sun, red-flag box (chest pain returns or spreads, fainting, sweating → 999), "PENICILLIN: do not take", QR to audio.
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
- Replay mode takes a folder of `turn_NN_<speaker>_<lang>.wav` files plus a manifest (order, expected route) and feeds them through the normal audio entry point. It must not shortcut ASR.
- The cached run is a JSONL of pipeline events (transcript, translation, alerts, timings) plus the final PDF, MP3 and note.
- The operator's control is off-screen (a laptop keyboard shortcut, or a hidden button on the tablet edge).

**Pre-flight checklist (T-30 min before pitch, and before filming)**

- [ ] Warm up every model endpoint with one dummy request each (ASR, LLM, TTS) to avoid cold starts. Check the Space is awake.
- [ ] Phone hotspot ready as a Wi-Fi fallback. Tablet and laptop charged above 80%.
- [ ] Tablet audio goes **direct to the venue PA by cable** if possible. Tablet mic not facing the speakers.
- [ ] Demo phone has WhatsApp logged in (and joined the Twilio sandbox within its expiry window, if C2 is used). SMS number verified on the Twilio trial (if S2 is used).
- [ ] A Golden Path dry run in replay mode passes: both alerts fire, the PDF renders, and the QR opens audio.
- [ ] Cached run (L2) loaded locally. Video (L3) downloaded locally, not streamed.
- [ ] Session cleared, so no leftover transcript is on screen.

---

## 4. Judge Q&A prep (15 questions)

Answer in ≤ 20 seconds, then stop. Lead with the honest limit and follow with the mitigation.

| # | Question | Answer |
|---|---|---|
| 1 | **How accurate is it? What about hallucinations?** | "We don't claim a clinical accuracy number yet. We measured `[[from 04: per-language ASR/MT metric]]` on our test set. Three design choices limit hallucination. Every line of the doctor's note links back to the exact transcript turn it came from. The assessment and plan come only from the doctor's own words. Numbers, doses and drug names are 'critical tokens': if they change between speech and translation, Bayan asks 'did you mean…?' instead of guessing." |
| 2 | **If the translation is wrong and a patient is harmed, who is liable?** | "The doctor stays the decision-maker. Bayan supports decisions and doesn't make them, and nothing reaches the patient without the doctor approving it. Every session leaves an audit trail of what was said, what Bayan showed, and what the doctor did. A real deployment would go through the hospital's clinical governance and medico-legal review before any pilot. We don't claim to have settled liability this weekend." |
| 3 | **Where does patient audio go? Privacy?** | "Audio is processed in memory and never stored. The transcript is wiped when the session ends, and patient links expire. Qatar's data protection law, Law 13 of 2016, treats health data as a special category, so consent is spoken in the patient's own language before anything else happens. This weekend we use synthetic data only. In production, the open models run on in-country infrastructure." |
| 4 | **Why not just use Google Translate?** | "A translator app isn't an interpreter in the room. Someone has to hold the phone and press buttons. It doesn't know that 'gas' in the chest might be cardiac, it doesn't notice the penicillin allergy, and it doesn't write the SOAP note or the care plan. It's also a consumer service: a hospital can't host it, audit it, or keep the data in Qatar. Bayan's value is the safety layer and the outputs, not only the translation." |
| 5 | **Why not a human interpreter?** | "Professional interpreters are the gold standard, and the research shows they make fewer consequential errors than ad hoc interpreters (Flores 2003: 53% vs 77% of errors). Bayan fills the gaps: nights, walk-in clinics, rarer languages. When the patient declines or Bayan is unsure, it tells the doctor to call a human interpreter." |
| 6 | **What does it cost?** | "About `[[from 07: cost per consultation]]` per consultation in our current setup, on Inference Providers' per-use pricing. We built and demoed everything for `[[from 07: total $]]` of the $100 budget. At scale, a dedicated endpoint changes the cost curve. See doc 07." |
| 7 | **What about languages with no good text-to-speech, or weak speech recognition?** | "We're honest about tiers: `[[from 04: Tier-1 list]]` are verified end to end. For others, Bayan still shows text to the doctor and produces the PDF. Where there's no adequate TTS, the review screen says 'audio not available', so the doctor knows to explain in person or call an interpreter. Closing those gaps, for example by fine-tuning TTS for Nepali or Sinhala, is exactly where Hugging Face's open models help. `[[from 06]]`" |
| 8 | **Dialects? Sylheti vs standard Bengali, or Nepali spoken in the hills vs the Terai?** | "This is a real limit. ASR is weaker on dialects and code-switching. We mitigate with confidence scores and confirm-back ('did you mean…?'), and we never guess on numbers or drugs. Dialect coverage is the main fine-tuning target after the hackathon, ideally with recordings collected with consent from Qatar's communities. `[[from 06]]`" |
| 9 | **Is this a regulated medical device?** | "The interpretation and note parts are communication and documentation tools. The safety sentinel is clinical decision support, and we'd expect regulators to look at it. We haven't verified the exact Ministry of Public Health pathway, and we'd do that with a clinical partner before any pilot. It's designed for this: deterministic, auditable rules with cited sources, and the doctor always decides." |
| 10 | **Who pays? What's the business model?** | "The buyers are providers and payers who carry the cost of miscommunication: HMC and PHCC for public clinics, private hospitals and clinics that serve worker populations, and employers and insurers who pay for workers' care. The model is per-clinic or per-tablet licensing, with a hosted or on-premise option. We have not validated pricing. That's what a pilot is for." |
| 11 | **Can it run sovereign, inside Qatar, with no data leaving?** | "Yes, by design. Every model is open-weight from the Hugging Face Hub, so the whole cascade can run on a dedicated Inference Endpoint in a suitable region, or on a hospital's own GPUs. For Arabic we can use Fanar, Qatar's own model from QCRI. `[[from 03 / 07: sovereign deployment sizing]]`" |
| 12 | **How exactly did you use Hugging Face?** | "The app is a Hugging Face Space. Speech recognition, the LLM and TTS are open models from the Hub, called through Inference Providers `[[from 04: provider + model list]]`. `[[from 06: fine-tune on HF Jobs, model on the Hub with a card]]`. The cascade design follows Hugging Face's open speech-to-speech pipeline pattern. No frontier closed model is in the core loop." |
| 13 | **Efficiency: how did you spend your $100?** | "`[[from 07: spend breakdown, one line]]`. Three choices saved money. Alerts are rules, not extra LLM calls. Consent and fixed prompts are cached audio. We picked the smallest model that passed our Golden Path checks at each stage." |
| 14 | **No one on your team is a clinician. How do you trust the clinical content?** | "We didn't invent any medicine. Every idiom note and every safety rule cites a published source `[[from 05]]`. The rules are deliberately simple: an allergy class conflict, missing basic workup for chest pain. Everything is framed as a flag for the doctor, never a diagnosis. Clinical review of the rule set is step one of any pilot." |
| 15 | **What's next?** | "Three things. A supervised pilot in one clinic that serves workers, alongside professional interpreters, measuring errors caught and patient understanding. Dialect fine-tuning with community recordings. And deeper Arabic support with Fanar, plus sovereign hosting. We'd love introductions to HMC, PHCC and QCRI." |

**Backup answers (if asked):**
- *Alert fatigue?* "There are only two alert colours, and every alert quotes its evidence. Only red alerts add friction, by holding the sentence. Dismissing an alert takes one tap with a reason, and that is logged."
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
