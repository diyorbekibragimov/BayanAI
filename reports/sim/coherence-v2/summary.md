# Bayan simulation run coherence-v2

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 1 · languages: 1 (ru) · wall 42s
- **checks passed: 5/7 (71%)** · scenarios fully passing: 0/1 · expected gaps confirmed: 0 (closed: 0)
- **coherence themes caught: 3/5 (60%)**
- clinical checks (hold/flag/suggest/no-flag): 1/1 (100%)
- false-positive traps tripped: 0/1 (0%)
- cost: total $0.0185 · per consultation median $0.0185 · max $0.0185
- latency (median, s from the start of the turn that preceded the card): rule cards 0.0 · agent cards 5.9 · lexicon/fallback 0.0 · translate+gate per turn 0.8 · wrap-up 0.0
- copilot: 6 think runs, 6 agent runs (0 failed/timed out); wrap-up modes: None×0

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| coherence | 1 | 0 | 5/7 | 1/1 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| no_flag | 1 | 1 |
| run | 1 | 1 |
| theme | 3 | 5 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | ru/en | FAIL | 2 | - | - | 0.0185 | 41.3 |

## Copilot cards per scenario (agent / fallback / lexicon; rule cards counted separately)

| id | agent cards | other non-rule | rule cards | agent runs | copilot $ | total $ |
|---|---|---|---|---|---|---|
| coh-01-nasal-spray-butt | 6: ask/info[safety] Ask about fever; ask/info[safety] Ask about swelling or redness; ask/info[safety] Ask about self-harm; observation/caution[consistency] Nose vs butt pain mismatch; observation/caution[plan] Nasal spray for butt pain; observation/caution[consistency] No temperature measured | 0 | 0 | 6 | 0.0087 | 0.0185 |

## Failures (with evidence)

**coh-01-nasal-spray-butt** — The user's live test: buttock pain after cold tiles and low mood; doctor prescribes nasal spray, patient asks if it goes in the butt, doctor claims a high temperature never measured
- [theme] [plan] prescription incomplete (no drug name, strength or dose) — cards: agent/ask[safety] 'Ask about fever'; agent/ask[safety] 'Ask about swelling or redness'; agent/ask[safety] 'Ask about self-harm'; agent/observation[consistency] 'Nose vs butt pain mismatch'; agent/observation[plan] 'Nasal spray for butt pain'; agent/observation[consistency] 'No temperature mea
- [theme] [communication] patient confused about how / where to use it — cards: agent/ask[safety] 'Ask about fever'; agent/ask[safety] 'Ask about swelling or redness'; agent/ask[safety] 'Ask about self-harm'; agent/observation[consistency] 'Nose vs butt pain mismatch'; agent/observation[plan] 'Nasal spray for butt pain'; agent/observation[consistency] 'No temperature mea

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)


## PDF review images

