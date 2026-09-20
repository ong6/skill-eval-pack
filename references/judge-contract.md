# Judge contract

## Evaluation input

Write this before treatment execution. baseline and treatment must be verbatim outputs.

    {
      "version": 1,
      "title": "Source distinction skill",
      "rubric": [
        {"id": "accuracy", "label": "Factual accuracy", "weight": 2, "max_score": 5, "core": true},
        {"id": "clarity", "label": "Clear and concise", "weight": 1, "max_score": 5, "core": false}
      ],
      "critical_failures": ["Invents a source", "Claims execution that did not occur"],
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

## Judge instruction

Give the judge only the generated packet and this instruction:

> Judge each anonymous answer only against the frozen case, expected behavior, rubric anchors, and
> critical failures. Do not guess which answer used a skill. For every criterion and answer, give a
> numeric score and a short reason quoting exact evidence from that answer. Mark a winner of A, B,
> or tie for each case. Report critical failures separately. Return JSON matching the schema below
> and no prose outside it.

## Judge output

    {
      "version": 1,
      "pairs": [
        {
          "case_id": "case-1",
          "winner": "A",
          "scores": {
            "A": {
              "accuracy": {"score": 5, "reason": "Quotes exact evidence here"},
              "clarity": {"score": 4, "reason": "Quotes exact evidence here"}
            },
            "B": {
              "accuracy": {"score": 3, "reason": "Quotes exact evidence here"},
              "clarity": {"score": 4, "reason": "Quotes exact evidence here"}
            }
          },
          "critical_failures": {"A": [], "B": []}
        }
      ]
    }

Scores are normalized by each criterion's max_score, then weighted. The gate checks the aggregate
score, core non-regression with at least one core improvement, case wins, completeness, and critical
failures.
