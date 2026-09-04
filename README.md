# Counterfactual Wish Contracts dataset

This is the canonical public source repository for **Counterfactual Wish Contracts - Original Wish Intent and Contingent Policy Dataset**.

The dataset is original synthetic work created for the Counterfactual Wish Contracts fine-tuning challenge. It is generated from `source_catalog.json` by the deterministic `prepare.py` program. No rows or labels were copied from another dataset.

## Canonical source URL

https://github.com/anjalikhatri019-hub/counterfactual-wish-contracts-dataset

Use the repository URL above as the dataset **Source URL**. Do not use the Creative Commons or SPDX page as the source URL; those pages identify the licence, not this dataset.

## Contents

- `source_catalog.json`: original semantic source catalogue.
- `source_manifest.csv`: provenance, licence, and canonical source URL inventory.
- `DATASET_DESCRIPTION.md`: fields, units, label semantics, limitations, biases, and generalizability.
- `prepare.py`: deterministic 12,000-train/3,000-test generator.
- `grade.py`: exact deterministic evaluator.
- `LICENSE_DATA.md`: CC BY 4.0 data and documentation licence.
- `LICENSE_CODE.md`: MIT code licence.
- `dataset-metadata.json`: machine-readable dataset identity.

The public repository contains no private test answers. Release assets provide the platform-ready raw dataset ZIP.

## Prepared evaluator contract

`train.csv` contains seven public input columns followed by the exact oracle `policy_json` supervised label and auxiliary unitless `oracle_value`. `test.csv` contains only the seven inputs. Both `sample_submission.csv` and the organizer-only `answers.csv` use the exact ordered header `case_id,policy_json`; private answer cells are sealed evaluator envelopes decoded only by `grade.py`. Train/test row IDs and row-local catalogue IDs are disjoint, and test additionally holds out ambiguity pairs, wish-template members, and a charter-composition rule.

## Licences

Generated dataset and documentation: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Preparation and grading code: MIT.
