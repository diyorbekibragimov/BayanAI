# Bayan simulation run 20261107-092941-eov

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 1 · languages: 1 (ru) · wall 61s
- **checks passed: 18/19 (95%)** · scenarios fully passing: 0/1 · expected gaps confirmed: 0 (closed: 0)
- **coherence themes caught: 4/5 (80%)**
- clinical checks (hold/flag/suggest/no-flag): 1/1 (100%)
- false-positive traps tripped: 0/1 (0%)
- cost: total $0.0264 · per consultation median $0.0264 · max $0.0264
- latency (median, s from the start of the turn that preceded the card): rule cards 0.0 · agent cards 8.5 · lexicon/fallback 0.0 · translate+gate per turn 0.9 · wrap-up 7.6
- copilot: 6 think runs, 6 agent runs (0 failed/timed out); wrap-up modes: agent×1

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| coherence | 1 | 0 | 18/19 | 1/1 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| no_flag | 1 | 1 |
| pdf | 11 | 11 |
| run | 2 | 2 |
| theme | 4 | 5 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | ru/en | FAIL | 1 | - | - | 0.0264 | 60.0 |

## Copilot cards per scenario (agent / fallback / lexicon; rule cards counted separately)

| id | agent cards | other non-rule | rule cards | agent runs | copilot $ | total $ |
|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | 5: ask/info[safety] Red flag symptoms; ask/info[safety] Ask about self-harm; observation/caution[consistency] Plan mismatched to complaint; observation/caution[communication] Patient confused about spray location; observation/caution[consistency] Temperature not measured | 0 | 0 | 6 | 0.0106 | 0.0264 |

## Failures (with evidence)

**coh-01-nasal-spray-butt** — The user's live test: buttock pain after cold tiles and low mood; doctor prescribes nasal spray, patient asks if it goes in the butt, doctor claims a high temperature never measured
- [theme] [plan] prescription incomplete (no drug name, strength or dose) — cards: agent/ask[safety] 'Red flag symptoms'; agent/ask[safety] 'Ask about self-harm'; agent/observation[consistency] 'Plan mismatched to complaint'; agent/observation[communication] 'Patient confused about spray location'; agent/observation[consistency] 'Temperature not measured'

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)


## PDF review images

- coh-01-nasal-spray-butt (ru): png/coh-01-nasal-spray-butt_patient_p1.png · png/coh-01-nasal-spray-butt_doctor_p1.png
