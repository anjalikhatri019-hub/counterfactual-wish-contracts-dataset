from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import random
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any


SEED = 260904
TRAIN_CASES = 12000
TEST_CASES = 3000
CATALOG_VERSION = "1.0.0"

AXES = ["beneficiary", "persistence", "source", "reversibility", "collateral"]
AXIS_VALUES = {
    "beneficiary": ["FOCAL", "SHARED"],
    "persistence": ["LASTING", "SEASONAL"],
    "source": ["CREATED", "REALLOCATED"],
    "reversibility": ["REVERSIBLE", "FINAL"],
    "collateral": ["PROTECT", "TRADEOFF"],
}
AXIS_CONTEXT = {
    ("beneficiary", "FOCAL"): "the benefit should stay with the named subject rather than spread broadly",
    ("beneficiary", "SHARED"): "the benefit should be shared with the surrounding community",
    ("persistence", "LASTING"): "a lasting result is preferred even if it takes more effort",
    ("persistence", "SEASONAL"): "a bounded seasonal result is preferred over a permanent change",
    ("source", "CREATED"): "the gain must be newly created and may not be taken from anyone else",
    ("source", "REALLOCATED"): "reallocation is acceptable when it makes the grant more effective",
    ("reversibility", "REVERSIBLE"): "the grant must remain reversible if its consequences turn out badly",
    ("reversibility", "FINAL"): "a final irreversible settlement is acceptable",
    ("collateral", "PROTECT"): "protecting bystanders takes priority over the size of the gain",
    ("collateral", "TRADEOFF"): "a limited external burden is acceptable for a much stronger result",
}
QUESTION_SPECS = {
    "beneficiary": (
        "Should the grant focus only on the named subject, or share its benefit more broadly?",
        "Only the named subject",
        "Share it broadly",
    ),
    "persistence": (
        "Must the result endure, or should it be limited to a season?",
        "Make it lasting",
        "Limit it to a season",
    ),
    "source": (
        "Must the gain be newly created, or may existing value be reallocated?",
        "Create it without taking",
        "Reallocation is acceptable",
    ),
    "reversibility": (
        "Should the grant be reversible, or may it be final?",
        "Keep it reversible",
        "It may be final",
    ),
    "collateral": (
        "Should bystanders be protected absolutely, or is a limited trade-off acceptable?",
        "Protect bystanders",
        "A limited trade-off is acceptable",
    ),
}
BENEFICIARY_TEXT = {
    "FOCAL": ["for the named subject alone", "only around the focal recipient", "within the named recipient's circle"],
    "SHARED": ["across the surrounding community", "for the focal recipient and nearby people", "as a broadly shared benefit"],
}
PERSISTENCE_TEXT = {
    "LASTING": ["with no planned expiry", "as an enduring change", "for the long term"],
    "SEASONAL": ["for one bounded season", "with an automatic near-term expiry", "as a temporary interval"],
}
SOURCE_TEXT = {
    "CREATED": ["from newly formed value", "without taking an existing holding", "through fresh provision"],
    "REALLOCATED": ["by reallocating existing value", "through a transfer from elsewhere", "by redirecting a current holding"],
}
REVERSIBILITY_TEXT = {
    "REVERSIBLE": ["and leave a working reversal path", "with an enforceable undo clause", "while preserving a way back"],
    "FINAL": ["as a final settlement", "without an undo path", "under an irreversible seal"],
}
FALLBACKS = ["ROLLBACK_ALL", "DROP_RISKY", "COMMIT_LITERAL"]
WORLD_MODES = ["LITERAL", "CONSERVATION", "ECHO", "FRAGILE"]
TEST_PAIR_INDICES = {0, 5, 8}


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_int(*parts: Any, mod: int = 2**31 - 1) -> int:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16) % mod


def token(prefix: str, *parts: Any, length: int = 10) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:length]}"


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _raw_marker(path: Path) -> bool:
    required = {
        "source_catalog.json",
        "source_manifest.csv",
        "LICENSE_DATA.md",
        "DATASET_DESCRIPTION.md",
    }
    return path.is_dir() and required.issubset({item.name for item in path.iterdir() if item.is_file()})


def _candidate_directories(root: Path) -> list[Path]:
    candidates = [root]
    if root.is_dir():
        for marker in root.rglob("source_catalog.json"):
            try:
                relative = marker.parent.relative_to(root)
            except ValueError:
                continue
            if len(relative.parts) <= 4:
                candidates.append(marker.parent)
    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(candidate)
    return result


def _resolve_raw(dataset_dir: Path, extraction_root: Path) -> Path:
    dataset_dir = Path(dataset_dir)
    if dataset_dir.is_file() and dataset_dir.suffix.lower() == ".zip":
        with zipfile.ZipFile(dataset_dir) as archive:
            archive.extractall(extraction_root)
        dataset_dir = extraction_root
    for candidate in _candidate_directories(dataset_dir):
        if _raw_marker(candidate):
            return candidate
    valid: list[Path] = []
    if dataset_dir.is_dir():
        for index, archive_path in enumerate(sorted(dataset_dir.rglob("*.zip"))):
            target = extraction_root / f"archive_{index}"
            target.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    archive.extractall(target)
            except zipfile.BadZipFile:
                continue
            valid.extend(candidate for candidate in _candidate_directories(target) if _raw_marker(candidate))
    unique = {candidate.resolve(): candidate for candidate in valid}
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        raise ValueError("Multiple valid raw source packs found; provide exactly one")
    raise FileNotFoundError(
        "Raw pack must contain source_catalog.json, source_manifest.csv, "
        "LICENSE_DATA.md, and DATASET_DESCRIPTION.md"
    )


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _read_catalog(raw: Path) -> dict[str, Any]:
    catalog = json.loads((raw / "source_catalog.json").read_text(encoding="utf-8"))
    if catalog.get("catalog_version") != CATALOG_VERSION:
        raise ValueError(f"Expected source catalog version {CATALOG_VERSION}")
    families = catalog.get("wish_families")
    if not isinstance(families, list) or len(families) < 8:
        raise ValueError("source_catalog.json must contain at least eight wish families")
    if set(catalog.get("world_charters", {})) != set(WORLD_MODES):
        raise ValueError("source_catalog.json has an invalid world charter catalogue")
    return catalog


def _make_profiles(fixed: dict[str, str], uncertain: tuple[str, str]) -> list[dict[str, str]]:
    profiles: list[dict[str, str]] = []
    for values in itertools.product(*(AXIS_VALUES[axis] for axis in uncertain)):
        profile = dict(fixed)
        profile.update(dict(zip(uncertain, values)))
        profiles.append(profile)
    return profiles


def _question_catalog(case_id: str, rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []
    for axis in AXES:
        question, answer_a, answer_b = QUESTION_SPECS[axis]
        question_id = token("Q", case_id, axis)
        burden = round(0.008 + 0.006 * (stable_int(case_id, axis, "burden", mod=6)), 3)
        public.append({
            "question_id": question_id,
            "question": question,
            "A": answer_a,
            "B": answer_b,
            "burden": burden,
        })
        private.append({
            "question_id": question_id,
            "axis": axis,
            "A": AXIS_VALUES[axis][0],
            "B": AXIS_VALUES[axis][1],
            "burden": burden,
        })
    rng.shuffle(public)
    rng.shuffle(private)
    return public, private


def _clause_description(catalog: dict[str, Any], family: str, attrs: dict[str, Any], rng: random.Random) -> str:
    verb = rng.choice(catalog["clause_verbs"][family])
    magnitude = rng.choice(catalog["magnitude_phrases"][str(attrs["magnitude"])])
    beneficiary = rng.choice(BENEFICIARY_TEXT[attrs["beneficiary"]])
    persistence = rng.choice(PERSISTENCE_TEXT[attrs["persistence"]])
    source = rng.choice(SOURCE_TEXT[attrs["source"]])
    reversibility = rng.choice(REVERSIBILITY_TEXT[attrs["reversibility"]])
    externality = rng.choice(catalog["externality_phrases"][str(attrs["externality"])])
    return (
        f"Use {magnitude} seal to {verb} {beneficiary}, {persistence}, {source}, "
        f"{reversibility}, {externality}. It consumes {attrs['cost']} seal mark"
        f"{'s' if attrs['cost'] != 1 else ''}."
    )


def _make_clauses(
    catalog: dict[str, Any], case_id: str, family: str, uncertain: tuple[str, str], fixed: dict[str, str], rng: random.Random
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def add(attrs: dict[str, Any]) -> None:
        key = tuple(attrs[name] for name in ["beneficiary", "persistence", "source", "reversibility", "magnitude", "externality", "cost"])
        if key not in seen:
            seen.add(key)
            candidates.append(attrs)

    # Guarantee at least one aligned primitive for every compatible intent profile.
    for profile in _make_profiles(fixed, uncertain):
        add({
            "beneficiary": profile["beneficiary"],
            "persistence": profile["persistence"],
            "source": profile["source"],
            "reversibility": profile["reversibility"],
            "magnitude": 2 if profile["collateral"] == "PROTECT" else 3,
            "externality": 0 if profile["collateral"] == "PROTECT" else 2,
            "cost": 2 if profile["collateral"] == "PROTECT" else 1,
        })

    while len(candidates) < 12:
        attrs = {
            "beneficiary": rng.choice(AXIS_VALUES["beneficiary"]),
            "persistence": rng.choice(AXIS_VALUES["persistence"]),
            "source": rng.choice(AXIS_VALUES["source"]),
            "reversibility": rng.choice(AXIS_VALUES["reversibility"]),
            "magnitude": rng.randint(1, 3),
            "externality": rng.randint(0, 3),
            "cost": rng.randint(1, 3),
        }
        add(attrs)

    public: list[dict[str, str]] = []
    private: list[dict[str, Any]] = []
    for index, attrs in enumerate(candidates):
        clause_id = token("C", case_id, index, dumps(attrs))
        public.append({"clause_id": clause_id, "text": _clause_description(catalog, family, attrs, rng)})
        private.append({"clause_id": clause_id, **attrs})
    rng.shuffle(public)
    rng.shuffle(private)
    return public, private


def _violates(clause: dict[str, Any], profile: dict[str, str]) -> bool:
    if clause["source"] != profile["source"]:
        return True
    if profile["reversibility"] == "REVERSIBLE" and clause["reversibility"] == "FINAL":
        return True
    if profile["collateral"] == "PROTECT" and int(clause["externality"]) > 1:
        return True
    return False


def _world_adjust(clause: dict[str, Any], mode: str) -> tuple[float, float]:
    gain_factor = 1.0
    extra_harm = 0.0
    if mode == "CONSERVATION":
        if clause["source"] == "CREATED":
            gain_factor *= 0.64
        else:
            gain_factor *= 1.04
            extra_harm += 1.0
    elif mode == "ECHO" and int(clause["magnitude"]) == 3:
        extra_harm += 1.5
    elif mode == "FRAGILE":
        if clause["persistence"] == "SEASONAL":
            gain_factor *= 1.15
        else:
            gain_factor *= 0.78
        if clause["reversibility"] == "FINAL":
            gain_factor *= 1.08
    return gain_factor, extra_harm


def _outcome(
    contract: dict[str, Any], profile: dict[str, str], mode: str, clauses: dict[str, dict[str, Any]], budget: int, target: float
) -> tuple[float, bool]:
    selected = [clauses[clause_id] for clause_id in contract["clauses"]]
    violating = [_violates(clause, profile) for clause in selected]
    over_budget = sum(int(clause["cost"]) for clause in selected) > budget
    fallback = contract["fallback"]
    if fallback == "ROLLBACK_ALL" and (any(violating) or over_budget):
        applied: list[dict[str, Any]] = []
    elif fallback == "DROP_RISKY":
        applied = [clause for clause, bad in zip(selected, violating) if not bad]
        if sum(int(clause["cost"]) for clause in applied) > budget:
            applied = []
    else:
        applied = selected

    # Guarding is not free: selective clause inspection weakens the realized grant.
    # This prevents DROP_RISKY from strictly dominating both rollback and commitment.
    control_factor = 0.80 if fallback == "DROP_RISKY" else (1.10 if fallback == "COMMIT_LITERAL" else 1.0)

    gain = 0.0
    harm = 0.0
    hard_violations = 0
    persistence_mismatches = 0
    for clause in applied:
        factor, extra_harm = _world_adjust(clause, mode)
        beneficiary_factor = 1.0 if clause["beneficiary"] == profile["beneficiary"] else 0.18
        persistence_factor = 1.0 if clause["persistence"] == profile["persistence"] else 0.52
        if clause["persistence"] != profile["persistence"]:
            persistence_mismatches += 1
        gain += 18.0 * int(clause["magnitude"]) * factor * beneficiary_factor * persistence_factor * control_factor
        harm += float(clause["externality"]) + extra_harm
        hard_violations += int(_violates(clause, profile))
    if fallback == "COMMIT_LITERAL":
        harm += 0.8 * len(applied)

    satisfaction = clamp(gain / target)
    harm_rate = 0.09 if profile["collateral"] == "PROTECT" else 0.035
    penalty = harm_rate * harm + 0.24 * hard_violations + 0.045 * persistence_mismatches
    if applied and sum(int(clause["cost"]) for clause in applied) > budget:
        penalty += 0.18
    score = clamp(satisfaction - penalty)
    harm_limit = 1.5 if profile["collateral"] == "PROTECT" else 5.0
    safe = bool(applied) and hard_violations == 0 and harm <= harm_limit and sum(int(clause["cost"]) for clause in applied) <= budget
    return score, safe


def _contract_quality(
    contract: dict[str, Any], profiles: list[dict[str, str]], modes: list[str], clauses: dict[str, dict[str, Any]], budget: int, target: float
) -> float:
    if not profiles:
        return 0.0
    scores: list[float] = []
    safe_count = 0
    per_profile: list[float] = []
    for profile in profiles:
        profile_scores: list[float] = []
        for mode in modes:
            score, safe = _outcome(contract, profile, mode, clauses, budget, target)
            scores.append(score)
            profile_scores.append(score)
            safe_count += int(safe)
        per_profile.append(sum(profile_scores) / len(profile_scores))
    mean_score = sum(scores) / len(scores)
    worst_score = min(scores)
    safety_rate = safe_count / len(scores)
    profile_floor = min(per_profile)
    return mean_score * (0.55 + 0.20 * safety_rate) + 0.15 * worst_score + 0.10 * profile_floor


def _contracts(clause_ids: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for size in (1, 2):
        for selected in itertools.combinations(sorted(clause_ids), size):
            for fallback in FALLBACKS:
                result.append({"clauses": list(selected), "fallback": fallback})
    return result


def _best_contract(
    contracts: list[dict[str, Any]], profiles: list[dict[str, str]], modes: list[str], clauses: dict[str, dict[str, Any]], budget: int, target: float
) -> tuple[dict[str, Any], float]:
    if not profiles:
        contract = contracts[0]
        return contract, 0.0
    best_contract = contracts[0]
    best_value = -1.0
    for contract in contracts:
        value = _contract_quality(contract, profiles, modes, clauses, budget, target)
        key = dumps(contract)
        best_key = dumps(best_contract)
        if value > best_value + 1e-12 or (abs(value - best_value) <= 1e-12 and key < best_key):
            best_contract = contract
            best_value = value
    return best_contract, best_value


def _oracle_policy(
    questions: list[dict[str, Any]], profiles: list[dict[str, str]], modes: list[str], clause_rows: list[dict[str, Any]], budget: int, target: float
) -> tuple[dict[str, Any], float]:
    clauses = {row["clause_id"]: row for row in clause_rows}
    contracts = _contracts(list(clauses))
    subset_cache: dict[tuple[int, ...], tuple[dict[str, Any], float]] = {}

    def best_for(indices: tuple[int, ...]) -> tuple[dict[str, Any], float]:
        if indices not in subset_cache:
            subset_cache[indices] = _best_contract(
                contracts, [profiles[index] for index in indices], modes, clauses, budget, target
            )
        return subset_cache[indices]

    best_policy: dict[str, Any] | None = None
    best_value = -1.0
    for question in questions:
        axis = question["axis"]
        subsets = {
            "A": tuple(index for index, profile in enumerate(profiles) if profile[axis] == question["A"]),
            "B": tuple(index for index, profile in enumerate(profiles) if profile[axis] == question["B"]),
        }
        branches: dict[str, dict[str, Any]] = {}
        weighted = 0.0
        for answer in ("A", "B"):
            branch_contract, quality = best_for(subsets[answer])
            branches[answer] = branch_contract
            weighted += len(subsets[answer]) * quality / len(profiles)
        value = max(0.0, weighted - float(question["burden"]))
        policy = {"question_id": question["question_id"], "if_A": branches["A"], "if_B": branches["B"]}
        key = dumps(policy)
        best_key = dumps(best_policy) if best_policy is not None else ""
        if value > best_value + 1e-12 or (abs(value - best_value) <= 1e-12 and (best_policy is None or key < best_key)):
            best_policy = policy
            best_value = value
    assert best_policy is not None
    return best_policy, best_value


def _make_case(catalog: dict[str, Any], split: str, index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    case_seed = stable_int(SEED, split, index)
    rng = random.Random(case_seed)
    case_id = token("wish", split, index, case_seed, length=12)
    families = catalog["wish_families"]
    family_row = families[stable_int(case_id, "family", mod=len(families))]
    family = family_row["family"]
    subject = catalog["subjects"][stable_int(case_id, "subject", mod=len(catalog["subjects"]))]
    template_pool = family_row["templates"][:3] if split == "train" else family_row["templates"][3:]
    wish_text = template_pool[stable_int(case_id, "wish_template", mod=len(template_pool))].format(subject=subject)

    all_pairs = list(itertools.combinations(AXES, 2))
    train_pairs = [pair for pair_index, pair in enumerate(all_pairs) if pair_index not in TEST_PAIR_INDICES]
    test_pairs = [pair for pair_index, pair in enumerate(all_pairs) if pair_index in TEST_PAIR_INDICES]
    pair_pool = train_pairs if split == "train" else test_pairs
    uncertain = pair_pool[stable_int(case_id, "uncertain_pair", mod=len(pair_pool))]
    fixed = {
        axis: AXIS_VALUES[axis][stable_int(case_id, axis, "fixed", mod=2)]
        for axis in AXES if axis not in uncertain
    }
    profiles = _make_profiles(fixed, uncertain)

    settled = [AXIS_CONTEXT[(axis, fixed[axis])] for axis in AXES if axis in fixed]
    rng.shuffle(settled)
    opener = catalog["context_openers"][stable_int(case_id, "opener", mod=len(catalog["context_openers"]))]
    context_text = opener + " " + "; ".join(settled) + ". Two other material preferences remain unresolved."

    public_questions, private_questions = _question_catalog(case_id, rng)
    public_clauses, private_clauses = _make_clauses(catalog, case_id, family, uncertain, fixed, rng)
    if split == "train":
        omitted_mode = stable_int(case_id, family, "train_world", mod=4)
    else:
        # Joint family/world holdout rotates differently from training construction.
        omitted_mode = (families.index(family_row) * 3 + 1) % 4
    modes = [mode for mode_index, mode in enumerate(WORLD_MODES) if mode_index != omitted_mode]
    charter_lines = [catalog["world_charters"][mode] for mode in modes]
    rng.shuffle(charter_lines)
    charter_text = "The seal may lawfully resolve under any of these disclosed readings: " + " ".join(charter_lines)

    budget = 4 + stable_int(case_id, "budget", mod=2)
    target = 54.0 + 6.0 * stable_int(case_id, family, "target", mod=3)
    oracle_policy, oracle_value = _oracle_policy(
        private_questions, profiles, modes, private_clauses, budget, target
    )
    public = {
        "case_id": case_id,
        "wish_text": wish_text,
        "context_text": context_text,
        "charter_text": charter_text,
        "question_catalog_json": dumps(public_questions),
        "clause_catalog_json": dumps(public_clauses),
        "contract_limits_json": dumps({"min_clauses": 1, "max_clauses": 2, "seal_mark_budget": budget}),
    }
    private = {
        "case_id": case_id,
        "profiles_json": dumps(profiles),
        "world_modes_json": dumps(modes),
        "clause_semantics_json": dumps(private_clauses),
        "question_semantics_json": dumps(private_questions),
        "target": f"{target:.6f}",
        "budget": str(budget),
        "oracle_policy_json": dumps(oracle_policy),
        "oracle_value": f"{oracle_value:.12f}",
        "wish_family": family,
        "ambiguity_pair": "+".join(uncertain),
        "world_tuple": "+".join(sorted(modes)),
    }
    return public, private


def _baseline_policy(public_row: dict[str, Any]) -> str:
    questions = json.loads(public_row["question_catalog_json"])
    clauses = json.loads(public_row["clause_catalog_json"])
    policy = {
        "question_id": questions[0]["question_id"],
        "if_A": {"clauses": [clauses[0]["clause_id"]], "fallback": "ROLLBACK_ALL"},
        "if_B": {"clauses": [clauses[0]["clause_id"]], "fallback": "ROLLBACK_ALL"},
    }
    return dumps(policy)


def _private_answer_payload(private: dict[str, str]) -> str:
    """Seal evaluator-only state behind the platform-required policy_json column."""
    return dumps({
        "profiles": json.loads(private["profiles_json"]),
        "world_modes": json.loads(private["world_modes_json"]),
        "clause_semantics": json.loads(private["clause_semantics_json"]),
        "question_semantics": json.loads(private["question_semantics_json"]),
        "target": float(private["target"]),
        "budget": int(private["budget"]),
        "oracle_policy": json.loads(private["oracle_policy_json"]),
        "oracle_value": float(private["oracle_value"]),
        "wish_family": private["wish_family"],
        "ambiguity_pair": private["ambiguity_pair"],
        "world_tuple": private["world_tuple"],
    })


def prepare_sized(
    dataset_dir: Path, public_dir: Path, private_dir: Path, train_cases: int, test_cases: int
) -> None:
    dataset_dir = Path(dataset_dir)
    public_dir = Path(public_dir)
    private_dir = Path(private_dir)
    if train_cases < 1 or test_cases < 1:
        raise ValueError("train_cases and test_cases must both be positive")
    with tempfile.TemporaryDirectory(prefix="wish_contract_prepare_") as temp:
        raw = _resolve_raw(dataset_dir, Path(temp))
        catalog = _read_catalog(raw)
        public_dir.mkdir(parents=True, exist_ok=True)
        private_dir.mkdir(parents=True, exist_ok=True)
        train_rows: list[dict[str, Any]] = []
        test_rows: list[dict[str, Any]] = []
        answer_rows: list[dict[str, Any]] = []
        for index in range(train_cases):
            public, private = _make_case(catalog, "train", index)
            train_rows.append({**public, "policy_json": private["oracle_policy_json"], "oracle_value": private["oracle_value"]})
        for index in range(test_cases):
            public, private = _make_case(catalog, "test", index)
            test_rows.append(public)
            answer_rows.append({
                "case_id": private["case_id"],
                "policy_json": _private_answer_payload(private),
            })

        input_columns = [
            "case_id", "wish_text", "context_text", "charter_text", "question_catalog_json",
            "clause_catalog_json", "contract_limits_json",
        ]
        _write_csv(public_dir / "train.csv", input_columns + ["policy_json", "oracle_value"], train_rows)
        _write_csv(public_dir / "test.csv", input_columns, test_rows)
        _write_csv(
            public_dir / "sample_submission.csv",
            ["case_id", "policy_json"],
            [{"case_id": row["case_id"], "policy_json": _baseline_policy(row)} for row in test_rows],
        )
        # ShipD requires answers.csv and sample_submission.csv to expose the
        # exact same columns in the exact same order. Evaluator-only state is
        # encoded inside the private policy_json cell and never copied public.
        _write_csv(private_dir / "answers.csv", ["case_id", "policy_json"], answer_rows)
        (public_dir / "policy_schema.json").write_text(
            dumps({
                "exact_top_level_keys": ["question_id", "if_A", "if_B"],
                "branch_exact_keys": ["clauses", "fallback"],
                "fallback_values": FALLBACKS,
                "clause_count": [1, 2],
            }) + "\n",
            encoding="utf-8",
        )
        summary = {
            "challenge": "Counterfactual Wish Contracts",
            "catalog_version": CATALOG_VERSION,
            "seed": SEED,
            "train_rows": train_cases,
            "test_rows": test_cases,
            "train_ambiguity_pairs": [
                "+".join(pair) for pair_index, pair in enumerate(itertools.combinations(AXES, 2))
                if pair_index not in TEST_PAIR_INDICES
            ],
            "test_ambiguity_pairs": [
                "+".join(pair) for pair_index, pair in enumerate(itertools.combinations(AXES, 2))
                if pair_index in TEST_PAIR_INDICES
            ],
        }
        (public_dir / "prepared_summary.json").write_text(dumps(summary) + "\n", encoding="utf-8")
        shutil.copy2(raw / "LICENSE_DATA.md", public_dir / "LICENSE_DATA.md")
        shutil.copy2(raw / "source_manifest.csv", public_dir / "source_manifest.csv")
        shutil.copy2(raw / "DATASET_DESCRIPTION.md", public_dir / "DATASET_DESCRIPTION.md")


def prepare(dataset_dir: Path, public_dir: Path, private_dir: Path) -> None:
    prepare_sized(dataset_dir, public_dir, private_dir, TRAIN_CASES, TEST_CASES)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("public_dir", type=Path)
    parser.add_argument("private_dir", type=Path)
    parser.add_argument("--train-cases", type=int, default=TRAIN_CASES)
    parser.add_argument("--test-cases", type=int, default=TEST_CASES)
    args = parser.parse_args()
    prepare_sized(args.dataset_dir, args.public_dir, args.private_dir, args.train_cases, args.test_cases)
