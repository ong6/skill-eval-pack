#!/usr/bin/env python3
"""Validate a skill candidate's bounded evaluation lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Invalid(ValueError):
    pass


def unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise Invalid(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def reject_json_constant(value: str) -> None:
    raise Invalid(f"non-finite JSON constant: {value}")


def read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_json_object,
                           parse_constant=reject_json_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise Invalid(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Invalid(f"{path} must contain a JSON object")
    return value


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Invalid(f"{field} must be non-empty text")
    return value


def require_sha(value: object, field: str) -> str:
    value = require_text(value, field)
    if not SHA256.fullmatch(value):
        raise Invalid(f"{field} must be a lowercase SHA-256 digest")
    return value


def artifact(root: Path, relative: object, expected_hash: object, field: str, manifest_parent: Path) -> dict:
    text = require_text(relative, field)
    candidate = Path(text)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise Invalid(f"{field} must be a safe path relative to the evidence root")
    path = root / candidate
    if not path.is_file() and candidate.parent == Path('.'):
        # Early v3 manifests stored a basename relative to the manifest's own
        # directory. The caller's evidence root is wider so cross-attempt
        # lifecycles can reference sibling bundles. Preserve both conventions.
        local = root / manifest_parent / candidate
        if local.is_file():
            path = local
    if not path.resolve().is_relative_to(root.resolve()):
        raise Invalid(f"{field} must remain inside the evidence root")
    if not path.is_file():
        raise Invalid(f"{field} does not exist: {text}")
    actual_hash = file_digest(path)
    if actual_hash != require_sha(expected_hash, field + "_sha256"):
        raise Invalid(f"{field} hash does not match retained artifact")
    return read_object(path)


def retained_inputs(packet: dict, field: str) -> tuple[set[str], set[str]]:
    judges = packet.get("judge_packets")
    if packet.get("version") != 3 or not isinstance(judges, list) or not judges:
        raise Invalid(f"{field} requires retained v3 judge packets to identify exposed cases")
    seen, heldout = set(), set()
    for judge in judges:
        comparisons = judge.get("comparisons") if isinstance(judge, dict) else None
        if not isinstance(comparisons, list) or not comparisons:
            raise Invalid(f"{field} comparisons are required to identify exposed cases")
        for item in comparisons:
            if not isinstance(item, dict) or item.get("split") not in ("development", "heldout"):
                raise Invalid(f"{field} exposed comparison must declare its split")
            prompt = require_text(item.get("input"), field + " exposed input").strip()
            seen.add(prompt)
            if item["split"] == "heldout":
                heldout.add(prompt)
    return seen, heldout


def replay_decision(attempt: dict, decision: dict, manifest: dict, root: Path,
                    manifest_parent: Path, field: str) -> tuple[set[str], set[str]]:
    """Recompute current decisions and return seen and heldout input fingerprints."""
    if type(decision.get("version")) is not int or decision["version"] != 3:
        raise Invalid(f"{field} activation requires a current v3 decision with replayable evidence")
    evidence = {
        name: artifact(root, attempt.get(name + "_artifact"), attempt.get(name + "_sha256"),
                       field + " " + name + "_artifact", manifest_parent)
        for name in ("packet", "key", "judgment")
    }
    condition = evidence["key"].get("condition_manifest")
    if not isinstance(condition, dict) or condition.get("treatment_skill_sha256") != attempt["candidate_sha256"]:
        raise Invalid(f"{field} candidate_sha256 does not match frozen treatment evidence")
    baseline = condition.get("baseline_skill")
    expected_baseline = "absent" if manifest["candidate_kind"] == "new" else {
        "mode": "prior_version", "version": manifest["last_proven_version"],
        "sha256": manifest["last_proven_sha256"],
    }
    if baseline != expected_baseline:
        raise Invalid(f"{field} baseline_skill does not match candidate_kind and last_proven evidence")
    if any(type(value.get("version")) is not int or value["version"] != 3 for value in evidence.values()):
        raise Invalid(f"{field} activation requires v3 packet, key, and judgment evidence")
    spec = importlib.util.spec_from_file_location("skillsmith_eval_gate", Path(__file__).with_name("eval_gate.py"))
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    try:
        replayed = evaluator.decide(evidence["packet"], evidence["key"], evidence["judgment"])
    except (ValueError, KeyError, TypeError) as exc:
        raise Invalid(f"{field} retained evaluation is invalid: {exc}") from exc
    if decision != replayed:
        raise Invalid(f"{field} decision does not match a replayed v3 decision")
    return retained_inputs(evidence["packet"], field)


def validate(manifest: dict, root: Path, manifest_parent: Path = Path('.')) -> dict:
    if manifest.get("version") != 1:
        raise Invalid("lifecycle manifest version must be 1")
    kind = manifest.get("candidate_kind")
    if kind not in ("new", "existing_revision"):
        raise Invalid("candidate_kind must be new or existing_revision")
    maximum = manifest.get("maximum_serious_revisions")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
        raise Invalid("maximum_serious_revisions must be a positive integer")
    if kind == "existing_revision":
        require_text(manifest.get("last_proven_version"), "last_proven_version")
        require_sha(manifest.get("last_proven_sha256"), "last_proven_sha256")

    attempts = manifest.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise Invalid("attempts must be a non-empty array")
    if len(attempts) > maximum:
        raise Invalid("attempt count exceeds maximum_serious_revisions")

    heldout_sets = set()
    candidate_hashes = set()
    decisions = []
    exposed_inputs = set()
    unknown_exposure = False
    for index, attempt in enumerate(attempts, 1):
        field = f"attempt {index}"
        if (not isinstance(attempt, dict) or type(attempt.get("revision")) is not int
                or attempt["revision"] != index):
            raise Invalid(f"{field} revision must be sequential starting at 1")
        candidate_hash = require_sha(attempt.get("candidate_sha256"), field + " candidate_sha256")
        if candidate_hash in candidate_hashes:
            raise Invalid(f"{field} reuses a candidate hash")
        candidate_hashes.add(candidate_hash)
        require_text(attempt.get("change"), field + " change")
        evidence = attempt.get("development_evidence")
        if not isinstance(evidence, list) or any(not isinstance(item, str) or not item.strip() for item in evidence):
            raise Invalid(f"{field} development_evidence must be a string array")
        if index > 1 and not evidence:
            raise Invalid(f"{field} must cite development evidence for the revision")
        heldout_set = require_text(attempt.get("heldout_set"), field + " heldout_set")
        if heldout_set in heldout_sets:
            raise Invalid(f"{field} reuses an exposed heldout_set")
        heldout_sets.add(heldout_set)
        if "invalid_evaluation" in attempt and not isinstance(attempt["invalid_evaluation"], bool):
            raise Invalid(f"{field} invalid_evaluation must be boolean")
        if attempt.get("invalid_evaluation") is True:
            require_text(attempt.get("invalid_reason"), field + " invalid_reason")
            if attempt.get("heldout_retired") is not True:
                raise Invalid(f"{field} invalid heldout_set must be retired")
            if "packet_artifact" in attempt:
                packet = artifact(root, attempt["packet_artifact"], attempt.get("packet_sha256"),
                                  field + " packet_artifact", manifest_parent)
                seen_inputs, _ = retained_inputs(packet, field)
                exposed_inputs.update(seen_inputs)
            else:
                unknown_exposure = True
            decisions.append("invalid")
            continue
        decision = artifact(
            root, attempt.get("decision_artifact"), attempt.get("decision_sha256"),
            field + " decision_artifact", manifest_parent,
        )
        if decision.get("decision") not in ("keep", "retire"):
            raise Invalid(f"{field} decision artifact must contain keep or retire")
        reasons = decision.get("reasons", [])
        if not isinstance(reasons, list) or any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise Invalid(f"{field} decision reasons must be a string array")
        if decision["decision"] == "keep" and reasons:
            raise Invalid(f"{field} keep decision cannot contain failure reasons")
        if decision.get("version") == 3:
            execution = decision.get("execution_provenance")
            runners = execution.get("runners") if isinstance(execution, dict) else None
            if not isinstance(runners, list) or not runners:
                raise Invalid(f"{field} v3 decision must retain runner provenance")
            for runner in runners:
                treatment = runner.get("treatment") if isinstance(runner, dict) else None
                if not isinstance(treatment, dict) or treatment.get("skill_sha256") != candidate_hash:
                    raise Invalid(f"{field} candidate_sha256 does not match v3 decision treatment evidence")
        has_replay = any(name + "_artifact" in attempt for name in ("packet", "key", "judgment"))
        if decision["decision"] == "keep" and unknown_exposure:
            raise Invalid(f"{field} activation cannot establish fresh heldouts after prior attempts with unavailable exposure evidence")
        if decision["decision"] == "keep" or decision.get("version") == 3 or has_replay:
            seen_inputs, heldout_inputs = replay_decision(attempt, decision, manifest, root, manifest_parent, field)
            if exposed_inputs & heldout_inputs:
                raise Invalid(f"{field} heldout inputs reuse exposed cases from an earlier attempt")
            exposed_inputs.update(seen_inputs)
        else:
            unknown_exposure = True
        decisions.append(decision["decision"])
        if decision["decision"] == "keep" and index != len(attempts):
            raise Invalid(f"{field} passed but later attempts exist")
        if decision["decision"] == "retire" and attempt.get("heldout_retired") is not True:
            raise Invalid(f"{field} failed heldout_set must be retired")

    terminal = manifest.get("terminal_action")
    if decisions[-1] == "keep":
        expected_terminal = "activate_candidate"
    elif len(attempts) < maximum:
        expected_terminal = "continue"
    elif kind == "new":
        expected_terminal = "archive_candidate"
    else:
        expected_terminal = "restore_last_proven"
    if terminal != expected_terminal:
        raise Invalid(f"terminal_action must be {expected_terminal}")
    return {
        "version": 1,
        "status": "valid",
        "candidate_kind": kind,
        "attempts_used": len(attempts),
        "maximum_serious_revisions": maximum,
        "terminal_action": terminal,
        "decision_sequence": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    root = (args.evidence_root or args.manifest.parent).resolve()
    try:
        parent = args.manifest.resolve().parent.relative_to(root)
        print(json.dumps(validate(read_object(args.manifest), root, parent), indent=2))
        return 0
    except (Invalid, KeyError, TypeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
