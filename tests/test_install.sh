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

# A conflicting Codex destination must be rejected before creating the Claude skill.
mkdir -p "$tmp/conflict/.agents/skills/skillsmith"
printf 'owner content\n' > "$tmp/conflict/.agents/skills/skillsmith/custom.txt"
if bash "$root/install.sh" "$tmp/conflict" >/dev/null 2>&1; then
  printf 'installer accepted an existing Codex destination\n' >&2; exit 1
fi
test ! -e "$tmp/conflict/.claude/skills/skillsmith"
test "$(cat "$tmp/conflict/.agents/skills/skillsmith/custom.txt")" = 'owner content'

# An incomplete download cannot destroy a prior install, even with --force.
mkdir -p "$tmp/incomplete"
cp "$root/install.sh" "$tmp/incomplete/install.sh"
printf 'keep this version\n' > "$tmp/repo/.claude/skills/skillsmith/custom.txt"
if bash "$tmp/incomplete/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer accepted incomplete source\n' >&2; exit 1
fi
test "$(cat "$tmp/repo/.claude/skills/skillsmith/custom.txt")" = 'keep this version'

# Host validation failure restores both original destinations, including custom files.
printf '#!/usr/bin/env bash\nln -s ../../.claude/skills/skillsmith .agents/skills/skillsmith\nexit 1\n' > "$tmp/repo/.agents/sync-skills.sh"
if bash "$root/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer ignored failing host validator\n' >&2; exit 1
fi
test "$(cat "$tmp/repo/.claude/skills/skillsmith/custom.txt")" = 'keep this version'
test "$(readlink "$tmp/repo/.agents/skills/skillsmith")" = '../../.claude/skills/skillsmith'
test ! -e "$tmp/repo/.claude/skills/.skillsmith-install.lock"

# A host validator that returns success without exposing the skill is still a failure.
printf '#!/usr/bin/env bash\nexit 0\n' > "$tmp/repo/.agents/sync-skills.sh"
if bash "$root/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer accepted absent Codex discovery\n' >&2; exit 1
fi
test "$(cat "$tmp/repo/.claude/skills/skillsmith/custom.txt")" = 'keep this version'
test -L "$tmp/repo/.agents/skills/skillsmith"

# Copy failures happen in staging and preserve the complete prior installation.
mkdir -p "$tmp/failing-bin"
printf '#!/usr/bin/env bash\nexit 1\n' > "$tmp/failing-bin/cp"
chmod +x "$tmp/failing-bin/cp"
if PATH="$tmp/failing-bin:$PATH" bash "$root/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer ignored a copy failure\n' >&2; exit 1
fi
test "$(cat "$tmp/repo/.claude/skills/skillsmith/custom.txt")" = 'keep this version'
test -L "$tmp/repo/.agents/skills/skillsmith"
test ! -e "$tmp/repo/.claude/skills/.skillsmith-install.lock"

# Interrupt immediately after each rename, before the caller's next assignment.
# This catches lost backups in signal windows between filesystem and shell state.
mkdir -p "$tmp/signal-bin"
cat > "$tmp/signal-bin/mv" <<'SH'
#!/usr/bin/env bash
/bin/mv "$@" || exit $?
case "$2" in
  */"$INSTALL_SIGNAL_POINT") kill -TERM "$PPID" ;;
esac
SH
chmod +x "$tmp/signal-bin/mv"
for point in previous previous-link skillsmith; do
  if INSTALL_SIGNAL_POINT="$point" PATH="$tmp/signal-bin:$PATH" bash "$root/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
    printf 'installer ignored interruption after %s rename\n' "$point" >&2; exit 1
  fi
  test "$(cat "$tmp/repo/.claude/skills/skillsmith/custom.txt")" = 'keep this version'
  test "$(readlink "$tmp/repo/.agents/skills/skillsmith")" = '../../.claude/skills/skillsmith'
  test ! -e "$tmp/repo/.claude/skills/.skillsmith-install.lock"
done
printf 'installer tests passed\n'
