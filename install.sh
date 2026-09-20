#!/usr/bin/env bash
# Install one canonical Claude skill and expose it to Codex with a relative link.
set -eu

usage() {
  printf 'usage: %s [--force] /absolute/path/to/repository\n' "$0" >&2
  exit 2
}

force=0
if [ "${1:-}" = "--force" ]; then
  force=1
  shift
fi
[ "$#" -eq 1 ] || usage
case "$1" in /*) ;; *) printf 'repository path must be absolute\n' >&2; exit 2 ;; esac

repo=${1%/}
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target="$repo/.claude/skills/skill-eval-pack"
codex_link="$repo/.agents/skills/skill-eval-pack"
[ -d "$repo" ] || { printf 'repository does not exist: %s\n' "$repo" >&2; exit 2; }

if [ -e "$target" ] || [ -L "$target" ]; then
  [ "$force" -eq 1 ] || { printf 'target exists; inspect it or rerun with --force: %s\n' "$target" >&2; exit 2; }
  rm -rf -- "$target"
fi
mkdir -p "$target/agents" "$target/references" "$target/scripts" "$target/tests" "$repo/.agents/skills"
cp "$source_dir/SKILL.md" "$target/SKILL.md"
cp "$source_dir/agents/openai.yaml" "$target/agents/openai.yaml"
cp "$source_dir/references/judge-contract.md" "$target/references/judge-contract.md"
cp "$source_dir/scripts/eval_gate.py" "$target/scripts/eval_gate.py"
cp "$source_dir/tests/test_eval_gate.py" "$target/tests/test_eval_gate.py"
cp "$source_dir/tests/test_workflow_contract.py" "$target/tests/test_workflow_contract.py"
chmod +x "$target/scripts/eval_gate.py"

if [ -x "$repo/.agents/sync-skills.sh" ]; then
  (cd "$repo" && bash .agents/sync-skills.sh)
else
  if [ -e "$codex_link" ] || [ -L "$codex_link" ]; then
    [ "$force" -eq 1 ] || { printf 'Codex target exists: %s\n' "$codex_link" >&2; exit 2; }
    rm -rf -- "$codex_link"
  fi
  ln -s ../../.claude/skills/skill-eval-pack "$codex_link"
fi

printf 'installed Claude skill: %s\n' "$target"
printf 'installed Codex link: %s\n' "$codex_link"
