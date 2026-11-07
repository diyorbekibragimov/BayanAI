# Bayan: 3-minute pitch script

Team QH-129, Qai × Hugging Face Hackathon O1, Doha.
Deck: [`deck/index.html`](deck/index.html). PDF: [`Bayan-pitch.pdf`](Bayan-pitch.pdf).

**Budget:** 365 spoken words across 14 slides. 315 are spoken over slides in 2:16, about 139 words a minute; 50 go over the 44-second demo video. The slides carry no footnotes; every source is in the table below.
Tone: plain and conversational. Say what the product does and what the numbers are; no slogans. Speak at an even pace and leave a short gap after each number.

**Deck controls:** → / Space / click = next, ← = back, `f` = fullscreen, `r` = restart the demo video, `p` = pause or play it.
Slide 5 plays `assets/demo.webm` automatically. It starts at 0:22 of the recording, plays at 1.5× and ends on the held screen 44 s later.

**Demo choice:** by default, play the recorded video. Inference credits are frozen, so a live run is not possible today. If credits come back and the venue network is solid, the same scripted consultation can run live at `/?demo=1` on the Space. Even then, keep the video one keypress away.

---

## 1. Title, 0:00–0:08
**On screen:** the Bayan wordmark at top left, "Bayan AI" with بيان beneath it, the tagline, then three items on one row with spacing between them: Team QH-129, Qai × Hugging Face Hackathon O1, Doha, 5–7 Nov 2026. The pearl is on the right.

> We're team QH-129. This is Bayan, an interpreter for doctors and patients in Qatar that also checks what's said.

## 2. Meet Anurag, 0:08–0:20
**On screen:** "Meet Anurag", "29, a Nepali construction worker in Doha", and three columns: Anurag says, The doctor hears, It could be.

> Anurag, a Nepali construction worker, says his chest is burning. He calls it gyastrik, Nepali for gastric. The doctor hears reflux, but it could be his heart.

## 3. Language barriers in Qatar, 0:20–0:33
**On screen:** 65%, 71%, 9.

> Anurag is made up; the numbers are real. 65% of HMC ambulance staff report language barriers, and 71% are comfortable letting family interpret. Sidra has no in-person Nepali, Malayalam, Bengali or Tagalog interpreters.

## 4. Adverse events and language, 0:33–0:41
**On screen:** a bar chart. Vermillion is patients with limited English; grey is English speakers.

> In one US study, about half of adverse events in patients with limited English caused physical harm, against 30% for English speakers.

## 5. Demo, 0:41–1:26 (44 s video)
**On screen:** the recorded Nepali consultation from the live Space. Each cue is the time from when the slide opens.

| Cue | On the video | Say |
|---|---|---|
| 0:00 | Ready, then the doctor speaks | "This is a recording from our Space." |
| 0:02 | "Do you have any allergies to medicines?" in Nepali | "The doctor asks about allergies, and the patient hears it in Nepali." |
| 0:10 | The patient's Nepali, with the English for the doctor | "He says he once reacted to penicillin." |
| 0:18 | *Gyastrik* underlined; idiom note; Notes panel | "He says gyastrik. Bayan notes it can be heart pain and suggests a follow-up question." |
| 0:28 | The suggested question as a Nepali caption | "The doctor asks it." |
| 0:38 | The doctor's next sentence | "Next, the doctor prescribes amoxicillin." |
| 0:41 | The pearl turns vermillion: Sentence held | (wait for the video to stop, then advance) |

## 6. Held, 1:26–1:36
**On screen:** the held screen, full size.

> Bayan holds that sentence, because amoxicillin is a penicillin. The check is a fixed rule, not the language model; it takes about 3 milliseconds. The doctor can rephrase or override.

## 7. Care plan and doctor's note, 1:36–1:44
**On screen:** the phone care-plan page in Nepali, a patient sheet PDF in Tamil and the doctor's note PDF.

> At the end, the patient gets a care plan in his language by QR code, and the doctor gets a note.

## 8. Architecture, 1:44–1:57
**On screen:** the diagram. On the left is the per-turn stack with the prescription gate in vermillion. In the middle is the background copilot stack, and on the right is the wrap-up stack.

> Each turn goes through speaker check, speech-to-text, translation, the prescription gate and speech. In the background, a smolagents copilot uses an idiom list and 83 rules to suggest questions.

## 9. Hugging Face stack, 1:57–2:06
**On screen:** two Space cards (Bayan AI on CPU upgrade, Bayan Voice Worker on an NVIDIA L4), the model boxes, and gpt-oss-120b through Inference Providers.

> It all runs on Hugging Face: the app Space, a voice Space on an L4 with eight open models, and gpt-oss-120b through Inference Providers.

## 10. Simulation results, 2:06–2:17
**On screen:** 99% of 727 checks, 0 of 44 false-alarm traps, 100% of 477 PDF checks, and the latency bars.

> On 38 scripted consultations in 14 languages, 99% of checks passed and none of the 44 false-alarm tests fired. It missed 3 of 16 holds, which we're fixing.

## 11. First customers in Qatar, 2:17–2:23
**On screen:** 1.46 M, 1.56 M, 5.17 M visits, and the pricing to test.

> First customers: QRCS workers' health centres, then HMC and PHCC.

## 12. Deployment and cost, 2:23–2:42
**On screen:** the three deployment tiers and a phone interpreter, with the cost-per-consultation ranges on a log scale.

> On Hugging Face it costs 9 to 28 cents a consultation. On a hospital's own server it's about 16 cents, and no audio leaves the building. A phone interpreter costs 11 to 16 dollars.

## 13. Comparison, 2:42–2:50
**On screen:** the comparison table.

> Other tools translate or take notes; none we found checks the medical content before it's spoken.

## 14. Next steps, 2:50–3:00
**On screen:** the pearl, the three next steps, the team and the Space URL.

> It isn't a certified interpreter yet. Next we need a pilot clinic, clinician review of our rules, and native-speaker testing. Thank you.

---

## Numbers on stage and where they come from

| Said | Source |
|---|---|
| 65% / 71% of HMC ambulance staff | Farhat et al., *Qatar Med J* 2025, n = 312 (research.md [16]) |
| Sidra in-person interpreters: 9 languages, no Nepali, Malayalam, Bengali or Tagalog | Sidra Medicine website, 2026 [10] |
| Physical harm in 49% vs 30% of adverse events | Divi et al., *Int J Qual Health Care* 2007 [19]. Voluntary reports from a pilot, so say "adverse events", not "twice as many events" |
| *Gyastrik* ("gastric") can hide cardiac pain; Anurag is an illustrative persona | `data/idiom_lexicon.json` entry npi-005; in Nepal only 23.8% of STEMI patients thought their pain was cardiac (Prajapati, *JNHRC* 2022 [36]) |
| Held in about 3 ms, no LLM | `bayan/brain/copilot.py` prescription gate; docs/11 §2 |
| 83 rules, 59 idioms | Counted in `data/safety_rules.json` (83) and `data/idiom_lexicon.json` (59). Older docs say 81 and the brief said 84, but the file has 83 |
| 37 patient languages | `bayan/ui.py`: 5 start chips plus 32 in "More…" (Filipino, Tamil, Swahili, then the 29 in `bayan/langs.py`) |
| 99% of 727, 0/44 traps, 477/477 PDF checks, 3 of 16 holds missed, $0.011 median, latencies | `reports/sim/gptoss120b-full/summary.md` (text turns, no audio) |
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

**5. What does the LLM decide, and why use agents?**
gpt-oss-120b does four jobs:
- It translates.
- It extracts facts into a fixed schema.
- It writes the note and the care plan.
- The smolagents copilot suggests up to 3 cards (ask, missed workup, observation), and each card must cite the utterance it came from.

It can never raise a critical alert or block a sentence; only the deterministic rule engine can. If the agent fails or passes its 20-second timeout, fixed fallback cards appear instead. It runs only when something new happens, usually in a single step.

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
