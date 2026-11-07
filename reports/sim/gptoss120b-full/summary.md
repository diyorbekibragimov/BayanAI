# Bayan simulation run gptoss120b-full

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 38 · languages: 14 (bn, es, fr, hi, id, ko, ml, ne, ru, sw, ta, tl, tr, ur) · wall 43s
- **checks passed: 718/727 (99%)** · scenarios fully passing: 31/38 · expected gaps confirmed: 2 (closed: 1)
- clinical checks (hold/flag/suggest/no-flag): 91/97 (94%)
- false-positive traps tripped: 0/44 (0%)
- cost: total $0.4490 · per consultation median $0.0114 · max $0.0180
- latency (median, s from the start of the turn that preceded the card): rule cards 0.9 · agent cards 5.7 · lexicon/fallback 0.9 · translate+gate per turn 0.9 · wrap-up 6.3
- copilot: 163 think runs, 104 agent runs (0 failed/timed out); wrap-up modes: agent×38

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| allergy | 12 | 8 | 270/276 | 31/34 | 1 |
| chest | 7 | 7 | 125/125 | 22/22 | 0 |
| dose | 11 | 10 | 188/189 | 23/24 | 1 |
| heat | 5 | 3 | 76/78 | 9/11 | 0 |
| interactions | 3 | 3 | 59/59 | 6/6 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| care_plan | 33 | 35 |
| flag | 33 | 36 |
| hold | 13 | 16 |
| no_flag | 22 | 22 |
| no_hold | 22 | 22 |
| pdf | 477 | 477 |
| run | 76 | 76 |
| state | 41 | 42 |
| suggest | 1 | 1 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| alg-03-sulfa-furosemide-trap | ur/en | FAIL | 1 | - | - | 0.0150 | 37.1 |
| alg-02-sulfa-class-bactrim | bn/en | PASS | 0 | co-trimoxazole:ALG-SULFA-01 | ALG-SULFA-01 | 0.0142 | 37.1 |
| alg-04-brufen-aspirin-asthma | ml/en | PASS | 0 | ibuprofen:ALG-NSAID-01 | ALG-NSAID-01 | 0.0141 | 38.8 |
| alg-01-augmentin-brand | ne/en | FAIL | 1 | - | ALG-PEN-01 | 0.0159 | 41.9 |
| alg-05-same-drug-paracetamol | tl/en | PASS | 0 | - | - | 0.0145 | 32.4 |
| alg-08-idiom-allergy-cephalexin | ne/en | FAIL | 3 | - | - | 0.0125 | 28.0 |
| alg-07-denied-then-remembered | sw/en | PASS | 0 | - | ALG-PEN-01 | 0.0144 | 33.5 |
| alg-06-late-allergy-after-rx | hi/en | PASS | 0 | - | ALG-PEN-01 | 0.0166 | 37.5 |
| alg-10-speak-anyway-override | ko/en | FAIL | 1 | amoxicillin:ALG-PEN-01 | ALG-PEN-01 | 0.0087 | 23.2 |
| alg-11-ceftriaxone-mild-pen-trap | es/en | PASS | 0 | - | - | 0.0089 | 22.0 |
| alg-09-withdraw-then-represcribe | ta/en | PASS | 0 | amoxicillin:ALG-PEN-01, amoxicillin:ALG-PEN-01 | ALG-PEN-01 | 0.0100 | 25.4 |
| alg-12-arabic-doctor-augmentin | ur/ar | PASS | 0 | co-amoxiclav:ALG-PEN-01 | ALG-PEN-01 | 0.0121 | 28.2 |
| chest-01-gyastrik-discharge | ne/en | PASS | 0 | - | WORK-CHEST-02, WORK-CHEST-03 | 0.0115 | 26.2 |
| chest-03-seene-mein-jalan-arm-sweat | ur/en | PASS | 0 | - | WORK-CHEST-02, WORK-CHEST-03 | 0.0113 | 26.8 |
| chest-02-kabag-ecg-ordered | tl/en | PASS | 0 | - | - | 0.0180 | 40.3 |
| chest-04-timer-10min-no-ecg | hi/en | PASS | 0 | - | - | 0.0142 | 35.7 |
| chest-05-korean-jaw-sweat-admit | ko/en | PASS | 0 | - | - | 0.0119 | 28.9 |
| chest-06-arabic-doctor-gastric | bn/ar | PASS | 0 | - | WORK-CHEST-02, WORK-CHEST-03 | 0.0122 | 29.3 |
| dose-01-para-every-4h | ne/en | PASS | 0 | paracetamol:DOSE-PARA-01 | DOSE-PARA-01 | 0.0079 | 20.3 |
| chest-07-ecg-normal-chest-wall | ta/en | PASS | 0 | - | - | 0.0167 | 36.0 |
| dose-03-ibuprofen-800-qid | bn/en | PASS | 0 | - | - | 0.0104 | 25.4 |
| dose-02-two-paracetamol-brands | hi/en | PASS | 0 | - | - | 0.0134 | 30.5 |
| dose-04-brufen-600-q4h | ml/en | PASS | 0 | ibuprofen:DOSE-IBU-01 | DOSE-IBU-01, DOSE-IBU-02 | 0.0098 | 23.8 |
| dose-05-diclofenac-75-tds | tl/en | PASS | 0 | diclofenac:DOSE-DICLO-01 | DOSE-DICLO-01 | 0.0092 | 20.5 |
| dose-06-levothyroxine-mg-mcg | ru/en | PASS | 0 | levothyroxine:DOSE-LEVO-01 | DOSE-LEVO-01 | 0.0088 | 20.2 |
| dose-08-prn-up-to-8-tabs | id/en | PASS | 0 | - | - | 0.0092 | 21.6 |
| dose-07-child-16kg-mother | sw/en | PASS | 0 | paracetamol:DOSE-PARA-03 | DOSE-PARA-03 | 0.0114 | 27.6 |
| dose-10-metformin-3g | tr/en | PASS | 0 | - | - | 0.0087 | 20.1 |
| dose-09-tramadol-qds-plus-prn | tr/en | FAIL | 1 | - | - | 0.0106 | 25.6 |
| dose-11-amlodipine-bd | fr/en | PASS | 0 | - | - | 0.0097 | 21.6 |
| heat-01-collapse-site-brain-hot | ne/en | FAIL | 1 | - | - | 0.0109 | 27.0 |
| heat-03-furosemide-outdoor | ml/en | PASS | 0 | - | - | 0.0081 | 19.4 |
| heat-02-matha-gorom-diclofenac | bn/en | FAIL | 1 | - | - | 0.0096 | 20.5 |
| heat-04-ramadan-metformin | ur/en | PASS | 0 | - | - | 0.0111 | 25.6 |
| ddi-01-warfarin-diclofenac | ml/en | PASS | 0 | warfarin+diclofenac:DDI-WARF-01 | DDI-WARF-01 | 0.0100 | 24.9 |
| heat-05-pasma-trap | tl/en | PASS | 0 | - | - | 0.0127 | 29.4 |
| ddi-02-triple-whammy-heat | ne/en | PASS | 0 | ibuprofen+lisinopril+hydrochlorothiazide:DDI-AKI-01 | DDI-AKI-01 | 0.0148 | 32.1 |
| ddi-03-sertraline-tramadol | ru/en | PASS | 0 | - | - | 0.0098 | 22.2 |

## Failures (with evidence)

**alg-03-sulfa-furosemide-trap** — Sulfa-antibiotic allergy, furosemide prescribed (non-antibiotic sulfonamide, info only, must not hold)
- [care_plan] care plan lists furosemide — medicines: 

**alg-01-augmentin-brand** — Penicillin rash, doctor prescribes Augmentin by brand name, then switches to azithromycin
- [hold] held: co-amoxiclav ALG-PEN-01 at turn 4 — no holds

**alg-08-idiom-allergy-cephalexin** — Allergy told only as 'my body swelled, lips too' with 'that red amoxi capsule'; cephalexin next (R1 side chain)
- [hold] held: cephalexin ALG-PEN-02/ALG-CEPH-01 at turn 2 — no holds
- [flag] ALG-PEN-02 severity=critical — ALG-DOC-01@t1 info; ALG-PEN-02@t2 caution
- [state] prescribed excludes cephalexin — prescribed=['cephalexin', 'clindamycin']

**alg-10-speak-anyway-override** — Penicillin hives, doctor overrides the hold ('speak it anyway') for amoxicillin
- [care_plan] care plan lists amoxicillin — medicines: 

**dose-09-tramadol-qds-plus-prn** — Tramadol 100 mg QDS plus 100 mg at night if needed (500 mg/day)
- [hold] held: tramadol DOSE-TRAM-01 at turn 2 — no holds

**heat-01-collapse-site-brain-hot** — Worker collapsed on site, confused and vomiting, 'dimaag taatyo'; no core temperature at first
- [flag] WORK-HEAT-01 severity=critical by turn 3 — no rule fired

**heat-02-matha-gorom-diclofenac** — Bengali labourer, 'matha gorom', dark urine, little water; doctor gives diclofenac
- [flag] HEAT-MED-01 — no rule fired

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)

- alg-05-same-drug-paracetamol: held: paracetamol  → **GAP** — No rule matches an allergy to the SAME non-class drug (paracetamol, metronidazole, ciprofloxacin...). ALG-* rules are class-based only.
- dose-02-two-paracetamol-brands: held: paracetamol  at turn 4 → **GAP** — No rule sums paracetamol across products/brands (Adol + Panadol Extra = 7 g/day). Both normalise to paracetamol and the second replaces the first in prescribed_meds, so the daily total is never computed.
- heat-04-ramadan-metformin: ask/observation/missed ~fast|ramadan|iftar|suhoor|sehri → **GAP-CLOSED** — No rule adapts dosing to Ramadan fasting (schedule doses at suhoor/iftar, hypoglycaemia risk). The agent may catch the contradiction the patient raises.

## PDF review images

- alg-03-sulfa-furosemide-trap (ur): png/alg-03-sulfa-furosemide-trap_patient_p1.png · png/alg-03-sulfa-furosemide-trap_doctor_p1.png
- alg-02-sulfa-class-bactrim (bn): png/alg-02-sulfa-class-bactrim_patient_p1.png · png/alg-02-sulfa-class-bactrim_doctor_p1.png
- alg-04-brufen-aspirin-asthma (ml): png/alg-04-brufen-aspirin-asthma_patient_p1.png · png/alg-04-brufen-aspirin-asthma_doctor_p1.png
- alg-01-augmentin-brand (ne): png/alg-01-augmentin-brand_patient_p1.png · png/alg-01-augmentin-brand_doctor_p1.png
- alg-05-same-drug-paracetamol (tl): png/alg-05-same-drug-paracetamol_patient_p1.png · png/alg-05-same-drug-paracetamol_doctor_p1.png
- alg-08-idiom-allergy-cephalexin (ne): png/alg-08-idiom-allergy-cephalexin_patient_p1.png · png/alg-08-idiom-allergy-cephalexin_doctor_p1.png
- alg-07-denied-then-remembered (sw): png/alg-07-denied-then-remembered_patient_p1.png · png/alg-07-denied-then-remembered_doctor_p1.png
- alg-06-late-allergy-after-rx (hi): png/alg-06-late-allergy-after-rx_patient_p1.png · png/alg-06-late-allergy-after-rx_doctor_p1.png
- alg-10-speak-anyway-override (ko): png/alg-10-speak-anyway-override_patient_p1.png · png/alg-10-speak-anyway-override_doctor_p1.png
- alg-11-ceftriaxone-mild-pen-trap (es): png/alg-11-ceftriaxone-mild-pen-trap_patient_p1.png · png/alg-11-ceftriaxone-mild-pen-trap_doctor_p1.png
- alg-09-withdraw-then-represcribe (ta): png/alg-09-withdraw-then-represcribe_patient_p1.png · png/alg-09-withdraw-then-represcribe_doctor_p1.png
- alg-12-arabic-doctor-augmentin (ur): png/alg-12-arabic-doctor-augmentin_patient_p1.png · png/alg-12-arabic-doctor-augmentin_doctor_p1.png
- chest-01-gyastrik-discharge (ne): png/chest-01-gyastrik-discharge_patient_p1.png · png/chest-01-gyastrik-discharge_doctor_p1.png
- chest-03-seene-mein-jalan-arm-sweat (ur): png/chest-03-seene-mein-jalan-arm-sweat_patient_p1.png · png/chest-03-seene-mein-jalan-arm-sweat_doctor_p1.png
- chest-02-kabag-ecg-ordered (tl): png/chest-02-kabag-ecg-ordered_patient_p1.png · png/chest-02-kabag-ecg-ordered_doctor_p1.png
- chest-04-timer-10min-no-ecg (hi): png/chest-04-timer-10min-no-ecg_patient_p1.png · png/chest-04-timer-10min-no-ecg_doctor_p1.png
- chest-05-korean-jaw-sweat-admit (ko): png/chest-05-korean-jaw-sweat-admit_patient_p1.png · png/chest-05-korean-jaw-sweat-admit_doctor_p1.png
- chest-06-arabic-doctor-gastric (bn): png/chest-06-arabic-doctor-gastric_patient_p1.png · png/chest-06-arabic-doctor-gastric_doctor_p1.png
- dose-01-para-every-4h (ne): png/dose-01-para-every-4h_patient_p1.png · png/dose-01-para-every-4h_doctor_p1.png
- chest-07-ecg-normal-chest-wall (ta): png/chest-07-ecg-normal-chest-wall_patient_p1.png · png/chest-07-ecg-normal-chest-wall_doctor_p1.png
- dose-03-ibuprofen-800-qid (bn): png/dose-03-ibuprofen-800-qid_patient_p1.png · png/dose-03-ibuprofen-800-qid_doctor_p1.png
- dose-02-two-paracetamol-brands (hi): png/dose-02-two-paracetamol-brands_patient_p1.png · png/dose-02-two-paracetamol-brands_doctor_p1.png
- dose-04-brufen-600-q4h (ml): png/dose-04-brufen-600-q4h_patient_p1.png · png/dose-04-brufen-600-q4h_doctor_p1.png
- dose-05-diclofenac-75-tds (tl): png/dose-05-diclofenac-75-tds_patient_p1.png · png/dose-05-diclofenac-75-tds_doctor_p1.png
- dose-06-levothyroxine-mg-mcg (ru): png/dose-06-levothyroxine-mg-mcg_patient_p1.png · png/dose-06-levothyroxine-mg-mcg_doctor_p1.png
- dose-08-prn-up-to-8-tabs (id): png/dose-08-prn-up-to-8-tabs_patient_p1.png · png/dose-08-prn-up-to-8-tabs_doctor_p1.png
- dose-07-child-16kg-mother (sw): png/dose-07-child-16kg-mother_patient_p1.png · png/dose-07-child-16kg-mother_doctor_p1.png
- dose-10-metformin-3g (tr): png/dose-10-metformin-3g_patient_p1.png · png/dose-10-metformin-3g_doctor_p1.png
- dose-09-tramadol-qds-plus-prn (tr): png/dose-09-tramadol-qds-plus-prn_patient_p1.png · png/dose-09-tramadol-qds-plus-prn_doctor_p1.png
- dose-11-amlodipine-bd (fr): png/dose-11-amlodipine-bd_patient_p1.png · png/dose-11-amlodipine-bd_doctor_p1.png
- heat-01-collapse-site-brain-hot (ne): png/heat-01-collapse-site-brain-hot_patient_p1.png · png/heat-01-collapse-site-brain-hot_doctor_p1.png
- heat-03-furosemide-outdoor (ml): png/heat-03-furosemide-outdoor_patient_p1.png · png/heat-03-furosemide-outdoor_doctor_p1.png
- heat-02-matha-gorom-diclofenac (bn): png/heat-02-matha-gorom-diclofenac_patient_p1.png · png/heat-02-matha-gorom-diclofenac_doctor_p1.png
- heat-04-ramadan-metformin (ur): png/heat-04-ramadan-metformin_patient_p1.png · png/heat-04-ramadan-metformin_doctor_p1.png
- ddi-01-warfarin-diclofenac (ml): png/ddi-01-warfarin-diclofenac_patient_p1.png · png/ddi-01-warfarin-diclofenac_doctor_p1.png
- heat-05-pasma-trap (tl): png/heat-05-pasma-trap_patient_p1.png · png/heat-05-pasma-trap_doctor_p1.png
- ddi-02-triple-whammy-heat (ne): png/ddi-02-triple-whammy-heat_patient_p1.png · png/ddi-02-triple-whammy-heat_doctor_p1.png
- ddi-03-sertraline-tramadol (ru): png/ddi-03-sertraline-tramadol_patient_p1.png · png/ddi-03-sertraline-tramadol_doctor_p1.png
