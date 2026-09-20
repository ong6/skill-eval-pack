#!/usr/bin/env bash
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/skill-eval-pack-test.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/repo"
bash "$root/install.sh" "$tmp/repo" >/dev/null
test -f "$tmp/repo/.claude/skills/skill-eval-pack/SKILL.md"
test -L "$tmp/repo/.agents/skills/skill-eval-pack"
test "$(readlink "$tmp/repo/.agents/skills/skill-eval-pack")" = '../../.claude/skills/skill-eval-pack'
if bash "$root/install.sh" "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer overwrote without --force\n' >&2
  exit 1
fi
bash "$root/install.sh" --force "$tmp/repo" >/dev/null

# A host sync script must run from the host repository, not this pack checkout.
rm -rf -- "$tmp/repo/.claude" "$tmp/repo/.agents"
mkdir -p "$tmp/repo/.agents"
printf '#!/usr/bin/env bash\ntest -f .claude/skills/skill-eval-pack/SKILL.md\nln -s ../../.claude/skills/skill-eval-pack .agents/skills/skill-eval-pack\n' > "$tmp/repo/.agents/sync-skills.sh"
chmod +x "$tmp/repo/.agents/sync-skills.sh"
bash "$root/install.sh" "$tmp/repo" >/dev/null
test -L "$tmp/repo/.agents/skills/skill-eval-pack"
printf 'installer tests passed\n'
