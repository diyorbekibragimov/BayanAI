# Bayan simulation run smoke-batch

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 4 · languages: 4 (hi, ka, ko, sw) · wall 43s
- **checks passed: 64/66 (97%)** · scenarios fully passing: 3/4 · expected gaps confirmed: 0 (closed: 0)
- clinical checks (hold/flag/suggest/no-flag): 6/6 (100%)
- false-positive traps tripped: 0/1 (0%)
- cost: total $0.0471 · per consultation median $0.0117 · max $0.0143
- latency (median, s from the start of the turn that preceded the card): rule cards 1.0 · agent cards 6.0 · lexicon/fallback 0.0 · translate+gate per turn 0.8 · wrap-up 8.3
- copilot: 20 think runs, 11 agent runs (0 failed/timed out); wrap-up modes: agent×4

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| allergy | 1 | 0 | 17/19 | 1/1 | 0 |
| chest | 1 | 1 | 16/16 | 2/2 | 0 |
| dose | 1 | 1 | 17/17 | 2/2 | 0 |
| redflags | 1 | 1 | 14/14 | 1/1 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| care_plan | 0 | 1 |
| flag | 3 | 3 |
| hold | 2 | 2 |
| no_flag | 1 | 1 |
| pdf | 47 | 48 |
| run | 8 | 8 |
| state | 3 | 3 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| alg-10-speak-anyway-override | ko/en | FAIL | 2 | amoxicillin:ALG-PEN-01 | ALG-PEN-01 | 0.0095 | 30.0 |
| chest-04-timer-10min-no-ecg | hi/en | PASS | 0 | - | - | 0.0143 | 42.4 |
| dose-07-child-16kg-mother | sw/en | PASS | 0 | paracetamol:DOSE-PARA-03 | DOSE-PARA-03 | 0.0127 | 36.9 |
| rf-06-georgian-stroke-signs | ka/en | PASS | 0 | - | WORK-STROKE-01 | 0.0106 | 34.4 |

## Failures (with evidence)

**alg-10-speak-anyway-override** — Penicillin hives, doctor overrides the hold ('speak it anyway') for amoxicillin
- [care_plan] care plan lists amoxicillin — medicines: 
- [pdf] doctor PDF records the held instruction — 

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)


## PDF review images

- alg-10-speak-anyway-override (ko): png/alg-10-speak-anyway-override_patient_p1.png · png/alg-10-speak-anyway-override_doctor_p1.png
- chest-04-timer-10min-no-ecg (hi): png/chest-04-timer-10min-no-ecg_patient_p1.png · png/chest-04-timer-10min-no-ecg_doctor_p1.png
- dose-07-child-16kg-mother (sw): png/dose-07-child-16kg-mother_patient_p1.png · png/dose-07-child-16kg-mother_doctor_p1.png
- rf-06-georgian-stroke-signs (ka): png/rf-06-georgian-stroke-signs_patient_p1.png · png/rf-06-georgian-stroke-signs_doctor_p1.png
