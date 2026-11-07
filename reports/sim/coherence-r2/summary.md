# Bayan simulation run coherence-r2

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 16 · languages: 9 (bn, es, hi, id, ne, ru, sw, tl, ur) · wall 243s
- **checks passed: 111/117 (95%)** · scenarios fully passing: 11/16 · expected gaps confirmed: 1 (closed: 0)
- **coherence themes caught: 8/12 (67%)**
- attention budget (max agent cards) respected: 4/6
- clinical checks (hold/flag/suggest/no-flag): 30/30 (100%)
- false-positive traps tripped: 0/22 (0%)
- cost: total $0.2298 · per consultation median $0.0143 · max $0.0216
- latency (median, s from the start of the turn that preceded the card): rule cards 5.2 · agent cards 7.0 · lexicon/fallback 0.9 · translate+gate per turn 0.9 · wrap-up 8.0
- copilot: 85 think runs, 56 agent runs (0 failed/timed out); wrap-up modes: None×0, agent×3

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| allergy | 1 | 1 | 33/33 | 5/5 | 0 |
| chest | 1 | 1 | 19/19 | 4/4 | 0 |
| coherence | 7 | 4 | 16/20 | 1/1 | 0 |
| quiet | 6 | 4 | 29/31 | 19/19 | 0 |
| redflags | 1 | 1 | 14/14 | 1/1 | 1 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| budget | 4 | 6 |
| care_plan | 5 | 5 |
| flag | 6 | 6 |
| hold | 1 | 1 |
| no_flag | 14 | 14 |
| no_hold | 8 | 8 |
| pdf | 41 | 41 |
| run | 19 | 19 |
| state | 4 | 4 |
| suggest | 1 | 1 |
| theme | 8 | 12 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| alg-01-augmentin-brand | ne/en | PASS | 0 | co-amoxiclav:ALG-PEN-01 | ALG-PEN-01 | 0.0160 | 35.6 |
| chest-01-gyastrik-discharge | ne/en | PASS | 0 | - | WORK-CHEST-02, WORK-CHEST-03 | 0.0147 | 32.1 |
| coh-01-nasal-spray-butt | ru/en | FAIL | 2 | - | - | 0.0216 | 43.3 |
| coh-02-antibiotic-viral-cold | hi/en | PASS | 0 | - | - | 0.0142 | 33.6 |
| coh-03-bp-fine-not-measured | bn/en | FAIL | 1 | - | - | 0.0145 | 31.4 |
| coh-04-uti-diagnosis-vs-lifting-history | tl/en | PASS | 0 | - | - | 0.0154 | 30.8 |
| coh-05-metformin-misunderstood | ur/en | PASS | 0 | - | - | 0.0171 | 30.7 |
| coh-06-hopeless-in-passing | ne/en | FAIL | 1 | - | - | 0.0122 | 28.5 |
| coh-07-leg-swelling-ignored | sw/en | PASS | 0 | - | - | 0.0133 | 29.1 |
| quiet-01-cold-paracetamol | ne/en | FAIL | 1 | - | - | 0.0123 | 32.3 |
| quiet-02-bp-followup | hi/en | PASS | 0 | - | - | 0.0161 | 29.0 |
| quiet-03-salbutamol-refill | tl/en | PASS | 0 | - | - | 0.0117 | 25.2 |
| quiet-04-spanish-gases-trap | es/en | PASS | 0 | - | - | 0.0127 | 26.1 |
| quiet-05-work-tension | ne/en | FAIL | 1 | - | - | 0.0120 | 24.3 |
| quiet-06-indonesian-followup-diabetes | id/en | PASS | 0 | - | - | 0.0100 | 20.2 |
| rf-02-black-stools-ibuprofen | ne/en | PASS | 0 | - | - | 0.0161 | 32.0 |

## Copilot cards per scenario (agent / fallback / lexicon; rule cards counted separately)

| id | agent cards | other non-rule | rule cards | agent runs | copilot $ | total $ |
|---|---|---|---|---|---|---|
| alg-01-augmentin-brand | 1: ask/info[safety] Airway compromise? | 0 | 1 | 3 | 0.0049 | 0.0160 |
| chest-01-gyastrik-discharge | 0:  | 2 | 1 | 3 | 0.0055 | 0.0147 |
| coh-01-nasal-spray-butt | 4: ask/info[safety] Fever or bleeding?; ask/info[safety] Ask about suicidal thoughts; observation/caution[consistency] Diagnosis mismatch; observation/caution[consistency] Temperature not measured | 0 | 1 | 6 | 0.0106 | 0.0216 |
| coh-02-antibiotic-viral-cold | 2: ask/info[safety] Breathing difficulty?; missed/caution[plan] Antibiotic details missing | 0 | 0 | 3 | 0.0065 | 0.0142 |
| coh-03-bp-fine-not-measured | 1: ask/info[safety] Red flag headache | 0 | 0 | 4 | 0.0053 | 0.0145 |
| coh-04-uti-diagnosis-vs-lifting-history | 2: ask/info[safety] Ask about red flags; observation/caution[consistency] UTI diagnosis not supported | 0 | 0 | 4 | 0.0063 | 0.0154 |
| coh-05-metformin-misunderstood | 3: ask/info[history] Ask about hyperglycemia symptoms; observation/caution[communication] Misunderstanding dosing schedule; ask/info[communication] Clarify dosing schedule | 0 | 0 | 5 | 0.0080 | 0.0171 |
| coh-06-hopeless-in-passing | 2: ask/info[safety] Red flag symptoms; ask/info[safety] Leg weakness or bladder issues | 2 | 0 | 3 | 0.0046 | 0.0122 |
| coh-07-leg-swelling-ignored | 2: ask/info[safety] Ask about DVT signs; observation/caution[consistency] Leg swelling not addressed | 0 | 0 | 3 | 0.0053 | 0.0133 |
| quiet-01-cold-paracetamol | 3: ask/info[safety] Ask about fever; ask/info[safety] Breathing difficulty; missed/info[communication] No return advice | 0 | 0 | 3 | 0.0045 | 0.0123 |
| quiet-02-bp-followup | 1: ask/info[safety] Check recent blood pressure | 0 | 0 | 4 | 0.0077 | 0.0161 |
| quiet-03-salbutamol-refill | 1: ask/info[history] Ask about recent symptoms | 0 | 0 | 3 | 0.0045 | 0.0117 |
| quiet-04-spanish-gases-trap | 1: ask/info[safety] Red flag symptoms | 0 | 0 | 3 | 0.0056 | 0.0127 |
| quiet-05-work-tension | 2: ask/info[safety] Ask about suicidal thoughts; ask/info[safety] Ask about hopelessness | 2 | 1 | 3 | 0.0055 | 0.0120 |
| quiet-06-indonesian-followup-diabetes | 1: ask/info[history] Ask about diabetes meds | 0 | 0 | 3 | 0.0041 | 0.0100 |
| rf-02-black-stools-ibuprofen | 1: ask/info[safety] Ask about fainting | 0 | 0 | 3 | 0.0074 | 0.0161 |

## Failures (with evidence)

**coh-01-nasal-spray-butt** — The user's live test: buttock pain after cold tiles and low mood; doctor prescribes nasal spray, patient asks if it goes in the butt, doctor claims a high temperature never measured
- [theme] [plan] prescription incomplete (no drug name, strength or dose) — cards: agent/ask[safety] 'Fever or bleeding?'; agent/ask[safety] 'Ask about suicidal thoughts'; agent/observation[consistency] 'Diagnosis mismatch'; agent/observation[consistency] 'Temperature not measured'
- [theme] [communication] patient confused about how / where to use it — cards: agent/ask[safety] 'Fever or bleeding?'; agent/ask[safety] 'Ask about suicidal thoughts'; agent/observation[consistency] 'Diagnosis mismatch'; agent/observation[consistency] 'Temperature not measured'

**coh-03-bp-fine-not-measured** — Headache and dizziness; doctor says "your blood pressure is fine" though no blood pressure was taken
- [theme] [consistency] blood pressure stated but never measured — cards: agent/ask[safety] 'Red flag headache'

**coh-06-hopeless-in-passing** — Back pain from carrying loads; in passing "what is the point of living like this"; the doctor treats the back only
- [theme] [communication] hopelessness voiced in passing, not explored — cards: agent/ask[safety] 'Red flag symptoms'; lexicon/idiom[-] 'Idiom: jham-jham (झमझम)'; fallback/ask[safety] 'Is it on one side of the body or both? Did it star'; agent/ask[safety] 'Leg weakness or bladder issues'

**quiet-01-cold-paracetamol** — Common cold after allergies asked; paracetamol 1 g TDS
- [budget] at most 1 agent card(s) shown — ask/info 'Ask about fever'; ask/info 'Breathing difficulty'; missed/info 'No return advice'

**quiet-05-work-tension** — 'A bit of tension at work', sleeping less (tension idiom); caution allowed, critical not
- [budget] at most 1 agent card(s) shown — ask/info 'Ask about suicidal thoughts'; ask/info 'Ask about hopelessness'

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)

- rf-02-black-stools-ibuprofen: card source=rules ~bleed|black|melaena → **GAP** — No rule for melaena / upper-GI bleed on NSAIDs (stop NSAID, Hb, urgent review). Recommend a WORK-GIB rule.

## PDF review images

- alg-01-augmentin-brand (ne): png/alg-01-augmentin-brand_patient_p1.png · png/alg-01-augmentin-brand_doctor_p1.png
- chest-01-gyastrik-discharge (ne): png/chest-01-gyastrik-discharge_patient_p1.png · png/chest-01-gyastrik-discharge_doctor_p1.png
- rf-02-black-stools-ibuprofen (ne): png/rf-02-black-stools-ibuprofen_patient_p1.png · png/rf-02-black-stools-ibuprofen_doctor_p1.png
