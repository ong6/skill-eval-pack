# Evaluation design references

Retrieved 2026-09-21. These sources informed the pack's contract; they are not runtime dependencies.

- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
  supports realistic tasks, multiple trials for stochastic agents, outcome and transcript inspection,
  complementary deterministic and model graders, and routine grader calibration.
- [Anthropic: Improving skill-creator](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills)
  supports baseline comparison, blind comparison between skill versions, repeated benchmark runs,
  and removing capability-uplift skills once the base model catches up.
- [Anthropic skills: skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator)
  is a concrete public implementation of skill generation, evaluation, blind comparison, and
  iterative improvement.
- [OpenAI: Evals design guide](https://platform.openai.com/docs/guides/evals)
  supports defining the objective and dataset before execution, combining metrics, and continuous
  evaluation as prompts and models change.
- [OpenAI: Graders](https://platform.openai.com/docs/guides/graders)
  supports deterministic graders where possible and calibrated model graders for nuanced quality.
- [OpenAI Evals](https://github.com/openai/evals) provides public examples and an evaluation
  registry for reproducible task, data, and scoring definitions.

Skill Eval Pack adds requirements that matter specifically for local Claude/Codex skills:

- The candidate skill must be the only intended baseline/treatment difference.
- No evaluation component may invoke a nested AI CLI. The host creates runners and judges through
  its native collaboration API, and every v3 record retains matching native-host receipts plus
  hashed process and agent-tree snapshots.
- Candidate outputs are untrusted quoted data. Judges ignore any embedded instructions.
- Heldouts are single-use after exposure, revisions are bounded, and terminal restore/archive
  actions are machine-validated.
- A keep requires both a point-estimate gain and an uncertainty-aware lower-bound gain without an
  excessive time, token, tool-call, or error regression.
