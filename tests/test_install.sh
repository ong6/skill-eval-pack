#!/usr/bin/env bash
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/skillsmith-test.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/repo"
bash "$root/install.sh" "$tmp/repo" >/dev/null
test -f "$tmp/repo/.claude/skills/build-skill/SKILL.md"
test -f "$tmp/repo/.claude/skills/build-skill/tests/test_eval_gate.py"
test -f "$tmp/repo/.claude/skills/build-skill/tests/test_workflow_contract.py"
test -f "$tmp/repo/.claude/skills/build-skill/scripts/lifecycle_gate.py"
test -f "$tmp/repo/.claude/skills/build-skill/scripts/check_payload.py"
test -f "$tmp/repo/.claude/skills/build-skill/references/research.md"
test -f "$tmp/repo/.claude/skills/build-skill/references/authoring.md"
test -x "$tmp/repo/.claude/skills/build-skill/scripts/inventory.py"
test -x "$tmp/repo/.claude/skills/build-skill/scripts/lint_skill.py"
python3 "$tmp/repo/.claude/skills/build-skill/scripts/lint_skill.py" "$tmp/repo/.claude/skills/build-skill" >/dev/null
python3 "$tmp/repo/.claude/skills/build-skill/scripts/check_payload.py" --installed "$tmp/repo/.claude/skills/build-skill" >/dev/null
test -L "$tmp/repo/.agents/skills/build-skill"
test "$(readlink "$tmp/repo/.agents/skills/build-skill")" = '../../.claude/skills/build-skill'
if bash "$root/install.sh" "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer overwrote without --force\n' >&2
  exit 1
fi
bash "$root/install.sh" --force "$tmp/repo" >/dev/null

# A host sync script must run from the host repository, not this pack checkout.
rm -rf -- "$tmp/repo/.claude" "$tmp/repo/.agents"
mkdir -p "$tmp/repo/.agents"
printf '#!/usr/bin/env bash\ntest -f .claude/skills/build-skill/SKILL.md\nln -s ../../.claude/skills/build-skill .agents/skills/build-skill\n' > "$tmp/repo/.agents/sync-skills.sh"
chmod +x "$tmp/repo/.agents/sync-skills.sh"
bash "$root/install.sh" "$tmp/repo" >/dev/null
test -L "$tmp/repo/.agents/skills/build-skill"

# A conflicting Codex destination must be rejected before creating the Claude skill.
mkdir -p "$tmp/conflict/.agents/skills/build-skill"
printf 'owner content\n' > "$tmp/conflict/.agents/skills/build-skill/custom.txt"
if bash "$root/install.sh" "$tmp/conflict" >/dev/null 2>&1; then
  printf 'installer accepted an existing Codex destination\n' >&2; exit 1
fi
test ! -e "$tmp/conflict/.claude/skills/build-skill"
test "$(cat "$tmp/conflict/.agents/skills/build-skill/custom.txt")" = 'owner content'

# An incomplete download cannot destroy a prior install, even with --force.
mkdir -p "$tmp/incomplete"
cp "$root/install.sh" "$tmp/incomplete/install.sh"
printf 'keep this version\n' > "$tmp/repo/.claude/skills/build-skill/custom.txt"
if bash "$tmp/incomplete/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer accepted incomplete source\n' >&2; exit 1
fi
test "$(cat "$tmp/repo/.claude/skills/build-skill/custom.txt")" = 'keep this version'

# Host validation failure restores both original destinations, including custom files.
printf '#!/usr/bin/env bash\nln -s ../../.claude/skills/build-skill .agents/skills/build-skill\nexit 1\n' > "$tmp/repo/.agents/sync-skills.sh"
if bash "$root/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer ignored failing host validator\n' >&2; exit 1
fi
test "$(cat "$tmp/repo/.claude/skills/build-skill/custom.txt")" = 'keep this version'
test "$(readlink "$tmp/repo/.agents/skills/build-skill")" = '../../.claude/skills/build-skill'
test ! -e "$tmp/repo/.claude/skills/.skillsmith-install.lock"

# A host validator that returns success without exposing the skill is still a failure.
printf '#!/usr/bin/env bash\nexit 0\n' > "$tmp/repo/.agents/sync-skills.sh"
if bash "$root/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer accepted absent Codex discovery\n' >&2; exit 1
fi
test "$(cat "$tmp/repo/.claude/skills/build-skill/custom.txt")" = 'keep this version'
test -L "$tmp/repo/.agents/skills/build-skill"

# Copy failures happen in staging and preserve the complete prior installation.
mkdir -p "$tmp/failing-bin"
printf '#!/usr/bin/env bash\nexit 1\n' > "$tmp/failing-bin/cp"
chmod +x "$tmp/failing-bin/cp"
if PATH="$tmp/failing-bin:$PATH" bash "$root/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
  printf 'installer ignored a copy failure\n' >&2; exit 1
fi
test "$(cat "$tmp/repo/.claude/skills/build-skill/custom.txt")" = 'keep this version'
test -L "$tmp/repo/.agents/skills/build-skill"
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
for point in previous previous-link build-skill; do
  if INSTALL_SIGNAL_POINT="$point" PATH="$tmp/signal-bin:$PATH" bash "$root/install.sh" --force "$tmp/repo" >/dev/null 2>&1; then
    printf 'installer ignored interruption after %s rename\n' "$point" >&2; exit 1
  fi
  test "$(cat "$tmp/repo/.claude/skills/build-skill/custom.txt")" = 'keep this version'
  test "$(readlink "$tmp/repo/.agents/skills/build-skill")" = '../../.claude/skills/build-skill'
  test ! -e "$tmp/repo/.claude/skills/.skillsmith-install.lock"
done
# A legacy personalized install must not be replaced or shadowed by a new name.
mkdir -p "$tmp/legacy/.claude/skills/skillsmith" "$tmp/legacy/.agents/skills"
printf 'owner customization\n' > "$tmp/legacy/.claude/skills/skillsmith/SKILL.md"
ln -s ../../.claude/skills/skillsmith "$tmp/legacy/.agents/skills/skillsmith"
if bash "$root/install.sh" --force "$tmp/legacy" >"$tmp/legacy-result" 2>&1; then
  printf 'installer shadowed legacy customization\n' >&2; exit 1
fi
test "$(cat "$tmp/legacy/.claude/skills/skillsmith/SKILL.md")" = 'owner customization'
test -L "$tmp/legacy/.agents/skills/skillsmith"
test ! -e "$tmp/legacy/.claude/skills/build-skill"
test ! -e "$tmp/legacy/.agents/skills/build-skill"
printf 'installer tests passed\n'
