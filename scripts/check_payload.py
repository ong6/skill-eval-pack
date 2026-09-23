#!/usr/bin/env python3
"""Verify that an installed Skillsmith install matches this checkout."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys


PAYLOAD = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/authoring.md",
    "references/judge-contract.md",
    "references/research.md",
    "scripts/eval_gate.py",
    "scripts/lifecycle_gate.py",
    "scripts/check_payload.py",
    "scripts/inventory.py",
    "scripts/lint_skill.py",
    "tests/test_eval_gate.py",
    "tests/test_authoring.py",
    "tests/test_lifecycle_gate.py",
    "tests/test_payload.py",
    "tests/test_workflow_contract.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def differences(source: Path, installed: Path) -> list[str]:
    findings = []
    for relative in PAYLOAD:
        left, right = source / relative, installed / relative
        if not left.is_file():
            findings.append(f"source missing {relative}")
        elif not right.is_file():
            findings.append(f"installed missing {relative}")
        elif digest(left) != digest(right):
            findings.append(f"payload differs {relative}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--installed", type=Path, required=True)
    args = parser.parse_args()
    findings = differences(args.source.resolve(), args.installed.resolve())
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"payload matches: {args.installed.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
