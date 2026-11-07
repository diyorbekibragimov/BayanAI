# Bayan simulation run coherence-r3

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 4 · languages: 3 (bn, ne, ru) · wall 147s
- **checks passed: 13/16 (81%)** · scenarios fully passing: 3/4 · expected gaps confirmed: 0 (closed: 0)
- **coherence themes caught: 4/7 (57%)**
- attention budget (max agent cards) respected: 1/1
- clinical checks (hold/flag/suggest/no-flag): 4/4 (100%)
- false-positive traps tripped: 0/4 (0%)
- cost: total $0.0706 · per consultation median $0.0169 · max $0.0214
- latency (median, s from the start of the turn that preceded the card): rule cards 5.8 · agent cards 7.2 · lexicon/fallback 0.9 · translate+gate per turn 0.9 · wrap-up 0.0
- copilot: 24 think runs, 16 agent runs (0 failed/timed out); wrap-up modes: None×0

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| coherence | 3 | 2 | 8/11 | 1/1 | 0 |
| quiet | 1 | 1 | 5/5 | 3/3 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| budget | 1 | 1 |
| no_flag | 3 | 3 |
| no_hold | 1 | 1 |
| run | 4 | 4 |
| theme | 4 | 7 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | ru/en | FAIL | 3 | - | - | 0.0214 | 44.7 |
| coh-03-bp-fine-not-measured | bn/en | PASS | 0 | - | - | 0.0175 | 40.1 |
| coh-06-hopeless-in-passing | ne/en | PASS | 0 | - | - | 0.0154 | 29.7 |
| quiet-01-cold-paracetamol | ne/en | PASS | 0 | - | - | 0.0163 | 32.2 |

## Copilot cards per scenario (agent / fallback / lexicon; rule cards counted separately)

| id | agent cards | other non-rule | rule cards | agent runs | copilot $ | total $ |
|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | 4: ask/info[history] Ask about recent injury; ask/info[safety] Ask about fever or infection; observation/caution[consistency] Diagnosis mismatch; observation/caution[consistency] Temperature not measured | 0 | 1 | 6 | 0.0100 | 0.0214 |
| coh-03-bp-fine-not-measured | 2: ask/info[safety] Ask about worst headache; observation/caution[consistency] BP not measured | 0 | 0 | 4 | 0.0058 | 0.0175 |
| coh-06-hopeless-in-passing | 1: ask/info[safety] Ask about self-harm | 1 | 0 | 3 | 0.0073 | 0.0154 |
| quiet-01-cold-paracetamol | 1: ask/info[safety] Ask about fever | 0 | 0 | 3 | 0.0083 | 0.0163 |

## Failures (with evidence)

**coh-01-nasal-spray-butt** — The user's live test: buttock pain after cold tiles and low mood; doctor prescribes nasal spray, patient asks if it goes in the butt, doctor claims a high temperature never measured
- [theme] [plan] prescription incomplete (no drug name, strength or dose) — cards: agent/ask[history] 'Ask about recent injury'; agent/ask[safety] 'Ask about fever or infection'; agent/observation[consistency] 'Diagnosis mismatch'; agent/observation[consistency] 'Temperature not measured'
- [theme] [communication] patient confused about how / where to use it — cards: agent/ask[history] 'Ask about recent injury'; agent/ask[safety] 'Ask about fever or infection'; agent/observation[consistency] 'Diagnosis mismatch'; agent/observation[consistency] 'Temperature not measured'
- [theme] [communication] low mood said in passing, not followed up — cards: agent/ask[history] 'Ask about recent injury'; agent/ask[safety] 'Ask about fever or infection'; agent/observation[consistency] 'Diagnosis mismatch'; agent/observation[consistency] 'Temperature not measured'

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)


## PDF review images

