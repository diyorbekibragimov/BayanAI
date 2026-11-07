# Bayan simulation run coherence-final (v1 + coh-01 from v2 + coh-06 from v3)

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 16 · languages: 9 (bn, es, hi, id, ne, ru, sw, tl, ur) · wall 129s
- **checks passed: 106/117 (91%)** · scenarios fully passing: 7/16 · expected gaps confirmed: 1 (closed: 0)
- **coherence themes caught: 7/12 (58%)**
- attention budget (max agent cards) respected: 5/6
- clinical checks (hold/flag/suggest/no-flag): 25/30 (83%)
- false-positive traps tripped: 5/22 (23%)
- cost: total $0.2085 · per consultation median $0.0126 · max $0.0185
- latency (median, s from the start of the turn that preceded the card): rule cards 4.3 · agent cards 6.7 · lexicon/fallback 0.9 · translate+gate per turn 0.9 · wrap-up 7.7
- copilot: 85 think runs, 56 agent runs (0 failed/timed out); wrap-up modes: None×0, agent×3

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| allergy | 1 | 1 | 33/33 | 5/5 | 0 |
| chest | 1 | 1 | 19/19 | 4/4 | 0 |
| coherence | 7 | 3 | 15/20 | 1/1 | 0 |
| quiet | 6 | 1 | 25/31 | 14/19 | 0 |
| redflags | 1 | 1 | 14/14 | 1/1 | 1 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| budget | 5 | 6 |
| care_plan | 5 | 5 |
| flag | 6 | 6 |
| hold | 1 | 1 |
| no_flag | 9 | 14 |
| no_hold | 8 | 8 |
| pdf | 41 | 41 |
| run | 19 | 19 |
| state | 4 | 4 |
| suggest | 1 | 1 |
| theme | 7 | 12 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| alg-01-augmentin-brand | ne/en | PASS | 0 | co-amoxiclav:ALG-PEN-01 | ALG-PEN-01 | 0.0167 | 42.7 |
| chest-01-gyastrik-discharge | ne/en | PASS | 0 | - | WORK-CHEST-02, WORK-CHEST-03 | 0.0150 | 37.5 |
| coh-01-nasal-spray-butt | ru/en | FAIL | 2 | - | - | 0.0185 | 41.3 |
| coh-02-antibiotic-viral-cold | hi/en | FAIL | 1 | - | - | 0.0150 | 33.4 |
| coh-03-bp-fine-not-measured | bn/en | FAIL | 1 | - | - | 0.0131 | 29.7 |
| coh-04-uti-diagnosis-vs-lifting-history | tl/en | PASS | 0 | - | - | 0.0133 | 29.2 |
| coh-05-metformin-misunderstood | ur/en | PASS | 0 | - | - | 0.0152 | 30.0 |
| coh-06-hopeless-in-passing | ne/en | FAIL | 1 | - | - | 0.0118 | 31.0 |
| coh-07-leg-swelling-ignored | sw/en | PASS | 0 | - | - | 0.0121 | 28.2 |
| quiet-01-cold-paracetamol | ne/en | FAIL | 1 | - | - | 0.0119 | 27.0 |
| quiet-02-bp-followup | hi/en | FAIL | 1 | - | - | 0.0121 | 24.5 |
| quiet-03-salbutamol-refill | tl/en | FAIL | 2 | - | - | 0.0101 | 21.7 |
| quiet-04-spanish-gases-trap | es/en | FAIL | 1 | - | - | 0.0097 | 23.6 |
| quiet-05-work-tension | ne/en | PASS | 0 | - | - | 0.0097 | 20.8 |
| quiet-06-indonesian-followup-diabetes | id/en | FAIL | 1 | - | - | 0.0083 | 18.9 |
| rf-02-black-stools-ibuprofen | ne/en | PASS | 0 | - | - | 0.0160 | 32.0 |

## Copilot cards per scenario (agent / fallback / lexicon; rule cards counted separately)

| id | agent cards | other non-rule | rule cards | agent runs | copilot $ | total $ |
|---|---|---|---|---|---|---|
| alg-01-augmentin-brand | 1: ask/caution[safety] Breathing difficulty | 0 | 1 | 3 | 0.0046 | 0.0167 |
| chest-01-gyastrik-discharge | 0:  | 2 | 1 | 3 | 0.0063 | 0.0150 |
| coh-01-nasal-spray-butt | 6: ask/info[safety] Ask about fever; ask/info[safety] Ask about swelling or redness; ask/info[safety] Ask about self-harm; observation/caution[consistency] Nose vs butt pain mismatch; observation/caution[plan] Nasal spray for butt pain; observation/caution[consistency] No temperature measured | 0 | 0 | 6 | 0.0087 | 0.0185 |
| coh-02-antibiotic-viral-cold | 2: ask/caution[safety] Breathing difficulty?; missed/caution[plan] Antibiotic likely unnecessary | 0 | 0 | 3 | 0.0080 | 0.0150 |
| coh-03-bp-fine-not-measured | 1: ask/caution[safety] Ask about fever or neck stiffness | 0 | 0 | 4 | 0.0047 | 0.0131 |
| coh-04-uti-diagnosis-vs-lifting-history | 2: ask/caution[safety] Check for nerve or bladder issues; observation/caution[consistency] Diagnosis mismatch | 0 | 0 | 4 | 0.0046 | 0.0133 |
| coh-05-metformin-misunderstood | 3: missed/caution[history] Ask about current meds; ask/caution[safety] Ask about kidney disease; missed/info[communication] Clarify metformin with food | 0 | 0 | 5 | 0.0061 | 0.0152 |
| coh-06-hopeless-in-passing | 1: ask/info[safety] Red flag symptoms | 2 | 0 | 3 | 0.0048 | 0.0118 |
| coh-07-leg-swelling-ignored | 2: ask/caution[safety] Leg swelling characteristics; missed/caution[safety] Leg swelling not evaluated | 0 | 0 | 3 | 0.0041 | 0.0121 |
| quiet-01-cold-paracetamol | 1: ask/caution[safety] Ask about fever | 0 | 0 | 3 | 0.0046 | 0.0119 |
| quiet-02-bp-followup | 1: ask/caution[safety] Ask about swelling | 0 | 0 | 4 | 0.0043 | 0.0121 |
| quiet-03-salbutamol-refill | 2: ask/info[history] Ask about symptom control; missed/caution[plan] Incomplete inhaler prescription | 0 | 0 | 3 | 0.0037 | 0.0101 |
| quiet-04-spanish-gases-trap | 1: ask/caution[history] Ask about other GI symptoms | 0 | 0 | 3 | 0.0032 | 0.0097 |
| quiet-05-work-tension | 1: ask/caution[safety] Screen for depression | 2 | 1 | 3 | 0.0039 | 0.0097 |
| quiet-06-indonesian-followup-diabetes | 1: ask/caution[history] Ask current meds | 0 | 0 | 3 | 0.0031 | 0.0083 |
| rf-02-black-stools-ibuprofen | 1: observation/caution[safety] Check orthostatic vitals | 0 | 0 | 3 | 0.0078 | 0.0160 |

## Failures (with evidence)

**coh-01-nasal-spray-butt** — The user's live test: buttock pain after cold tiles and low mood; doctor prescribes nasal spray, patient asks if it goes in the butt, doctor claims a high temperature never measured
- [theme] [plan] prescription incomplete (no drug name, strength or dose) — cards: agent/ask[safety] 'Ask about fever'; agent/ask[safety] 'Ask about swelling or redness'; agent/ask[safety] 'Ask about self-harm'; agent/observation[consistency] 'Nose vs butt pain mismatch'; agent/observation[plan] 'Nasal spray for butt pain'; agent/observation[consistency] 'No temperature mea
- [theme] [communication] patient confused about how / where to use it — cards: agent/ask[safety] 'Ask about fever'; agent/ask[safety] 'Ask about swelling or redness'; agent/ask[safety] 'Ask about self-harm'; agent/observation[consistency] 'Nose vs butt pain mismatch'; agent/observation[plan] 'Nasal spray for butt pain'; agent/observation[consistency] 'No temperature mea

**coh-02-antibiotic-viral-cold** — Runny nose and sneezing for two days without fever; doctor gives "an antibiotic" with no name, dose or reason
- [theme] [plan] prescription incomplete (no drug name or dose) — cards: agent/ask[safety] 'Breathing difficulty?'; agent/missed[plan] 'Antibiotic likely unnecessary'

**coh-03-bp-fine-not-measured** — Headache and dizziness; doctor says "your blood pressure is fine" though no blood pressure was taken
- [theme] [consistency] blood pressure stated but never measured — cards: agent/ask[safety] 'Ask about fever or neck stiffness'

**coh-06-hopeless-in-passing** — Back pain from carrying loads; in passing "what is the point of living like this"; the doctor treats the back only
- [theme] [communication] hopelessness voiced in passing, not explored — cards: agent/ask[safety] 'Red flag symptoms'; lexicon/idiom[-] 'Idiom: jham-jham (झमझम)'; fallback/ask[safety] 'Is it on one side of the body or both? Did it star'

**quiet-01-cold-paracetamol** — Common cold after allergies asked; paracetamol 1 g TDS
- [no_flag] NOT card severity=caution — agent/ask/caution 'Ask about fever' ask='Do you have a fever or feel hot?'

**quiet-02-bp-followup** — Hypertension follow-up, BP controlled, continue amlodipine 5 mg
- [no_flag] NOT card severity=caution — agent/ask/caution 'Ask about swelling' ask='Do you have any swelling in your feet or ankles?'

**quiet-03-salbutamol-refill** — Asthma inhaler refill, well controlled
- [no_flag] NOT card severity=caution — agent/missed/caution 'Incomplete inhaler prescription'
- [budget] at most 1 agent card(s) shown — ask/info 'Ask about symptom control'; missed/caution 'Incomplete inhaler prescription'

**quiet-04-spanish-gases-trap** — Spanish patient with 'gases' after beans (the English rendering says 'gas'; no Hindi idiom card expected)
- [no_flag] NOT card severity=caution — agent/ask/caution 'Ask about other GI symptoms' ask='Do you have any nausea, vomiting, diarrhea, constipation, or'

**quiet-06-indonesian-followup-diabetes** — Diabetes follow-up, metformin 500 mg BD continued, allergies asked
- [no_flag] NOT card severity=caution — agent/ask/caution 'Ask current meds' ask='What medicines are you currently taking?'

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)

- rf-02-black-stools-ibuprofen: card source=rules ~bleed|black|melaena → **GAP** — No rule for melaena / upper-GI bleed on NSAIDs (stop NSAID, Hb, urgent review). Recommend a WORK-GIB rule.

## PDF review images

- alg-01-augmentin-brand (ne): ../coherence-v1/png/alg-01-augmentin-brand_patient_p1.png · ../coherence-v1/png/alg-01-augmentin-brand_doctor_p1.png
- chest-01-gyastrik-discharge (ne): ../coherence-v1/png/chest-01-gyastrik-discharge_patient_p1.png · ../coherence-v1/png/chest-01-gyastrik-discharge_doctor_p1.png
- rf-02-black-stools-ibuprofen (ne): ../coherence-v1/png/rf-02-black-stools-ibuprofen_patient_p1.png · ../coherence-v1/png/rf-02-black-stools-ibuprofen_doctor_p1.png
