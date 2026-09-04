# Counterfactual Wish Contracts — raw dataset card

## Origin, licence, and contents

This raw pack is the original human-authored semantic source for the Counterfactual Wish Contracts benchmark. It is not copied or adapted from another dataset. Generated data and documentation are CC BY 4.0; preparation and grading code distributed separately are MIT.

## Canonical source URL

https://github.com/anjalikhatri019-hub/counterfactual-wish-contracts-dataset

The public repository identifies this dataset by its exact title and contains the matching `source_catalog.json`, dataset metadata, documentation, licences, and deterministic preparation code. The Creative Commons and SPDX pages identify the licence but are not dataset source URLs.

The raw ZIP contains exactly:

- `source_catalog.json`: UTF-8 JSON containing original wish families, paraphrase templates, charter modes, preference-axis wording, clause wording, simulator constants, and fallback names.
- `source_manifest.csv`: UTF-8 CSV provenance and licence inventory.
- `LICENSE_DATA.md`: dataset and documentation licence.
- `DATASET_DESCRIPTION.md`: this dataset card.
- `README.md`: preparation note and concise semantic warning.

The raw pack contains no generated rows and no private test labels. `prepare.py` deterministically expands it into 12,000 training rows and 3,000 test rows.

## Prepared fields and labels

- `case_id` is an opaque answer-independent string identifier with no predictive or ordinal semantics.
- `wish_text`, `context_text`, and `charter_text` are synthetic English strings.
- `question_catalog_json` is a JSON string encoding exactly five independently permuted question objects. Every object has string fields `question_id`, `question`, `A`, and `B`, and numeric field `burden`.
- `clause_catalog_json` is a JSON string encoding exactly twelve independently permuted objects with string fields `clause_id` and `text`.
- `contract_limits_json` is a JSON string encoding integer `min_clauses`, `max_clauses`, and `seal_mark_budget`.
- Training-only `policy_json` is the exact oracle contingent-policy label. It chooses one row-local question and one answer-specific branch for A and B; each branch contains one or two row-local clause IDs and one categorical fallback.
- Training-only `oracle_value` is the exact exhaustive oracle's raw policy value.

## Units and label semantics

### `oracle_value`

`oracle_value` is a dimensionless simulator value in `[0,1]`. It is not a probability, percentage, currency amount, human rating, or final leaderboard row score. For a candidate policy, the evaluator forms the answer-probability-weighted mean of its A and B branch qualities, subtracts question burden once, and floors at zero. The organizer exhaustively searches every valid question and branch contract; the maximum is `oracle_value`, also written `V*`. Higher is better. Submission evaluation later uses `min(1, V / V*)`, so raw `oracle_value` and normalized row score are different quantities.

### Question `burden`

`burden` is a dimensionless score penalty for asking a clarification. It is not time, money, tokens, response probability, or a human-measured discomfort score. Allowed generated values are `0.008`, `0.014`, `0.020`, `0.026`, `0.032`, and `0.038`. Higher means more costly or intrusive under the simulator. It is subtracted exactly once after answer-branch averaging and before the zero floor, on the same unitless scale as `oracle_value`.

### Other quantities

- A seal mark is an abstract integer budget unit, not a real-world resource. Clause text states costs of 1, 2, or 3 seal marks; `seal_mark_budget` is 4 or 5.
- `min_clauses` and `max_clauses` are inclusive counts; generated values are 1 and 2.
- Magnitude, duration, and externality phrases are ordinal simulator attributes without calibrated real-world units.
- IDs are synthetic opaque strings. Prefixes indicate object type only; hash characters encode no label, order, cost, burden, or value.
- Fallback is categorical. `ROLLBACK_ALL` cancels a violating or over-budget branch; `DROP_RISKY` removes violating clauses and realizes 80% strength; `COMMIT_LITERAL` realizes 110% strength and adds 0.8 simulator exposure per executed clause.

## Known limitations, biases, and generalizability

- This dataset is fully synthetic and simulator-labelled. It has no real people, observed wishes, human clarification behaviour, or human safety judgements. Its score does not establish real-world alignment, safety, or deployment readiness.
- Language is English-only and generated from finite templates and paraphrase families. Dialects, multilingual usage, cultural variation, slang, typos, indirect speech, long dialogue, and adversarial natural language are poorly represented or absent.
- The intent model has exactly five binary axes, exactly two unresolved axes, and four compatible profiles per case. It does not cover continuous, correlated, changing, multi-party, or open-ended preferences.
- Each case provides five binary questions and twelve fixed-format clause candidates. A policy asks one question and chooses a one- or two-clause branch. Free-form question generation, repeated questioning, negotiation, open-vocabulary contracts, and plans outside this grammar are not measured.
- The evaluator embeds specific normative simulator choices about safety, satisfaction, worst cases, question cost, externality, clause strength, and fallback behaviour. The oracle is optimal only for those rules and is not a claim about correct real-world values.
- The finalized test oracle has label imbalance. Question targets are source 1,062, beneficiary 909, persistence 784, reversibility 179, and collateral 66. Across 6,000 oracle branches, fallback counts are 4,641 rollback, 974 drop-risky, and 385 literal; clause counts are 849 single and 5,151 double. Models can exploit majority tendencies.
- Held-out ambiguity pairs, templates, and charter composition test specified compositional shifts, not arbitrary open-world generalization. Primitive axis, clause, question, and charter families remain related to training support.
- The dataset contains no real personal or sensitive attributes. This limits privacy risk but prevents meaningful demographic-fairness or disparate-impact evaluation.
- Deterministic templating may leave surface regularities despite independent ID and catalogue permutation. Surface performance should be reported as a shortcut diagnostic.

Use this dataset only as a controlled benchmark for fine-tuning, active clarification, constrained contingent synthesis, and compositional generalization. Review the full participant dataset description and evaluation specification before interpreting scores.
