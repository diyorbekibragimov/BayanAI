# Bayan simulation run coherence-v3

- models: LLM `openai/gpt-oss-120b` on cerebras (extraction on groq), agent `openai/gpt-oss-120b` on cerebras
- scenarios: 1 · languages: 1 (ne) · wall 32s
- **checks passed: 1/2 (50%)** · scenarios fully passing: 0/1 · expected gaps confirmed: 0 (closed: 0)
- **coherence themes caught: 0/1 (0%)**
- clinical checks (hold/flag/suggest/no-flag): 0/0 (-)
- false-positive traps tripped: 0/0 (-)
- cost: total $0.0118 · per consultation median $0.0118 · max $0.0118
- latency (median, s from the start of the turn that preceded the card): rule cards 0.0 · agent cards 9.1 · lexicon/fallback 1.0 · translate+gate per turn 0.9 · wrap-up 0.0
- copilot: 6 think runs, 3 agent runs (0 failed/timed out); wrap-up modes: None×0

## Pass rate by category

| category | scenarios | fully passing | checks | clinical checks | gaps |
|---|---|---|---|---|---|
| coherence | 1 | 0 | 1/2 | 0/0 | 0 |

## Pass rate by check type

| type | passed | total |
|---|---|---|
| run | 1 | 1 |
| theme | 0 | 1 |

## Scenarios

| id | lang | result | failed checks | holds | critical rules seen | cost $ | wall s |
|---|---|---|---|---|---|---|---|
| coh-06-hopeless-in-passing | ne/en | FAIL | 1 | - | - | 0.0118 | 31.0 |

## Copilot cards per scenario (agent / fallback / lexicon; rule cards counted separately)

| id | agent cards | other non-rule | rule cards | agent runs | copilot $ | total $ |
|---|---|---|---|---|---|---|
| coh-06-hopeless-in-passing | 1: ask/info[safety] Red flag symptoms | 2 | 0 | 3 | 0.0048 | 0.0118 |

## Failures (with evidence)

**coh-06-hopeless-in-passing** — Back pain from carrying loads; in passing "what is the point of living like this"; the doctor treats the back only
- [theme] [communication] hopelessness voiced in passing, not explored — cards: agent/ask[safety] 'Red flag symptoms'; lexicon/idiom[-] 'Idiom: jham-jham (झमझम)'; fallback/ask[safety] 'Is it on one side of the body or both? Did it star'

## Unexpected critical alerts (not in the scenario's expectations; review for false positives)

- none

## Expected gaps (no rule / agent behaviour exists; recommendations, not failures)


## PDF review images

