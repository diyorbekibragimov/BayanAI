# Bayan simulation run 20261107-102251-coherence-hold

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 4 · languages: 4 (bn, hi, ne, ru) · wall 38s
- **checks passed: 20/22 (91%)** · scenarios fully passing: 3/4 · expected gaps confirmed: 0 (closed: 0)
- **coherence themes caught: 4/6 (67%)**
- attention budget (max agent cards) respected: 2/2
- clinical checks (hold/flag/suggest/no-flag): 10/10 (100%)
- false-positive traps tripped: 0/7 (0%)
- cost: total $0.0405 · per consultation median $0.0104 · max $0.0110
- latency (median, s from the start of the turn that preceded the card): rule cards 9.4 · agent cards 2.6 · lexicon/fallback 0.0 · translate+gate per turn 1.0 · wrap-up 0.0
- copilot: 21 think runs, 0 agent runs (0 failed/timed out); wrap-up modes: None×0

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| coherence | 2 | 1 | 10/12 | 4/4 | 0 |
| quiet | 2 | 2 | 10/10 | 6/6 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| budget | 2 | 2 |
| hold | 3 | 3 |
| no_flag | 5 | 5 |
| no_hold | 2 | 2 |
| run | 4 | 4 |
| theme | 4 | 6 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | ru/en | FAIL | 2 | :COHERENCE, :COHERENCE | - | 0.0110 | 37.5 |
| coh-03-bp-fine-not-measured | bn/en | PASS | 0 | :COHERENCE | - | 0.0087 | 28.2 |
| quiet-01-cold-paracetamol | ne/en | PASS | 0 | - | - | 0.0110 | 36.9 |
| quiet-02-bp-followup | hi/en | PASS | 0 | - | - | 0.0098 | 29.6 |

## Copilot cards per scenario (agent / fallback / lexicon; rule cards counted separately)

| id | agent cards | other non-rule | rule cards | agent runs | copilot $ | total $ |
|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | 2: observation/caution[plan] Nasal spray unrelated to butt pain, chest cold, ; observation/caution[consistency] No temperature measured; claim of high fever uns | 0 | 1 | 0 | 0.0000 | 0.0110 |
| coh-03-bp-fine-not-measured | 1: observation/caution[consistency] No blood pressure measurement was taken | 0 | 0 | 0 | 0.0000 | 0.0087 |
| quiet-01-cold-paracetamol | 0:  | 0 | 0 | 0 | 0.0000 | 0.0110 |
| quiet-02-bp-followup | 0:  | 0 | 0 | 0 | 0.0000 | 0.0098 |

## Failures (with evidence)

**coh-01-nasal-spray-butt** — The user's live test: buttock pain after cold tiles and low mood; doctor prescribes nasal spray, patient asks if it goes in the butt, doctor claims a high temperature never measured
- [theme] [plan] prescription incomplete (no drug name, strength or dose) — cards: agent/observation[plan] 'Nasal spray unrelated to butt pain, chest cold, mo'; agent/observation[consistency] 'No temperature measured; claim of high fever unsup'
- [theme] [communication] patient confused about how / where to use it — cards: agent/observation[plan] 'Nasal spray unrelated to butt pain, chest cold, mo'; agent/observation[consistency] 'No temperature measured; claim of high fever unsup'

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)


## PDF review images

