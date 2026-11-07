# Bayan AI: pitch research pack

> Research lead brief for the 3-minute finalist pitch (Qai × Hugging Face hackathon, team QH-129). Compiled 2026-11-07.
> Every number has a numbered source in §9 with its year. **Confidence:** *high* = primary source read (journal abstract, official page, live API); *medium* = reputable secondary (news citing the official figure, vendor page); *low* = estimate, aggregator or conflicting sources. Chart data is in [`data/`](data/).
> **Scope:** this pack checks and updates the earlier docs (01, 07, 09, 11, README). §0 lists where they are now out of date.

---

## 0. Corrections to the earlier docs (fix before going on stage)

| Item | Earlier docs | Verified now | Action |
|---|---|---|---|
| Safety rules | 81 | **83** in `data/safety_rules.json` | Say "83 cited rules" |
| Patient languages | 6 Tier-1 (README); brief says 5 + 31 | **37 in code**: 8 start chips (ne, hi, ur, bn, ml, tl, ta, sw) + 29 in "More" (`bayan/langs.py`) | Say "37 patient languages"; quality varies (see §8) |
| LLM cost per consultation | $0.019 measured (9-turn golden path, excl. translation, doc 07); brief says $0.005–0.008 | Token model (§6.1): **~$0.025** on today's routing (Cerebras + Groq), **$0.004–0.006** on cheaper gpt-oss-120b providers (DeepInfra, Novita) | Re-measure with `smoke_e2e.py` incl. translation; quote "under 3 cents" unless re-measured |
| Qatar population | 3.21 M (Dec 2025) | 3,214,609 (Dec 2025) [1]; NPC reported **3,370,611 (Mar 2026)** [2], an unexplained +5% in 3 months | Say "about 3.2 million" |
| HMC ED volume | 672,701 (2024) | 2025: **974,268 adult ED + 583,864 paediatric ED** visits [11] | Use 2025 numbers |
| Farhat 2025 | "37% sufficient" | **36%** sufficient; 65% = 24% "very frequently" + 41% "occasionally" [16] | Fix the decimals |
| Lindholm 2012 | "+1.49 days" | Regression +1.49 d (no interpreter vs both); abstract states 0.75–1.47 d [23] | Say "up to 1.5 extra days" |
| Sidra | "66 languages" | Phone/video line 66, but **face-to-face only 9** (Arabic, French, Russian, Chinese, Turkish, Spanish, Korean, Urdu, Hindi) [10] | Strong fact: no in-person Nepali, Malayalam, Bengali or Tagalog |

---

## 1. Key numbers

| # | Claim | Number | Source | Year | Conf. |
|---|---|---|---|---|---|
| 1 | Qatar population | **3,214,609** (Dec 2025); 3,370,611 (Mar 2026) | NPC via [1], [2] | 2026 | high / low |
| 2 | Population that is male | **70.5%** (2,215,203 of 3,143,491, mid-2024) | PSA/NPC via GLMM [3] | 2025 | high |
| 3 | Employed people who are non-Qatari | **94.3%** (2,112,589 of 2,239,938) | LFS 2024 via GLMM [4] | 2025 | medium |
| 4 | Residents who are not Qatari | **≈ 89%** (no official breakdown published) | Ahmad & Hillman [5] | 2021 | low |
| 5 | Largest communities (est.) | India ~0.7–0.84 M, Nepal ~0.4 M, Bangladesh ~0.4 M, Egypt ~0.3 M, Philippines ~0.24 M, Pakistan ~0.15 M, Sri Lanka ~0.14 M | Embassy-based [6]; MEA via [7] | 2018–25 | low |
| 6 | Languages of Qatar's Patients' Bill of Rights | **8**: Arabic, English, Bengali, Filipino, Hindi, Malayalam, Nepali, Urdu | MOPH [8] | 2026 | high |
| 7 | Sidra face-to-face interpreter languages | **9**, none of them Nepali, Malayalam, Bengali or Tagalog (66 by phone/video) | Sidra [10] | 2026 | high |
| 8 | HMC activity 2025 | 974,268 adult ED, 583,864 paediatric ED, >3 M outpatient visits | HMC via Gulf Times [11] | 2026 | medium |
| 9 | PHCC | **31** health centres; >5.17 M visits (2024) | [12], [13] | 2024–25 | high / medium |
| 10 | QRCS workers' health centres (4, with MOPH) | **1,460,696** visits in 2025 (≈4,000/day) | Qatar Tribune [14] | 2026 | medium |
| 11 | HMC ambulance staff who face language-barrier difficulties | **65%** (24% very often, 41% occasionally); only **36%** get sufficient information; **71%** comfortable using family as interpreters (n = 312) | Farhat et al. [16] | 2025 | high |
| 12 | Nepali workers in Qatar: cardiovascular share of deaths | **22% cool season vs 58% hot season** (global benchmark for age 25–35: 15%); 571 CVD deaths 2009–17, ~200 preventable with heat protection | Pradhan et al. [17] | 2019 | high |
| 13 | Occupational injuries, Qatar 2020 | 50 deaths, 506 severe, 37,600 mild/moderate injuries (ILO: likely undercount) | ILO [18] | 2021 | high |
| 14 | LEP adverse events causing physical harm | **49.1% vs 29.5%** (English speakers) | Divi et al. (Joint Commission) [19] | 2007 | high |
| 15 | LEP harmful events, moderate harm to death | **46.8% vs 24.4%** | [19] | 2007 | high |
| 16 | LEP adverse events caused by communication errors | **52.4% vs 35.9%** | [19] | 2007 | high |
| 17 | Interpreter errors per encounter | **31**; 63% potentially clinical; ad hoc 77% vs hospital 53%; examples include *omitting drug-allergy questions* and *amoxicillin "in both ears"* | Flores et al. [20] | 2003 | high |
| 18 | Errors of potential consequence | professional 12%, ad hoc 22%, none 20%; ≥100 h trained interpreters **2%** | Flores et al. [21] | 2012 | high |
| 19 | 30-day readmission, LEP patients | **24.3%** with no interpreter vs **14.9%** with one at admission and discharge | Lindholm et al. [23] | 2012 | high |
| 20 | Google Translate meaning retained (ED instructions) | Spanish 94%, Tagalog 90%, Korean 82.5%, Chinese 81.7%, Farsi 67.5%, Armenian 55% | Taira et al. [26] | 2021 | high |
| 21 | LLM/MT clinically significant errors, low-resource language | Haitian Creole: ChatGPT 33.3%, Google 23.3%, professional 8.3% | Brewster et al. [27] | 2024 | high |
| 22 | Cost of a preventable adverse drug event | **$4,685** (+4.6 days), 1990s USD; an ADE nearly doubles risk of death (×1.88) | Bates [30]; Classen [31] | 1997 | high |
| 23 | Malpractice claims involving communication failure | 30% of 23,658 claims; 1,744 deaths; $1.7 B | CRICO 2015 via [32] | 2016 | medium |
| 24 | Reported vs true penicillin allergy | ~10% report it, <1% truly allergic | CDC [33] | 2025 | high |
| 25 | Max adult paracetamol dose | **4 g / 24 h** (so 8 g/day is 2×) | NHS [34] | 2026 | high |
| 26 | Human interpreter prices | Phone $0.75–1.10/min (contracts); video $1.95/min; pay-as-you-go $3.95 (audio) / $4.95 (video) per min | [49]–[52] | 2025–26 | medium |
| 27 | Medical interpreter salary, Doha | QAR 6,000–6,500/month package | job postings [53] | 2026 | low |
| 28 | gpt-oss-120b price on HF Inference Providers | Cerebras $0.35/$0.75, Groq $0.15/$0.75, DeepInfra $0.037/$0.17 per M tokens | HF router [47] | 2026-11-07 | high |
| 29 | HF L4 GPU Space | **$0.80/h** | HF docs [48] | 2026 | high |

---

## 2. Problem story (composites built from the evidence; say "illustrative" on stage)

**Case 1. Ram, 29, Nepali scaffolder, QRCS Al Hemailah, 9 p.m. in August.** After a shift in the heat his chest burns "like *gyastrik*" (gastric). His roommate interprets "stomach problem" and leaves out that a penicillin injection once made him swell. The doctor prescribes amoxicillin and sends him home. *Evidence:* omissions are the most common interpreter error (52%) and Flores recorded omitted allergy questions [20]; in Nepal only 23.8% of STEMI patients thought their pain was cardiac [36]; CVD's share of Nepali worker deaths in Qatar nearly triples in the hot season [17]. *Bayan:* the idiom card flags that *gyastrik* can mask cardiac pain, the chest-pain workup card asks for ECG and troponin (ECG within 10 min, AHA/ACC [37]), and the amoxicillin sentence is **held before it is spoken**.

**Case 2. Maricel, 34, Filipino domestic worker, PHCC centre.** Her employer drove her in and "helps with English". She does not mention a missed period or that she is not allowed to rest. *Evidence:* ad hoc interpreters make more consequential errors (77% vs 53%; 22% vs 12%) [20][21]; the Bill of Rights promises information "easily understood" and privacy [8]. *Bayan:* she speaks Filipino directly, and the care plan goes to *her* phone by QR code.

**Case 3. Ammini, 68, Malayalam-only visitor, private clinic.** She takes metformin and two BP tablets and describes the doses differently each time. In the rush, the instruction becomes "two 1 g paracetamol tablets, four times a day": 8 g/day. *Evidence:* LEP adverse events are more often harmful (49% vs 30%) and more often due to communication (52% vs 36%) [19]; the safe ceiling is 4 g/day [34]. *Bayan:* a dose rule holds the sentence, and she leaves with a Malayalam care sheet in her own script.

---

## 3. Evidence on harm (what to say, what not to say)

1. **Language barriers make adverse events worse, not just more frequent.** Joint Commission pilot (6 hospitals): physical harm 49.1% vs 29.5%; moderate-to-death 46.8% vs 24.4%; communication-caused 52.4% vs 35.9% [19]. *Caveat:* voluntarily reported events, pilot. Cohen 2005 found no overall increase (OR 1.36, CI 0.73–2.55) but a doubled risk for Spanish speakers (OR 2.26) [24]. Do not say "LEP patients have twice as many adverse events".
2. **Who interprets matters.** Ad hoc interpreters: 77% of errors potentially consequential vs 53% [20]; 22% vs 12% professional, 2% for ≥100 h training [21]. Professional interpreters bring LEP care close to that of patients without a language barrier (systematic review, 28 studies) [22].
3. **Outcomes and cost.** No interpreter: 30-day readmission 24.3% vs 14.9%, up to ~1.5 extra days [23]. A preventable ADE costs $4,685 and 4.6 days (1990s USD) [30]; an ADE raises death risk 1.88× [31]. Communication failure features in 30% of US malpractice claims (1,744 deaths, $1.7 B) [32].
4. **Allergies are fragile even without a language barrier.** 6.7% of patient-reported reactions were missing from the EHR and 12.4% recorded wrongly (n = 270) [35]. A penicillin label is common (~10%) [33], so asking well and checking every prescription against it is routine safety work.
5. **Machine translation is good in big languages, unreliable in small ones.** GPT-4o and Google Translate were non-inferior to professional interpreters for Spanish, Portuguese and Chinese discharge text [28], and frontier LLMs preserved meaning well even in Tagalog and Haitian Creole by embedding similarity [29]. But human raters found 33% clinically significant errors for ChatGPT in Haitian Creole vs 8% professional [27], and Google Translate ranged from 94% to 55% by language [26]. **Implication:** translation quality alone is not a safety system; Bayan's value is the check layer on top, and native-speaker validation per language.
6. **Qatar specifically.** Hamad General outpatients relied on incidental interpreters and fragments of languages; Hindi/Urdu speakers were most exposed [15]. 65% of ambulance staff report barriers; the authors recommend mobile translation and AI tools [16].

**Never claim:** that missed diagnosis kills workers in Qatar (Pradhan attributes preventable deaths to missing heat protection [17]); that Bayan reduces adverse events (unmeasured); the Guardian's 6,500 deaths figure without "disputed by Qatar's government".

---

## 4. Pitch best practices

**Rules (with source)**
- Open with the product, not the backstory: "start with the name of your company and what it does" [40]; judges lose a third of the slot when context comes first [45]. Hook ≤ 20 s, then "Bayan is…".
- One idea per slide, ≤ 7 words, big type, key text at top [39]. One throughline the audience can repeat in a sentence [41].
- 3–4 points the room can remember, restated at the end ("end with a bang, not a whimper") [39].
- Contrast "what is" with "what could be" (Duarte's sparkline) [42]: roommate interpreting → held sentence.
- Charts: maximise data-ink, erase gridlines and legends, label the bars directly [43]. One number per chart; no cumulative graphs [39].
- Restraint: finish slightly under time (*hara hachi bu*) [44]. Speak "unnaturally slowly" and pause after key numbers [39].
- Live demo: YC warns live demos often fail at demo day [39], but hackathon judges reward a working demo over slides [45] and "Demo" is a judging criterion. **Do it live in replay mode, with a recorded fallback one click away.**
- Name a weakness before you are asked; it raises scores [45] (see §8).
- Be concrete and bottom-up on the market: clinics × consultations × price [40].
- Rehearse with a stopwatch in front of honest critics; record yourself [39].

**Word budget.** ~150 wpm is the conversational benchmark (NCVS, via [46]); presentations run 130–150. 3:00 at 140 wpm ≈ **420 words**, minus ~25 s of demo audio ⇒ **~360 spoken words**.

**Recommended 3-minute timing**

| Time | Section | Words | Judging criterion | Slide (≤ 7 words) |
|---|---|---|---|---|
| 0:00–0:20 | Hook (Ram, held sentence) | 45 | Impact | "My chest burns like gyastrik." |
| 0:20–0:40 | What Bayan is + Qatar problem | 50 | Impact | "9 in 10 residents aren't Qatari" / Bill of Rights in 8 languages |
| 0:40–1:50 | Live demo: idiom card → allergy hold → workup → Nepali PDF via QR | 90 + audio | Demo, technical execution | (tablet mirror) |
| 1:50–2:15 | How it works on HF (open models, 83 rules, smolagents) | 60 | Use of HF, technical | Pipeline diagram, model names |
| 2:15–2:35 | Efficiency + cost vs interpreter | 50 | Efficiency | "Cents vs $11–74 per visit" bar chart |
| 2:35–2:50 | Impact & business (QRCS 1.46 M visits; self-hostable) | 40 | Impact | "1.46 M worker visits / year" |
| 2:50–3:00 | Ask + tagline | 25 | — | QR to Space |

---

## 5. Competitive analysis

| Product | Type | Nepali / Malayalam / Bengali | Safety layer (allergy, dose, workup) | Price | Offline / on-prem | Data residency |
|---|---|---|---|---|---|---|
| **Bayan AI** | AI interpreter + clinical copilot | **Yes**, 37 languages in code; native-script PDFs | **Yes**: 83 rules, 59 idioms, holds sentence before speaking | LLM ≈ $0.004–0.03/visit + L4 $0.80/h | **Self-hostable** (all open weights); offline not yet demonstrated | Where you deploy it |
| HMC / Sidra staff interpreters | Human | Sidra in-person: **no** (9 languages); phone line 66 [10] | Human judgement only | Free to patient; staff ≈ QAR 6–6.5k/month [53] | n/a | In-country |
| LanguageLine | Human, phone/video | Yes (240+) | None | $0.99–1.95/min contract; $3.95–4.95 PAYG [49]–[51] | No | US vendor |
| CyraCom / Propio | Human, phone/video | Yes (300+) | None | $0.75–0.81/min [52] | No | US vendor |
| Google Translate | Consumer MT | Text yes; Nepali/Malayalam conversation mode unverified | None | Free | Partial (offline packs) | Consumer cloud |
| Microsoft Translator | Consumer/enterprise MT | Nepali text yes; speech unverified | None | Free / per-use API | Limited | Azure regions |
| Pocketalk | Device MT | 92+ claimed | None | Device + subscription | Limited | Vendor cloud |
| Care to Translate | Verified phrases + live AI | 130+ live, 52 verified (list unchecked) | Verified phrase library; no clinical checks | Not public | "Offline mode" (phrases) | Claims no data stored |
| No Barrier (US) | AI medical interpreter | 40+ live (press) | None described; human escalation | Fixed fee | No | US VPC |
| Opalite Health (YC W26) | AI medical interpreter | 150+ claimed | **Translation QA** ("Guardian": meaning, numbers, hallucination); no allergy/dose rules described | Flat, not public | Not stated | US |
| Mabel (Sweden) | AI interpreter | Not listed | Translation verification only | Not public | **On-prem Docker/K8s**, on-device | EU/US/customer DC |
| Abridge; Dragon Copilot (DAX) | Ambient scribes | Record some languages, English note; DAX "doesn't translate conversations" | Documentation only | ~$150–600 / ~$600 per clinician-month (third-party est.) | No | Vendor cloud |
| Sahl AI, Augnito, Commure (GCC) | Arabic-English scribes | No | Documentation only | Not public | Varies | GCC |

Sources: vendor pages and press [54]–[62]; scribe prices are third-party estimates (low confidence).

**Takeaway.**
1. Scribes save doctor time but assume a shared language; MT tools and AI interpreters move words; human lines are accurate but cost $11–74 per visit and are not in the room at 2 a.m. in Mesaimeer.
2. We found **no product that checks the clinical content of a sentence (allergy, dose, missed workup) and holds it before it reaches the patient**; the closest, Opalite's Guardian, checks translation fidelity, not clinical safety.
3. Bayan's real edge is that combination plus open weights you can run in-country; its real weakness is unvalidated translation quality in low-resource languages and no clinical or regulatory sign-off yet.

---

## 6. Business and cost model

### 6.1 Assumptions (all editable in `data/cost_model.json`)

| Parameter | Value | Basis |
|---|---|---|
| Consultations per clinic | 40/day × 30 days = **1,200/month** | brief |
| Clinic hours (GPU awake) | 12 h/day | assumption (QRCS centres run long hours) |
| Tokens per consultation | **52,200 in / 12,250 out** | assumption: 24 translation calls (700/150), 8 extractions (1,800/350), 3 agent runs (3,500/450), 3 wrap-up calls (3,500/1,500) |
| LLM prices | router listing 2026-11-07 [47] | see `data/llm_price_sheet.csv` |
| HF L4 Space / CPU-upgrade Space | $0.80/h / $0.03/h | [48] |
| Clinics sharing one L4 | 4 | **unverified** (worker runs one GPU job at a time today) |
| Hardware | L4 ≈ $2,800 [63]; L40S ≈ $8,500 ($7.6–11.9k) [64]; H100 PCIe ≈ $27,500 ($25–38k) [64]; server chassis $9–12k (assumption) | street prices, low confidence |
| Amortisation / support | 36 months / 15% of capex per year | assumption |
| Power | QAR 0.13/kWh business [65], PUE 1.5 | low confidence |
| Interpreter minutes per visit | 15 | assumption (interpreted visits run longer) |
| USD/QAR | 3.64 (fixed peg) | QCB |

**Formulas**
- `LLM = Σ_jobs (calls × in × p_in + calls × out × p_out) / 1e6`
- `Online clinic-month = 0.80 × 12 × 30 / clinics_per_L4 + LLM × 1,200 + 0.03 × 720 / clinics_per_L4`
- `Self-hosted month = capex / 36 + kW × 1.5 × 720 × 0.13 / 3.64 + capex × 0.15 / 12`
- `Human per visit = price_per_min × 15`; `per consultation = month / consultations`

### 6.2 LLM cost per consultation

| Routing | USD | QAR |
|---|---|---|
| gpt-oss-120b, today's code (Cerebras; Groq for extraction) | **0.025** | 0.09 |
| gpt-oss-120b, all Cerebras | 0.028 | 0.10 |
| gpt-oss-120b, Novita | 0.006 | 0.02 |
| gpt-oss-120b, DeepInfra | **0.004** | 0.015 |

The brief's $0.005–0.008 matches the cheap-provider rows, not today's routing. Either way the LLM is <10% of the online cost; the GPU dominates.

### 6.3 Per consultation and per clinic-month (1,200 consultations)

| Option | USD / consultation | USD / clinic-month | QAR / clinic-month |
|---|---|---|---|
| **Bayan online, dedicated L4 (12 h/day)** | **0.28** | 339 | 1,234 |
| Bayan online, L4 shared by 4 clinics | 0.09 | 107 | 389 |
| Self-hosted S1: 2× L4 (voice + gpt-oss-20b), 1 clinic; capex $14.6k (QAR 53k) | 0.51 | 607 | 2,211 |
| Self-hosted S1, 4 clinics | 0.13 | — | — |
| Self-hosted S2: H100 80GB (gpt-oss-120b) + L40S (voice), 1 site; capex $48k (QAR 175k) | 1.65 (1 clinic) / **0.16** (10 clinics) | 1,980 per box | 7,206 per box |
| Phone interpreter, CyraCom/Propio ~$0.76/min | 11.40 | 13,680 | 49,795 |
| Phone interpreter, LanguageLine contract ~$1.05/min | 15.75 | 18,900 | 68,796 |
| Video interpreter, LanguageLine contract $1.95/min | 29.25 | — | — |
| Pay-as-you-go phone / video ($3.95 / $4.95) | 59 / 74 | — | — |
| In-house interpreters, 6 languages × 12 h × 7 days (12.6 FTE × QAR 6,250) | 18.03 | 21,635 | 78,750 |

**Reading it:** even the most expensive Bayan setup for one clinic (S2 at $1.65) is ~7× cheaper than the cheapest phone interpreter ($11.40). Online on HF it is **~40–130× cheaper** ($0.09–0.28 vs $11.40). One prevented ADE ($4,685 in 1990s dollars [30]) pays for **~14 months** of a dedicated online clinic deployment. Bayan does not replace interpreters for consent or bad news (§8); the realistic case is covering the visits that today get a roommate or nothing.

Chart files: `data/cost_per_consultation.csv`, `data/cost_per_clinic_month.csv`.

### 6.4 Target buyers in Qatar

| Buyer | Why | Scale |
|---|---|---|
| **QRCS Workers' Health Centres** (4, with MOPH) | Single male workers; urgent care; no published interpreter provision | 1.46 M visits/yr [14] |
| **HMC**: Hazm Mebaireek General Hospital (Industrial Area), EDs, ambulance | Interpreters "on request", not ambient; ambulance staff ask for AI tools [16] | 974k adult ED + 584k paediatric ED visits [11]; 210k ambulance cases |
| **PHCC** | Residents' primary care; Bill of Rights languages | 31 centres [12]; >5.17 M visits (2024) [13] |
| Private hospitals & clinics serving workers (e.g. Aster, Naseem, Al Ahli) | Mandatory employer-paid insurance (Law 22/2021) moves workers into private care | not quantified |
| Employer/contractor clinics (construction, LNG), Ministry of Labour programmes | Heat-season occupational health; annual checks (Decision 17/2021) | not quantified |
| Sidra Medicine | Already has a 66-language line; secondary buyer for the safety layer | — |

**Pricing hypotheses (to test, not validated):** (a) SaaS per clinic-month, online: QAR 2,500–3,500 (≈$690–960) for up to 1,200 consultations (2–3× cost on a dedicated L4); (b) per consultation: QAR 2–3 (≈$0.55–0.80), still ~15–20× below a phone interpreter; (c) on-prem: hardware at cost + annual licence per site, for HMC/PHCC data-sovereignty requirements.

### 6.5 Data sovereignty

- Qatar's **Law No. 13 of 2016** (Personal Data Privacy Protection) treats health data as "personal data of a special nature"; processing needs regulator permission and a DPIA under the regulator's guidance [66]. Vendor commentary says MOPH expects patient data to stay in Qatar with limited cross-border exceptions [67]; **we could not find the primary MOPH text**, so say "designed for in-country hosting", not "required by law".
- Bayan's argument: every model is open-weight (gpt-oss, Whisper, IndicConformer, Parler-TTS, Supertonic), so the whole stack can run on an HMC/PHCC server (S1/S2) with no audio leaving the building. gpt-oss-120b fits one 80 GB GPU (MXFP4); gpt-oss-20b runs in 16 GB [68]. **Not yet demonstrated offline end to end.**

---

## 7. Novelty

1. **A safety gate in the speech path.** The prescription gate checks each doctor sentence against the structured patient state (allergies, doses) in ~3 ms and **holds it before it is spoken** to the patient. Commercial AI interpreters check translation fidelity (Opalite Guardian [58], Mabel verification [59]); scribes document after the fact. We found no published system or paper that gates interpreted speech on clinical content.
2. **A culturally aware idiom lexicon for migrant languages** (59 entries, e.g. Nepali *gyastrik* → "can mask cardiac pain"). Idioms of distress are well described in medical anthropology (Nepali *man*/heart-mind [38]) and interpreters handle them inconsistently [69], but they are not part of MT or AI-interpreter products.
3. **Low-resource languages with native-script, take-home outputs.** Doctor note PDF + patient care plan in the patient's script via QR, aimed at the 8 Bill of Rights languages and more. Brewster [27] and Taira [26] show this is exactly where generic MT is weakest, so outputs are doctor-approved and rule-checked.
4. **Open, self-hostable, cheap.** Built on open models from the HF Hub and HF Inference Providers; deterministic rules cost $0; an agent runs only when something new appears.

Related work to cite if asked: LLM vs professional translation of discharge instructions [27][28][29]; MT error taxonomy for low-resourced healthcare languages (EMNLP 2025, MBZUAI) [70]; ASR error and patient safety [71].

---

## 8. Risks and honest limitations

| Risk | Status | Mitigation / what to say |
|---|---|---|
| Machine translation is not certified interpreting | True | "Bayan fills the gap where no interpreter is in the room; for consent and bad news it tells the doctor to call one." |
| Accuracy varies by language | Unmeasured per language; literature shows 55–94% for MT [26] | Native-speaker audits per language; pilot KPI. Many of the 37 languages have no native check yet. |
| Clinical content not reviewed | 83 rules and 59 idioms cited but **not clinician-reviewed** | Clinical advisory review before any pilot |
| Rule false positives / alert fatigue | Unmeasured | Track alert precision (target ≥ 70%) |
| ASR errors (accents, noise) | Real risk [71] | Show the transcript; patient-side "say again / slower" buttons |
| Cost figures | One live scenario measured; token model is an estimate; L4 concurrency unverified | Re-measure before quoting; say "under 3 cents of LLM" |
| Regulation | No MOPH clinical-AI rule found; PDPPL applies | Research-ethics approval, DPIA, in-country hosting |
| Evidence base is mostly US, Spanish, paediatric | True | Say so; Qatar evidence is qualitative [15] and EMS survey [16] |
| Competitors move fast (US AI interpreters raising money) | True | Edge is the clinical gate + Gulf languages + open self-hosting |

---

## 9. Sources

1. NPC, Dec 2025 population, via Qatar Tribune (Jan 2026). https://www.qatar-tribune.com/article/212590/latest-news/qatars-population-surpasses-321-million-by-end-of-2025
2. NPC, Mar 2026 population, via Marhaba (2026). https://marhaba.qa/?p=346856
3. GLMM, Qatar population by sex 1986–2024 (PSA/NPC). https://gulfmigration.grc.net/?p=11457
4. GLMM, employed population by nationality 2006–2024 (LFS 2024). https://gulfmigration.grc.net/?p=11488
5. Ahmad R, Hillman S. *Multilingua* 40(3), 2021. https://doi.org/10.1515/multi-2020-0119
6. Embassy-based nationality estimates (2015–2019), archived. https://web.archive.org/web/20181122162153/http://priyadsouza.com/population-of-qatar-by-nationality-in-2017/
7. Indians in Qatar (citing MEA), 2026. https://www.findeasy.in/indian-population-in-qatar/
8. MOPH Patients' Bill of Rights, language editions. https://dhp.moph.gov.qa/en/Pages/FTPDownloads.aspx
9. HMC Interpreter Services. https://hamad.qa/EN/Patient-Information/Interpreter-Services/
10. Sidra Medicine, medical interpreters. https://www.sidra.org/patients-visitors/your-visit/during-your-visit-2/medical-interpreters/
11. Gulf Times, "HMC reports major healthcare advances in 2025" (15 May 2026). https://www.gulf-times.com/article/725532/qatar/hmc-reports-major-healthcare-advances-in-2025
12. The Peninsula, PHCC 31 centres (14 Aug 2024). https://thepeninsulaqatar.com/article/14/08/2024/phcc-logs-219-million-patients-in-six-months
13. The Peninsula, PHCC 5.17 M visits in 2024 (31 Aug 2025). https://thepeninsulaqatar.com/article/31/08/2025/qatar-strengthens-healthcare-system-with-prevention-at-core
14. Qatar Tribune, QRCS workers' health centres (2026). https://www.qatar-tribune.com/article/247543/nation/qrcs-medical-affairs-division-getsaccreditation-canada-diamond-tag
15. Abdelrahim H, et al. *J Health Commun* 2017;22(4):355–363. https://doi.org/10.1080/10810730.2017.1296507
16. Farhat H, et al. *Qatar Med J* 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC12127531/
17. Pradhan B, Kjellstrom T, et al. *Cardiology* 2019;143(1):37–48. https://doi.org/10.1159/000500853
18. ILO, *One is too many* (Nov 2021). https://www.ilo.org/publications/one-too-many-collection-and-analysis-data-occupational-injuries-qatar
19. Divi C, et al. *Int J Qual Health Care* 2007;19(2):60–67. https://doi.org/10.1093/intqhc/mzl069
20. Flores G, et al. *Pediatrics* 2003;111(1):6–14. https://doi.org/10.1542/peds.111.1.6
21. Flores G, et al. *Ann Emerg Med* 2012;60(5):545–553. https://doi.org/10.1016/j.annemergmed.2012.01.025
22. Karliner LS, et al. *Health Serv Res* 2007;42(2):727–754. https://doi.org/10.1111/j.1475-6773.2006.00629.x
23. Lindholm M, et al. *J Gen Intern Med* 2012;27(10):1294–1299. https://pmc.ncbi.nlm.nih.gov/articles/PMC3445680/
24. Cohen AL, et al. *Pediatrics* 2005;116(3):575–579. https://doi.org/10.1542/peds.2005-0521
25. Khoong EC, et al. *JAMA Intern Med* 2019;179(4):580–582 (Google Translate: 92%/81% of sentences accurate in Spanish/Chinese; 2%/8% potentially harmful). https://pmc.ncbi.nlm.nih.gov/articles/PMC6450297/
26. Taira BR, et al. *J Gen Intern Med* 2021;36(11):3361–3365. https://doi.org/10.1007/s11606-021-06666-z
27. Brewster RCL, et al. *Pediatrics* 2024;154(1):e2023065573. https://doi.org/10.1542/peds.2023-065573
28. Rodriguez G, et al. *Acad Emerg Med* 2026;33(4):e70289. https://doi.org/10.1111/acem.70289
29. Anyaegbuna C, et al. arXiv:2603.22642 (Mar 2026). https://arxiv.org/abs/2603.22642
30. Bates DW, et al. *JAMA* 1997;277(4):307–311. https://pubmed.ncbi.nlm.nih.gov/9002493/
31. Classen DC, et al. *JAMA* 1997;277(4):301–306. https://pubmed.ncbi.nlm.nih.gov/9002492/
32. CRICO Strategies 2015 benchmarking report, via STAT (Feb 2016). https://www.statnews.com/2016/02/01/communication-failures-malpractice-study/
33. CDC, Clinical features of penicillin allergy (Aug 2025). https://www.cdc.gov/antibiotic-use/hcp/clinical-signs/index.html
34. NHS, How and when to take paracetamol (adults). https://www.nhs.uk/medicines/paracetamol-for-adults/how-and-when-to-take-paracetamol-for-adults/
35. Kabakov A, et al. *J Pharm Technol* 2019;35(4):139–145. https://doi.org/10.1177/8755122519840700
36. Prajapati et al. *J Nepal Health Res Counc* 2022 (from doc 01; not re-read). https://jnhrc.com.np/index.php/jnhrc/article/view/1217
37. Gulati M, et al. 2021 AHA/ACC chest pain guideline. https://doi.org/10.1161/CIR.0000000000001029
38. Kohrt BA, Hruschka DJ. *Cult Med Psychiatry* 2010;34:322–352. https://pmc.ncbi.nlm.nih.gov/articles/PMC3819627
39. Ralston G. "A Guide to Demo Day Presentations", Y Combinator (2016). https://www.ycombinator.com/blog/guide-to-demo-day-pitches/
40. Seibel M. "How to Pitch Your Company", Y Combinator (2016). https://www.ycombinator.com/blog/how-to-pitch-your-company/
41. Anderson C. "TED's secret to great public speaking" (TED, 2016) and *TED Talks: The Official TED Guide to Public Speaking* (2016). https://www.ted.com/talks/chris_anderson_ted_s_secret_to_great_public_speaking
42. Duarte N. *Resonate* (Wiley, 2010), "sparkline" structure. https://www.duarte.com/resources/books/resonate/
43. Tufte ER. *The Visual Display of Quantitative Information* (Graphics Press, 1983), data-ink ratio ("above all else show the data"). https://www.edwardtufte.com/ ; summary: https://jtr13.github.io/cc19/tuftes-principles-of-data-ink.html
44. Reynolds G. *Presentation Zen*, 3rd ed. (2019): restraint, simplicity, naturalness. https://garrreynolds.com/
45. Kurbaitaev M. "What Judges Actually Score: Notes From a Year of Hackathon Judging" (DEV, 2026; practitioner blog, medium confidence). https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l
46. Average speaking rate (NCVS figure, secondary). https://virtualspeech.com/blog/average-speaking-rate-words-per-minute
47. Hugging Face router model and price listing (retrieved 2026-11-07). https://router.huggingface.co/v1/models
48. Hugging Face Spaces GPU pricing. https://huggingface.co/docs/hub/spaces-gpus
49. LanguageLine rates, Cornell University KB. https://tdx.cornell.edu/TDClient/95/Portal/KB/ArticleDet?ID=6396
50. LanguageLine contract, Town of Ulysses NY (Jul 2025). https://www.townofulyssesny.gov/__cms/docs/2025-07-03_Languageline-Contract.pdf
51. LanguageLine Personal Interpreter (pay-as-you-go). https://languageline.com/personal-interpreter
52. ADA News, "CyraCom joins Propio" member pricing (Apr 2026). https://adanews.ada.org/ada-news/2026/april/ada-member-advantage-endorsed-cyracom-joins-propio-language-services/
53. Medical interpreter postings, Doha (Sidra, 2026). https://wuzzuf.net/jobs/p/V1XjDKHEKTcF-Medical-Interpreter-Sidra-Medicine-Doha-Qatar ; https://app.qureos.com/jobs/medical-interpreter-patient-language-services-specialist-1757581983687
54. Microsoft, DAX Copilot multilingual recording. https://support.microsoft.com/en-us/dax-copilot/epic/record-multilingual-conversations
55. Abridge, recording in multiple languages. https://support.abridge.com/hc/en-us/articles/30235001206419-Record-an-Encounter-in-Multiple-Languages
56. Pocketalk healthcare. https://pocketalk.com/healthcare
57. No Barrier: Healthcare Brew (Dec 2025) https://www.healthcare-brew.com/stories/2025/12/15/startup-no-barrier-ai-improve-medical-translation ; https://www.nobarrier.ai/medical-interpretation
58. Opalite Health. https://opalitehealth.com/
59. Mabel. https://mabel.care/
60. Care to Translate. https://www.caretotranslate.com/
61. Sahl AI evaluation, *JMIR Med Inform* 2026. https://medinform.jmir.org/2026/1/e83335/
62. Commure × Mediclinic Middle East (2026). https://www.commure.com/blog/mediclinic-middle-east-and-commure ; Augnito × Almoosa (2025) https://www.hospitalmanagement.net/newsletters/augnito-omni-scribe-almoosa-hospital ; Google Translate 2024 expansion https://blog.google/intl/en-mena/product-updates/connect-communicate/google-translate-new-languages-2024/ ; Third-party scribe price estimates https://checkthat.ai/brands/abridge/pricing
63. NVIDIA L4 street prices: SabrePC https://sabrepc.com/900-2G193-0000-000-NVIDIA-S5891322 ; GPUpoet https://gpupoet.com/gpu/learn/card/nvidia-l4
64. L40S and H100 price ranges: https://community.nasscom.in/communities/cloud-computing/h100-and-l40s-gpu-pricing-what-enterprises-need-know ; https://www.fluence.network/blog/nvidia-h100-deep-dive/ ; https://gpupoet.com/gpu/learn/price/may-2026/nvidia-h100-pcie
65. GlobalPetrolPrices, Qatar business electricity (Mar 2025). https://www.globalpetrolprices.com/Qatar/electricity_prices/
66. Clyde & Co, Qatar PDPPL regulatory guidelines (2021). https://www.clydeco.com/en/insights/2021/03/new-regulatory-guidelines-on-the-qatar-persona-1
67. Kiteworks, Qatar healthcare data residency (vendor commentary; low confidence). https://www.kiteworks.com/regulatory-compliance/qatar-healthcare-data-residency-compliance/
68. openai/gpt-oss-120b model card (single 80 GB GPU; 20b in 16 GB). https://huggingface.co/openai/gpt-oss-120b
69. Center for Victims of Torture, interpreters and heart idioms. https://cvt.org/articles/at-cvt-interpreter-relationships-are-key-part-2
70. "Viability of Machine Translation for Healthcare in Low-Resourced Languages", EMNLP 2025 (MBZUAI). https://underline.io/lecture/130287-viability-of-machine-translation-for-healthcare-in-low-resourced-languages
71. ASR errors in medical transcription across accents, arXiv:2501.15310 (2025). https://arxiv.org/abs/2501.15310

**Not verified / deliberately omitted:** official nationality breakdown (none published); HMC interpreter language list and headcount; Nepali/Malayalam speech support in Google/Microsoft conversation modes; primary MOPH data-residency text; Abridge/DAX list prices; L4 concurrency for multiple clinics; CPI-adjusted ADE cost (≈2× is a rough approximation).
