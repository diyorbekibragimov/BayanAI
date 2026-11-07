# Bayan simulation scenarios

Scripted consultations played through the real engine (`bayan.consult.process_text` → live translation, the
synchronous prescription gate, the idiom lexicon, the background copilot think loop, then `end_visit` + `approve`
→ wrap-up agent, care plan, both PDFs). Runner: `scripts/simulate.py` (see its docstring). Results land in
`reports/sim/<run-id>/` (`results.json`, `summary.md`, `pdf/`, `png/`).

```
python scripts/simulate.py --list
python scripts/simulate.py                          # everything, 4 consultations at a time (~$0.015 each)
python scripts/simulate.py --only alg-01,chest-0    # id prefixes
python scripts/simulate.py --lang ur --category allergy
python scripts/simulate.py --rescore reports/sim/<run-id>   # re-score after editing expectations (no LLM calls)
python scripts/simulate.py --category coherence,quiet --no-wrapup all --budget 0.15   # copilot only, capped spend
```

`--no-wrapup <categories|all>` stops after the last turn (no end_visit / PDFs; the wrap-up and PDF checks are
skipped). `--budget <$>` stops starting new scenarios once that much has been spent.

Other models: set the app's own env vars (`BAYAN_LLM`, `BAYAN_LLM_PROVIDER`, `BAYAN_LLM_FALLBACK`,
`BAYAN_AGENT_LLM`, `BAYAN_AGENT_PROVIDER`, `BAYAN_EXTRACT_PROVIDER`, `BAYAN_EXTRACT_FALLBACK`). Providers the
installed `huggingface_hub` does not know (0.36.2 has no `deepinfra`) are reached through the HF router's
OpenAI-compatible endpoint (`model:provider`) by a shim inside the runner; app code is untouched.

## File format

One YAML list per category file (`allergy`, `dose`, `interactions`, `pregnancy`, `heat`, `chest`, `redflags`,
`quiet`, `messy`, `coherence`). Each scenario:

| key | meaning |
|---|---|
| `id`, `title` | unique id (prefix = category), one-line description |
| `patient_lang` | patient language code (`ne`, `hi`, `ur`, `bn`, `ml`, `ta`, `tl`, `sw`, `ko`, `ka`, `ja`, `es`, `fr`, `id`, `tr`, `ru`, ...) |
| `doctor_lang` | `en` (default) or `ar` |
| `turns` | ordered steps (index = position in this list, used by `turn` / `by_turn`) |
| `expect` | expectations (below) |
| `expected_gap` | `true` marks every expectation of the scenario as a known gap |

Turn steps:

- `{role: doctor|patient, text: "...", t: <minutes>}`: one utterance. Patient text is in the native script (natural,
  colloquial, idioms, code-switching, native digits). Doctor text is English, or Arabic when `doctor_lang: ar`.
  `t` sets the consultation clock (default +0.75 min per step) so timer rules (WORK-CHEST-01, 10 min) can be tested.
- `{action: held_else}`: "Say something else" on a held sentence (withdrawn, never spoken).
- `{action: held_anyway}`: "Speak it anyway" (audited override).
- `{action: ask, keywords: [...]}`: tap the first open "Ask next" suggestion (optionally matching keywords).
- `{action: tick, t: 12}`: advance the clock and re-check timer rules.
- `{action: dismiss_open, source: agent}`: the doctor dismisses open cards.

After every step the runner waits for the background copilot to go idle (as the live UI would while speech plays),
then ticks the timer rules. A new turn while a sentence is held discards it (the app's own behaviour).

## Expectations

```yaml
expect:
  must_hold:      [{drug: co-amoxiclav, rule: ALG-PEN-01, turn: 4}]   # the gate held this sentence (rule_any: [...])
  must_not_hold:  [paracetamol, {drug: diclofenac, turn: 4}, "*"]      # "*" = no hold at all
  must_flag:      # by the end (or by_turn): a rule fired (any time; grouped cards are tracked per rule item) ...
    - {rule: WORK-CHEST-05, severity: caution, by_turn: 1}
    - {rule_any: [WORK-CHEST-02, WORK-CHEST-03], severity: critical}
    # ... or a card matched by kind / kind_any / source / grounding / severity / keywords (title+body+ask_text)
    - {kind: idiom, grounding: npi-005}
    - {kind_any: [observation, missed], keywords: [paracetamol, duplicate]}
  must_suggest:   [{keywords: [arm, jaw, sweat], by_turn: 1}]          # an "ask" card (default kind)
  must_not_flag:  [{rule: ALG-ASK-01}, {severity: critical}, {severity: caution}, {kind: idiom}, {source: rules}]
  state:          {prescribed_has: [...], prescribed_not: [...], allergy_has: [...], patient: {weight_kg: 16},
                   symptoms_has: [...], investigations_has: [ecg_12lead]}
  care_plan:      {meds_has: [...], meds_not: [...], avoid_has: [penicillin]}
  themes:         # general clinical review (coherence.yaml): caught if ANY card shown in the visit matches
    - {name: treatment does not fit the complaint, dimension: plan,
       all: [[nasal, nose, spray], [buttock, complaint, fit, unrelated]]}   # every group matches the same card
    - {name: low mood not followed up, dimension: communication, any: [mood, depress, " sad"]}  # " x" = word start
  max_agent_cards: 1    # attention budget: agent cards shown during the whole visit
  pdf:            {patient_meds_not: [...], patient_meds_has: [...], patient_contains: [...],
                   patient_not_contains: [...], doctor_contains: [...], doctor_not_contains: [...]}
```

Any item may carry `gap: true` and a `note`: no rule or agent behaviour exists for it yet. A gap is reported as
`GAP` (confirmed) or `GAP-CLOSED` (it passed anyway), never as a failure; the summary lists them as
recommendations. Severity in `must_flag` is a minimum; in rule checks it is the rule item's own (possibly
escalated) severity, not the grouped card's.

Automatic checks on every scenario: both PDFs exist, start with `%PDF`, have pages and extractable text; no tofu
(`??` runs, `?` inside a word, `□`, U+FFFD); no "section could not be printed" placeholder; the patient sheet has
the patient's script (≥ 20 characters of it; Latin-script languages: the native "Your medicines" heading); native
sheet labels exist for the language; the patient PDF title and the doctor PDF name the language; the doctor PDF
records a held sentence ("held") or an override ("continued"), and has a Safety alerts section when a caution or
critical rule card was shown; the wrap-up reached the sent screen; no translation errors.

Rule ids are those in `data/safety_rules.json`. Expectations encode clinical correctness, not current behaviour:
a failing check is either an app bug, an extraction miss, or a missing rule (then it should be `gap: true`).
