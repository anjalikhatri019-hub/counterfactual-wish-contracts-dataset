# Counterfactual Wish Contracts dataset

This is the canonical public source repository for **Counterfactual Wish Contracts - Original Wish Intent and Contingent Policy Dataset**.

The dataset is original synthetic work created for the Counterfactual Wish Contracts fine-tuning challenge. Organizer-only deterministic preparation expands `source_catalog.json` into the competition data. No rows or labels were copied from another dataset.

## Canonical source URL

https://github.com/anjalikhatri019-hub/counterfactual-wish-contracts-dataset

Use the repository URL above as the dataset **Source URL**. Do not use the Creative Commons or SPDX page as the source URL; those pages identify the licence, not this dataset.

## Contents

- `source_catalog.json`: original semantic source catalogue.
- `source_manifest.csv`: per-asset provenance and canonical source-link inventory. Dataset-wide licensing is defined once in `LICENSE_DATA.md`, avoiding a redundant constant CSV column.
- `DATASET_DESCRIPTION.md`: fields, units, label semantics, limitations, biases, and generalizability.
- `LICENSE_DATA.md`: CC BY 4.0 data and documentation licence.
- `dataset-metadata.json`: machine-readable dataset identity.

The public repository contains no private test answers, evaluator, or private-oracle generator. Those components are restricted to the challenge organizer. Release assets provide the platform-ready raw dataset ZIP.

Version 2.1.0 removes the redundant constant `license` field from `source_manifest.csv`. The pack-wide CC BY 4.0 licence remains authoritative in `LICENSE_DATA.md`; no generated examples, labels, splits, simulator rules, or evaluation behavior changed.

## Prepared evaluator contract

`train.csv` contains seven public input columns followed by the exact oracle `policy_json` supervised label. `test.csv` contains the same seven inputs and no label. Both `sample_submission.csv` and the organizer-only `answers.csv` use the exact ordered header `case_id,policy_json`; private answer cells are sealed evaluator envelopes decoded only by the organizer. Train/test row IDs and row-local catalogue IDs are disjoint. Test holds out five complete three-axis ambiguity combinations, wish/context/question paraphrase families, and a family-conditioned charter-omission rule.

## Licences

Generated dataset and documentation: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Organizer preparation and grading code, when distributed separately: MIT.
