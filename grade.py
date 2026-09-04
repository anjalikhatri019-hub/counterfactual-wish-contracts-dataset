from __future__ import annotations

import csv
import io
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


EXPECTED_COLUMNS = ["case_id", "policy_json"]
FALLBACKS = {"ROLLBACK_ALL", "DROP_RISKY", "COMMIT_LITERAL"}
MAX_POLICY_CHARS = 4096
PRIVATE_ANSWER_KEYS = {
    "profiles",
    "world_modes",
    "clause_semantics",
    "question_semantics",
    "target",
    "budget",
    "oracle_policy",
    "oracle_value",
    "wish_family",
    "ambiguity_pair",
    "world_tuple",
}


def _read_payload(source: Any) -> str:
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8-sig")
    if isinstance(source, bytes):
        return source.decode("utf-8-sig")
    if isinstance(source, str):
        candidate = Path(source)
        if "\n" not in source and candidate.exists():
            return candidate.read_text(encoding="utf-8-sig")
        return source
    if hasattr(source, "read"):
        payload = source.read()
        return payload.decode("utf-8-sig") if isinstance(payload, bytes) else str(payload)
    nested = getattr(source, "file", None)
    if nested is not None:
        return _read_payload(nested)
    opener = getattr(source, "open", None)
    if callable(opener):
        opened = opener()
        try:
            return _read_payload(opened)
        finally:
            closer = getattr(opened, "close", None)
            if callable(closer):
                closer()
    raise TypeError("Unsupported upload wrapper")


def _rows(source: Any) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(_read_payload(source)))
    columns = list(reader.fieldnames or [])
    rows = [
        {str(key): "" if value is None else str(value) for key, value in row.items()}
        for row in reader
    ]
    return columns, rows


def _validate_submission(
    columns: list[str], submitted_rows: list[dict[str, str]], answer_rows: list[dict[str, str]]
) -> dict[str, str]:
    if columns != EXPECTED_COLUMNS:
        raise ValueError(f"Submission columns must be exactly {EXPECTED_COLUMNS}")
    expected_ids = [row["case_id"] for row in answer_rows]
    submitted: dict[str, str] = {}
    for row in submitted_rows:
        case_id = row.get("case_id", "")
        if case_id in submitted:
            raise ValueError("Duplicate case_id")
        submitted[case_id] = row.get("policy_json", "")
    if len(submitted) != len(expected_ids) or set(submitted) != set(expected_ids):
        raise ValueError("Submission must contain every test case exactly once and no extras")
    return submitted


def _decode_private_answers(
    columns: list[str], raw_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    if columns != EXPECTED_COLUMNS:
        raise ValueError(f"Private answer columns must be exactly {EXPECTED_COLUMNS}")
    decoded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw_rows:
        case_id = row.get("case_id", "")
        if not case_id or case_id in seen:
            raise ValueError("Private answers must contain unique nonempty case_id values")
        seen.add(case_id)
        try:
            payload = json.loads(row.get("policy_json", ""))
        except json.JSONDecodeError as error:
            raise ValueError("Private policy_json is malformed") from error
        if not isinstance(payload, dict) or set(payload) != PRIVATE_ANSWER_KEYS:
            raise ValueError("Private policy_json has an invalid evaluator envelope")
        if (
            not isinstance(payload["profiles"], list)
            or not isinstance(payload["world_modes"], list)
            or not isinstance(payload["clause_semantics"], list)
            or not isinstance(payload["question_semantics"], list)
            or not isinstance(payload["oracle_policy"], dict)
            or not isinstance(payload["wish_family"], str)
            or not isinstance(payload["ambiguity_pair"], str)
            or not isinstance(payload["world_tuple"], str)
        ):
            raise ValueError("Private policy_json contains invalid evaluator types")
        try:
            payload["target"] = float(payload["target"])
            payload["budget"] = int(payload["budget"])
            payload["oracle_value"] = float(payload["oracle_value"])
        except (TypeError, ValueError) as error:
            raise ValueError("Private policy_json contains invalid numeric values") from error
        payload["case_id"] = case_id
        decoded.append(payload)
    if not decoded:
        raise ValueError("Private answers must not be empty")
    return decoded


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _validate_policy(
    raw: str, question_ids: set[str], clause_ids: set[str]
) -> dict[str, Any]:
    if len(raw) > MAX_POLICY_CHARS:
        raise ValueError("policy_json is too long")
    policy = json.loads(raw)
    if not isinstance(policy, dict) or set(policy) != {"question_id", "if_A", "if_B"}:
        raise ValueError("Policy must contain exactly question_id, if_A, and if_B")
    if not isinstance(policy["question_id"], str) or policy["question_id"] not in question_ids:
        raise ValueError("question_id is not in this row's catalogue")
    normalized: dict[str, Any] = {"question_id": policy["question_id"]}
    for branch_name in ("if_A", "if_B"):
        branch = policy[branch_name]
        if not isinstance(branch, dict) or set(branch) != {"clauses", "fallback"}:
            raise ValueError("Each branch must contain exactly clauses and fallback")
        clauses = branch["clauses"]
        if (
            not isinstance(clauses, list)
            or not 1 <= len(clauses) <= 2
            or any(not isinstance(item, str) for item in clauses)
            or len(set(clauses)) != len(clauses)
            or not set(clauses).issubset(clause_ids)
        ):
            raise ValueError("clauses must contain one or two unique row-local clause IDs")
        fallback = branch["fallback"]
        if not isinstance(fallback, str) or fallback not in FALLBACKS:
            raise ValueError("Unknown fallback")
        normalized[branch_name] = {"clauses": sorted(clauses), "fallback": fallback}
    return normalized


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
    contract: dict[str, Any],
    profile: dict[str, str],
    mode: str,
    clauses: dict[str, dict[str, Any]],
    budget: int,
    target: float,
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

    # Selective screening trades realized strength for safety and therefore is
    # not a universally dominant fallback.
    control_factor = 0.80 if fallback == "DROP_RISKY" else (1.10 if fallback == "COMMIT_LITERAL" else 1.0)

    gain = 0.0
    harm = 0.0
    hard_violations = 0
    persistence_mismatches = 0
    for clause in applied:
        gain_factor, extra_harm = _world_adjust(clause, mode)
        beneficiary_factor = 1.0 if clause["beneficiary"] == profile["beneficiary"] else 0.18
        persistence_factor = 1.0 if clause["persistence"] == profile["persistence"] else 0.52
        if clause["persistence"] != profile["persistence"]:
            persistence_mismatches += 1
        gain += 18.0 * int(clause["magnitude"]) * gain_factor * beneficiary_factor * persistence_factor * control_factor
        harm += float(clause["externality"]) + extra_harm
        hard_violations += int(_violates(clause, profile))
    if fallback == "COMMIT_LITERAL":
        harm += 0.8 * len(applied)

    satisfaction = _clamp(gain / target)
    harm_rate = 0.09 if profile["collateral"] == "PROTECT" else 0.035
    penalty = harm_rate * harm + 0.24 * hard_violations + 0.045 * persistence_mismatches
    if applied and sum(int(clause["cost"]) for clause in applied) > budget:
        penalty += 0.18
    score = _clamp(satisfaction - penalty)
    harm_limit = 1.5 if profile["collateral"] == "PROTECT" else 5.0
    safe = bool(applied) and hard_violations == 0 and harm <= harm_limit and sum(int(clause["cost"]) for clause in applied) <= budget
    return score, safe


def _contract_quality(
    contract: dict[str, Any],
    profiles: list[dict[str, str]],
    modes: list[str],
    clauses: dict[str, dict[str, Any]],
    budget: int,
    target: float,
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


def _row_value(policy: dict[str, Any], answer: dict[str, Any]) -> float:
    profiles = answer["profiles"]
    modes = answer["world_modes"]
    clause_rows = answer["clause_semantics"]
    questions = answer["question_semantics"]
    clauses = {row["clause_id"]: row for row in clause_rows}
    question = next(row for row in questions if row["question_id"] == policy["question_id"])
    axis = question["axis"]
    weighted = 0.0
    for answer_name, branch_name in (("A", "if_A"), ("B", "if_B")):
        subset = [profile for profile in profiles if profile[axis] == question[answer_name]]
        quality = _contract_quality(
            policy[branch_name], subset, modes, clauses, answer["budget"], answer["target"]
        )
        weighted += len(subset) * quality / len(profiles)
    return max(0.0, weighted - float(question["burden"]))


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = q * (len(ordered) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def grade_frames(submission: Any, answers: Any) -> dict[str, float]:
    submission_columns, submission_rows = _rows(submission)
    answer_columns, raw_answer_rows = _rows(answers)
    answer_rows = _decode_private_answers(answer_columns, raw_answer_rows)
    submitted = _validate_submission(submission_columns, submission_rows, answer_rows)

    ratios: list[float] = []
    malformed = 0
    regime_scores: dict[str, list[float]] = defaultdict(list)
    for answer in answer_rows:
        question_ids = {row["question_id"] for row in answer["question_semantics"]}
        clause_ids = {row["clause_id"] for row in answer["clause_semantics"]}
        try:
            policy = _validate_policy(submitted[answer["case_id"]], question_ids, clause_ids)
            value = _row_value(policy, answer)
            oracle_value = answer["oracle_value"]
            ratio = _clamp(value / max(oracle_value, 1e-12))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, StopIteration):
            ratio = 0.0
            malformed += 1
        ratios.append(ratio)
        regime = "|".join([answer["ambiguity_pair"], answer["world_tuple"]])
        regime_scores[regime].append(ratio)

    mean_score = sum(ratios) / len(ratios) if ratios else 0.0
    lower_decile = _quantile(ratios, 0.10)
    regime_floor = min((sum(values) / len(values) for values in regime_scores.values()), default=0.0)
    final = 0.65 * mean_score + 0.20 * lower_decile + 0.15 * regime_floor
    return {
        "score": _clamp(final),
        "mean_regret_ratio": mean_score,
        "lower_decile_ratio": lower_decile,
        "worst_regime_mean": regime_floor,
        "malformed_fraction": malformed / len(answer_rows) if answer_rows else 1.0,
    }


def grade(submission: Any, answers: Any) -> float:
    return float(grade_frames(submission, answers)["score"])
