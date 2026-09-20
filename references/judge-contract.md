# Judge contract

Use version 2 for new evaluations. The helper still accepts version 1 inputs, packets, judgments,
and produces the unchanged version 1 decision shape.

## Version 2 evaluation input

Write the rubric and all cases before treatment execution. Development cases may guide iteration;
heldout cases must be fresh and unseen after the last candidate change. transcript and outcome
must be verbatim. Trigger routing tests are an optional separate section, not behavioral A/B cases.
Set stochastic to true whenever sampling, external state, timing, or tool
behavior can vary; such cases require at least two trials.

    {
      "version": 2,
      "title": "Source distinction skill",
      "judge_count": 2,
      "rubric": [
        {"id": "accuracy", "label": "Factual accuracy", "weight": 2, "max_score": 5, "core": true},
        {"id": "clarity", "label": "Clear and concise", "weight": 1, "max_score": 5, "core": false}
      ],
      "critical_failures": ["Invents a source", "Claims execution that did not occur"],
      "gate": {"minimum_overall_delta": 5},
      "cases": [
        {
          "id": "development-positive",
          "split": "development",
          "input": "A realistic request for the skill",
          "expected": "Expected behavior and deterministic acceptance criteria",
          "deterministic_grader": "python3 check_result.py output.json",
          "stochastic": false,
          "trials": [
            {
              "id": "trial-1",
              "baseline": {
                "transcript": "Verbatim no-skill transcript",
                "outcome": "Verbatim outcome",
                "grader_result": {"passed": true, "details": "Verbatim deterministic grader result"}
              },
              "treatment": {
                "transcript": "Verbatim candidate transcript",
                "outcome": "Verbatim outcome",
                "grader_result": {"passed": true, "details": "Verbatim deterministic grader result"}
              }
            }
          ]
        },
        {
          "id": "heldout-edge-case",
          "split": "heldout",
          "input": "A fresh difficult request within the skill's behavioral scope",
          "expected": "Candidate behavior should improve the difficult outcome",
          "stochastic": true,
          "trials": [
            {
              "id": "trial-1",
              "baseline": {"transcript": "Verbatim transcript", "outcome": "Verbatim outcome"},
              "treatment": {"transcript": "Verbatim transcript", "outcome": "Verbatim outcome"}
            },
            {
              "id": "trial-2",
              "baseline": {"transcript": "Verbatim transcript", "outcome": "Verbatim outcome"},
              "treatment": {"transcript": "Verbatim transcript", "outcome": "Verbatim outcome"}
            }
          ]
        },
        {
          "id": "heldout-positive",
          "split": "heldout",
          "input": "A fresh relevant request not used during iteration",
          "expected": "Candidate behavior should activate and improve the outcome",
          "stochastic": false,
          "trials": [
            {
              "id": "trial-1",
              "baseline": {"transcript": "Verbatim transcript", "outcome": "Verbatim outcome"},
              "treatment": {"transcript": "Verbatim transcript", "outcome": "Verbatim outcome"}
            }
          ]
        }
      ],
      "trigger_tests": [
        {
          "id": "positive-routing",
          "split": "heldout",
          "input": "A prompt that should discover this skill",
          "expected_trigger": true,
          "observed_trigger": true,
          "details": "Verbatim routing evidence"
        },
        {
          "id": "negative-routing",
          "split": "heldout",
          "input": "A nearby prompt that should not discover this skill",
          "expected_trigger": false,
          "observed_trigger": false,
          "details": "Verbatim routing evidence"
        }
      ]
    }

Version 2 requires development and heldout behavioral cases. trigger_tests is optional; when
present it records routing separately and any heldout mismatch retires the candidate. A
deterministic_grader is optional only where no mechanical check is possible. When one is declared,
every baseline and treatment run must include grader_result with a boolean passed and non-empty
details. Any heldout treatment failure retires the candidate. Judge scores do not supersede it.

## Packet distribution

prepare writes a version 2 bundle with a judge_packets array. Each entry contains a distinct
judge_id and all blinded comparisons for that judge. Give a judge only that array entry. Do not
give any judge the bundle, another packet, the key, candidate text, authoring history, or another
judge's output. Treatment positions are counterbalanced across judges for every trial.

## Version 2 judge instruction

Give each judge its generated packet and this instruction:

> Judge each anonymous run only against the frozen input, expected behavior, rubric, deterministic
> grader description or retained result, and critical failures. Review both the complete transcript
> and final outcome. Do not guess which run used a skill. For every criterion and run, give a numeric
> score, a short reason, and an evidence_quote copied exactly from that answer's transcript, outcome,
> or deterministic grader details. Mark the winner implied by weighted scores; exact equality requires
> tie. Report only critical failures from the frozen taxonomy and do not average or vote one away. Return JSON matching
> the schema below and no prose outside it.

## Version 2 combined judge output

Collect each independent response unchanged under judgments:

    {
      "version": 2,
      "judgments": [
        {
          "judge_id": "judge-1",
          "comparisons": [
            {
              "comparison_id": "heldout-edge-case::trial-1",
              "winner": "A",
              "scores": {
                "A": {
                  "accuracy": {"score": 5, "reason": "Explains the evidence", "evidence_quote": "Exact substring from answer A"},
                  "clarity": {"score": 4, "reason": "Explains the evidence", "evidence_quote": "Exact substring from answer A"}
                },
                "B": {
                  "accuracy": {"score": 3, "reason": "Explains the evidence", "evidence_quote": "Exact substring from answer B"},
                  "clarity": {"score": 4, "reason": "Explains the evidence", "evidence_quote": "Exact substring from answer B"}
                }
              },
              "critical_failures": {"A": [], "B": []}
            }
          ]
        },
        {
          "judge_id": "judge-2",
          "comparisons": ["Every comparison from judge-2's packet, using the same object schema"]
        }
      ]
    }

Every judge must score every comparison exactly once. Scores are normalized by each criterion's
maximum and then weighted. The decision reports development and heldout score dispersion, case
wins, and per-judge/pairwise agreement. The keep gate uses heldout aggregates only. The treatment
critical-failure gate is a strict union: one heldout failure from one judge is sufficient to retire.
Failure strings must exactly match the frozen critical_failures taxonomy. The helper also verifies
that each evidence_quote occurs in the matching anonymous run and that winner matches the weighted
scores, with exact equality requiring tie.

## Version 1 compatibility

Existing version 1 input remains valid:

    {
      "version": 1,
      "title": "Source distinction skill",
      "rubric": [
        {"id": "accuracy", "label": "Factual accuracy", "weight": 2, "max_score": 5, "core": true}
      ],
      "critical_failures": ["Invents a source"],
      "gate": {"minimum_overall_delta": 5},
      "cases": [
        {
          "id": "case-1",
          "input": "The frozen user request",
          "expected": "The behavior expected from a good answer",
          "baseline": "Verbatim no-skill output",
          "treatment": "Verbatim candidate-skill output"
        }
      ]
    }

The version 1 packet, judgment (version 1 with a pairs array), scoring, and decision schema are
unchanged. Use it only to reproduce or finish an existing v1 evaluation; use v2 for new work.
