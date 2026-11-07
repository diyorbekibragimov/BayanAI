# 05 · Clinical Safety & Cultural Intelligence

> **Scope.** This document specifies two of Bayan AI's background "thinking" components: the **Cultural Idiom Interpreter** and the **Safety Sentinel**. It also covers the guardrails, evaluation plan and limitations that apply to both.
> **Data files:** [`data/idiom_lexicon.json`](../data/idiom_lexicon.json) (98 entries) · [`data/safety_rules.json`](../data/safety_rules.json) (81 rules).
> **Who wrote this:** engineers. The team includes **no clinician**, so every clinical statement here comes from a cited label, guideline or peer-reviewed paper. Nothing in this document is medical advice. Bayan AI is **decision support for a licensed doctor**: it never diagnoses, prescribes or speaks a safety alert to the patient.

---

## TL;DR

- **Problem.** Patients describe illness in *idioms of distress*, for example a Nepali worker's *"gyastrik"* or a Syrian patient's *"qalbi maqboud"* (my heart is squeezed). Literal translation loses the meaning, and the idiom can **mask a red flag**: "gas" in the chest may be cardiac. Human interpreters also make errors. In one paediatric study, interpreters averaged **31 errors per encounter, and 63% of errors had potential clinical consequences** ([Flores et al., *Pediatrics* 2003](https://pubmed.ncbi.nlm.nih.gov/12509547/)).
- **Cultural Idiom Interpreter.** When the patient uses a known idiom, a deterministic matcher (native script, romanised forms, English loanwords; no LLM) finds the lexicon entry and the card text comes straight from that entry. The doctor sees the literal translation, a short clinical note and questions to ask, with the entry id and source. **98 sourced entries** cover 10 primary languages: **55** from peer-reviewed or institutional literature and **43** honestly marked `community_reported`.
- **Safety Sentinel.** An open-weights LLM (`gpt-oss-120b`, one JSON-schema call per think run) *extracts* a structured clinical state (allergies, meds, doses, symptoms, vitals, tests, disposition) from the bilingual transcript. **81 deterministic, cited rules** then check that state. The rule families are drug–allergy, dose ceilings, drug–drug interactions, missing critical workup and pregnancy, plus Qatar-specific heat rules. **Rules are the authority for drug and dose checks.** The LLM never decides that a dose is safe.
- **Alerts are silent** (on screen only, never spoken). Each alert shows the **exact quoted utterance, its timestamp and the rule source**, and takes **one tap** to acknowledge, override or dismiss; every action goes to an append-only audit list. A prescribing sentence that trips a critical rule is **held** before it is spoken. Dedupe, grouping and caps keep alert fatigue down. Override rates of 49–96% for drug alerts are documented ([van der Sijs et al. 2006](https://pubmed.ncbi.nlm.nih.gov/16357358/)).
- **Qatar grounding.** Heat-illness rules include core-temperature and cooling checks; Qatar's 2021 heat-stress decision requires work to stop above WBGT 32.1 °C. The chest-pain rules and the *gyastrik* card cite the "gastric" attribution of cardiac pain in Nepal: 87.9% of STEMI patients had typical chest pain, only 23.8% thought it was cardiac ([Prajapati et al., JNHRC 2022](https://jnhrc.com.np/index.php/jnhrc/article/view/1217)). Imported malaria surveillance data come from Qatar's MoPH ([Bansal et al. 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11725959/)). The privacy design follows **Qatar's PDPPL (Law No. 13 of 2016)**.
- **Judging fit.** *Impact:* targets the errors that hurt migrant patients most. *HF use:* `gpt-oss-120b` through HF Inference Providers and a **smolagents** copilot agent (publishing the lexicon as a Hub dataset is planned, not done). *Efficiency:* rules and idiom matching run in milliseconds on CPU; the LLM is spent on extraction and, only when something new appears, one agent step. *Technical execution:* the JSON files are executed by `bayan/brain/rules.py` and `bayan/brain/idioms.py`, with 269 offline tests.

---

## 0. As built (2026-11-07)

What the code in `bayan/brain/` does today. Sections 1 to 4 keep the design detail; where the design goes further than the build, the text says *designed, not built*.

| Piece | What runs | Where |
|---|---|---|
| **Deterministic spine** (every turn, before any agent) | Idiom match on new patient turns (no LLM) → **one** extraction call (`gpt-oss-120b`, JSON schema, on Groq with Cerebras fallback; courtesy turns skipped, a doctor's plain question batched with the patient's answer) → state merge (every fact keeps utterance-id evidence and quotes; unknown stays unknown) → **all 81 rules** (no LLM). Each step is logged as a tool call in the activity trace. | `copilot.think_now`, `extract.py`, `merge.py`, `rules.py`, `idioms.py` |
| **Prescription gate** | Synchronous, no LLM, about 3 ms. Runs on doctor turns that name a drug, using the translation JSON's `intent`: `prescribe` (or missing intent) is checked against the `on_prescribe` rules, `stop` removes the drug from the state, `mention` is ignored. A critical hit **holds the sentence**; the doctor chooses "Say something else" or "Speak it anyway" (the override is logged). Allergies on patient turns are merged at once for the same reason. | `copilot.prescription_gate`, `copilot.record_allergies` |
| **Cards** | Four sources: `rules`, `lexicon`, `agent`, `fallback`. **Only `rules` can be critical**; agent and fallback cards are capped at caution and are rejected unless they cite real utterance ids and a grounding that exists (rule, idiom or checklist id). At most 3 open "ask" cards; dedupe on kind + grounding + title, plus fuzzy matching of the question; a dismissed card never returns; `WORK-CHEST-*` hits collapse into one "Chest-pain workup" card (`WORK-HEAT-*` into "Heat-illness workup"); ask and missed cards resolve themselves when the checklist item is done (e.g. troponin ordered). Doctor actions: acknowledge, override, dismiss, accept, ask (the question is spoken to the patient), wrong fact. Every alert and action is appended to the consultation's audit list. | `cards.py`, `checklist.py` |
| **Copilot agent** | smolagents 1.26.0 `ToolCallingAgent` on `gpt-oss-120b` (Cerebras, reasoning medium). Runs in the background only when the spine found something new. Tools: `lookup_idiom`, `lookup_drug`, `check_safety_rules` (read-only) and `final_answer(cards)`, which posts 0 to 2 ask / possibly-missed / observation cards (hard cap 3 in code) and ends the run. Agent off, failed, timed out or no valid card → deterministic fallback ask cards. | `copilot.py`, `agentkit.py` ([11](11-clinical-copilot-agent.md)) |
| **Wrap-up guard** | The note's Assessment holds only the clinician's own words: a code-level check drops diagnostic claims nobody in the consultation stated. Every care-plan medicine is re-checked by the rule engine; `check_care_plan` checks numbers, stopped drugs, the 999 line and missing translations. | `wrapup.py` |

Measured on the live golden path (9 text turns, `scripts/smoke_e2e.py`): copilot agent about 1.2 to 1.6 s per run in 1 step, extraction about 1.1 s, gate about 3 ms. **Limits:** the offline tests use fake models; one live scenario; no clinician or native-speaker review yet. The brain is wired into the Space code (local; not yet deployed).

### 0.1 Rule changes (2026-11-07)

Recorded in each rule's `change_note` in `data/safety_rules.json`.

| Rule / entry | Before | Now | Why |
|---|---|---|---|
| `WORK-CHEST-04` (idiom may mask ACS, caution) | Any idiom tagged `acs` with no ECG fired | Needs an `acs`-tagged idiom **and** a chest-pain-group symptom (`chest_pain`, `chest_discomfort`, `chest_pressure`, `chest_burning`, `epigastric_pain_exertional`, `jaw_arm_pain`), the same codes as `WORK-CHEST-01..03` | 27 of 98 entries carry `acs` (e.g. *kabag* = gas pain or infant colic, *man bhaari* = heavy heart-mind), so the old rule would alert on most consultations. The golden path (*gyastrik* + `chest_burning`) still fires. |
| `WORK-SUICIDE-01` (no risk assessment) | Critical for any idiom tagged `suicidality` | **Caution** for an idiom alone; escalates to **critical** when `suicidal_ideation` or `self_harm` is extracted, including a passive death wish ("I wish I could sleep and not wake up") | 19 of 98 entries carry `suicidality` (e.g. *tension*, *chinta* = worry), so idiom-only critical alerts would be noise. Explicit statements stay critical. |
| `npi-005` (*gyastrik*) red flag; `WORK-CHEST-02` and `WORK-CHEST-04` rationale and sources | Cited Pradhan et al. 2019 as if missed diagnosis drove deaths | Cite Prajapati et al., JNHRC 2022 | Pradhan 2019 attributes preventable deaths to missing heat protection, not missed diagnosis. Prajapati 2022: 87.9% of STEMI patients in Nepal had typical chest pain, only 23.8% thought it was cardiac. |

Base severity mix after the change: **37 critical · 35 caution · 9 info**; 14 rules carry `escalate_to_critical_if`.

---

## 1. Cultural Idiom Interpreter

### 1.1 Why this matters

Medical anthropology calls these expressions **idioms of distress**: culturally shared ways of communicating suffering that do not map one-to-one onto biomedical categories ([Nichter, *Idioms of distress revisited*, Cult Med Psychiatry 2010](https://experts.arizona.edu/en/publications/idioms-of-distress-revisited/)). DSM-5 formalised this as *cultural concepts of distress* (for example *dhat* and "thinking too much"). Systematic reviews warn that such idioms **should not be read as a gloss for a single psychiatric disorder** ([Kaiser et al. 2015](https://pmc.ncbi.nlm.nih.gov/articles/PMC4689615/)). Three findings shaped the design:

| Finding | Source | Design consequence |
|---|---|---|
| Nepali *man* (heart-mind) idioms are a socially acceptable way to seek help; *dimaag* (brain-mind) idioms are stigmatised. "Gastric" (*gyastrik*) and tingling (*jham-jham*) are common bodily idioms. | [Kohrt & Hruschka 2010](https://pmc.ncbi.nlm.nih.gov/articles/PMC3819627/); [Kohrt & Harper 2008](https://pmc.ncbi.nlm.nih.gov/articles/PMC3869091/) | Notes never label the patient "psychiatric". They show possibilities, including the dangerous physical one. |
| South Asian "tension" ranges from everyday hassle to severe distress or suicidality. | [Weaver & Karasz 2022](https://doi.org/10.1016/j.ssmmh.2022.100092) | The note always suggests a **severity question**, and a suicide-screen question where relevant. |
| Arabic idioms rarely separate body and soul. Indirect phrases such as *"I wish I could sleep and not wake up"* express suicidal thoughts. | [UNHCR / Hassan et al. 2015, Table 1](https://www.unhcr.org/sites/default/files/legacy-pdf/55f6b90f9.pdf) | Some lexicon entries carry `red_flag_tags` (e.g., `suicidality`) that feed Safety Sentinel rules. |

Qatar context: Qatar's migrant workforce is mostly South Asian, Southeast Asian, Arab and East African, and many workers do outdoor manual work in extreme heat. In Nepal, cardiac pain is often read as "gastric": among STEMI patients, 87.9% had typical chest pain but only 23.8% thought it was cardiac ([Prajapati et al., JNHRC 2022](https://jnhrc.com.np/index.php/jnhrc/article/view/1217)). When a worker says *"my chest burns like gyastrik,"* the literal translation alone is dangerous.

### 1.2 What is in the lexicon

`data/idiom_lexicon.json` → `{ "meta": {...}, "entries": [...] }`. The schema for each entry:

| Field | Meaning |
|---|---|
| `id`, `language`, `iso639_3`, `also_used_in[]` | e.g. `npi-005`, Nepali, `npi` |
| `native`, `romanized`, `literal_en` | Native script, romanisation, and a literal English rendering |
| `clinical_interpretations[]` | `{meaning, likelihood: high/medium/low}`, a rough ordering taken from the sources. **It is not a probability.** |
| `masks_red_flags[]` + derived `red_flag_tags[]` | Dangerous conditions the idiom can hide (`acs`, `suicidality`, `stroke`, `heat_illness`, `malaria`, …) |
| `clarifying_questions_en[]` | Questions the doctor can ask. Bayan translates and speaks them only if the doctor taps them. |
| `body_system`, `source_urls[]`, `evidence_level`, `notes` | `literature` / `clinical_guideline` / `community_reported` |

**Coverage (v0.2):**

| Language | Entries | Main sources |
|---|---|---|
| Nepali (npi) | 15 + 1 shared | Kohrt & Hruschka 2010; Kohrt & Harper 2008 (*dimaag gayo*, *dimaag kharaab bhayo*, *Chait laagyo*) |
| Arabic (Levantine-documented; Gulf/Egyptian/Sudanese listed in `also_used_in`) | 15 | UNHCR 2015 Table 1; Lambert et al. 2024; lay health pages for *humooda* (acidity) and *darbat shams* (sunstroke) |
| Hindi/Urdu (hin/urd) | 23 + 1 shared | Krause 1989; Sumathipala 2004 (dhat); Weaver & Karasz 2022; Trollope-Kumar 2001 (*safed pani*); Population Council (*gupt rog*); Rekhta dictionary for symptom and pregnancy idioms (*loo lagna*, *saans phoolna*, *paon bhari*, *daura padna*, …) |
| Tagalog/Filipino (tgl) | 15 | Pasma literature (Palis 2006, Cuyonon study); Visayan *bughat* ethnography; Lasco et al. 2020 (*high blood*, *low blood*, *maintenance*); Gaw et al. 2011 (*bangungot*); dictionaries |
| Bengali (ben) | 14 | Wahid et al. 2021 (Bangladesh; incl. *brain stroke*, *matha noshto*, *hotasha*); Bengali health-education pages |
| Malayalam (mal) | 4 | Malayalam health media and Wiktionary (community-reported only) |
| Swahili (swh) | 5 | Greene et al. 2022 (*msongo wa mawazo*); Kaiser et al. 2015 (*kichwa kinajaa mawazo*); Makundi et al. 2006 (*degedege*); Temu et al. 2017 (*pressure*); Wiktionary |
| Tamil (tam) | 3 | Affleck et al. 2022 (Walking Corpse Syndrome); Tamil health media and Wiktionary (*vaayvu*, *mayakkam*) |
| Punjabi (pan), Amharic (amh) | 1 each | Krause 1989; Ethiopian ethnobotany (*mich*) |

**Honesty rules.** An idiom without a source is not included. `community_reported` means the meaning comes from dictionaries or lay health media, and its clinical interpretations are generic differentials. The file's `meta.authorship_caveat` states that a clinician and a native speaker must review every entry before real use. Section 6 lists the gaps.

### 1.3 How the lexicon is used at runtime (as built: deterministic matching)

```mermaid
flowchart LR
  A[Patient utterance<br/>native-script ASR text<br/>+ English rendering] --> M{bayan/brain/idioms.py<br/>no LLM}
  L[(idiom_lexicon.json<br/>98 entries)] --> M
  M -- no match --> D[Plain translation only<br/>no clinical note]
  M -- match --> F["Idiom card from the entry<br/>literal · clinical note · ask<br/>+ entry id + source"]
  M -- match --> G[red_flag_tags → idiom_hits<br/>in the clinical state → rules]
```

1. **Match.** Three matchers, no LLM: (a) native-script substring (Nepali suffixes such as -ले attach directly); (b) romanised or Latin-script forms, normalised for case, diacritics and common transliteration variants, matched token by token, with a rapidfuzz ratio of at least 90 for longer forms; (c) English loanword entries ("gastric", "gas", "tension") matched in the English rendering. When the patient's language is known, romanised forms are tried only for entries of that language, and same-language entries win.
2. **Card.** The card text comes from the entry itself (interpretations, masked red flags, clarifying questions, sources). No model writes or rephrases it, so it cannot invent a meaning. The card goes up at once, before the extraction call.
3. **Route red flags.** A matched entry's `red_flag_tags` are added to `idiom_hits` in the clinical state, so rules such as `WORK-CHEST-04` (with a chest-pain-group symptom) and `WORK-SUICIDE-01` can fire.

*Designed, not built:* embedding retrieval (e.g. [`intfloat/multilingual-e5-large`](https://huggingface.co/intfloat/multilingual-e5-large)) to catch paraphrases the string matchers miss. It would add recall, not authority: any retrieved entry still supplies the card text.

### 1.4 What the doctor sees

A single line per matched idiom, expandable. The **literal translation is always shown**:

```
🗣 Patient (Nepali, 00:42): "छाती ग्यास्ट्रिकले जस्तो पोलेको छ"
Literal: "My chest is burning, like gastric."
Clinical note: "Gyastrik" is a common Nepali idiom for dyspepsia and can also carry
  psychosocial distress. It can mask cardiac chest pain.   [npi-005 · literature]
Ask: ▸ Does it come on with work or walking and ease with rest?
     ▸ Any sweating, breathlessness, or pain to arm/jaw?
     ▸ Black stools or vomiting blood?
[Ask]  [Dismiss]                                     Sources: Kohrt & Harper 2008 · AHA/ACC 2021
```

- Tapping **Ask** translates the question and speaks it to the patient (back-translation check: designed, not built, §4.1).
- Card actions (ask, accept, dismiss) are logged in the audit list. They are the raw data for the "idiom note acceptance" metric (§5).
- No idiom match means no note. The UI never displays a speculative cultural interpretation.

### 1.5 From lexicon to HF Dataset and fine-tuning data (roadmap, not done)

None of these steps has run yet: no dataset is on the Hub and no model was fine-tuned.

| Step | What | HF tooling |
|---|---|---|
| 1. Publish | Flatten `entries[]` to JSONL (one row per entry; lists as list columns) and push it as `dullgrey/team-qh-129-bayan-idioms`. Write a dataset card covering sources, evidence levels, licence notes and "not for diagnosis". | `datasets.Dataset.from_list(...).push_to_hub()` |
| 2. Expand to examples | For each entry, generate 10–20 realistic utterances (native script and romanised, code-mixed). Native speakers review them, and each row is labelled `{utterance, lang, entry_id}`. | HF Jobs (one short CPU/GPU job) + `datasets` |
| 3. Retrieval fine-tune | Contrastive pairs (utterance ↔ entry text) with hard negatives (e.g., *gyastrik* vs *kabag*) to improve recall at τ. | `sentence-transformers` trainer on HF Jobs; push to Hub with card |
| 4. Note-writer SFT (optional) | `{utterance, retrieved entries} → card text` pairs, so a small open model learns the exact output format and the `NO_MATCH` behaviour. | TRL `SFTTrainer` (LoRA) on HF Jobs |
| 5. Preference data | Doctor ✓/✗ on cards → `{prompt, chosen, rejected}` for DPO later. | TRL `DPOTrainer` (post-hackathon) |

The lexicon stays the **source of truth**. Fine-tuning improves recall and formatting but does not add new clinical claims. Any new meaning must enter as a cited lexicon row first.

---

## 2. Safety Sentinel

### 2.1 Design principle

> **The LLM listens and structures. The rules judge.**

Drug–allergy, dose and interaction checks are **deterministic, explainable and cited**. Every alert can be traced to a rule ID, a source URL and the transcript utterance that triggered it. An LLM *could* notice that "amoxicillin is a penicillin," but it can also hallucinate, miss the allergy, or reason inconsistently between runs. We use the LLM only where rules cannot work: turning messy bilingual speech into structured facts, plus a clearly labelled, lower-tier "observations" channel (§2.6).

### 2.2 Architecture

```mermaid
flowchart TB
  subgraph Room["Consultation room (one tablet)"]
    MIC[Ambient audio] --> ASR[VAD → language ID → ASR<br/>doctor vs patient by language]
  end
  ASR --> TR[Talk loop: gpt-oss-120b translation<br/>+ drugs / allergies / tests JSON]
  TR --> GATE[Prescription gate<br/>sync, no LLM, ~3 ms]
  GATE -- critical --> HOLD[Sentence held<br/>Say something else / Speak it anyway]
  TR --> TX[(Transcript turns<br/>id · speaker · lang · text · English)]
  TX --> IDI[Idiom matcher<br/>idioms.py, no LLM]
  TX --> EXT[Extraction: one gpt-oss-120b call<br/>JSON schema, Groq]
  EXT --> VAL[merge.py<br/>drug name → INN + class<br/>dose × frequency, evidence kept]
  IDI --> STATE
  VAL --> STATE[(Clinical state<br/>versioned)]
  GATE --> STATE
  STATE --> ENG[Rule engine<br/>81 rules · CPU, ms]
  CLK[Timer tick] --> ENG
  ENG --> CS[Card store<br/>dedupe · group · caps · guardrails]
  IDI --> CS
  STATE --> AG[smolagents copilot<br/>only when something is new<br/>max severity = caution]
  AG --> CS
  CS --> UI[Doctor screen: silent cards<br/>quote + timestamp + source]
  UI -- ack / override / dismiss --> AUD[(Append-only audit list)]
  CS -. never .-> TTS[🔇 TTS / speaker]
```

Notes:
- **Event types** (`fire_on` in each rule): `state_change`, `on_prescribe`, `on_disposition` (doctor says "you can go home", "we'll admit you", …) and `timer` (e.g., "chest pain mentioned more than 10 min ago and still no ECG").
- **Language as diarisation.** Doctor speech is English/Arabic and patient speech is another language. The extractor still tags the speaker, because a patient may *mention* a drug they take while the doctor *prescribes* a drug.
- **Model choice** (see [04 Models & Languages](04-models-and-languages.md)): extraction runs on `openai/gpt-oss-120b` via HF Inference Providers on **Groq** (same model, cheaper input than Cerebras; Cerebras is the fallback), at reasoning effort medium ("high" was measured to return empty replies). The copilot agent runs on Cerebras only, because gpt-oss tool calling through Groq called a tool that does not exist. No fine-tuned model and no Fanar model is in the runtime. Running the rule engine costs nothing.

### 2.3 Clinical state schema (extractor output)

The extractor must return JSON that validates against this schema. Every fact carries `evidence` (utterance IDs and the quoted span) and `confidence`. **Unknown is a valid value**: the extractor must not guess pregnancy status, a dose or a reaction.

```json
{
  "allergies": [
    {"substance": "penicillin", "class": "penicillin", "reaction": "rash", "severity": "mild|moderate|severe|anaphylaxis|scar|unknown",
     "evidence": [{"utt": "u017", "t": "00:01:12", "quote": "पेनिसिलिनले मलाई एलर्जी भयो, छालामा दाग आयो"}], "confidence": 0.93}
  ],
  "current_meds":    [{"drug": "lisinopril", "dose_mg": 10, "frequency_per_day": 1, "route": "oral", "evidence": [], "confidence": 0.8}],
  "prescribed_meds": [{"drug": "amoxicillin", "dose_mg": 500, "unit_raw": "mg", "dose_raw": "500 mg", "route": "oral",
                       "frequency_per_day": 3, "duration_days": 5, "indication": "sore throat",
                       "evidence": [{"utt": "u088", "t": "00:10:50", "quote": "I'll give you amoxicillin 500 three times a day"}], "confidence": 0.95}],
  "symptoms":   [{"code": "chest_burning", "severity": "moderate", "onset": "2h", "first_mention_t": "00:00:42", "evidence": [], "confidence": 0.9}],
  "vitals":     {"hr": 96, "bp_sys": 138, "rr": null, "spo2": null, "temp_c": null, "temp_site": "unknown"},
  "investigations": [{"code": "ecg_12lead", "status": "ordered|resulted", "evidence": []}],
  "interventions":  [{"code": "active_cooling", "evidence": []}],
  "assessments":    [{"code": "suicide_risk_assessment", "evidence": []}],
  "disposition":    {"type": "discharge|admit|refer|observe|null", "evidence": []},
  "patient": {"age_years": 34, "sex": "male", "pregnant": "unknown", "gestation_weeks": null, "weight_kg": null,
              "egfr": null, "hepatic_impairment": "unknown", "heat_exposure": true, "heat_illness_suspected": false,
              "dehydration": "none|mild|moderate|severe|unknown", "travel_malaria_endemic_days": null, "ancestry_region": "south_asia"},
  "idiom_hits": [{"id": "npi-005", "red_flag_tags": ["acs", "gi_bleed"], "utt": "u006"}]
}
```

The **validator** (`bayan/brain/merge.py`, plain Python, not the LLM) normalises brand names to INN (e.g., *Adol/Panadol* → paracetamol, *Augmentin* → co-amoxiclav; see `meta.brand_aliases_examples`). It also maps drugs to classes (`meta.drug_classes`), converts units (g → mg, "one tablet" + known strength → mg), computes `daily_dose_mg`, and computes `elapsed_min_since.*` from timestamps (the code stores `first_mention_min` per symptom). `elapsed_min_since.first_match` is the number of minutes since the earliest first mention among the items matched by the same rule's `exists_in` clause. For example, `WORK-CHEST-01` counts from the first mention of *any* chest-pain-group symptom, including `chest_burning`. If the dose unit is ambiguous, it records `dose_mg: null` and raises an *info* prompt asking for the strength instead of guessing.

### 2.4 Rule families (81 rules in `safety_rules.json`)

| Family | # | Example rules (id → what fires) | Key sources |
|---|---|---|---|
| **Drug–allergy** | 12 | `ALG-PEN-01` penicillin allergy + any penicillin incl. co-amoxiclav, piperacillin-tazobactam → **critical** · `ALG-PEN-02` aminopenicillin allergy + cephalexin/cefadroxil/cefaclor/cefprozil (similar R1 side chain) → caution, escalating if anaphylaxis · `ALG-PEN-04` non-severe penicillin allergy + dissimilar cephalosporin → **info only** (current guidance generally permits it) · `ALG-SULFA-02` sulfa-antibiotic allergy + furosemide/thiazide → **info** (no specific cross-reactivity) · `ALG-NSAID-01` aspirin/NSAID hypersensitivity + COX-1 NSAID → critical · `ALG-HLA-01` carbamazepine in a patient of Asian ancestry without an HLA-B*1502 result → caution | [AAAAI/ACAAI 2022 practice parameter](https://doi.org/10.1016/j.jaci.2022.08.028); [Shenoy et al. JAMA 2019](https://pubmed.ncbi.nlm.nih.gov/30644987/); [NICE CG183](https://www.nice.org.uk/guidance/cg183); [Strom et al. NEJM 2003](https://pubmed.ncbi.nlm.nih.gov/14573734/); [Kowalski et al. 2013](https://pubmed.ncbi.nlm.nih.gov/24117484/); [carbamazepine FDA label](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=047bc284-060a-4db9-bf37-75d10f95a0a6) |
| **Dose ceilings** | 29 | `DOSE-PARA-01` paracetamol over 1 g/dose or 4 g/day → critical · `DOSE-PARA-03` over 75 mg/kg/day if under 50 kg · `DOSE-PARA-04` over 3 g/day with hepatic risk or heat illness → caution · ibuprofen over 2.4 g (critical over 3.2 g) · diclofenac over 150 mg · ketorolac oral over 40 mg/day or more than 5 days · amoxicillin over 3 g oral · co-amoxiclav clavulanate over 375 mg/day · azithromycin · ceftriaxone over 2 g/day (caution; label maximum 4 g/day) · metformin over 2550 mg, or eGFR under 30 → critical · amlodipine over 10 mg · omeprazole over 40 mg (info) · ondansetron IV over 16 mg · metoclopramide over 30 mg/day · tramadol over 400 mg · codeine · colchicine over 1.8 mg/flare · prednisolone over 60 mg (info) · salbutamol over 12 puffs/day (info) · levothyroxine over 300 mcg (mg/mcg unit error) · adrenaline 1 mg/mL given IV or over 0.5 mg IM | FDA labels on DailyMed (set IDs in file, retrieved via openFDA 2026-11-06); [EMA metoclopramide review](https://www.ema.europa.eu/en/medicines/human/referrals/metoclopramide-containing-medicines); [Resus Council UK anaphylaxis](https://www.resus.org.uk/library/additional-guidance/guidance-anaphylaxis/emergency-treatment) |
| **Drug–drug** (small curated set) | 12 | warfarin + NSAID; warfarin + fluconazole/metronidazole · simvastatin + clarithromycin/azoles (contraindicated) · clopidogrel + omeprazole · PDE5 inhibitor + nitrate · tizanidine + ciprofloxacin · tramadol/linezolid + SSRI (serotonin syndrome) · ACE inhibitor/ARB + spironolactone/K⁺ · methotrexate + trimethoprim · allopurinol + azathioprine · NSAID + ACE inhibitor/ARB + diuretic ("triple whammy"), escalating with heat or dehydration | Interacting-drug FDA labels; [CDC heat & medications](https://www.cdc.gov/heat-health/hcp/clinical-guidance/heat-and-medications-guidance-for-clinicians.html) |
| **Missing critical workup** | 16 | Chest pain → ECG within 10 min (`WORK-CHEST-01`, timer); chest pain + discharge with no ECG or no troponin → critical; idiom tagged `acs` (gas/gyastrik/kabag) + a chest-pain-group symptom + no ECG → caution (§0.1) · **Heat:** heat exposure + confusion/collapse with no **rectal/core temperature** → critical; suspected heat stroke with no active cooling → critical; no CK/creatinine/electrolytes → caution; antipyretic for heat stroke → info · Headache + SNNOOP10 red flag + discharge with no exam or imaging decision · Abdominal/pelvic pain, bleeding or dizziness in a woman 12–55 with unknown pregnancy status → pregnancy test (critical before CT, a teratogen or discharge) · Fever + endemic travel within 90 days → malaria test · IV fluids/severe dehydration → U&E · Suicidal ideation → risk assessment (caution for an idiom alone, critical when explicit; §0.1) · Sepsis criteria → lactate/cultures · TLoC → ECG · Focal neuro signs → imaging | [AHA/ACC 2021](https://doi.org/10.1161/CIR.0000000000001029); [ESC ACS 2023](https://doi.org/10.1093/eurheartj/ehad191); [ACSM 2023](https://doi.org/10.1249/JSR.0000000000001058); [WMS 2024](https://doi.org/10.1177/10806032241227924); [IOC heat consensus 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC9811094/); [SNNOOP10](https://pmc.ncbi.nlm.nih.gov/articles/PMC6340385/); NICE [NG126](https://www.nice.org.uk/guidance/ng126), [CG174](https://www.nice.org.uk/guidance/cg174), [NG225](https://www.nice.org.uk/guidance/ng225), [NG51](https://www.nice.org.uk/guidance/ng51), [CG109](https://www.nice.org.uk/guidance/cg109), [NG128](https://www.nice.org.uk/guidance/ng128); [WHO malaria](https://www.who.int/publications/i/item/guidelines-for-malaria) |
| **Pregnancy** | 10 | ACE inhibitor/ARB, isotretinoin, warfarin, valproate, methotrexate, misoprostol → critical · NSAID at 20 weeks or later → caution (critical at 30 weeks or later) · tetracyclines → caution · **statin → info** (FDA removed the blanket contraindication in 2021) · unknown pregnancy status + teratogen → caution | Boxed warnings on FDA labels; [FDA NSAID ≥20 wk](https://www.fda.gov/drugs/drug-safety-and-availability/fda-recommends-avoiding-use-nsaids-pregnancy-20-weeks-or-later-because-they-can-result-low-amniotic); [FDA statins 2021](https://www.fda.gov/drugs/drug-safety-and-availability/fda-requests-removal-strongest-warning-against-using-cholesterol-lowering-statins-during-pregnancy) |
| **Heat & medication** (Qatar) | 2 | NSAID for a dehydrated, heat-exposed patient → caution · diuretic/anticholinergic/antipsychotic/β-blocker/TCA/topiramate for an outdoor worker → info: add heat counselling to the patient plan | [CDC heat & medications](https://www.cdc.gov/heat-health/hcp/clinical-guidance/heat-and-medications-guidance-for-clinicians.html); [Qatar heat-stress decision (ILO)](https://www.ilo.org/resource/qatars-ministerial-decision-heat-stress) |

Base severity mix: **37 critical · 35 caution · 9 info** (14 rules also carry `escalate_to_critical_if`). The *info* rules are deliberate. Several exist to **prevent false critical alerts** from outdated beliefs: cephalosporins in non-severe penicillin allergy, sulfa "cross-allergy", and statins in pregnancy.

**Verification field.** `label_or_guideline_checked` means we read the threshold in the cited text. `threshold_is_design_choice` means the source supports the concern but the exact number is a conservative engineering choice, for example paracetamol over 3 g/day with risk factors or oral amoxicillin over 3 g/day. Every threshold must be confirmed against the local formulary (e.g., HMC) by a pharmacist before real use.

### 2.5 The rule language (machine-checkable triggers)

Each rule's `trigger` is a small JSON logic tree: `all` / `any` / `none`, plus `exists_in` / `none_in` over a state collection, with facts compared by `eq, neq, in, not_in, gt, gte, lt, lte, exists, not_exists, contains_any`. Missing data evaluates to *false*, so a rule never fires on absent data. The exception is `none_in`, which is designed to fire when an investigation is missing. `escalate_to_critical_if` raises severity when extra conditions hold.

```json
{
  "id": "ALG-PEN-01",
  "family": "drug_allergy",
  "trigger": {"all": [
    {"exists_in": "allergies",       "where": {"fact": "class", "op": "in", "value": ["penicillin"]}},
    {"exists_in": "prescribed_meds", "where": {"fact": "class", "op": "in", "value": ["penicillin"]}}
  ]},
  "severity": "critical",
  "message_en": "Penicillin allergy reported ({allergy.evidence}). {rx.drug} is a penicillin.",
  "rationale": "Every penicillin, including combination products …",
  "source_urls": ["https://doi.org/10.1016/j.jaci.2022.08.028", "https://pubmed.ncbi.nlm.nih.gov/30644987/", "https://www.nice.org.uk/guidance/cg183"],
  "fire_on": "on_prescribe",
  "verification": "label_or_guideline_checked"
}
```

The evaluator is `bayan/brain/rules.py` (`json-logic`-style recursion; no LLM involved). `tests/test_rules.py` runs the three worked examples in §3 against the shipped JSON and asserts the alert lists.

### 2.6 What the LLM does, and what it may not do

| LLM may | LLM may not |
|---|---|
| Extract the clinical state into the JSON schema, with evidence spans and `unknown` where unsure | Decide whether a dose, allergy or interaction is safe |
| Resolve code-mixing and colloquial drug names ("the white pain tablet" → asks the doctor to confirm; never assumes) | Raise a **critical** alert. LLM-only observations are capped at *caution*. |
| Post **non-rule patterns** as observation cards (copilot agent), e.g., "the patient said 'I have no one here' twice; consider a social-work referral" or "dose stated twice with different numbers (500 vs 50)" | Hide or reword a rule alert |
| Draft the clarifying question for the doctor to tap | Speak anything to the patient on its own initiative |

Agent cards carry `source: agent`, the quoted utterance ids and their grounding; they are excluded from rule-precision metrics. An agent attempt to post a critical card is rejected and logged.

### 2.7 Alert UX: silent, evidenced, accountable (as built in `cards.py`)

| Property | As built |
|---|---|
| **Channel** | **On-screen only.** The card store has no path to TTS. Alerts never chime or vibrate. |
| **Severity** | `info`, `caution`, `critical`. Only the rule engine can produce `critical`. Cards sort by severity, then recency. |
| **Held sentence** | A *critical prescribing* rule (e.g. `ALG-PEN-01`) found by the prescription gate holds the doctor's sentence before it is spoken. The doctor picks **Say something else** (nothing is spoken) or **Speak it anyway** (spoken, override logged). Nothing else interrupts the conversation. |
| **Evidence** | Every card carries the rule id(s) or grounding, the **quoted utterance(s)** with utterance ids and minute marks, the rule message and the source links. There is no audio replay: audio is not kept. |
| **Actions** | **Acknowledge** · **Override** (with a reason) · **Dismiss** · **Accept** · **Ask** (the question is translated and spoken; the card is done) · **Wrong fact** (extraction error, logged as an override). |
| **Audit** | Append-only list per consultation: card id, rule id, grounding, kind, severity, source, action, reason, user, minute, state version, evidence utterance ids. No audio. The wrap-up turns it into plain-sentence "Safety alerts" in the note. |
| **Fatigue controls** | (1) **Dedupe** on kind + grounding + normalised title, plus fuzzy matching of reworded questions; a dismissed card never returns in that consultation. (2) **Grouping**: `WORK-CHEST-01…04` collapse into one "Chest-pain workup" card; `WORK-HEAT-*` into "Heat-illness workup". (3) **Cap**: at most 3 open "ask" cards. (4) **Self-resolving**: ask and missed cards close when the checklist item is done; rule cards resolve when the rule stops firing. (5) **Timing**: `on_disposition` and timer rules wait for the right moment. (6) **Thresholds** use label maxima, and info-level rules suppress known false alarms. Rationale: reminder acceptance dropped 30% per extra reminder per encounter ([Ancker et al. 2017](https://pubmed.ncbi.nlm.nih.gov/28395667/)). |

*Designed, not built:* a cap on visible caution/critical cards, and blocking note sign-off until every critical card is acknowledged.

---

## 3. Worked examples (end-to-end)

These are scripted demo scenarios with fictional people. `tests/test_rules.py` asserts the alert lists below against `bayan/brain/rules.py` and `safety_rules.json`; Example 1 is also the live golden path in `scripts/smoke_e2e.py`.

### Example 1: Nepali construction worker, "chest burning like gyastrik", penicillin allergy, amoxicillin, discharge without ECG

| t | Speaker | Utterance (source → EN) | System |
|---|---|---|---|
| 00:42 | Patient (ne) | "छाती ग्यास्ट्रिकले जस्तो पोलेको छ, काम गर्दा बढ्छ" → "My chest burns like gastric; it gets worse when I work." | Idiom card **npi-005** (gyastrik) with *Ask* questions. `idiom_hits += [acs, gi_bleed]` + symptom `chest_burning` (first mention 00:42) → **caution `WORK-CHEST-04`** (idiom may mask ACS). |
| 01:12 | Patient (ne) | "पेनिसिलिनले मलाई एलर्जी भयो, छालामा दाग आयो" → "I had an allergy to penicillin; I got spots on my skin." | Allergy `{penicillin, reaction: rash, severity: moderate}`. |
| 03:05 | Doctor (en) | "Probably acidity and a throat infection." | No new alert. |
| 10:42 | (timer) | No ECG ordered 10 min after first mention | **Caution `WORK-CHEST-01`**, grouped with `WORK-CHEST-04` into one "Chest-pain workup" card. |
| 10:50 | Doctor (en) | "Amoxicillin 500 three times a day for 5 days, and omeprazole. You can go home." | **Critical `ALG-PEN-01`**: quote from 01:12 + quote from 10:50 + AAAAI/ACAAI 2022 · NICE CG183. **Critical `WORK-CHEST-02`** (discharge, no ECG) and **critical `WORK-CHEST-03`** (no troponin): AHA/ACC 2021 · ESC 2023 · Prajapati 2022. The amoxicillin sentence is held, not spoken. |
| 11:05 | Doctor taps | Acknowledges the cards (no override), says "let's not use amoxicillin", prescribes paracetamol and orders an ECG + troponin. | Alerts resolve and the audit log records both actions. The patient heard only the doctor's words. |

### Example 2: Filipino domestic worker, "kabag" + "pasma", unknown pregnancy, ibuprofen, CT ordered

| t | Speaker | Utterance | System |
|---|---|---|---|
| 00:05 | (triage) | 12-lead ECG already recorded at triage | `WORK-CHEST-04` stays silent: an ECG exists, and since 2026-11-07 *kabag* (tagged `acs`) also needs a chest-pain-group symptom. |
| 00:30 | Patient (tl) | "May kabag po ako, masakit ang tiyan, tsaka nahihilo." → "I have gas pain, my stomach hurts, and I feel dizzy." | Idiom card **tgl-002** (kabag). Symptoms `abdominal_pain`, `dizziness`. |
| 01:50 | Patient (tl) | "Pasma po ang kamay ko, nanginginig." → "My hands have pasma; they tremble." | Idiom card **tgl-001** (pasma): differential incl. thyroid dysfunction, diabetes, overuse; *Ask* about chemicals or cleaning products and gloves. |
| 04:10 | Doctor (en) | "Ibuprofen 800 four times a day, and let's get a CT abdomen." | **Caution `DOSE-IBU-01`** (3200 mg/day; above 2.4 g, at the label max). **Critical `WORK-PREG-01`**: woman aged 29, abdominal pain + dizziness, pregnancy status unknown, CT ordered with no pregnancy test → escalated (NICE NG126). |
| 04:30 | Doctor | Taps the suggested question → Bayan asks in Tagalog: "Kailan po ang huling regla ninyo?" (When was your last period?) + back-translation check | If the answer implies 20 weeks or more, **`PREG-NSAID-01`** fires (FDA 2020), and it becomes critical at 30 weeks or more. |

### Example 3: Bangladeshi labourer in August, "matha gorom", confusion after an outdoor shift

| t | Speaker | Utterance | System |
|---|---|---|---|
| 00:20 | Colleague (bn) | "দুপুরে কাজ করার পর থেকে ও উল্টাপাল্টা কথা বলছে, বমি করেছে" → "Since working at midday he's been talking nonsense and vomited." | Symptoms `confusion`, `vomiting_in_heat`. `patient.heat_exposure = true`. |
| 00:45 | Patient (bn) | "মাথা গরম, শরীর দুর্বল" → "My head is hot, my body is weak." | Idiom cards **ben-003** (*matha gorom*: usually anger, **but in heat context consider literal heat illness**) and **ben-005**. |
| 00:46 | (state) | Only a tympanic temperature recorded | **Critical `WORK-HEAT-01`**: no core (rectal) temperature with CNS signs after heat exposure (ACSM 2023 · WMS 2024 · Qatar heat-stress decision). **Critical `WORK-HEAT-02`**: no active cooling documented ("cool first"). |
| 03:00 | Doctor (en) | "Dehydration. Paracetamol 1 g four times a day, ibuprofen 400 three times a day, oral fluids, home." (Patient's own meds: lisinopril + hydrochlorothiazide.) | **Info `WORK-HEAT-04`**: antipyretics don't treat heat stroke. **Caution `DOSE-PARA-04`**: 4 g/day with heat illness. **Critical `DDI-AKI-01`**: NSAID + ACE inhibitor + thiazide, escalated by heat and dehydration. **Caution `HEAT-MED-01`**. **Caution `WORK-HEAT-03`**: no CK/creatinine/electrolytes. The `WORK-HEAT-*` hits collapse into **one "Heat-illness workup" card** with a checklist; the dose, interaction and heat-medication alerts stay as their own cards. |

---

## 4. Guardrails

### 4.1 Hallucination and translation controls

*Status: 1, 2 and 6 are built; 3, 4 and 5 are designed, not built.*

1. **Literal first, always.** Every patient utterance is shown as source text plus a literal English translation. The clinical note is a separate, labelled layer, so the doctor can always see what was actually said.
2. **Lexicon-grounded notes only.** Idiom cards are built from the matched entry (§1.3); no model writes them. A non-match produces no note. Agent cards must cite a grounding that exists. There is no "the model thinks this is cultural" output.
3. **Confidence flags** *(designed)*. ASR confidence, translation quality estimate and extraction `confidence` are shown as a small dot (green/amber/red). Any **safety-relevant fact** (allergy, drug, dose, pregnancy) extracted below the threshold is shown as *"Unconfirmed: tap to confirm"* and **cannot silence a rule**. The rule still fires, and the card says "based on an unconfirmed extraction".
4. **Back-translation check ("uncertain translation: confirm")** *(designed)*. Doctor → patient sentences that contain numbers, drug names, doses, negations or red-flag instructions are machine back-translated into English *before* TTS. A low similarity score between the original and the back-translation (chrF, or an embedding cosine) triggers a doctor-screen banner: *"Uncertain translation: confirm or rephrase."* Doses are also spoken as digits plus words.
5. **Numbers and negations** *(designed; the wrap-up already rejects care-plan numbers the doctor did not say)*. The extractor and the validator both parse numbers. If they disagree (e.g., "fifteen" vs "fifty"), the dose is set to `null` and the doctor is asked to confirm.
6. **No silent fallbacks.** If the voice service or translation fails, the UI says so ("Voice is offline. Showing text only.", "Please say it again"). Agent failures fall back to deterministic cards; wrap-up failures fall back to a note built from the structured record. Bayan never pretends to understand.

### 4.2 Consent, at the start of every consultation

Spoken by Bayan in the patient's language (and shown on screen) after the doctor taps *Start*. The draft below is subject to legal review:

> "Hello. This tablet is an AI assistant called Bayan. It will translate between you and your doctor and help the doctor write notes. The doctor makes all medical decisions. Your conversation is processed securely; the audio is not saved unless you agree. You can ask to stop it at any time. Do you agree to use it today?"

- **As built**, the Space speaks a shorter consent line in the patient's language (`CONSENT_EN` in `bayan/consult.py`) and waits for a tap on yes or no. It now says the voice is processed and not stored; the Nepali line is a machine draft pending a native check.
- A verbal "yes" is captured as a consent event (timestamp, language, doctor ID), with **no audio stored** *(designed)*. "No" means Bayan turns off, and the doctor uses the usual interpreter service.
- A separate, optional opt-in covers audio retention for quality review.
- Children, and adults who lack capacity, follow the facility's existing consent policy. Bayan does not decide capacity.

### 4.3 Privacy: Qatar PDPPL (Law No. 13 of 2016)

- **Health data is "personal data of a special nature."** Under Article 16 it may be processed only with permission from the competent department and under the controls set by ministerial decision. Violations of Articles 13, 16 and 17 can draw fines of up to QR 5 million ([Clyde & Co summary of PDPPL guidelines](https://www.clydeco.com/en/insights/2021/03/new-regulatory-guidelines-on-the-qatar-persona-1); [The Peninsula, 2016](https://thepeninsulaqatar.com/article/04/11/2016/Up-to-QR5m-fine-for-leaking-personal-data)). The regulator's name has changed over time. **Confirm the current authority and the permission process before any pilot.**
- **As built:** the Space writes each utterance to a temporary WAV only for the call to the voice worker and deletes it right after; output files (PDFs, note text, audio) live in a per-consultation temp folder that is purged on reset and swept after 24 h; the care-plan page is held in memory and expires after 24 h; phone numbers are used to build a link and never stored; tests block every paid call. The voice worker deletes each uploaded utterance right after loading it and runs Gradio `delete_cache`.
- **Design defaults:** no audio retention (streaming buffers only; transcripts kept with the clinical note under the hospital's record policy); data minimisation (the clinical state stores only what the rules need); patient identifiers never sent to the LLM (the encounter uses a random ID); an audit log with no audio.
- **Deployment path.** The **hackathon demo** uses HF Inference Providers plus our own GPU voice worker (a private L4 GPU Space reached with `gradio_client`, because no provider serves Indic ASR/TTS) with **synthetic, scripted consultations only**; no real patient data. **Production** follows a sovereign path: the same open-weights models (ASR, LLM, TTS) on **in-country or on-prem infrastructure** (e.g., HF Inference Endpoints in a compliant region, or self-hosted vLLM/llama.cpp), so health data never leaves Qatar. This is possible precisely because every model is open-weights. A DPIA and a record of processing are needed before a pilot.

### 4.4 Regulatory framing

- **What Bayan AI claims:** clinical decision support for a licensed clinician, who reviews the evidence and decides. **What it does not claim:** diagnosis, autonomous prescribing, or medical-device status. The hackathon build is a research prototype on synthetic data.
- **Qatar:** the Ministry of Public Health (MoPH) held a national health-research ethics workshop on AI in health research in December 2024 with NCSA, QU and HBKU ([QNA](https://www.qna.org.qa/en/News-Area/News/2024-12/01/0057-moph-discusses-ethics-of-use-of-artificial-intelligence-in-health-research)). We did **not** find a published MoPH regulation that specifically governs clinical AI decision support. A pilot would go through MoPH/HMC research ethics (IRB) and the facility's clinical-governance process.
- **International reference:** the US FDA's *Clinical Decision Support Software* guidance (current version dated January 2026, [FDA](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software)) distinguishes non-device CDS under FD&C Act §520(o)(1)(E). A key idea is that the clinician must be able to **independently review the basis** for a recommendation. Bayan's evidence-first cards (quote + rule + source) are built around that idea. Whether *real-time* alerts fall inside the non-device criteria under the 2026 text is **unverified** and would need regulatory advice.

---

## 5. Evaluation plan

**Done so far:** 269 offline tests (`pytest tests`) with fake models, covering the rule engine (incl. the §3 examples), idiom matching, cards and guardrails, the copilot agent with a scripted smolagents model, and the PDF outputs; plus a live golden-path run on the merged code (`scripts/smoke_e2e.py`, 17/17). Fake models test our logic, not model quality. PDF layout is checked by eye.

**Planned test set (not built yet, all synthetic).** 30–40 scripted consultations in Tier-1 languages (Nepali, Hindi/Urdu, Bengali, Tagalog, Malayalam, Arabic), each 2–5 minutes. Native-speaker volunteers read the patient lines and team members read the doctor lines. Each script has a **gold annotation**: clinical state, idioms present, and the set of rule IDs that must fire. Scripts seed specific errors: allergy then cross-reactive prescription, verbal dose slips (e.g., "paracetamol 2 grams four times"), missing workups, and pregnancy-unknown cases. They also include **negative controls**: safe cephalosporin after a mild penicillin rash, statin in pregnancy, and furosemide after a sulfa-antibiotic allergy, all of which must *not* raise critical alerts.

| Component | Metric | How measured | Demo target (aspirational) |
|---|---|---|---|
| Extraction | Field-level precision/recall/F1 for allergies, meds (drug, dose, frequency), symptoms, investigations, disposition | Compare extractor JSON with gold | F1 ≥ 0.85 on meds/allergies |
| Safety Sentinel | **Alert precision and recall** per family, end-to-end from audio | Fired rule IDs vs gold rule IDs | Recall ≥ 0.9 on critical; precision ≥ 0.8 |
| Safety Sentinel | Rule-only precision/recall on the **gold** state | Isolates rule bugs from extraction errors | 1.0 (rules are deterministic) |
| Alert burden | Alerts per encounter; % grouped; time from trigger to display | Logs | ≤ 3 visible cards per encounter |
| Idiom interpreter | Retrieval recall@2 and false-match rate at τ | Gold idiom labels | Recall@2 ≥ 0.8; false matches ≤ 5% |
| Idiom interpreter | **Note acceptance** (✓ rate) and harmful-note rate | Clinician reviewers rate each card | ✓ ≥ 70%; harmful = 0 |
| Translation | **Adequacy and fluency by native speakers** (1–5 DA-style) on doctor → patient instructions | Two raters per language | Mean adequacy ≥ 4 on medication instructions |
| Translation | **chrF** ([Popović 2015](https://aclanthology.org/W15-3049/), via [sacreBLEU](https://github.com/mjpost/sacrebleu)) and **COMET** ([Rei et al. 2020](https://aclanthology.org/2020.emnlp-main.213/); [`Unbabel/wmt22-comet-da`](https://huggingface.co/Unbabel/wmt22-comet-da), Apache-2.0) against reference translations; **back-translation chrF** as a reference-free proxy | Scripts | Track per language; no fixed target (low-resource languages vary) |
| Safety of speech | Number and negation fidelity in TTS output | Manual check of all dose sentences | 100% of doses correct, or flagged as uncertain |

Efficiency (a judging criterion): the rule engine and the idiom matcher run on CPU at negligible cost. Paid LLM calls are translation, one extraction call per think run (courtesy turns skipped, a doctor's plain question batched with the answer) and an agent step only when something is new. Measured on the 9-turn golden path: ≈ $0.015 for extraction + copilot agent, ≈ $0.004 for the wrap-up (excluding talk-loop translation and GPU-worker hours). Every call's tokens and cost are counted in `llm.USAGE` ([07](07-compute-budget-and-efficiency.md)).

---

## 6. Limitations (read before demoing)

- **No clinician on the team, no native-speaker review yet.** All thresholds and mappings are literature-derived and **unreviewed**. The demo must say so. `verification: threshold_is_design_choice` marks numbers we chose ourselves.
- **Lexicon gaps.** We could not find citable sources for several idioms the brief asked about: Malayalam *neerkettu* and *vayu*; Nepali *ritto* and *jhamjhamaunu* (the literature uses *jham-jham*); Tagalog *bughat* in Tagalog proper (sourced as Cebuano, with Tagalog *binat*); Sinhala idioms; Swahili beyond five entries (*presha* is sourced only indirectly); Gulf-specific Arabic phrasing (the main source is Syrian Arabic); Egyptian and Sudanese idioms; Tamil beyond three entries; medication-instruction idioms ("1-0-1", "after food") and suicidal-ideation phrasings in Nepali, Hindi and Tagalog. Bengali *buk dhorfor*, Hindi *dil ghabrana*, and most Tagalog symptom words are `community_reported` only. Several native-script spellings (Punjabi, Tamil) need native-speaker confirmation.
- **Likelihoods are ordinal and uncalibrated.** "High/medium/low" reflects the sources' emphasis, not prevalence among Qatar's patients.
- **Dose rules are adult-only.** There are no paediatric, renal-adjusted (except the few explicit eGFR rules) or weight-based dosing rules beyond paracetamol under 50 kg. Acute-asthma, oncology and ICU dosing are out of scope.
- **Small interaction set.** Twelve interaction rules are an illustration, not a formulary-grade DDI database. A production system should license a maintained knowledge base and keep these rules only as a transparent overlay.
- **Extraction is the weakest link.** A missed allergy means a missed alert. That is why allergies and prescribed drugs are also taken synchronously from the talk loop's translation JSON, and why rule-only evaluation is separate from end-to-end evaluation. "Unconfirmed" chips for low-confidence facts are designed, not built.
- **Thin live evidence.** One live scenario (the golden path); everything else runs on fake models.
- **Guideline provenance.** Sources are mostly US/UK/European (FDA, NICE, AHA/ACC, ESC) because they are openly accessible. HMC/MoPH local protocols may differ and must take precedence.
- **Culture is not destiny.** Idiom cards describe possibilities. They must not stereotype a patient by nationality, and the UI never infers ethnicity from accent. `ancestry_region` is set only when the patient states it or it is in the record.

---

## 7. Sources

Accessed or verified on 2026-11-06. FDA label links use DailyMed set IDs retrieved through the openFDA API.

**Idioms of distress and cultural psychiatry**
- Nichter M. Idioms of distress revisited. *Cult Med Psychiatry* 2010;34(2):401–416. https://experts.arizona.edu/en/publications/idioms-of-distress-revisited/
- Kohrt BA, Hruschka DJ. Nepali concepts of psychological trauma. *Cult Med Psychiatry* 2010. https://pmc.ncbi.nlm.nih.gov/articles/PMC3819627/
- Kohrt BA, Harper I. Navigating diagnoses: mind–body relations, mental health, and stigma in Nepal. *Cult Med Psychiatry* 2008. https://pmc.ncbi.nlm.nih.gov/articles/PMC3869091/
- Kaiser BN et al. "Thinking too much": a systematic review of a common idiom of distress. *Soc Sci Med* 2015. https://pmc.ncbi.nlm.nih.gov/articles/PMC4689615/
- Weaver LJ, Karasz A. "Tension" and distress in South Asia: a systematic literature review. *SSM – Mental Health* 2022. https://doi.org/10.1016/j.ssmmh.2022.100092
- Wahid SS et al. Tension and other idioms of distress among slum-dwelling young men (Bangladesh). *Cult Med Psychiatry* 2021. https://pmc.ncbi.nlm.nih.gov/articles/PMC9034992/
- Krause IB. Sinking heart: a Punjabi communication of distress. *Soc Sci Med* 1989. https://pubmed.ncbi.nlm.nih.gov/2756440/
- Sumathipala A et al. Culture-bound syndromes: the story of dhat syndrome. *Br J Psychiatry* 2004. https://pubmed.ncbi.nlm.nih.gov/14990517/
- Hassan G et al. *Culture, Context and the Mental Health and Psychosocial Wellbeing of Syrians.* UNHCR 2015. https://www.unhcr.org/sites/default/files/legacy-pdf/55f6b90f9.pdf
- Lambert JE et al. "Let it stay in the heart": distress among Syrian refugees in Jordan. *Front Psychol* 2024. https://doi.org/10.3389/fpsyg.2024.1456201
- Affleck W et al. Walking Corpse Syndrome: a trauma-related idiom of distress amongst Sri Lankan Tamils. *Transcult Psychiatry* 2022. https://pmc.ncbi.nlm.nih.gov/articles/PMC9388945/
- Palis FG et al. Our farmers at risk: behaviour and belief system in pesticide safety (pasma). *J Public Health* 2006. https://pubmed.ncbi.nlm.nih.gov/16436451/
- Pasma (overview, cites Tan 1987). https://en.wikipedia.org/wiki/Pasma · Cuyonon concept of pasma: https://scholarspace.manoa.hawaii.edu/items/61328dc2-e7f4-4094-bd73-ea1c0e21b096
- Millondaga (bughat, Visayan postpartum practices): https://ojs.upmin.edu.ph/index.php/jcsh/article/view/60 · Philippine TKDL on bughat: https://www.tkdlph.com/index.php/ct-menu-item-3/ct-menu-item-15/conditions-illnesses/zamboanga-salambuyan/40-bughat-after-giving-birth
- Osman A et al. 2020 (Ethiopian febrile illness "mich"). https://pmc.ncbi.nlm.nih.gov/articles/PMC7647763/
- Trollope-Kumar K. Cultural and biomedical meanings of the complaint of leukorrhea in South Asian women. *Trop Med Int Health* 2001. https://doi.org/10.1046/j.1365-3156.2001.00699.x
- Population Council. Addressing Gupt Rog: narrative prevention counselling for STI/HIV prevention. https://knowledgecommons.popcouncil.org/departments_sbsr-hiv/571
- Lasco G et al. *Nasa dugo* ('It's in the blood'): lay conceptions of hypertension in the Philippines. *BMJ Glob Health* 2020. https://pmc.ncbi.nlm.nih.gov/articles/PMC7351273/
- Gaw AC et al. Unraveling the enigma of bangungut (SUNDS) in the Philippines. *Philipp J Intern Med* 2011. https://pmc.ncbi.nlm.nih.gov/articles/PMC3404490/
- Greene MC et al. Why local concepts matter: cultural expressions of distress among Congolese women in Nyarugusu refugee camp (Tanzania). *Transcult Psychiatry* 2022. https://doi.org/10.1177/13634615221122626
- Makundi EA et al. Role of traditional healers in the management of severe malaria (degedege) among children below five, Kilosa and Handeni, Tanzania. *Malar J* 2006. https://pmc.ncbi.nlm.nih.gov/articles/PMC1540433/
- Temu TM et al. Lay beliefs about hypertension among HIV-infected adults in Kenya. *Open Heart* 2017. https://pmc.ncbi.nlm.nih.gov/articles/PMC5384458/
- Rekhta Urdu dictionary (Hindi/Urdu idioms, one URL per entry) and Wiktionary (Tamil, Malayalam, Bengali, Tagalog, Swahili words) for `community_reported` entries.
- Dictionaries and lay health sources for `community_reported` entries are listed per entry in `idiom_lexicon.json` (Wiktionary, Rekhta, TagalogNow, Unilab, Medanta-bn, Prothom Alo, Asianet News Malayalam, Star Health, Lokmanya Hospitals).

**Qatar context**
- Prajapati et al. *J Nepal Health Res Counc* 2022 (87.9% of STEMI patients had typical chest pain; 23.8% thought it was cardiac). https://jnhrc.com.np/index.php/jnhrc/article/view/1217
- Pradhan B et al. Heat stress impacts on cardiac mortality in Nepali migrant workers in Qatar. *Cardiology* 2019. https://doi.org/10.1159/000500853 (heat-exposure context only; no longer cited by the rules)
- Bansal D et al. Imported malaria cases and potential local transmission in Qatar. *Eur J Public Health* 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC11725959/
- ILO: Qatar's Ministerial Decision on Heat Stress (2021). https://www.ilo.org/resource/qatars-ministerial-decision-heat-stress
- Racinais S et al. IOC consensus on sport events in the heat. *BJSM* 2023. https://pmc.ncbi.nlm.nih.gov/articles/PMC9811094/

**Clinical guidelines and labels**
- Gulati M et al. 2021 AHA/ACC chest pain guideline. https://doi.org/10.1161/CIR.0000000000001029
- Byrne RA et al. 2023 ESC Guidelines for acute coronary syndromes. https://doi.org/10.1093/eurheartj/ehad191
- Roberts WO et al. ACSM consensus on exertional heat illness. 2023. https://doi.org/10.1249/JSR.0000000000001058
- Wilderness Medical Society heat-illness guidelines 2019 (https://pubmed.ncbi.nlm.nih.gov/31221601/) and 2024 update (https://doi.org/10.1177/10806032241227924)
- Do TP et al. SNNOOP10 red flags for secondary headache. *Neurology* 2019. https://pmc.ncbi.nlm.nih.gov/articles/PMC6340385/
- Khan DA et al. Drug allergy: a 2022 practice parameter update. *JACI* 2022. https://doi.org/10.1016/j.jaci.2022.08.028
- Shenoy ES et al. Evaluation and management of penicillin allergy. *JAMA* 2019. https://pubmed.ncbi.nlm.nih.gov/30644987/
- Strom BL et al. Sulfonamide antibiotic vs non-antibiotic cross-reactivity. *NEJM* 2003. https://pubmed.ncbi.nlm.nih.gov/14573734/
- Kowalski ML et al. NSAID hypersensitivity classification. *Allergy* 2013. https://pubmed.ncbi.nlm.nih.gov/24117484/
- NICE: CG183 drug allergy · CG150 headache · NG126 ectopic pregnancy · CG174 IV fluids · NG225 self-harm · NG51 sepsis · CG109 TLoC · NG128 stroke (https://www.nice.org.uk/guidance/…)
- WHO Guidelines for malaria. https://www.who.int/publications/i/item/guidelines-for-malaria
- CDC Heat and Medications: Guidance for Clinicians. https://www.cdc.gov/heat-health/hcp/clinical-guidance/heat-and-medications-guidance-for-clinicians.html
- FDA: NSAIDs at 20 weeks or later in pregnancy (2020); statins in pregnancy (2021). Links are in `safety_rules.json`.
- EMA metoclopramide referral (2013) · Resuscitation Council UK anaphylaxis emergency treatment. Links are in `safety_rules.json`.
- FDA labels (DailyMed) for every drug cited in `safety_rules.json` → `source_urls`.

**Safety-alert design and evaluation**
- Flores G et al. Errors in medical interpretation. *Pediatrics* 2003. https://pubmed.ncbi.nlm.nih.gov/12509547/
- van der Sijs H et al. Overriding of drug safety alerts in CPOE. *JAMIA* 2006. https://pubmed.ncbi.nlm.nih.gov/16357358/
- Ancker JS et al. Workload, complexity and repeated alerts and alert fatigue. *BMC Med Inform Decis Mak* 2017. https://pubmed.ncbi.nlm.nih.gov/28395667/
- Popović M. chrF. WMT 2015. https://aclanthology.org/W15-3049/ · Rei R et al. COMET. EMNLP 2020. https://aclanthology.org/2020.emnlp-main.213/

**Privacy and regulation**
- Qatar Law No. 13 of 2016 (PDPPL), regulatory guidelines summary (Clyde & Co). https://www.clydeco.com/en/insights/2021/03/new-regulatory-guidelines-on-the-qatar-persona-1
- MoPH national workshop on AI ethics in health research (QNA, Dec 2024). https://www.qna.org.qa/en/News-Area/News/2024-12/01/0057-moph-discusses-ethics-of-use-of-artificial-intelligence-in-health-research
- FDA Clinical Decision Support Software guidance. https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software
