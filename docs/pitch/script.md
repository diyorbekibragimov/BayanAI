# Bayan: 3-minute pitch script

Team QH-129, Qai × Hugging Face Hackathon O1, Doha.
Deck: [`deck/index.html`](deck/index.html). PDF: [`Bayan-pitch.pdf`](Bayan-pitch.pdf).

## Say it exactly (rehearsal text, 3:00)

> Hello, we're team QH-129. This is Bayan, a clinical AI system for consultations in Qatar. First, a patient.
>
> Meet Anurag, a Nepali construction worker in Doha. He says his chest is burning, "just gyastrik", Nepali for gastric. The doctor hears reflux. It could be his heart.
>
> Anurag is made up, but the problem is real. 65% of HMC ambulance staff face language barriers at work. And that affects safety.
>
> In US hospitals that measured it, 49% of adverse events in patients with limited English caused physical harm, against 30% for English speakers.
>
> Bayan listens to both sides. It interprets in 37 patient languages, keeps a running case summary, and suggests one next question at a time. Here it is.
>
> *(demo plays)* This is a recording of our Space. The doctor asks about allergies, and the patient hears it in Nepali. He says a penicillin injection once made him swell. Now he says his chest burns, gyastrik. A card flags it, and Bayan suggests the next question. The doctor taps it, and it is asked in Nepali. Then the doctor prescribes amoxicillin.
>
> Bayan paused that sentence before the patient heard it, because amoxicillin is a penicillin. The doctor can say something else or speak it anyway.
>
> When the visit ends, the patient gets a care plan in his own language by QR code, and the doctor gets a note. Here's how it works.
>
> Each turn is heard, translated and checked before it is spoken. In the background, a smolagents agent reviews the case and picks one thing to show the doctor.
>
> It all runs on Hugging Face Spaces, with gpt-oss-120b through Inference Providers.
>
> In scripted tests, the safety rules passed 99% of 727 checks with no false alarms, and the clinical review flagged 8 of 12 expected concerns. Results vary between runs.
>
> In Qatar, we'd start with the QRCS workers' health centres, then HMC and PHCC.
>
> On Hugging Face it costs 9 to 28 cents a consultation, and hospitals can run it on their own servers. A phone interpreter costs about 11 to 16 dollars.
>
> Other tools translate or take notes. None we found checks the consultation as it happens.
>
> It isn't a certified interpreter yet. Next, we need a pilot clinic, clinician review of our rules, and native-speaker testing.
>
> This is our team. Thank you.

**Word count:** 383 spoken words in total.
- 323 are spoken over the slides, in 2:14 of slide time, which is about 145 words a minute.
- 60 are short cues over the 42-second demo (4 s spare).
- Slide 9 or 10 is presented, not both.
- Slide 18 (Thank you) stays up after 3:00 for questions.

## Timing

| # | Slide | Time | Words |
|---|---|---|---|
| 1 | Title | 0:00–0:07 | 18 |
| 2 | Meet Anurag | 0:07–0:19 | 28 |
| 3 | Language barriers in Qatar | 0:19–0:29 | 23 |
| 4 | Adverse events and language | 0:29–0:38 | 23 |
| 5 | What Bayan does | 0:38–0:49 | 27 |
| 6 | Demo (video, 42 s) | 0:49–1:35 | 60 |
| 7 | Check before it is said | 1:35–1:45 | 24 |
| 8 | Care plan and doctor's note | 1:45–1:56 | 27 |
| 9 (or 10) | Architecture, present one | 1:56–2:08 | 28 |
| 11 | Hugging Face stack | 2:08–2:13 | 12 |
| 12 | Simulation results | 2:13–2:25 | 29 |
| 13 | First customers in Qatar | 2:25–2:31 | 14 |
| 14 | Deployment and cost | 2:31–2:43 | 29 |
| 15 | Comparison | 2:43–2:49 | 15 |
| 16 | Next steps | 2:49–2:57 | 20 |
| 17 | Team | 2:57–3:00 | 6 |
| 18 | Thank you | after 3:00 | none |

**Deck controls:**
- → / Space / click: next slide. ←: back.
- `f`: fullscreen.
- `r`: restart the demo video. `p`: pause or play it.

**Demo video:** slide 6 plays `assets/demo.webm` (42 s, no audio) from the start at normal speed. It is a fast cut of the live Space recording: the start and consent screens, then the consultation at 2×, the paused screen ("Paused: please check"), the doctor's choice and the review screen.

**Demo choice:** play the recorded video. Inference credits are frozen, so a live run is not possible today. If credits come back and the venue network is solid, the same scripted consultation can run live at `/?demo=1` on the Space. Keep the video one keypress away even then.

**Tone:** plain and conversational. Short sentences. Leave a short gap after each number.

---

## Presenter script, slide by slide

### 1. Title (0:00–0:07)
**On screen:** "بيان Bayan AI", the tagline, then Team QH-129, Qai × Hugging Face Hackathon O1 and Doha, 5–7 Nov 2026, with the pearl.
> Hello, we're team QH-129. This is Bayan, a clinical AI system for consultations in Qatar. First, a patient.

### 2. Meet Anurag (0:07–0:19)
**On screen:** the illustration of Anurag with the slide's text:
- "Meet Anurag", "29, a Nepali construction worker in Doha"
- "My chest is burning. It's just gyastrik.", with ग्यास्ट्रिक, Nepali for "gastric"
- "The doctor hears reflux. It could be his heart."
> Meet Anurag, a Nepali construction worker in Doha. He says his chest is burning, "just gyastrik", Nepali for gastric. The doctor hears reflux. It could be his heart.

### 3. Language barriers in Qatar (0:19–0:29)
**On screen:** three figures:
- 65% of HMC ambulance staff face language barriers at work
- 71% are comfortable letting family members interpret
- 9 face-to-face interpreter languages at Sidra
> Anurag is made up, but the problem is real. 65% of HMC ambulance staff face language barriers at work. And that affects safety.

### 4. Adverse events and language (0:29–0:38)
**On screen:** three rows of bars, limited English in vermillion and English-speaking in grey:
- physical harm: 49% vs 30%
- moderate harm or worse: 47% vs 24%
- communication errors: 52% vs 36%

Below the bars: the line about Bayan closing the gap.
> In US hospitals that measured it, 49% of adverse events in patients with limited English caused physical harm, against 30% for English speakers.

### 5. What Bayan does (0:38–0:49)
**On screen:** four columns: Interprets, Reasons, Flags, Suggests.
> Bayan listens to both sides. It interprets in 37 patient languages, keeps a running case summary, and suggests one next question at a time. Here it is.

### 6. Demo (0:49–1:35)
**On screen:** the recorded Nepali consultation, silent, sped up; you narrate. Cue times are from when the slide opens. The care plan and QR code are on slide 8.

| Cue | What appears | Say |
|---|---|---|
| 0:00 | Start screen and the patient's consent | "This is a recording of our Space. The patient picks Nepali and consents." |
| 0:03 | "Do you have any allergies to medicines?", then the Nepali caption | "The doctor asks about allergies, and the patient hears it in Nepali." |
| 0:09 | The patient's Nepali and the English for the doctor | "He says a penicillin injection once made him swell." |
| 0:15 | *Gyastrik* underlined; the Notes panel shows the flag and "Ask next" | "Now he says his chest burns, gyastrik. A card flags it, and Bayan suggests the next question." |
| 0:24 | The suggested question shown and spoken in Nepali | "The doctor taps it, and it is asked in Nepali." |
| 0:33 | "Amoxicillin 500 three times a day…" and the pearl turns vermillion: "Paused: please check" | "Then the doctor prescribes amoxicillin, and Bayan pauses it." |
| 0:37 | "Say something else" | "The doctor changes the plan." |
| 0:42 | The video ends on the review screen | (advance) |

### 7. Check before it is said (1:35–1:45)
**On screen:** the paused screen in a frame, with the line: "The patient mentioned a penicillin allergy, and the doctor then prescribed amoxicillin. Bayan paused the sentence before the patient heard it, so the doctor can say something else or speak it anyway."
> Bayan paused that sentence before the patient heard it, because amoxicillin is a penicillin. The doctor can say something else or speak it anyway.

### 8. Care plan and doctor's note (1:45–1:56)
**On screen:** the phone page from the QR code, the patient sheet in Tamil and the doctor's note.
> When the visit ends, the patient gets a care plan in his own language by QR code, and the doctor gets a note. Here's how it works.

### 9. Architecture (overview): present this one (1:56–2:08)
**On screen:** three parts:
- Each turn: Hear, Interpret, Safety gate ("paused for the doctor to check"), Speak.
- The reasoning loop: Case summary, Clinical review agent, Attention filter, Doctor's screen, with a "next turn" arrow back to the summary.
- Wrap-up: care plan, PDFs, QR.
> Each turn is heard, translated and checked before it is spoken. In the background, a smolagents agent reviews the case and picks one thing to show the doctor.

### 10. Architecture (detailed): skip in the talk, keep for questions
**On screen:** the full diagram:
- The per-turn stack with model names.
- The reasoning loop with five checks and its tools: safety rules (83), idiom lexicon (98), drug check, case lookup.
- Wrap-up.

**Skip:** press → twice from slide 9. If you present this slide instead of slide 9, say the same line as on slide 9.

### 11. Hugging Face stack (2:08–2:13)
**On screen:** two Space cards (Bayan AI on CPU upgrade, Bayan Voice Worker on an NVIDIA L4), the model boxes, and gpt-oss-120b through Inference Providers.
> It all runs on Hugging Face Spaces, with gpt-oss-120b through Inference Providers.

### 12. Simulation results (2:13–2:25)
**On screen:** two groups:
- Safety rules: 99% of 727 checks, 0 of 44 false-alarm traps, 100% of 477 PDF checks.
- Clinical review: 8 of 12 expected concerns, 0 false caution alerts on 6 quiet visits, 30 of 30 rule checks.

Underneath: timings and cost. The subtitle says results vary between runs.
> In scripted tests, the safety rules passed 99% of 727 checks with no false alarms, and the clinical review flagged 8 of 12 expected concerns. Results vary between runs.

### 13. First customers in Qatar (2:25–2:31)
**On screen:** 1.46 M QRCS visits, 1.56 M HMC emergency visits and 5.17 M PHCC visits, plus the pricing to test.
> In Qatar, we'd start with the QRCS workers' health centres, then HMC and PHCC.

### 14. Deployment and cost (2:31–2:43)
**On screen:** online, clinic box and hospital tiers against a phone interpreter, with cost per consultation on a log scale.
> On Hugging Face it costs 9 to 28 cents a consultation, and hospitals can run it on their own servers. A phone interpreter costs about 11 to 16 dollars.

### 15. Comparison (2:43–2:49)
**On screen:** the comparison table.
> Other tools translate or take notes. None we found checks the consultation as it happens.

### 16. Next steps (2:49–2:57)
**On screen:** a pilot at one QRCS workers' health centre, clinician review of 83 rules and 98 idioms, native-speaker validation; the Space URL.
> It isn't a certified interpreter yet. Next, we need a pilot clinic, clinician review of our rules, and native-speaker testing.

### 17. Team (2:57–3:00)
**On screen:** Team QH-129 with four initials avatars: Diyorbek Ibragimov, Sangyoon Lim, Mohammed Al-Kuwari, George Chkhaidze.
> This is our team. Thank you.

### 18. Thank you (after 3:00)
**On screen:** the pearl, "Thank you", "Questions" and the Space URL. Leave it up during questions.

---

## Numbers on stage and where they come from

| Said or shown | Source |
|---|---|
| 65% / 71% of HMC ambulance staff | Farhat et al., *Qatar Med J* 2025, n = 312 (research.md [16]) |
| Sidra in-person interpreters: 9 languages, no Nepali, Malayalam, Bengali or Tagalog | Sidra Medicine website, 2026 [10] |
| Adverse events, limited English vs English-speaking: physical harm 49.1% vs 29.5% (shown 49% and 30%, 1.7×); moderate harm to death 46.8% vs 24.4% (47% and 24%, 1.9×); caused by communication errors 52.4% vs 35.9% (52% and 36%, 1.5×) | Divi C, et al. *Int J Qual Health Care* 2007;19(2):60–67, https://doi.org/10.1093/intqhc/mzl069 (research.md [19]); rows 1–3 of `docs/pitch/data/lep_adverse_events.csv`. Six US Joint Commission hospitals, voluntarily reported events, pilot study. Say "adverse events", not "twice as many events". The year is not on the slide |
| *Gyastrik* ("gastric") can hide cardiac pain; Anurag is an illustrative persona | `data/idiom_lexicon.json` entry npi-005; in Nepal only 23.8% of STEMI patients thought their pain was cardiac (Prajapati, *JNHRC* 2022 [36]) |
| Rule pause in about 3 ms, no LLM | `bayan/brain/copilot.py` prescription gate; docs/11 §2 |
| Coherence pause: one fast gpt-oss-120b call, 3 s limit | `bayan/brain/coherence.py` (checks the doctor's plans, diagnoses and clinical claims; on error or timeout the sentence is spoken) |
| 37 patient languages; doctor in English or Arabic | `bayan/ui.py`: 5 start chips plus 32 in "More…" (Filipino, Tamil, Swahili, then the 29 in `bayan/langs.py`) |
| 83 rules, 98 idioms | `data/safety_rules.json` (83) and `data/idiom_lexicon.json` (98 entries; the 38-scenario simulation ran on the earlier 59-entry lexicon) |
| Safety rules: 99% of 727, 0 of 44 traps, 477 of 477 PDF checks, 3 of 16 expected pauses missed, $0.011 median LLM cost, 0.9 s per turn | `reports/sim/gptoss120b-full/summary.md` (38 consultations, 14 languages; text turns, no audio) |
| Clinical review: 8 of 12 expected concerns, 0 caution alerts on 6 quiet visits, 30 of 30 clinical checks, 0 of 22 traps, agent card median 7.0 s, $0.0143 median per consultation | `reports/sim/coherence-r2/summary.md`: one full run of 16 consultations in 9 languages (7 coherence, 6 quiet, 3 regression). Smaller reruns caught 4 of 7 (`coherence-r3`) and 2 of 5 (`coherence-r4`), so results vary between runs |
| Online $0.09–0.28, clinic box $0.13–0.51, hospital $0.16–1.65 per consultation; phone interpreter $11.40–15.75 | research.md §6.3, `data/cost_per_consultation.csv`, `data/cost_per_clinic_month.csv`. Assumptions: 1,200 consultations per clinic-month; L4 Space at $0.80/h for 12 h a day; CPU Space at $0.03/h; LLM $0.025 per consultation from the token model; 15 interpreter-minutes per visit |
| Clinic box $14.6k (QAR 53k), hospital server $48k (QAR 175k) | research.md §6.1, `data/cost_model.json`: street prices L4 ≈ $2,800, L40S ≈ $8,500, H100 PCIe ≈ $27,500, plus a $9–12k server; 36-month amortisation, support at 15% of capex a year, Qatar business electricity QAR 0.13/kWh, PUE 1.5. Sharing across clinics not load-tested; offline not demonstrated end to end |
| gpt-oss-120b fits one 80 GB GPU (MXFP4); gpt-oss-20b fits in 16 GB | openai/gpt-oss-120b model card [68] |
| QRCS 1.46 M visits (2025); HMC 974,268 adult + 583,864 paediatric ED visits (2025); PHCC 5.17 M visits (2024) | Qatar Tribune 2026 [14]; Gulf Times 2026 [11]; The Peninsula 2025 [13] |
| Pricing to test: QAR 2–3 per consultation; phone interpreter about QAR 40–60 per visit | research.md §6.4 (hypothesis, not validated); $11.40–15.75 × 3.64 |

---

## Q&A cheat sheet (about 30 seconds per answer)

**1. How accurate is the translation in Nepali or Malayalam?**
- **Not measured yet:** we haven't tested each language with native speakers, and we say so.
- **What the literature shows:** machine translation keeps 55–94% of the meaning depending on the language. In Haitian Creole, one study found clinically significant LLM errors 33% of the time, against 8% for professionals.
- **What Bayan does about it:** it doesn't rely on the translation alone. The doctor sees what will be said, and the patient can tap "Say it again" or "Slower" in their own language. The checks work on the facts pulled out of the conversation.
- **Next step:** a native-speaker audit for each of the 37 languages. Voice quality also varies by language.

**2. When does Bayan pause a sentence?**
Two checks run before a doctor's sentence is spoken:
- **Safety rules.** 83 cited rules run with no language model, in about 3 ms. They cover allergy cross-reactions, dose limits and interactions.
- **Coherence check.** One fast gpt-oss-120b call looks only at plans, diagnoses and clinical claims. It pauses for:
  - a clear contradiction with what the patient said;
  - a treatment that doesn't fit the complaint;
  - a claim nothing in the consultation supports;
  - an instruction likely to be misunderstood.

If that call fails or takes more than 3 seconds, the sentence is spoken. Either way the doctor decides: say something else, or speak it anyway, which is logged.

**3. Won't the alerts annoy doctors?**
- **Safety rules:** in the 38-consultation suite, 0 of 44 false-alarm traps tripped. One example trap was a sulfa allergy with furosemide.
- **Clinical review:** it raised no false caution alerts on 6 quiet visits.
- **One card at a time:** the attention filter shows a single "Ask next". It merges or expires older cards.
- **Pilot measure:** alert precision, with a target of at least 70%.

**4. What did it miss?**
- **Safety rules: 3 of 16 expected pauses missed:**
  - Augmentin given by brand name;
  - an allergy described only as "my body swelled" from "that red amoxi capsule", followed by cephalexin;
  - a tramadol daily total that was not summed.

  Each fix is a rule or an alias.
- **Clinical review: 8 of 12 found in one full run.** It missed four:
  - a prescription with no drug name or dose;
  - a patient confused about where to use a nasal spray;
  - a blood pressure called fine without being taken;
  - hopelessness mentioned in passing.

  Smaller reruns found 4 of 7 and 2 of 5, so results vary between runs.

**5. What does the AI decide, and why an agent?**
- **Translation step:** gpt-oss-120b translates each turn and, in the same call, updates the case summary: complaint, history, working diagnosis, plan, the patient's understanding and mood.
- **Review step:** after each substantive turn, a smolagents clinical review agent runs five checks: safety, history, plan coherence, communication and consistency.
- **Tools the agent can call:** the 83 rules, the 98-entry idiom lexicon, a drug check and a case lookup.
- **Evidence:** every concern it raises must quote the transcript.
- **What reaches the doctor:** an attention filter scores concerns by severity, confidence and novelty, then shows one question at a time.
- **What the agent can't do:** it suggests but never pauses a sentence. Only the rules or the coherence check can do that.

**6. Why not Google Translate, or an end-to-end speech model?**
- **Translation tools:** they move words, but none checks a sentence against the patient's allergies, doses or history before it is spoken.
- **End-to-end speech models:** no open model produces Nepali or Malayalam speech.
- **Why text in the middle:** the checks, the audit log and the PDFs all work on that text.

**7. Privacy, data residency and self-hosting?**
- **Data handling:** audio is deleted right after transcription, and transcripts stay in memory. Output files are purged after 24 hours, and the Space is behind an access code.
- **Qatar's rules:** Qatar's data protection law (Law 13 of 2016) treats health data as special.
- **Self-hosting:** every model has open weights.
  - **One clinic:** two NVIDIA L4 cards (about $14.6k) run the voice models and gpt-oss-20b.
  - **Hospital:** one H100 80 GB runs gpt-oss-120b on a single GPU, and one L40S runs voice. About $48k, or 16 cents a consultation across 10 clinics.
- **Not yet done:** we haven't run the stack offline end to end, and gpt-oss-20b needs its own quality test.

**8. How fast is it, and what does it cost?**
- **Speed:** translation and the safety rules take 0.9 s a turn. First audio comes in about 1–3 s, and an agent card in about 7 s, in the background.
- **Cost:** the LLM costs about 1 to 1.5 cents per consultation. The GPU is the main cost: about 28 cents a consultation on a dedicated L4, or 9 cents if four clinics share one.
- **Caveat:** sharing is not load-tested yet.

**9. Who pays?**
- **First customers:** QRCS workers' health centres (1.46 M visits in 2025), then HMC emergency departments and PHCC (31 centres), plus private clinics paid through employer insurance.
- **Pricing to test, not validated:** QAR 2–3 per consultation, against about QAR 40–60 for a phone interpreter.
- **On-premise option:** hardware at cost plus an annual licence.
