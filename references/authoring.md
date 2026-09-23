# Authoring a skill

The make half of Skillsmith: gate, ground, draft. Deeper references:
[Anthropic's skill-authoring best practices](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/best-practices)
and [OpenAI's Codex skill guide](https://developers.openai.com/codex/skills/).

## Gate: does this need a skill?

A skill earns its place only when **all** hold: a reusable multi-step procedure, nameable trigger
phrases, judgment needed each time, and repeated use. If any fail, say so and point to the right home:

| Situation | Right home, not a skill |
|---|---|
| An always-apply rule for this repo | `AGENTS.md` or `CLAUDE.md` (the repo's agent manual) |
| A preference or point-in-time fact | The agent's memory |
| Should fire automatically on an event | A hook in the host's settings |
| A one-off task, even a complex one | Just do it |
| A single reference doc with no procedure | A document in the repo |
| An existing skill covers about 80% of it | Extend that skill |

Build only once the user confirms or the four criteria clearly hold.

## Ground: what does this repo already have?

    python3 scripts/inventory.py --repo /absolute/repo --query "what the skill should do" --global

It lists the repo's agent manuals and every skill it can discover, ranked by term overlap with the
query. Read the manuals and the top matches before drafting.

1. **Overlap.** A match that already covers the job gets extended, not duplicated. Two skills with
   similar descriptions make selection worse for both.
2. **Conventions.** Follow the repo's own rules for where skills live, how Codex discovers them, how
   a skill retires and what may never be deleted. Those rules outrank the defaults here.
3. **Prior art.** Check installed plugins (the `--global` scan reads their caches), then official
   Anthropic and OpenAI skill collections. Plugins are all-or-nothing; if the user doesn't want the
   rest of the set, write the skill locally. The gap you find is the new skill's focus.

## Draft

**Frontmatter.** Only `name` and `description`. `name`: lowercase letters, digits and hyphens, at
most 64 characters, matching the folder. `description`: at most 1024 characters, no angle brackets,
a YAML block scalar when punctuation could be misparsed.

**The description is a trigger, not a summary.** It is the only text the agent sees when choosing a
skill. Name the literal phrases and situations that should reach it and the near-misses that
shouldn't (`...; not resume editing`). Vague descriptions are the main failure mode.

**Pick the side of invocation.** Heavy workflows a user starts on purpose are explicit-only, or they
fire as noise. Steering skills that must apply whenever the situation arises stay implicit. Codex
metadata and invocation policy go in `agents/openai.yaml`, never frontmatter; for explicit-only
skills set `policy.allow_implicit_invocation: false` and say explicit-only in the description.

**Body.** Under 500 lines; split into sibling files past that, each one level deep from SKILL.md.
Assume the agent is competent: add only what it doesn't know, and cut any paragraph that doesn't
change behavior.

- **Match specificity to fragility.** Fragile, order-dependent or destructive work gets exact
  commands; judgment work gets direction and latitude.
- **Prefer scripts for deterministic steps.** Say whether to run or read each one. Scripts handle
  their own errors and name every missing dependency at once.
- **Build in a feedback loop** for anything quality-critical: check, fix, repeat, and say which
  step to return to on failure. Verification the agent can skip will get skipped.
- **Show bad, then good.** A failure mode not demonstrated will survive. A two-column table of bad
  and required behavior beats a paragraph of principle.
- **The prose is itself a prompt.** Tics in the file leak into everything generated while it is
  loaded. Cut filler and generic framing.
- **Compose instead of inflating.** Link to a skill that already defines the vocabulary or
  sub-procedure and say when to reach for it.
- **Avoid** time-sensitive statements, inconsistent terminology, and several tools where one default
  plus an escape hatch will do.

Then lint until it passes:

    python3 scripts/lint_skill.py /absolute/repo/.claude/skills/new-skill

Errors block; warnings are judgment calls you resolve or justify.

## Maintain

Whenever a skill is edited, check it for:

- **Overlap** with a plugin or another skill: slim it to the delta or merge.
- **Focus**: sections nobody uses, or that restate what the agent does anyway.
- **Staleness**: hardcoded dates, prices, versions, dead links, retired skill names.
- **Size**: grown past a checklist, so split or cut.

A material behavior change goes back through the prove half before it stays active.
