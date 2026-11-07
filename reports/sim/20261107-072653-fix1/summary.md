# Bayan simulation run 20261107-072653-fix1

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 7 · languages: 5 (bn, ko, ne, tr, ur) · wall 62s
- **checks passed: 146/146 (100%)** · scenarios fully passing: 7/7 · expected gaps confirmed: 0 (closed: 0)
- clinical checks (hold/flag/suggest/no-flag): 18/18 (100%)
- false-positive traps tripped: 0/7 (0%)
- cost: total $0.0844 · per consultation median $0.0107 · max $0.0158
- latency (median, s from the start of the turn that preceded the card): rule cards 1.1 · agent cards 6.8 · lexicon/fallback 0.9 · translate+gate per turn 0.9 · wrap-up 7.8
- copilot: 28 think runs, 17 agent runs (0 failed/timed out); wrap-up modes: agent×6, agent+fallback×1

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| allergy | 4 | 4 | 96/96 | 13/13 | 0 |
| dose | 1 | 1 | 16/16 | 1/1 | 0 |
| heat | 2 | 2 | 34/34 | 4/4 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| care_plan | 9 | 9 |
| flag | 7 | 7 |
| hold | 4 | 4 |
| no_flag | 3 | 3 |
| no_hold | 4 | 4 |
| pdf | 93 | 93 |
| run | 14 | 14 |
| state | 12 | 12 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| alg-01-augmentin-brand | ne/en | PASS | 0 | co-amoxiclav:ALG-PEN-01 | ALG-PEN-01 | 0.0145 | 37.0 |
| alg-03-sulfa-furosemide-trap | ur/en | PASS | 0 | - | - | 0.0158 | 38.9 |
| alg-08-idiom-allergy-cephalexin | ne/en | PASS | 0 | cephalexin:ALG-PEN-02 | ALG-PEN-02 | 0.0104 | 28.6 |
| alg-10-speak-anyway-override | ko/en | PASS | 0 | amoxicillin:ALG-PEN-01 | ALG-PEN-01 | 0.0105 | 30.4 |
| dose-09-tramadol-qds-plus-prn | tr/en | PASS | 0 | tramadol:DOSE-TRAM-01 | DOSE-TRAM-01 | 0.0098 | 22.8 |
| heat-01-collapse-site-brain-hot | ne/en | PASS | 0 | - | WORK-HEAT-01 | 0.0126 | 30.8 |
| heat-02-matha-gorom-diclofenac | bn/en | PASS | 0 | - | - | 0.0107 | 24.0 |

## Failures (with evidence)

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)


## PDF review images

- alg-01-augmentin-brand (ne): png/alg-01-augmentin-brand_patient_p1.png · png/alg-01-augmentin-brand_doctor_p1.png
- alg-03-sulfa-furosemide-trap (ur): png/alg-03-sulfa-furosemide-trap_patient_p1.png · png/alg-03-sulfa-furosemide-trap_doctor_p1.png
- alg-08-idiom-allergy-cephalexin (ne): png/alg-08-idiom-allergy-cephalexin_patient_p1.png · png/alg-08-idiom-allergy-cephalexin_doctor_p1.png
- alg-10-speak-anyway-override (ko): png/alg-10-speak-anyway-override_patient_p1.png · png/alg-10-speak-anyway-override_doctor_p1.png
- dose-09-tramadol-qds-plus-prn (tr): png/dose-09-tramadol-qds-plus-prn_patient_p1.png · png/dose-09-tramadol-qds-plus-prn_doctor_p1.png
- heat-01-collapse-site-brain-hot (ne): png/heat-01-collapse-site-brain-hot_patient_p1.png · png/heat-01-collapse-site-brain-hot_doctor_p1.png
- heat-02-matha-gorom-diclofenac (bn): png/heat-02-matha-gorom-diclofenac_patient_p1.png · png/heat-02-matha-gorom-diclofenac_doctor_p1.png
