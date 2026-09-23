# skillsmith

[![CI](https://github.com/ong6/skillsmith/actions/workflows/ci.yml/badge.svg)](https://github.com/ong6/skillsmith/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Make an agent skill from your repo, then prove it beats no skill.

A portable Claude Code and Codex skill with two halves. **Make** gates whether the job needs a skill
at all, inventories the skills and agent manuals the repository already has so the new one fills a
gap instead of overlapping, and drafts a trigger-first skill that passes a linter. **Prove** runs the
same model with and without the candidate in isolated contexts, separates development cases from
fresh heldouts, combines deterministic checks with counterbalanced blind judges, and applies a
machine-checked keep-or-retire gate with a bounded revision loop.

It never calls a model itself. The host agent supplies runners and judges; the helpers are
standard-library Python that inventory, lint, blind, gate and validate. Version 3 evaluations require
matched-condition hashes, retained host-native receipts, judge calibration, efficiency metrics and
uncertainty-aware gates. Recursive Claude/Codex CLI runs are rejected.

It sits between [Skillpack](https://github.com/ong6/skillpack) and
[Groundplane](https://github.com/ong6/groundplane). Skillpack holds the instructions an agent can
load; skillsmith makes them and tests whether they help; Groundplane checks declared facts when the
resulting agent runs. The write-up is at [junxiong.dev/skillsmith](https://junxiong.dev/skillsmith).

## Install

    git clone https://github.com/ong6/skillsmith.git
    bash skillsmith/install.sh /absolute/path/to/repository

The installer copies one canonical skill to .claude/skills/skillsmith and exposes the same files to
Codex at .agents/skills/skillsmith. If the target repo has .agents/sync-skills.sh, that existing
validator owns the Codex link. Existing installs are never overwritten unless --force is explicit.

Then ask the agent to add or revise a skill; the description routes those requests to skillsmith.
Evaluation is deliberate, not a lifecycle hook: launching model runs during PostToolUse or Stop
would be expensive, context-poor, and hard to isolate.

## Helpers

| Script | Does |
|---|---|
| `scripts/inventory.py` | Lists the repo's agent manuals and skills (plus user-level and plugin skills with `--global`), ranked by overlap with the proposed job |
| `scripts/lint_skill.py` | Blocks on frontmatter, name, size and broken-link errors; warns on weak triggers and explicit-only mismatches |
| `scripts/eval_gate.py` | Prepares counterbalanced blind judge packets, then gates on heldout cases only |
| `scripts/lifecycle_gate.py` | Validates the bounded revision history and the keep, restore or archive action |
| `scripts/check_payload.py` | Detects drift between this checkout and an installation |

The gate requires at least two judges, verifies quoted evidence and winner arithmetic, unions
critical failures, and can veto a candidate on deterministic, trigger, uncertainty, provenance,
calibration or efficiency failures. Evaluation versions 1 and 2 remain compatible. Private prompts
and outputs stay in the host repository.

## Test

    python3 -m unittest discover -s tests -p 'test_*.py' -v
    bash tests/test_install.sh

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) before changing the evaluation contract. Report unsafe
execution paths or provenance bypasses through the private route in [SECURITY.md](SECURITY.md).

## License

MIT © 2026 Ong Jun Xiong
