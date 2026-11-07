# Bayan simulation run coherence-r4

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 2 · languages: 2 (ne, ru) · wall 70s
- **checks passed: 8/12 (67%)** · scenarios fully passing: 0/2 · expected gaps confirmed: 0 (closed: 0)
- **coherence themes caught: 2/5 (40%)**
- attention budget (max agent cards) respected: 0/1
- clinical checks (hold/flag/suggest/no-flag): 4/4 (100%)
- false-positive traps tripped: 0/3 (0%)
- cost: total $0.0326 · per consultation median $0.0163 · max $0.0204
- latency (median, s from the start of the turn that preceded the card): rule cards 8.0 · agent cards 6.7 · lexicon/fallback 0.9 · translate+gate per turn 0.9 · wrap-up 0.0
- copilot: 11 think runs, 9 agent runs (0 failed/timed out); wrap-up modes: None×0

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| coherence | 1 | 0 | 4/7 | 1/1 | 0 |
| quiet | 1 | 0 | 4/5 | 3/3 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| budget | 0 | 1 |
| flag | 1 | 1 |
| no_flag | 2 | 2 |
| no_hold | 1 | 1 |
| run | 2 | 2 |
| theme | 2 | 5 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | ru/en | FAIL | 3 | - | - | 0.0204 | 41.4 |
| quiet-05-work-tension | ne/en | FAIL | 1 | - | - | 0.0122 | 28.2 |

## Copilot cards per scenario (agent / fallback / lexicon; rule cards counted separately)

| id | agent cards | other non-rule | rule cards | agent runs | copilot $ | total $ |
|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | 4: ask/info[safety] Ask about red flag symptoms; ask/info[safety] Ask about self-harm; observation/caution[consistency] Nose diagnosis mismatch; observation/caution[plan] Nasal spray mismatch | 0 | 0 | 6 | 0.0095 | 0.0204 |
| quiet-05-work-tension | 2: ask/info[safety] Ask about suicidal thoughts; ask/info[safety] Ask about suicide plan | 2 | 1 | 3 | 0.0046 | 0.0122 |

## Failures (with evidence)

**coh-01-nasal-spray-butt** — The user's live test: buttock pain after cold tiles and low mood; doctor prescribes nasal spray, patient asks if it goes in the butt, doctor claims a high temperature never measured
- [theme] [plan] prescription incomplete (no drug name, strength or dose) — cards: agent/ask[safety] 'Ask about red flag symptoms'; agent/ask[safety] 'Ask about self-harm'; agent/observation[consistency] 'Nose diagnosis mismatch'; agent/observation[plan] 'Nasal spray mismatch'
- [theme] [communication] patient confused about how / where to use it — cards: agent/ask[safety] 'Ask about red flag symptoms'; agent/ask[safety] 'Ask about self-harm'; agent/observation[consistency] 'Nose diagnosis mismatch'; agent/observation[plan] 'Nasal spray mismatch'
- [theme] [consistency] temperature claim not backed by a measurement / contradicts the patient — cards: agent/ask[safety] 'Ask about red flag symptoms'; agent/ask[safety] 'Ask about self-harm'; agent/observation[consistency] 'Nose diagnosis mismatch'; agent/observation[plan] 'Nasal spray mismatch'

**quiet-05-work-tension** — 'A bit of tension at work', sleeping less (tension idiom); caution allowed, critical not
- [budget] at most 1 agent card(s) shown — ask/info 'Ask about suicidal thoughts'; ask/info 'Ask about suicide plan'

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)


## PDF review images

