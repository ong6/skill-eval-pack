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
target="$repo/.claude/skills/build-skill"
codex_link="$repo/.agents/skills/build-skill"
[ -d "$repo" ] || { printf 'repository does not exist: %s\n' "$repo" >&2; exit 2; }

# An old personalized skill must be reviewed, not silently shadowed by a second
# active installation under the new identifier.
for legacy in "$repo/.claude/skills/skillsmith" "$repo/.agents/skills/skillsmith"; do
  if [ -e "$legacy" ] || [ -L "$legacy" ]; then
    printf 'legacy skillsmith installation found: %s\n' "$legacy" >&2
    printf 'Preserve it outside active skill discovery and reconcile its customizations before installing build-skill. See README.md migration instructions. No installation files changed.\n' >&2
    exit 2
  fi
done

# Check both destinations and the complete source before touching an installation.
if [ -e "$target" ] || [ -L "$target" ]; then
  [ "$force" -eq 1 ] || { printf 'target exists; inspect it or rerun with --force: %s\n' "$target" >&2; exit 2; }
fi
if [ -e "$codex_link" ] || [ -L "$codex_link" ]; then
  [ "$force" -eq 1 ] || { printf 'Codex target exists: %s\n' "$codex_link" >&2; exit 2; }
fi
payload=(
  SKILL.md \
  agents/openai.yaml \
  references/authoring.md \
  references/judge-contract.md \
  references/research.md \
  scripts/eval_gate.py \
  scripts/lifecycle_gate.py \
  scripts/check_payload.py \
  scripts/inventory.py \
  scripts/lint_skill.py \
  tests/test_eval_gate.py \
  tests/test_authoring.py \
  tests/test_lifecycle_gate.py \
  tests/test_payload.py \
  tests/test_workflow_contract.py
)
for relative in "${payload[@]}"; do
  [ -f "$source_dir/$relative" ] || { printf 'source missing: %s\n' "$relative" >&2; exit 2; }
done
mkdir -p "$repo/.claude/skills" "$repo/.agents/skills"
lock="$repo/.claude/skills/.skillsmith-install.lock"
mkdir "$lock" 2>/dev/null || { printf 'installation already in progress: %s\n' "$lock" >&2; exit 2; }
stage=''
target_installed=0
link_managed=0
success=0
cleanup() {
  result=$?
  trap - EXIT
  trap '' HUP INT TERM
  if [ "$success" -eq 0 ]; then
    # Retain the backup if restoration fails; never discard the prior install.
    if [ "$link_managed" -eq 1 ]; then rm -rf -- "$codex_link" || exit 1; fi
    if [ "$target_installed" -eq 1 ]; then rm -rf -- "$target" || exit 1; fi
    # Inspect the filesystem: a signal can arrive after mv succeeds but before
    # the shell executes its next assignment.
    if [ -n "$stage" ] && { [ -e "$stage/previous" ] || [ -L "$stage/previous" ]; }; then
      mv "$stage/previous" "$target" || exit 1
    fi
    if [ -n "$stage" ] && { [ -e "$stage/previous-link" ] || [ -L "$stage/previous-link" ]; }; then
      mv "$stage/previous-link" "$codex_link" || exit 1
    fi
  fi
  [ -z "$stage" ] || rm -rf -- "$stage"
  rmdir "$lock"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
# Another installer may have completed between preflight and acquiring the lock.
if [ "$force" -eq 0 ] && { [ -e "$target" ] || [ -L "$target" ] || [ -e "$codex_link" ] || [ -L "$codex_link" ]; }; then
  printf 'installation appeared during preflight; refusing to overwrite\n' >&2
  exit 2
fi
stage=$(mktemp -d "$repo/.claude/skills/.skillsmith-stage.XXXXXX")
mkdir -p "$stage/candidate/agents" "$stage/candidate/references" "$stage/candidate/scripts" "$stage/candidate/tests"
for relative in "${payload[@]}"; do
  cp "$source_dir/$relative" "$stage/candidate/$relative"
done
chmod +x "$stage/candidate"/scripts/*.py
python3 "$source_dir/scripts/check_payload.py" --source "$source_dir" --installed "$stage/candidate" >/dev/null

if [ -e "$target" ] || [ -L "$target" ]; then
  mv "$target" "$stage/previous"
fi
if [ -e "$codex_link" ] || [ -L "$codex_link" ]; then
  mv "$codex_link" "$stage/previous-link"
fi
target_installed=1
mv "$stage/candidate" "$target"
link_managed=1

if [ -x "$repo/.agents/sync-skills.sh" ]; then
  (cd "$repo" && bash .agents/sync-skills.sh)
else
  ln -s ../../.claude/skills/build-skill "$codex_link"
fi
# A successful validator must actually expose the canonical payload.
python3 - "$target" "$codex_link" <<'PY'
from pathlib import Path
import sys
target, link = map(Path, sys.argv[1:])
if not link.is_symlink() or link.resolve() != target.resolve():
    raise SystemExit("Codex discovery does not resolve to the installed skill")
PY
success=1

printf 'installed Claude skill: %s\n' "$target"
printf 'installed Codex link: %s\n' "$codex_link"
