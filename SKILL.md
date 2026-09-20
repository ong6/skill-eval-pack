---
name: skill-eval-pack
description: >-
  Evaluate a newly created or materially revised agent skill against a no-skill
  baseline, then keep or retire it based on a blinded independent-agent judgment.
  Use whenever asked to add, create, revise, install, or prove a skill for Claude
  Code or Codex; not for typo-only edits or ordinary prompts that do not change a skill.
---

# Skill Eval Pack

No new skill earns permanent prompt space without beating the same model on the same task without
that skill. Run this workflow during skill creation, before declaring the skill installed.

## Contract

- Freeze the task, model, tools, context, rubric, and keep threshold before seeing treatment output.
- Run baseline and treatment in separate fresh contexts. The candidate skill is the only intended
  difference. Do not show its name, text, or purpose to the baseline runner.
- Use at least one realistic case. Use three or more when the skill is broad, costly, or safety-critical.
- Preserve failed runs and unknown measurements. Never manufacture an output or score.
- Give anonymized outputs to a third, fresh judge agent. The author and runners do not judge.
- Keep only a clear improvement. A tied overall result, cosmetic change, missing run, or critical regression fails.

Use Skillforge (https://github.com/ong6/skillforge) when available to freeze and retain the full
evaluation bundle. It owns model/case/version provenance and baseline deltas. This pack owns the
creation-time orchestration, blind judging, and keep-or-retire decision. The local helper remains
usable when Skillforge is unavailable.

## Procedure

1. **Define the behavioral claim.** State what the proposed skill should improve and which behavior
   must not regress. If this cannot be tested in an output, do not create the skill yet.
2. **Freeze cases and rubric.** Before drafting or loading the candidate, write realistic inputs,
   expected qualities, weighted criteria, core criterion IDs, critical failures, and a minimum
   overall delta. Default to 5 points on a normalized 100-point score. Structural validation is a
   prerequisite, not evidence that the skill helps.
3. **Run the baseline.** Spawn a fresh general-purpose agent with the exact case, normal repository
   instructions, and no candidate instructions. Record its output verbatim. Do not let the baseline
   inspect the candidate file.
4. **Create the candidate.** Follow the host repository's skill-authoring and validation rules. Keep
   one canonical skill body. For a Claude/Codex repository, expose that body through each client's
   normal skill directory without making divergent copies.
5. **Run the treatment.** Spawn another fresh agent using the same model, case, tools, and context.
   Explicitly load the candidate skill. Record the output verbatim. If isolation or model parity is
   unavailable, stop and report that the comparison is not controlled.
6. **Blind the comparison.** Put verbatim baseline/treatment outputs into the input accepted by
   scripts/eval_gate.py prepare. Keep its key away from the judge. Candidate ordering changes per
   case from the declared seed, so a fixed A/B position cannot leak identity.
7. **Judge independently.** Spawn a third fresh agent with only the blind packet and the rubric. It
   must return the schema in references/judge-contract.md, quote evidence for every score, and list
   critical failures separately. It must not inspect the skill, key, authoring conversation, or
   runner identities.
8. **Apply the gate.** Run scripts/eval_gate.py decide. Pass only when all runs exist, treatment's
   weighted score clears the frozen minimum delta, treatment wins more cases than it loses, no core
   criterion regresses, at least one core criterion improves, and
   treatment has no critical failure. Do not override a failure by editorial judgment.
9. **Keep or retire.** On pass, leave the skill active and rerun both clients' skill validation. On
   failure, tell the human plainly and remove it from active discovery. In repositories with a
   no-delete rule, move it to the documented archive and remove stale client links; otherwise use
   the repository's normal retirement policy. Never silently delete evidence or the candidate.
10. **Report.** Give the decision, baseline and treatment scores, per-case winners, critical failures,
    model/isolation limitations, active or archived path, and Claude/Codex validation result.

## Helper

    python3 scripts/eval_gate.py prepare \
      --input evaluation-input.json \
      --packet judge-packet.json \
      --key judge-key.json \
      --seed 20260920

Give judge-packet.json, never judge-key.json, to the judge agent.

    python3 scripts/eval_gate.py decide \
      --packet judge-packet.json \
      --key judge-key.json \
      --judgment judge-output.json \
      --output decision.json

The helper refuses malformed, incomplete, mismatched, or overwritten artifacts. Inputs and examples
are documented in references/judge-contract.md. Evaluation artifacts may contain private prompts and
outputs; keep them out of public repositories unless reviewed.

## Failure patterns

| Bad | Required |
|---|---|
| Ask one agent to remember how it would answer without the skill | Use separate fresh baseline and treatment contexts |
| Tell the judge which output used the skill | Blind labels and withhold the key |
| Score after seeing both outputs with an invented rubric | Freeze criteria, weights, core IDs, and threshold first |
| Keep a tie because the skill sounds useful | Retire it; extra prompt cost needs measured benefit |
| Treat formatting checks as effectiveness | Validate structure, then separately measure behavior |
| Delete a failed skill in a no-delete repository | Archive it and remove active client links |
