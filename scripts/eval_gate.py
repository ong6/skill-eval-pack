#!/usr/bin/env python3
"""Create blinded skill A/B packets and apply strict keep-or-retire gates."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
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


def require_number(value: object, field: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Invalid(f"{field} must be a finite number")
    if minimum is not None and value < minimum:
        raise Invalid(f"{field} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise Invalid(f"{field} must be at most {maximum}")
    return float(value)


def validate_rubric(data: dict) -> None:
    rubric = data.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        raise Invalid("rubric must be a non-empty array")
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
        require_number(item.get("weight"), f"rubric {item_id} weight", minimum=0.0000001)
        require_number(item.get("max_score"), f"rubric {item_id} max_score", minimum=0.0000001)
        if not isinstance(item.get("core"), bool):
            raise Invalid(f"rubric {item_id} core must be boolean")
        core |= item["core"]
    if not core:
        raise Invalid("at least one rubric criterion must be core")


def validate_common(data: dict) -> None:
    require_text(data.get("title"), "title")
    validate_rubric(data)
    failures = data.get("critical_failures", [])
    if not isinstance(failures, list) or any(not isinstance(x, str) or not x.strip() for x in failures):
        raise Invalid("critical_failures must be an array of non-empty strings")
    gate = data.get("gate", {"minimum_overall_delta": 5})
    if not isinstance(gate, dict):
        raise Invalid("gate must be an object")
    require_number(gate.get("minimum_overall_delta", 5), "minimum_overall_delta", minimum=0, maximum=100)


def validate_input_v1(data: dict) -> None:
    validate_common(data)
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise Invalid("cases must be a non-empty array")
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


def validate_run(run: object, field: str) -> None:
    if not isinstance(run, dict):
        raise Invalid(f"{field} must be an object")
    require_text(run.get("transcript"), f"{field}.transcript")
    require_text(run.get("outcome"), f"{field}.outcome")
    if "grader_result" in run:
        grader_result = run.get("grader_result")
        if not isinstance(grader_result, dict) or not isinstance(grader_result.get("passed"), bool):
            raise Invalid(f"{field}.grader_result must contain a boolean passed field")
        require_text(grader_result.get("details"), f"{field}.grader_result.details")


def validate_trigger_tests(data: dict) -> None:
    tests = data.get("trigger_tests", [])
    if not isinstance(tests, list):
        raise Invalid("trigger_tests must be an array")
    ids = set()
    for test in tests:
        if not isinstance(test, dict):
            raise Invalid("each trigger test must be an object")
        test_id = require_text(test.get("id"), "trigger_test.id")
        if test_id in ids:
            raise Invalid(f"duplicate trigger test id: {test_id}")
        ids.add(test_id)
        require_text(test.get("input"), f"trigger test {test_id} input")
        if test.get("split") not in ("development", "heldout"):
            raise Invalid(f"trigger test {test_id} split must be development or heldout")
        for field in ("expected_trigger", "observed_trigger"):
            if not isinstance(test.get(field), bool):
                raise Invalid(f"trigger test {test_id} {field} must be boolean")
        require_text(test.get("details"), f"trigger test {test_id} details")


def validate_input_v2(data: dict) -> None:
    validate_common(data)
    judge_count = data.get("judge_count")
    if isinstance(judge_count, bool) or not isinstance(judge_count, int) or judge_count < 2:
        raise Invalid("judge_count must be an integer of at least 2")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise Invalid("cases must be a non-empty array")
    case_ids = set()
    splits = set()
    comparison_ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise Invalid("each case must be an object")
        case_id = require_text(case.get("id"), "case.id")
        if case_id in case_ids:
            raise Invalid(f"duplicate case id: {case_id}")
        case_ids.add(case_id)
        split = case.get("split")
        if split not in ("development", "heldout"):
            raise Invalid(f"case {case_id} split must be development or heldout")
        splits.add(split)
        for field in ("input", "expected"):
            require_text(case.get(field), f"case {case_id} {field}")
        if "deterministic_grader" in case:
            require_text(case["deterministic_grader"], f"case {case_id} deterministic_grader")
        stochastic = case.get("stochastic", False)
        if not isinstance(stochastic, bool):
            raise Invalid(f"case {case_id} stochastic must be boolean")
        trials = case.get("trials")
        if not isinstance(trials, list) or not trials:
            raise Invalid(f"case {case_id} trials must be a non-empty array")
        if stochastic and len(trials) < 2:
            raise Invalid(f"case {case_id} is stochastic and requires at least two trials")
        trial_ids = set()
        for trial in trials:
            if not isinstance(trial, dict):
                raise Invalid(f"case {case_id} trial must be an object")
            trial_id = require_text(trial.get("id"), f"case {case_id} trial.id")
            if trial_id in trial_ids:
                raise Invalid(f"duplicate trial id in case {case_id}: {trial_id}")
            trial_ids.add(trial_id)
            comparison_id = f"{case_id}::{trial_id}"
            if comparison_id in comparison_ids:
                raise Invalid(f"duplicate comparison id: {comparison_id}")
            comparison_ids.add(comparison_id)
            validate_run(trial.get("baseline"), f"case {case_id} trial {trial_id} baseline")
            validate_run(trial.get("treatment"), f"case {case_id} trial {trial_id} treatment")
            if "deterministic_grader" in case:
                for role in ("baseline", "treatment"):
                    require_text(
                        trial[role].get("grader_result", {}).get("details"),
                        f"case {case_id} trial {trial_id} {role}.grader_result.details",
                    )
    if splits != {"development", "heldout"}:
        raise Invalid("v2 requires both development and heldout cases")
    validate_trigger_tests(data)


def validate_input(data: dict) -> None:
    version = data.get("version")
    if version == 1:
        validate_input_v1(data)
    elif version == 2:
        validate_input_v2(data)
    else:
        raise Invalid("input version must be 1 or 2")


def prepare_v1(data: dict, seed: str) -> tuple[dict, dict]:
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


def prepare_v2(data: dict, seed: str) -> tuple[dict, dict]:
    rng = random.Random(seed)
    bases = {}
    comparisons = []
    for case in data["cases"]:
        for trial in case["trials"]:
            comparison_id = f"{case['id']}::{trial['id']}"
            bases[comparison_id] = rng.choice(["A", "B"])
            comparisons.append((case, trial, comparison_id))

    judge_packets = []
    mappings = []
    instruction = (
        "Review transcript and outcome for both anonymous runs. Score every criterion with quoted "
        "evidence, choose A, B, or tie, and report every critical failure. Do not infer identities."
    )
    for judge_index in range(data["judge_count"]):
        judge_id = f"judge-{judge_index + 1}"
        blinded = []
        for case, trial, comparison_id in comparisons:
            treatment_label = bases[comparison_id]
            if judge_index % 2:
                treatment_label = "B" if treatment_label == "A" else "A"
            baseline_label = "B" if treatment_label == "A" else "A"
            runs = {baseline_label: trial["baseline"], treatment_label: trial["treatment"]}
            item = {
                "comparison_id": comparison_id,
                "case_id": case["id"],
                "trial_id": trial["id"],
                "split": case["split"],
                "input": case["input"],
                "expected": case["expected"],
                "answers": [{"label": label, **runs[label]} for label in ("A", "B")],
            }
            if "deterministic_grader" in case:
                item["deterministic_grader"] = case["deterministic_grader"]
            blinded.append(item)
            mappings.append({
                "judge_id": judge_id, "comparison_id": comparison_id,
                "case_id": case["id"], "trial_id": trial["id"],
                "split": case["split"], "treatment_label": treatment_label,
            })
        judge_packets.append({
            "version": 2, "judge_id": judge_id, "title": data["title"],
            "rubric": data["rubric"], "critical_failures": data.get("critical_failures", []),
            "judge_instruction": instruction, "comparisons": blinded,
        })
    packet = {
        "version": 2, "title": data["title"],
        "distribution_instruction": "Give each judge only its matching entry from judge_packets. Never give a judge this bundle or the key.",
        "judge_packets": judge_packets,
    }
    key = {
        "version": 2, "packet_hash": digest(packet), "seed": seed,
        "gate": data.get("gate", {"minimum_overall_delta": 5}),
        "rubric": data["rubric"], "mappings": mappings,
        "trigger_tests": data.get("trigger_tests", []),
    }
    return packet, key


def prepare(data: dict, seed: str) -> tuple[dict, dict]:
    validate_input(data)
    return prepare_v1(data, seed) if data["version"] == 1 else prepare_v2(data, seed)


def validate_scored_comparison(
    pair: dict,
    rubric: dict,
    field: str,
    *,
    answers: dict[str, dict] | None = None,
    allowed_failures: set[str] | None = None,
) -> None:
    if pair.get("winner") not in ("A", "B", "tie"):
        raise Invalid(f"{field} winner must be A, B, or tie")
    scores_object = pair.get("scores")
    failures_object = pair.get("critical_failures")
    if not isinstance(scores_object, dict) or not isinstance(failures_object, dict):
        raise Invalid(f"{field} scores and critical_failures must be objects")
    for label in ("A", "B"):
        scores = scores_object.get(label)
        if not isinstance(scores, dict) or set(scores) != set(rubric):
            raise Invalid(f"{field} answer {label} must score every rubric criterion")
        for criterion_id, criterion in rubric.items():
            entry = scores[criterion_id]
            if not isinstance(entry, dict):
                raise Invalid(f"{field} {label}/{criterion_id} must be an object")
            require_number(entry.get("score"), f"{field} {label}/{criterion_id} score", minimum=0, maximum=criterion["max_score"])
            require_text(entry.get("reason"), f"{field} {label}/{criterion_id} reason")
            if answers is not None:
                quote = require_text(entry.get("evidence_quote"), f"{field} {label}/{criterion_id} evidence_quote")
                source = answers[label]
                evidence_sources = [source["transcript"], source["outcome"]]
                if "grader_result" in source:
                    evidence_sources.append(source["grader_result"]["details"])
                if not any(quote in evidence for evidence in evidence_sources):
                    raise Invalid(f"{field} {label}/{criterion_id} evidence_quote does not occur in that answer")
        failures = failures_object.get(label)
        if not isinstance(failures, list) or any(not isinstance(x, str) or not x.strip() for x in failures):
            raise Invalid(f"{field} answer {label} critical_failures must be a string array")
        if allowed_failures is not None and any(failure not in allowed_failures for failure in failures):
            raise Invalid(f"{field} answer {label} contains a critical failure outside the frozen taxonomy")
    if answers is not None:
        rubric_items = list(rubric.values())
        score_a = weighted_score(scores_object["A"], rubric_items)
        score_b = weighted_score(scores_object["B"], rubric_items)
        expected_winner = "A" if score_a > score_b else "B" if score_b > score_a else "tie"
        if pair["winner"] != expected_winner:
            raise Invalid(f"{field} winner does not agree with weighted scores; expected {expected_winner}")


def validate_judgment_v1(packet: dict, judgment: dict) -> None:
    if judgment.get("version") != 1 or not isinstance(judgment.get("pairs"), list):
        raise Invalid("judgment must have version 1 and a pairs array")
    expected_pairs = {p["case_id"]: p for p in packet["pairs"]}
    actual_pairs = judgment["pairs"]
    actual_ids = [p.get("case_id") for p in actual_pairs if isinstance(p, dict)]
    if set(actual_ids) != set(expected_pairs) or len(actual_ids) != len(expected_pairs):
        raise Invalid("judgment must contain every packet case exactly once")
    rubric = {r["id"]: r for r in packet["rubric"]}
    for pair in actual_pairs:
        validate_scored_comparison(pair, rubric, f"case {pair['case_id']}")


def validate_judgment_v2(packet: dict, key: dict, judgment: dict) -> None:
    if judgment.get("version") != 2 or not isinstance(judgment.get("judgments"), list):
        raise Invalid("v2 judgment must have version 2 and a judgments array")
    judge_packets = packet.get("judge_packets")
    if not isinstance(judge_packets, list) or len(judge_packets) < 2:
        raise Invalid("v2 packet must contain at least two judge packets")
    expected = {}
    for judge_packet in judge_packets:
        if not isinstance(judge_packet, dict):
            raise Invalid("each judge packet must be an object")
        judge_id = require_text(judge_packet.get("judge_id"), "judge_packet.judge_id")
        if judge_id in expected:
            raise Invalid(f"duplicate judge packet: {judge_id}")
        comparisons = judge_packet.get("comparisons")
        if not isinstance(comparisons, list) or not comparisons:
            raise Invalid(f"judge packet {judge_id} comparisons must be non-empty")
        ids = [c.get("comparison_id") for c in comparisons if isinstance(c, dict)]
        if len(ids) != len(comparisons) or len(ids) != len(set(ids)):
            raise Invalid(f"judge packet {judge_id} has malformed or duplicate comparisons")
        expected[judge_id] = {comparison["comparison_id"]: comparison for comparison in comparisons}
    actual = judgment["judgments"]
    actual_ids = [j.get("judge_id") for j in actual if isinstance(j, dict)]
    if set(actual_ids) != set(expected) or len(actual_ids) != len(expected):
        raise Invalid("judgment must contain every judge packet exactly once")
    rubric_items = key.get("rubric")
    if not isinstance(rubric_items, list):
        raise Invalid("v2 key rubric is missing")
    for judge_packet in judge_packets:
        if judge_packet.get("rubric") != rubric_items:
            raise Invalid("v2 key rubric does not match judge packets")
    rubric = {r["id"]: r for r in rubric_items}
    for judge in actual:
        judge_id = judge["judge_id"]
        comparisons = judge.get("comparisons")
        if not isinstance(comparisons, list):
            raise Invalid(f"judge {judge_id} comparisons must be an array")
        ids = [c.get("comparison_id") for c in comparisons if isinstance(c, dict)]
        if set(ids) != set(expected[judge_id]) or len(ids) != len(expected[judge_id]):
            raise Invalid(f"judge {judge_id} must score every comparison exactly once")
        for comparison in comparisons:
            packet_comparison = expected[judge_id][comparison["comparison_id"]]
            answers = {answer["label"]: answer for answer in packet_comparison["answers"]}
            validate_scored_comparison(
                comparison, rubric, f"judge {judge_id} comparison {comparison['comparison_id']}",
                answers=answers, allowed_failures=set(packet["judge_packets"][0].get("critical_failures", [])),
            )


def validate_judgment(packet: dict, judgment: dict, key: dict | None = None) -> None:
    if packet.get("version") == 1:
        validate_judgment_v1(packet, judgment)
    elif packet.get("version") == 2 and key is not None:
        validate_judgment_v2(packet, key, judgment)
    else:
        raise Invalid("packet version must be 1 or 2")


def weighted_score(scores: dict, rubric: list[dict]) -> float:
    weight_sum = sum(r["weight"] for r in rubric)
    return sum((scores[r["id"]]["score"] / r["max_score"]) * r["weight"] for r in rubric) / weight_sum * 100


def decide_v1(packet: dict, key: dict, judgment: dict) -> dict:
    validate_judgment_v1(packet, judgment)
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
        for label, role in role_for.items():
            score = weighted_score(pair["scores"][label], rubric)
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


def summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "stdev": None, "min": None, "max": None}
    return {
        "count": len(values), "mean": round(statistics.mean(values), 2),
        "stdev": round(statistics.pstdev(values), 2),
        "min": round(min(values), 2), "max": round(max(values), 2),
    }


def union_failures(entries: list[dict]) -> list[dict]:
    grouped = {}
    for entry in entries:
        key = (entry["case_id"], entry["trial_id"], entry["failure"])
        grouped.setdefault(key, set()).add(entry["judge_id"])
    return [
        {"case_id": key[0], "trial_id": key[1], "failure": key[2], "judges": sorted(judges)}
        for key, judges in sorted(grouped.items())
    ]


def agreement_report(winners: dict[tuple[str, str], str], judge_ids: list[str], heldout_ids: set[str]) -> dict:
    comparison_ids = sorted({comparison_id for _, comparison_id in winners})
    consensus = {}
    for comparison_id in comparison_ids:
        counts = Counter(winners[(judge_id, comparison_id)] for judge_id in judge_ids)
        top = max(counts.values())
        leaders = [role for role, count in counts.items() if count == top]
        consensus[comparison_id] = leaders[0] if len(leaders) == 1 else "tie"

    def rate(matches: list[bool]) -> float | None:
        return round(sum(matches) / len(matches) * 100, 2) if matches else None

    per_judge = {}
    for judge_id in judge_ids:
        all_matches = [winners[(judge_id, item)] == consensus[item] for item in comparison_ids]
        heldout_matches = [winners[(judge_id, item)] == consensus[item] for item in comparison_ids if item in heldout_ids]
        per_judge[judge_id] = {
            "agreement_with_consensus_percent": rate(all_matches),
            "heldout_agreement_with_consensus_percent": rate(heldout_matches),
            "winner_counts": dict(Counter(winners[(judge_id, item)] for item in comparison_ids)),
        }
    pairwise = []
    for index, left in enumerate(judge_ids):
        for right in judge_ids[index + 1:]:
            matches = [winners[(left, item)] == winners[(right, item)] for item in comparison_ids]
            heldout_matches = [winners[(left, item)] == winners[(right, item)] for item in comparison_ids if item in heldout_ids]
            pairwise.append({
                "judges": [left, right], "agreement_percent": rate(matches),
                "heldout_agreement_percent": rate(heldout_matches),
            })
    return {
        "per_judge": per_judge, "pairwise": pairwise,
        "mean_pairwise_agreement_percent": round(statistics.mean(x["agreement_percent"] for x in pairwise), 2),
        "heldout_mean_pairwise_agreement_percent": round(statistics.mean(x["heldout_agreement_percent"] for x in pairwise), 2),
    }


def decide_v2(packet: dict, key: dict, judgment: dict) -> dict:
    validate_judgment_v2(packet, key, judgment)
    mappings = key.get("mappings")
    if not isinstance(mappings, list):
        raise Invalid("v2 key mappings are missing")
    mapping_by_id = {}
    for item in mappings:
        if not isinstance(item, dict):
            raise Invalid("each v2 key mapping must be an object")
        map_key = (item.get("judge_id"), item.get("comparison_id"))
        if map_key in mapping_by_id or item.get("treatment_label") not in ("A", "B"):
            raise Invalid("v2 key has duplicate or malformed mappings")
        mapping_by_id[map_key] = item
    expected_keys = {
        (judge_packet["judge_id"], comparison["comparison_id"])
        for judge_packet in packet["judge_packets"] for comparison in judge_packet["comparisons"]
    }
    if set(mapping_by_id) != expected_keys:
        raise Invalid("v2 key must map every judge comparison exactly once")
    packet_metadata = {
        (judge_packet["judge_id"], comparison["comparison_id"]): {
            "case_id": comparison.get("case_id"), "trial_id": comparison.get("trial_id"),
            "split": comparison.get("split"), "answers": comparison.get("answers"),
        }
        for judge_packet in packet["judge_packets"] for comparison in judge_packet["comparisons"]
    }
    for map_key, mapping in mapping_by_id.items():
        if any(mapping.get(field) != packet_metadata[map_key][field] for field in ("case_id", "trial_id", "split")):
            raise Invalid("v2 key mapping metadata does not match packet")

    rubric = key["rubric"]
    totals = {split: {role: [] for role in ("baseline", "treatment")} for split in ("development", "heldout")}
    criterion_totals = {
        split: {role: {r["id"]: [] for r in rubric} for role in ("baseline", "treatment")}
        for split in ("development", "heldout")
    }
    case_scores = defaultdict(lambda: {"baseline": [], "treatment": []})
    failures = {split: {role: [] for role in ("baseline", "treatment")} for split in ("development", "heldout")}
    winners = {}
    judge_ids = [judge["judge_id"] for judge in judgment["judgments"]]
    heldout_ids = set()
    deterministic_failures = {"development": {"baseline": [], "treatment": []}, "heldout": {"baseline": [], "treatment": []}}
    deterministic_seen = set()
    for judge in judgment["judgments"]:
        judge_id = judge["judge_id"]
        for comparison in judge["comparisons"]:
            comparison_id = comparison["comparison_id"]
            mapping = mapping_by_id[(judge_id, comparison_id)]
            split = mapping["split"]
            if split == "heldout":
                heldout_ids.add(comparison_id)
            treatment_label = mapping["treatment_label"]
            baseline_label = "B" if treatment_label == "A" else "A"
            role_for = {treatment_label: "treatment", baseline_label: "baseline"}
            winner = "tie" if comparison["winner"] == "tie" else role_for[comparison["winner"]]
            winners[(judge_id, comparison_id)] = winner
            for label, role in role_for.items():
                packet_answer = next(
                    answer for answer in packet_metadata[(judge_id, comparison_id)]["answers"]
                    if answer["label"] == label
                )
                score = weighted_score(comparison["scores"][label], rubric)
                totals[split][role].append(score)
                case_scores[(split, mapping["case_id"])][role].append(score)
                for criterion in rubric:
                    normalized = comparison["scores"][label][criterion["id"]]["score"] / criterion["max_score"] * 100
                    criterion_totals[split][role][criterion["id"]].append(normalized)
                failures[split][role].extend({
                    "case_id": mapping["case_id"], "trial_id": mapping["trial_id"],
                    "judge_id": judge_id, "failure": failure,
                } for failure in comparison["critical_failures"][label])
                grader_result = packet_answer.get("grader_result") if packet_answer else None
                grader_key = (comparison_id, role)
                if grader_result is not None and not grader_result["passed"] and grader_key not in deterministic_seen:
                    deterministic_seen.add(grader_key)
                    deterministic_failures[split][role].append({
                        "case_id": mapping["case_id"], "trial_id": mapping["trial_id"],
                        "details": grader_result["details"],
                    })

    score_summary = {split: {role: summary(values) for role, values in roles.items()} for split, roles in totals.items()}
    criterion_scores = {
        split: {
            role: {criterion: round(statistics.mean(values), 2) for criterion, values in criteria.items()}
            for role, criteria in roles.items()
        } for split, roles in criterion_totals.items()
    }
    case_results = {"development": [], "heldout": []}
    case_wins = {split: {"baseline": 0, "treatment": 0, "tie": 0} for split in case_results}
    for (split, case_id), role_values in sorted(case_scores.items()):
        means = {role: round(statistics.mean(values), 2) for role, values in role_values.items()}
        if means["treatment"] > means["baseline"]:
            winner = "treatment"
        elif means["baseline"] > means["treatment"]:
            winner = "baseline"
        else:
            winner = "tie"
        case_wins[split][winner] += 1
        case_results[split].append({"case_id": case_id, "winner": winner, "scores": means})

    unioned_failures = {
        split: {role: union_failures(entries) for role, entries in roles.items()}
        for split, roles in failures.items()
    }
    heldout_means = {role: score_summary["heldout"][role]["mean"] for role in ("baseline", "treatment")}
    delta = round(heldout_means["treatment"] - heldout_means["baseline"], 2)
    minimum = key.get("gate", {}).get("minimum_overall_delta", 5)
    core_deltas = [
        criterion_scores["heldout"]["treatment"][r["id"]] - criterion_scores["heldout"]["baseline"][r["id"]]
        for r in rubric if r["core"]
    ]
    reasons = []
    if delta < minimum:
        reasons.append(f"heldout overall delta {delta} is below required {minimum}")
    if any(value < 0 for value in core_deltas):
        reasons.append("one or more heldout core criteria regressed")
    if not any(value > 0 for value in core_deltas):
        reasons.append("no heldout core criterion improved")
    if case_wins["heldout"]["treatment"] <= case_wins["heldout"]["baseline"]:
        reasons.append("treatment did not win more heldout cases than baseline")
    if unioned_failures["heldout"]["treatment"]:
        reasons.append("treatment has heldout critical failures reported by at least one judge")
    if deterministic_failures["heldout"]["treatment"]:
        reasons.append("treatment has heldout deterministic grader failures")
    trigger_results = key.get("trigger_tests", [])
    heldout_trigger_failures = [
        test for test in trigger_results
        if test["split"] == "heldout" and test["expected_trigger"] != test["observed_trigger"]
    ]
    if heldout_trigger_failures:
        reasons.append("one or more heldout trigger tests failed")
    return {
        "version": 2, "decision": "keep" if not reasons else "retire", "reasons": reasons,
        "gate_scope": "heldout_only", "minimum_overall_delta": minimum,
        "overall_scores": heldout_means, "treatment_delta": delta,
        "score_dispersion": score_summary, "criterion_scores": criterion_scores,
        "case_wins": case_wins["heldout"], "development_case_wins": case_wins["development"],
        "critical_failures": unioned_failures, "cases": case_results,
        "deterministic_grader_failures": deterministic_failures,
        "trigger_tests": {
            "results": trigger_results, "heldout_failures": heldout_trigger_failures,
        },
        "judge_agreement": agreement_report(winners, judge_ids, heldout_ids),
        "packet_hash": digest(packet),
    }


def decide(packet: dict, key: dict, judgment: dict) -> dict:
    version = packet.get("version")
    if key.get("version") != version or key.get("packet_hash") != digest(packet):
        raise Invalid("key does not match packet")
    if version == 1:
        return decide_v1(packet, key, judgment)
    if version == 2:
        return decide_v2(packet, key, judgment)
    raise Invalid("packet version must be 1 or 2")


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
            if args.packet.exists() or args.key.exists():
                existing = args.packet if args.packet.exists() else args.key
                raise Invalid(f"refusing to overwrite {existing}")
            packet, key = prepare(read_object(args.input), args.seed)
            write_new(args.packet, packet)
            write_new(args.key, key)
            count = len(packet["pairs"]) if packet["version"] == 1 else len(packet["judge_packets"])
            noun = "blinded case(s)" if packet["version"] == 1 else "counterbalanced judge packet(s)"
            print(f"prepared {count} {noun}")
        else:
            result = decide(read_object(args.packet), read_object(args.key), read_object(args.judgment))
            write_new(args.output, result)
            print(result["decision"])
        return 0
    except (Invalid, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
