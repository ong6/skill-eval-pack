# skill-eval-pack

[![CI](https://github.com/ong6/skill-eval-pack/actions/workflows/ci.yml/badge.svg)](https://github.com/ong6/skill-eval-pack/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A portable Claude Code and Codex skill that A/B tests a new or revised skill before it earns
permanent prompt space. It separates development cases from fresh heldouts, runs isolated baseline
and treatment trials, combines deterministic checks with counterbalanced independent judges, and
applies a machine-checked keep-or-retire gate.

It complements Skillforge (https://github.com/ong6/skillforge): Skillforge stores rigorous frozen
evaluation bundles and baseline deltas; this pack makes evaluation a required part of skill creation
and supplies the blind judging and lifecycle decision. It never calls a model itself. Version 3
requires matched-condition hashes, retained host-native receipts, judge calibration, efficiency
metrics, and uncertainty-aware gates. Recursive Claude/Codex CLI runs are rejected.

This sits between [Skillpack](https://github.com/ong6/skillpack) and
[Groundplane](https://github.com/ong6/groundplane). Skillpack holds the instructions an agent can
load; this pack tests whether one helps; Groundplane checks declared facts when the resulting agent
runs. The write-up and animated lifecycle are at
[junxiong.dev/skill-eval-pack](https://junxiong.dev/skill-eval-pack).

## Install

    git clone https://github.com/ong6/skill-eval-pack.git
    bash skill-eval-pack/install.sh /absolute/path/to/repository

The installer copies one canonical skill to .claude/skills/skill-eval-pack and exposes the same files
to Codex at .agents/skills/skill-eval-pack. If the target repo has .agents/sync-skills.sh, that
existing validator owns the Codex link. Existing installs are never overwritten unless --force is
explicit.

Then make the repository's normal skill-authoring workflow invoke skill-eval-pack whenever a new
skill or material revision is requested. Evaluation is deliberate, not a lifecycle hook: launching
model runs during PostToolUse or Stop would be expensive, context-poor, and hard to isolate.

## Test

    python3 -m unittest discover -s tests -p 'test_*.py' -v
    bash tests/test_install.sh

scripts/eval_gate.py uses only the Python standard library. Version 3 gates on heldout cases only,
requires at least two judges, verifies quoted evidence and winner arithmetic, unions critical
failures, and can veto a candidate on deterministic, trigger, uncertainty, provenance, calibration,
or efficiency failures. `scripts/lifecycle_gate.py` validates the bounded revision and terminal
action record. `scripts/check_payload.py` detects drift between this repository and an installation.
Versions 1 and 2 remain compatible. Private prompts and outputs stay in the host repository.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) before changing the evaluation contract. Report unsafe
execution paths or provenance bypasses through the private route in [SECURITY.md](SECURITY.md).

## License

MIT © 2026 Ong Jun Xiong
