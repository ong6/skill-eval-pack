#!/usr/bin/env python3
"""Create a blinded skill A/B packet and apply a strict keep-or-retire gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys


class Invalid(ValueError):
    pass


def read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Invalid(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Invalid(f"{path} must contain a JSON object")
    return value


def write_new(path: Path, value: dict) -> None:
    if path.exists():
        raise Invalid(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Invalid(f"{field} must be non-empty text")
    return value


def validate_input(data: dict) -> None:
    if data.get("version") != 1:
        raise Invalid("input version must be 1")
    require_text(data.get("title"), "title")
    rubric = data.get("rubric")
    cases = data.get("cases")
    if not isinstance(rubric, list) or not rubric:
        raise Invalid("rubric must be a non-empty array")
    if not isinstance(cases, list) or not cases:
        raise Invalid("cases must be a non-empty array")
    ids = set()
    core = False
    for item in rubric:
        if not isinstance(item, dict):
            raise Invalid("each rubric item must be an object")
        item_id = require_text(item.get("id"), "rubric.id")
        if item_id in ids:
            raise Invalid(f"duplicate rubric id: {item_id}")
        ids.add(item_id)
        require_text(item.get("label"), f"rubric {item_id} label")
        if not isinstance(item.get("weight"), (int, float)) or item["weight"] <= 0:
            raise Invalid(f"rubric {item_id} weight must be positive")
        if not isinstance(item.get("max_score"), (int, float)) or item["max_score"] <= 0:
            raise Invalid(f"rubric {item_id} max_score must be positive")
        if not isinstance(item.get("core"), bool):
            raise Invalid(f"rubric {item_id} core must be boolean")
        core |= item["core"]
    if not core:
        raise Invalid("at least one rubric criterion must be core")
    case_ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise Invalid("each case must be an object")
        case_id = require_text(case.get("id"), "case.id")
        if case_id in case_ids:
            raise Invalid(f"duplicate case id: {case_id}")
        case_ids.add(case_id)
        for field in ("input", "expected", "baseline", "treatment"):
            require_text(case.get(field), f"case {case_id} {field}")
    failures = data.get("critical_failures", [])
    if not isinstance(failures, list) or any(not isinstance(x, str) or not x.strip() for x in failures):
        raise Invalid("critical_failures must be an array of non-empty strings")
    delta = data.get("gate", {}).get("minimum_overall_delta", 5)
    if not isinstance(delta, (int, float)) or delta < 0 or delta > 100:
        raise Invalid("minimum_overall_delta must be between 0 and 100")


def prepare(data: dict, seed: str) -> tuple[dict, dict]:
    validate_input(data)
    rng = random.Random(seed)
    pairs = []
    keys = []
    for case in data["cases"]:
        treatment_label = rng.choice(["A", "B"])
        baseline_label = "B" if treatment_label == "A" else "A"
        answers = {baseline_label: case["baseline"], treatment_label: case["treatment"]}
        pairs.append({
            "case_id": case["id"],
            "input": case["input"],
            "expected": case["expected"],
            "answers": [{"label": label, "output": answers[label]} for label in ("A", "B")],
        })
        keys.append({"case_id": case["id"], "treatment_label": treatment_label})
    packet = {
        "version": 1, "title": data["title"], "rubric": data["rubric"],
        "critical_failures": data.get("critical_failures", []),
        "judge_instruction": "Score both answers on every criterion, quote evidence in each reason, choose A, B, or tie, and list critical failures. Do not infer how either answer was produced.",
        "pairs": pairs,
    }
    key = {
        "version": 1, "packet_hash": digest(packet), "seed": seed,
        "gate": data.get("gate", {"minimum_overall_delta": 5}), "pairs": keys,
    }
    return packet, key


def validate_judgment(packet: dict, judgment: dict) -> None:
    if judgment.get("version") != 1 or not isinstance(judgment.get("pairs"), list):
        raise Invalid("judgment must have version 1 and a pairs array")
    expected_pairs = {p["case_id"]: p for p in packet["pairs"]}
    actual_pairs = judgment["pairs"]
    actual_ids = [p.get("case_id") for p in actual_pairs if isinstance(p, dict)]
    if set(actual_ids) != set(expected_pairs) or len(actual_ids) != len(expected_pairs):
        raise Invalid("judgment must contain every packet case exactly once")
    rubric = {r["id"]: r for r in packet["rubric"]}
    for pair in actual_pairs:
        case_id = pair["case_id"]
        if pair.get("winner") not in ("A", "B", "tie"):
            raise Invalid(f"case {case_id} winner must be A, B, or tie")
        for label in ("A", "B"):
            scores = pair.get("scores", {}).get(label)
            if not isinstance(scores, dict) or set(scores) != set(rubric):
                raise Invalid(f"case {case_id} answer {label} must score every rubric criterion")
            for criterion_id, criterion in rubric.items():
                entry = scores[criterion_id]
                if not isinstance(entry, dict):
                    raise Invalid(f"case {case_id} {label}/{criterion_id} must be an object")
                score = entry.get("score")
                if not isinstance(score, (int, float)) or score < 0 or score > criterion["max_score"]:
                    raise Invalid(f"case {case_id} {label}/{criterion_id} score is out of range")
                require_text(entry.get("reason"), f"case {case_id} {label}/{criterion_id} reason")
            failures = pair.get("critical_failures", {}).get(label)
            if not isinstance(failures, list) or any(not isinstance(x, str) or not x.strip() for x in failures):
                raise Invalid(f"case {case_id} answer {label} critical_failures must be a string array")


def decide(packet: dict, key: dict, judgment: dict) -> dict:
    if key.get("version") != 1 or key.get("packet_hash") != digest(packet):
        raise Invalid("key does not match packet")
    validate_judgment(packet, judgment)
    key_by_case = {p["case_id"]: p["treatment_label"] for p in key.get("pairs", [])}
    if set(key_by_case) != {p["case_id"] for p in packet["pairs"]}:
        raise Invalid("key must map every packet case")
    rubric = packet["rubric"]
    totals = {"baseline": [], "treatment": []}
    criterion_totals = {role: {r["id"]: [] for r in rubric} for role in totals}
    wins = {"baseline": 0, "treatment": 0, "tie": 0}
    critical = {"baseline": [], "treatment": []}
    cases = []
    for pair in judgment["pairs"]:
        treatment_label = key_by_case[pair["case_id"]]
        baseline_label = "B" if treatment_label == "A" else "A"
        role_for = {treatment_label: "treatment", baseline_label: "baseline"}
        role_scores = {}
        weight_sum = sum(r["weight"] for r in rubric)
        for label, role in role_for.items():
            score = sum((pair["scores"][label][r["id"]]["score"] / r["max_score"]) * r["weight"] for r in rubric) / weight_sum * 100
            totals[role].append(score)
            role_scores[role] = round(score, 2)
            for r in rubric:
                criterion_totals[role][r["id"]].append(pair["scores"][label][r["id"]]["score"] / r["max_score"] * 100)
            critical[role].extend({"case_id": pair["case_id"], "failure": failure} for failure in pair["critical_failures"][label])
        winner = "tie" if pair["winner"] == "tie" else role_for[pair["winner"]]
        wins[winner] += 1
        cases.append({"case_id": pair["case_id"], "winner": winner, "scores": role_scores})
    means = {role: round(sum(values) / len(values), 2) for role, values in totals.items()}
    criteria = {role: {criterion: round(sum(values) / len(values), 2) for criterion, values in items.items()} for role, items in criterion_totals.items()}
    delta = round(means["treatment"] - means["baseline"], 2)
    minimum = key.get("gate", {}).get("minimum_overall_delta", 5)
    core_deltas = [criteria["treatment"][r["id"]] - criteria["baseline"][r["id"]] for r in rubric if r["core"]]
    reasons = []
    if delta < minimum:
        reasons.append(f"overall delta {delta} is below required {minimum}")
    if any(value < 0 for value in core_deltas):
        reasons.append("one or more core criteria regressed")
    if not any(value > 0 for value in core_deltas):
        reasons.append("no core criterion improved")
    if wins["treatment"] <= wins["baseline"]:
        reasons.append("treatment did not win more cases than baseline")
    if critical["treatment"]:
        reasons.append("treatment has critical failures")
    return {
        "version": 1, "decision": "keep" if not reasons else "retire",
        "reasons": reasons, "minimum_overall_delta": minimum, "overall_scores": means,
        "treatment_delta": delta, "criterion_scores": criteria, "case_wins": wins,
        "critical_failures": critical, "cases": cases, "packet_hash": digest(packet),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--input", type=Path, required=True)
    prep.add_argument("--packet", type=Path, required=True)
    prep.add_argument("--key", type=Path, required=True)
    prep.add_argument("--seed", required=True)
    final = sub.add_parser("decide")
    final.add_argument("--packet", type=Path, required=True)
    final.add_argument("--key", type=Path, required=True)
    final.add_argument("--judgment", type=Path, required=True)
    final.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            packet, key = prepare(read_object(args.input), args.seed)
            write_new(args.packet, packet)
            write_new(args.key, key)
            print(f"prepared {len(packet['pairs'])} blinded case(s)")
        else:
            result = decide(read_object(args.packet), read_object(args.key), read_object(args.judgment))
            write_new(args.output, result)
            print(result["decision"])
        return 0
    except Invalid as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
