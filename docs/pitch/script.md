# Bayan: 3-minute pitch script

Team QH-129, Qai × Hugging Face Hackathon O1, Doha.
Deck: [`deck/index.html`](deck/index.html). PDF: [`Bayan-pitch.pdf`](Bayan-pitch.pdf).

**Budget:** 368 spoken words across 15 timed slides; slide 9 is an untimed alternate. 310 are spoken over slides in 2:15, about 138 words a minute; 58 go over the 44-second demo video. The slides carry no footnotes; every source is in the table below.
Tone: plain and conversational. Say what the product does and what the numbers are; no slogans. Speak at an even pace and leave a short gap after each number.

**Deck controls:** → / Space / click = next, ← = back, `f` = fullscreen, `r` = restart the demo video, `p` = pause or play it.
Slide 6 plays `assets/demo.webm` automatically. It starts at 0:22 of the recording, plays at 1.5× and ends on the held screen 44 s later.

**Demo choice:** by default, play the recorded video. Inference credits are frozen, so a live run is not possible today. If credits come back and the venue network is solid, the same scripted consultation can run live at `/?demo=1` on the Space. Even then, keep the video one keypress away.

---

## 1. Title, 0:00–0:09
**On screen:** the Bayan wordmark at top left, "Bayan AI" with بيان beneath it, the tagline "A clinical AI system that interprets between doctors and patients in Qatar, reasons about the consultation, and flags what gets missed." Below that, three items on one row: Team QH-129, Qai × Hugging Face Hackathon O1, Doha, 5–7 Nov 2026. The pearl is on the right.

> We're team QH-129. Bayan is a clinical AI system: it interprets between doctor and patient, reasons about the case, and flags what gets missed.

## 2. Meet Anurag, 0:09–0:19
**On screen:** "Meet Anurag", "29, a Nepali construction worker in Doha", and three columns: Anurag says, The doctor hears, It could be.

> Anurag, a Nepali construction worker, says his chest is burning: gyastrik, Nepali for gastric. The doctor hears reflux. It could be his heart.

## 3. Language barriers in Qatar, 0:19–0:29
**On screen:** three figures: 65%, 71%, 9.

> Anurag is made up; the numbers are real: 65% of HMC ambulance staff report language barriers.

## 4. Adverse events and language, 0:29–0:43
**On screen:** three rows of bars. Each row compares patients with limited English (vermillion) with English-speaking patients (grey):

| Row | Limited English | English-speaking | Ratio |
|---|---|---|---|
| Adverse events that caused physical harm | 49% | 30% | 1.7× |
| Harmful events rated moderate harm or worse | 47% | 24% | 1.9× |
| Adverse events caused by communication errors | 52% | 36% | 1.5× |

Below the bars: "Bayan is built to close this gap: it interprets, reasons about the consultation and flags what gets missed."

> In six US hospitals, about half of adverse events in patients with limited English caused physical harm, against 30% for English speakers. Bayan is built to close that gap.

## 5. What Bayan does, 0:43–0:54
**On screen:** four columns: Interprets, Reasons, Flags, Suggests.

> It listens to both sides and interprets in 37 languages. It keeps a running case summary, flags problems, and suggests one next question at a time.

## 6. Demo, 0:54–1:39 (44 s video)
**On screen:** the recorded Nepali consultation from the live Space. Each cue is the time from when the slide opens.

| Cue | On the video | Say |
|---|---|---|
| 0:00 | Ready, then the doctor speaks | "This is a recording from our Space." |
| 0:02 | "Do you have any allergies to medicines?" in Nepali | "The doctor asks about allergies; the patient hears it in Nepali." |
| 0:10 | The patient's answer, with the English for the doctor | "He reports a penicillin reaction, and Bayan notes the allergy." |
| 0:18 | *Gyastrik* underlined; Notes panel with flags and Ask next | "He says gyastrik. The notes flag it as possible heart pain and suggest the next question." |
| 0:28 | The suggested question as a Nepali caption | "The doctor taps it, and it's asked in Nepali." |
| 0:38 | The doctor's next sentence | "Then the doctor prescribes amoxicillin." |
| 0:41 | The pearl turns vermillion: Sentence held | (wait for the video to stop, then advance) |

## 7. Held, 1:39–1:47
**On screen:** the held screen, full size.

> Bayan holds it: amoxicillin is a penicillin. That's a fixed rule, not the language model, and the doctor can override.

## 8. Care plan and doctor's note, 1:47–1:54
**On screen:** the phone care-plan page in Nepali, a patient sheet PDF in Tamil and the doctor's note PDF.

> At the end, the patient gets a care plan in his language by QR code; the doctor gets a note.

## 9. Architecture (overview), alternate slide, not timed
This is an alternate to slide 10; we will keep one of the two. If you use this one, skip slide 10 and say the slide 10 line here.

**On screen:** three parts:
- Each turn: Hear (speaker check, speech-to-text), Interpret (gpt-oss-120b), Safety gate (83 rules; vermillion, "held, not spoken"), Speak, then Spoken translation.
- Reasoning loop (each turn, in the background): Case summary, Clinical review agent (smolagents + gpt-oss-120b; tools: rules, idioms, drug check), Attention filter, Doctor's screen (one Ask next + flags), with a "next turn" arrow back to the summary.
- Wrap-up at the end: care plan, PDFs, QR.

## 10. Architecture, 1:54–2:07
**On screen:** the diagram:
- Left: the per-turn interpretation stack, with the prescription gate in vermillion.
- Centre: the reasoning loop. A case summary feeds the clinical review agent, which calls its agent tools. Candidate concerns go through an attention filter to the doctor's screen, then the loop repeats on the next turn.
- Right: wrap-up.

> Each turn is transcribed, translated and checked by the prescription gate. In the background, a smolagents agent reviews the case summary with tools, and a filter picks what the doctor sees.

## 11. Hugging Face stack, 2:07–2:14
**On screen:** two Space cards (Bayan AI on CPU upgrade, Bayan Voice Worker on an NVIDIA L4), the model boxes, and gpt-oss-120b through Inference Providers.

> It runs on Hugging Face: an app Space, a voice Space on an L4, and gpt-oss-120b via Inference Providers.

## 12. Simulation results, 2:14–2:27
**On screen:** two groups:
- **Safety rules** (38 consultations, 14 languages): 99% of 727 checks, 0 of 44 false-alarm traps, 100% of 477 PDF checks.
- **Clinical review** (16 consultations, 9 languages): 8 of 12 expected concerns flagged, 0 false caution alerts on 6 quiet visits, 30 of 30 rule checks still passing with 0 of 22 traps.

A line underneath gives the timings and cost: 0.9 s per turn, an agent card about 7 s after the turn, about $0.014 of LLM per consultation.

> In simulation, the rules passed 99% of checks with no false alarms. The clinical review flagged 8 of 12 planted problems, with no false cautions on quiet visits. Results vary between runs.

## 13. First customers in Qatar, 2:27–2:31
**On screen:** 1.46 M, 1.56 M and 5.17 M visits, and the pricing to test.

> First customers: QRCS workers' health centres, then HMC and PHCC.

## 14. Deployment and cost, 2:31–2:42
**On screen:** the three deployment tiers and a phone interpreter, with the cost-per-consultation ranges on a log scale.

> On Hugging Face it's 9 to 28 cents a consultation; on a hospital's own server, about 16. A phone interpreter costs 11 to 16 dollars.

## 15. Comparison, 2:42–2:49
**On screen:** the comparison table.

> Other tools translate or take notes; none we found reviews the consultation as it happens.

## 16. Next steps, 2:49–3:00
**On screen:** the pearl, the three next steps, the team and the Space URL.

> It isn't a certified interpreter yet. Next: a pilot clinic, clinician review of our rules, and native-speaker testing. Thank you.

---

## Numbers on stage and where they come from

| Said | Source |
|---|---|
| 65% / 71% of HMC ambulance staff | Farhat et al., *Qatar Med J* 2025, n = 312 (research.md [16]) |
| Sidra in-person interpreters: 9 languages, no Nepali, Malayalam, Bengali or Tagalog | Sidra Medicine website, 2026 [10] |
| Adverse events, limited English vs English-speaking patients: physical harm 49.1% vs 29.5% (shown 49% and 30%, 1.7×); moderate harm to death 46.8% vs 24.4% (47% and 24%, 1.9×); caused by communication errors 52.4% vs 35.9% (52% and 36%, 1.5×) | Divi C, et al. *Int J Qual Health Care* 2007;19(2):60–67, https://doi.org/10.1093/intqhc/mzl069 (research.md [19]). Rows 1–3 of `docs/pitch/data/lep_adverse_events.csv`. Six US Joint Commission hospitals, voluntarily reported events, pilot study. Say "adverse events", not "twice as many events". The year is not shown on the slide |
| *Gyastrik* ("gastric") can hide cardiac pain; Anurag is an illustrative persona | `data/idiom_lexicon.json` entry npi-005; in Nepal only 23.8% of STEMI patients thought their pain was cardiac (Prajapati, *JNHRC* 2022 [36]) |
| Held in about 3 ms, no LLM | `bayan/brain/copilot.py` prescription gate; docs/11 §2 |
| 83 rules, 98 idioms | Counted in `data/safety_rules.json` (83) and `data/idiom_lexicon.json` (98 entries; the 38-scenario simulation ran on the earlier 59-entry lexicon). Older docs say 81 rules |
| 37 patient languages | `bayan/ui.py`: 5 start chips plus 32 in "More…" (Filipino, Tamil, Swahili, then the 29 in `bayan/langs.py`) |
| 99% of 727, 0/44 traps, 477/477 PDF checks, 3 of 16 holds missed, $0.011 median, 0.9 s per turn | `reports/sim/gptoss120b-full/summary.md` (text turns, no audio) |
| Clinical review: 8 of 12 expected concerns, 0 caution alerts on 6 quiet visits, 30/30 clinical checks, 0/22 traps, agent card median 7.0 s, $0.0143 median per consultation | `reports/sim/coherence-r2/summary.md`: one full run of 16 scenarios in 9 languages (7 coherence, 6 quiet, 3 regression). Smaller reruns caught 4 of 7 (`coherence-r3`) and 2 of 5 (`coherence-r4`), so results vary between runs |
| Online $0.09–0.28, clinic box $0.13–0.51, hospital $0.16–1.65 per consultation; phone interpreter $11.40–15.75 | research.md §6.3, `data/cost_per_consultation.csv`, `data/cost_per_clinic_month.csv`. Model assumptions: 1,200 consultations per clinic-month; L4 Space at $0.80/h for 12 h a day; CPU Space at $0.03/h; LLM $0.025 per consultation from the token model; 15 interpreter-minutes per visit |
| Clinic box $14.6k (QAR 53k), hospital server $48k (QAR 175k) | research.md §6.1, `data/cost_model.json`: street prices L4 ≈ $2,800, L40S ≈ $8,500, H100 PCIe ≈ $27,500, plus a $9–12k server; 36-month amortisation, support at 15% of capex a year, Qatar business electricity QAR 0.13/kWh, PUE 1.5. Sharing across clinics not load-tested; offline not demonstrated end to end |
| gpt-oss-120b fits one 80 GB GPU (MXFP4); gpt-oss-20b fits in 16 GB | openai/gpt-oss-120b model card [68] |
| QRCS 1.46 M visits (2025); HMC 974,268 adult + 583,864 paediatric ED visits (2025); PHCC 5.17 M visits (2024) | Qatar Tribune 2026 [14]; Gulf Times 2026 [11]; The Peninsula 2025 [13] |

---

## Q&A cheat sheet (about 30 seconds per answer)

**1. How accurate is the translation in Nepali or Malayalam?**
We haven't measured it per language with native speakers yet, and we say so. Published studies show machine translation keeping 55–94% of the meaning depending on the language. One study found clinically significant LLM errors in Haitian Creole 33% of the time, against 8% for professionals. So we don't trust the translation on its own. The doctor sees what will be said. The patient can tap "Say it again" or "Slower" in their own language. The safety rules check the facts we pull out of the conversation, not the wording. Next step: a native-speaker audit for each language.

**2. Why not just Google Translate, or an end-to-end speech model?**
Translators move words; none checks a sentence against the patient's allergies or doses before it is spoken. Opalite's Guardian checks translation fidelity, not clinical content. As for end-to-end speech: no open model produces Nepali or Malayalam speech. We also need the text in the middle, because that text is what the rules check, the audit trail records and the PDFs print.

**3. Won't the alerts annoy doctors?**
Our suite included 44 deliberate traps, such as a sulfa allergy with furosemide or a mild penicillin rash with ceftriaxone. None of them tripped. Only a critical rule holds a sentence. Everything else is a quiet card in the Notes panel. "Speak it anyway" is always available and is logged. In a pilot we would track alert precision, with a target of at least 70%.

**4. What did it miss?**
Three of 16 expected holds:
- Augmentin given by brand name: the brand alias was missing.
- An allergy described only as "my body swelled" from "that red amoxi capsule", followed by cephalexin.
- Tramadol four times a day plus extra at night, where the daily total was not summed.

We also found two known gaps: an allergy to the same non-class drug, and paracetamol added up across brands. Each fix is a rule or an alias, which is deterministic, testable and cheap.

The clinical review caught 8 of 12 planted concerns in its full run (`coherence-r2`). The four it missed:
- a prescription with no drug name or dose;
- a patient confused about where to use a nasal spray;
- a blood pressure called fine without being taken;
- hopelessness mentioned in passing.

In the same consultations it did flag a diagnosis that didn't fit and a temperature claimed but never measured.

On two of the six quiet visits it showed more cards than its target of one. Smaller reruns caught 4 of 7 and 2 of 5, so the rate varies between runs.

**5. What does the AI decide, and why use an agent?**
gpt-oss-120b has four jobs:
- It translates each turn and, in the same call, updates the case summary: complaint, history, working diagnosis, plan, the patient's understanding and mood.
- After each substantive turn, a smolagents clinical review agent reads that summary and runs five checks: safety, history, plan coherence, communication and consistency.
- The agent can call tools: the 83 safety rules, the 98-entry idiom lexicon, a drug check and a case lookup.
- It also writes the note and the care plan at the end.

Every candidate concern must quote the transcript. An attention filter scores each one by severity, confidence and novelty, shows one "Ask next" at a time, and merges or expires older cards.

The agent cannot hold a sentence; only the deterministic prescription gate can.

**6. Privacy and data residency?**
- Audio is deleted right after transcription, and transcripts stay in memory.
- Output files are purged after 24 hours, and the care-plan page is not cached or indexed.
- The Space is behind an access code.

Qatar's data protection law (Law 13 of 2016) treats health data as special. Every model we use has open weights, so the whole stack can run on an HMC or PHCC server. We have not yet run it offline end to end.

**7. How fast is it, what does it cost, and does it scale?**
- Speed: translation and the gate take 0.9 s a turn. First audio comes in about 1–3 s, and cards follow in the background in about 6 s.
- Cost: the LLM cost a measured $0.011 per consultation. The GPU is the main cost: $0.28 a consultation with one L4 per clinic, or about $0.09 if four clinics share one. Sharing is not load-tested yet, since the worker runs one GPU job at a time today.

**8. Who pays?**
- First buyers: QRCS workers' health centres (1.46 M visits in 2025), HMC emergency departments and the industrial-area hospital, then PHCC (31 centres) and private clinics now paid through employer insurance.
- Pricing ideas, not yet validated: QAR 2–3 per consultation, or QAR 2,500–3,500 per clinic per month. That is still at least 15 times cheaper than a phone interpreter.
- On-premise option for data sovereignty: hardware at cost plus an annual licence.

**9. How much GPU do you need to self-host?**
- **Online today:** one NVIDIA L4 Space at $0.80 an hour runs all the speech models; the LLM is paid per token.
- **One clinic, on site:** two NVIDIA L4 cards, about $2,800 each. One runs the voice models (Whisper, IndicConformer, MMS, Parler-TTS). The other runs gpt-oss-20b, which fits in 16 GB. The server costs about $14.6k (QAR 53k): $0.51 a consultation for one clinic, $0.13 if four clinics share it.
- **Hospital, in-country:** one H100 80 GB (about $27.5k) runs gpt-oss-120b on a single GPU in MXFP4, the same model we use today, and one L40S (about $8.5k) runs the voice models. About $48k (QAR 175k), or $0.16 a consultation across 10 clinics.
- **Caveats:**
  - These are street prices, amortised over 36 months with 15% a year for support.
  - Sharing a box across clinics is not load-tested.
  - We have not yet run the stack offline end to end.
  - The clinic box's gpt-oss-20b needs its own quality test before we rely on it.
