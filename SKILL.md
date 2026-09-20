---
name: skill-eval-pack
description: >-
  Evaluate a newly created or materially revised agent skill against a no-skill
  baseline, then keep or retire it based on blinded independent-agent judgment.
  Use whenever asked to add, create, revise, install, or prove a skill for Claude
  Code or Codex; not for typo-only edits or ordinary prompts that do not change a skill.
---

# Skill Eval Pack

No new skill earns permanent prompt space without beating the same model on the same task without
that skill. Run this workflow during skill creation, before declaring the skill installed.

## Contract

- Freeze the task, model, tools, context, rubric, critical failures, and keep threshold before
  seeing treatment output.
- Split cases into development and heldout sets. Development cases guide iteration. Only heldout
  cases decide keep or retire. After any candidate iteration informed by a heldout result, discard
  those heldouts and write fresh unseen ones before the next gate.
- Test trigger routing separately when discovery behavior is in scope. Include both positive and
  negative trigger probes without forcing unrelated requests into the behavioral A/B case set.
- Prefer deterministic graders for anything mechanically checkable. Run them before judge scoring
  and retain their results with the evaluation. Do not replace an exact check with model opinion.
- Run baseline and treatment in separate fresh contexts. The candidate skill is the only intended
  difference. Do not show its name, text, or purpose to the baseline runner.
- Use multiple baseline and treatment trials whenever execution is stochastic. Use at least two
  independent judges and three or more for broad, costly, or safety-critical skills.
- Preserve failed runs and unknown measurements. Record verbatim transcripts and final outcomes;
  judges must inspect both. Never manufacture an output or score.
- Give counterbalanced anonymous packets to fresh judge agents. The author and runners do not
  judge. No judge sees the key or another judge's result.
- Keep only a clear heldout improvement. A tie, cosmetic change, missing run, core regression, or
  any heldout treatment critical failure reported by any judge fails. A failed heldout deterministic
  grader or heldout trigger test also fails.

Use Skillforge (https://github.com/ong6/skillforge) when available to freeze and retain the full
evaluation bundle. It owns model/case/version provenance and baseline deltas. This pack owns the
creation-time orchestration, blind judging, and keep-or-retire decision. The local helper remains
usable when Skillforge is unavailable.

## Procedure

1. **Define the behavioral claim.** State what the proposed skill should improve, what must not
   regress, and when the skill should and should not trigger. If these cannot be observed, do not
   create the skill yet.
2. **Freeze development cases and rubric.** Before drafting or loading the candidate, write
   realistic inputs, expected qualities, weighted criteria, core criterion IDs, critical failures,
   deterministic graders where possible, and a minimum overall delta. Default to 5 normalized
   points. Structural validation is a prerequisite, not evidence that the skill helps.
3. **Iterate on development cases.** Run no-skill baselines and candidate treatments in fresh,
   matched contexts. Use multiple trials for stochastic behavior. Review complete transcripts,
   tool use, artifacts, deterministic grader results, and final outcomes. Fix the skill using only
   development evidence.
4. **Freeze fresh heldouts.** Write unseen heldout behavioral cases only after iteration stops. Do
   not tune against these cases. If routing is in scope, freeze separate positive and negative
   trigger tests too.
5. **Run heldout trials.** Use the same model, tools, context, and trial count for baseline and
   treatment. If isolation or parity is unavailable, stop and report that the comparison is not
   controlled.
6. **Blind the comparisons.** Put verbatim transcripts and outcomes into a version 2 input for
   scripts/eval_gate.py prepare. It emits one packet per judge and counterbalances A/B position
   for every trial. Keep the key and full packet bundle away from judges; give each judge only its
   own entry under judge_packets.
7. **Judge independently.** Each fresh judge uses only its packet and the contract in
   references/judge-contract.md. It scores every criterion with an exact evidence quote from that
   run, chooses the winner implied by weighted scores (exact equality is a tie), and selects critical
   failures only from the frozen taxonomy. Collect all judge results into one v2 judgment file.
8. **Apply the gate.** Run scripts/eval_gate.py decide. Only heldout cases affect the decision.
   Treatment must clear the frozen delta, win more heldout cases than it loses, avoid every core
   regression, improve at least one core criterion, and have an empty union of heldout treatment
   critical failures across judges. Any heldout treatment deterministic-grader failure or heldout
   trigger mismatch also retires the candidate. Never override a failure by editorial judgment.
9. **Keep or retire.** On pass, leave the skill active and rerun both clients' skill validation. On
   failure, tell the human plainly and follow the repository's retirement policy without deleting
   evidence. A future attempt needs fresh heldouts.
10. **Report.** Give the decision, heldout scores and delta, score dispersion, per-case winners,
    per-judge and pairwise agreement, the strict critical-failure union, trial count,
    model/isolation limitations, active or retired path, and Claude/Codex validation results.

## Helper

Version 2 is the default for new evaluations. Version 1 remains accepted for existing bundles.

    python3 scripts/eval_gate.py prepare \
      --input evaluation-input.json \
      --packet judge-packets.json \
      --key judge-key.json \
      --seed 20260920

Give each judge only its matching object from judge-packets.json under judge_packets, never the
bundle or judge-key.json.

    python3 scripts/eval_gate.py decide \
      --packet judge-packets.json \
      --key judge-key.json \
      --judgment judge-outputs.json \
      --output decision.json

The helper refuses malformed, incomplete, mismatched, or overwritten artifacts. Inputs and schemas
are documented in references/judge-contract.md. Evaluation artifacts may contain private prompts,
transcripts, and outputs; keep them out of public repositories unless reviewed.

## Failure patterns

| Bad | Required |
|---|---|
| Tune on the cases used for the final decision | Iterate on development cases, then freeze fresh heldouts |
| Ask one agent to remember how it would answer without the skill | Use separate fresh baseline and treatment contexts |
| Run one trial for stochastic behavior | Run multiple independent baseline and treatment trials |
| Give every judge treatment in the same position | Use generated counterbalanced judge packets |
| Judge only the final prose | Review the verbatim transcript, tool behavior, artifacts, and outcome |
| Ask a model to judge an exact property | Use a deterministic grader with structured passed and details fields; its heldout result gates the decision |
| Let a judge name a new critical failure | Require every reported failure to match the frozen taxonomy exactly |
| Accept a winner inconsistent with scores | Derive the winner from weighted scores; equal scores require tie |
| Accept a generic evidence rationale | Require an evidence_quote copied exactly from that run |
| Average away one judge's critical failure | Union critical failures; any heldout treatment failure retires |
| Let strong development results rescue weak heldouts | Gate only on heldout cases |
| Keep a tie because the skill sounds useful | Retire it; extra prompt cost needs measured benefit |
