#!/usr/bin/env bash
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/skillsmith-test.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/repo"
bash "$root/install.sh" "$tmp/repo" >/dev/null
test -f "$tmp/repo/.claude/skills/skillsmith/SKILL.md"
test -f "$tmp/repo/.claude/skills/skillsmith/tests/test_eval_gate.py"
test -f "$tmp/repo/.claude/skills/skillsmith/tests/test_workflow_contract.py"
test -f "$tmp/repo/.claude/skills/skillsmith/scripts/lifecycle_gate.py"
test -f "$tmp/repo/.claude/skills/skillsmith/scripts/check_payload.py"
test -f "$tmp/repo/.claude/skills/skillsmith/references/research.md"
test -f "$tmp/repo/.claude/skills/skillsmith/references/authoring.md"
test -x "$tmp/repo/.claude/skills/skillsmith/scripts/inventory.py"
test -x "$tmp/repo/.claude/skills/skillsmith/scripts/lint_skill.py"
python3 "$tmp/repo/.claude/skills/skillsmith/scripts/lint_skill.py" "$tmp/repo/.claude/skills/skillsmith" >/dev/null
python3 "$tmp/repo/.claude/skills/skillsmith/scripts/check_payload.py" --installed "$tmp/repo/.claude/skills/skillsmith" >/dev/null
test -L "$tmp/repo/.agents/skills/skillsmith"
test "$(readlink "$tmp/repo/.agents/skills/skillsmith")" = '../../.claude/skills/skillsmith'
if bash "$root/install.sh" "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer overwrote without --force\n' >&2
  exit 1
fi
bash "$root/install.sh" --force "$tmp/repo" >/dev/null

# A host sync script must run from the host repository, not this pack checkout.
rm -rf -- "$tmp/repo/.claude" "$tmp/repo/.agents"
mkdir -p "$tmp/repo/.agents"
printf '#!/usr/bin/env bash\ntest -f .claude/skills/skillsmith/SKILL.md\nln -s ../../.claude/skills/skillsmith .agents/skills/skillsmith\n' > "$tmp/repo/.agents/sync-skills.sh"
chmod +x "$tmp/repo/.agents/sync-skills.sh"
bash "$root/install.sh" "$tmp/repo" >/dev/null
test -L "$tmp/repo/.agents/skills/skillsmith"
printf 'installer tests passed\n'
