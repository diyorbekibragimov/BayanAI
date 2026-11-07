# Bayan simulation run 20261107-073316-ab-gptoss

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 10 · languages: 6 (bn, es, ja, ka, ne, ru) · wall 111s
- **checks passed: 164/165 (99%)** · scenarios fully passing: 9/10 · expected gaps confirmed: 1 (closed: 1)
- clinical checks (hold/flag/suggest/no-flag): 21/22 (95%)
- false-positive traps tripped: 0/8 (0%)
- cost: total $0.1096 · per consultation median $0.0108 · max $0.0137
- latency (median, s from the start of the turn that preceded the card): rule cards 4.7 · agent cards 6.1 · lexicon/fallback 0.9 · translate+gate per turn 0.9 · wrap-up 6.6
- copilot: 44 think runs, 24 agent runs (0 failed/timed out); wrap-up modes: agent×10

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| allergy | 1 | 1 | 23/23 | 3/3 | 0 |
| chest | 1 | 1 | 19/19 | 4/4 | 0 |
| interactions | 1 | 1 | 13/13 | 0/0 | 0 |
| quiet | 2 | 2 | 33/33 | 7/7 | 0 |
| redflags | 5 | 4 | 76/77 | 7/8 | 1 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| care_plan | 2 | 2 |
| flag | 10 | 11 |
| hold | 1 | 1 |
| no_flag | 5 | 5 |
| no_hold | 3 | 3 |
| pdf | 118 | 118 |
| run | 20 | 20 |
| state | 3 | 3 |
| suggest | 2 | 2 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| alg-08-idiom-allergy-cephalexin | ne/en | PASS | 0 | cephalexin:ALG-PEN-02 | ALG-PEN-02 | 0.0103 | 29.0 |
| chest-01-gyastrik-discharge | ne/en | PASS | 0 | - | WORK-CHEST-02, WORK-CHEST-03 | 0.0119 | 33.5 |
| ddi-04-metformin-contrast | bn/en | PASS | 0 | - | - | 0.0106 | 30.5 |
| quiet-01-cold-paracetamol | ne/en | PASS | 0 | - | - | 0.0131 | 31.1 |
| quiet-04-spanish-gases-trap | es/en | PASS | 0 | - | - | 0.0111 | 27.6 |
| rf-02-black-stools-ibuprofen | ne/en | PASS | 0 | - | - | 0.0103 | 27.2 |
| rf-04-bengali-wish-not-wake | bn/en | FAIL | 1 | - | - | 0.0089 | 23.0 |
| rf-05-russian-better-without-me | ru/en | PASS | 0 | - | WORK-SUICIDE-01 | 0.0089 | 22.1 |
| rf-06-georgian-stroke-signs | ka/en | PASS | 0 | - | WORK-STROKE-01 | 0.0111 | 25.1 |
| rf-07-japanese-syncope-discharge | ja/en | PASS | 0 | - | WORK-TLOC-01 | 0.0137 | 29.2 |

## Failures (with evidence)

**rf-04-bengali-wish-not-wake** — 'Mon kharap' and a passive death wish ('sleep and never wake up')
- [flag] WORK-SUICIDE-01 severity=critical by turn 3 — WORK-SUICIDE-01@t1 caution

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)

- ddi-04-metformin-contrast: missed/observation/ask ~metformin|contrast|kidney|renal|creatinine → **GAP-CLOSED** — No metformin + iodinated contrast rule (hold metformin, check eGFR). Recommend a DDI/WORK rule; the agent may still catch it.
- rf-02-black-stools-ibuprofen: card source=rules ~bleed|black|melaena → **GAP** — No rule for melaena / upper-GI bleed on NSAIDs (stop NSAID, Hb, urgent review). Recommend a WORK-GIB rule.

## PDF review images

- alg-08-idiom-allergy-cephalexin (ne): png/alg-08-idiom-allergy-cephalexin_patient_p1.png · png/alg-08-idiom-allergy-cephalexin_doctor_p1.png
- chest-01-gyastrik-discharge (ne): png/chest-01-gyastrik-discharge_patient_p1.png · png/chest-01-gyastrik-discharge_doctor_p1.png
- ddi-04-metformin-contrast (bn): png/ddi-04-metformin-contrast_patient_p1.png · png/ddi-04-metformin-contrast_doctor_p1.png
- quiet-01-cold-paracetamol (ne): png/quiet-01-cold-paracetamol_patient_p1.png · png/quiet-01-cold-paracetamol_doctor_p1.png
- quiet-04-spanish-gases-trap (es): png/quiet-04-spanish-gases-trap_patient_p1.png · png/quiet-04-spanish-gases-trap_doctor_p1.png
- rf-02-black-stools-ibuprofen (ne): png/rf-02-black-stools-ibuprofen_patient_p1.png · png/rf-02-black-stools-ibuprofen_doctor_p1.png
- rf-04-bengali-wish-not-wake (bn): png/rf-04-bengali-wish-not-wake_patient_p1.png · png/rf-04-bengali-wish-not-wake_doctor_p1.png
- rf-05-russian-better-without-me (ru): png/rf-05-russian-better-without-me_patient_p1.png · png/rf-05-russian-better-without-me_doctor_p1.png
- rf-06-georgian-stroke-signs (ka): png/rf-06-georgian-stroke-signs_patient_p1.png · png/rf-06-georgian-stroke-signs_doctor_p1.png
- rf-07-japanese-syncope-discharge (ja): png/rf-07-japanese-syncope-discharge_patient_p1.png · png/rf-07-japanese-syncope-discharge_doctor_p1.png
