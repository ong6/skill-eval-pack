import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "eval_gate.py"
SPEC = importlib.util.spec_from_file_location("eval_gate", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)


_context_counter = 0


def native_provenance(prefix="runner"):
    global _context_counter
    _context_counter += 1
    return {
        "mechanism": "host-native-subagent",
        "agent_id": f"{prefix}-{_context_counter}",
        "context_id": f"context-{_context_counter}",
        "fresh_context": True,
        "recursive_ai_cli_spawned": False,
        "details": "Spawned through the host collaboration tool.",
    }


def run(output, graded=False):
    result = {
        "transcript": f"transcript: {output}",
        "outcome": output,
        "provenance": native_provenance(),
    }
    if graded:
        result["grader_result"] = {"passed": True, "details": "PASS: exact result matched"}
    return result


def v2_input(judge_count=2):
    return {
        "version": 2,
        "title": "Candidate evaluation",
        "judge_count": judge_count,
        "execution_policy": {
            "runner_mechanism": "host-native-subagent",
            "judge_mechanism": "host-native-subagent",
            "max_active_agents": 4,
            "recursive_ai_cli_allowed": False,
        },
        "rubric": [
            {"id": "core", "label": "Core behavior", "weight": 2, "max_score": 5, "core": True},
            {"id": "quality", "label": "Quality", "weight": 1, "max_score": 5, "core": False},
        ],
        "critical_failures": ["Unsafe action"],
        "gate": {"minimum_overall_delta": 5},
        "cases": [
            {
                "id": "dev-positive", "split": "development", "input": "Do the task",
                "expected": "Correct result", "stochastic": False,
                "deterministic_grader": "Check exact result",
                "trials": [{"id": "trial-1", "baseline": run("base-dev", True), "treatment": run("treat-dev", True)}],
            },
            {
                "id": "held-negative", "split": "heldout", "input": "Unrelated task",
                "expected": "Do not apply candidate behavior", "stochastic": True,
                "trials": [
                    {"id": "trial-1", "baseline": run("base-held-1"), "treatment": run("treat-held-1")},
                    {"id": "trial-2", "baseline": run("base-held-2"), "treatment": run("treat-held-2")},
                ],
            },
            {
                "id": "held-positive", "split": "heldout", "input": "Fresh relevant task",
                "expected": "Apply candidate behavior", "stochastic": False,
                "trials": [{"id": "trial-1", "baseline": run("base-held-positive"),
                            "treatment": run("treat-held-positive")}],
            },
        ],
    }


def judgment_for(packet, key, scores=None, failures=None):
    scores = scores or {}
    failures = failures or {}
    mapping = {(item["judge_id"], item["comparison_id"]): item for item in key["mappings"]}
    judgments = []
    for judge_packet in packet["judge_packets"]:
        judge_id = judge_packet["judge_id"]
        comparisons = []
        for item in judge_packet["comparisons"]:
            comparison_id = item["comparison_id"]
            item_mapping = mapping[(judge_id, comparison_id)]
            treatment_label = item_mapping["treatment_label"]
            baseline_label = "B" if treatment_label == "A" else "A"
            values = scores.get(comparison_id, {"baseline": (3, 3), "treatment": (5, 5)})
            by_label = {baseline_label: values["baseline"], treatment_label: values["treatment"]}
            weighted = {
                label: (by_label[label][0] * 2 + by_label[label][1]) / 3
                for label in ("A", "B")
            }
            winner = "A" if weighted["A"] > weighted["B"] else "B" if weighted["B"] > weighted["A"] else "tie"
            answers = {answer["label"]: answer for answer in item["answers"]}
            comparisons.append({
                "comparison_id": comparison_id,
                "winner": winner,
                "scores": {
                    label: {
                        "core": {"score": by_label[label][0], "reason": f"evidence for {label}",
                                 "evidence_quote": answers[label]["outcome"]},
                        "quality": {"score": by_label[label][1], "reason": f"evidence for {label}",
                                    "evidence_quote": answers[label]["transcript"]},
                    } for label in ("A", "B")
                },
                "critical_failures": {
                    label: failures.get((judge_id, comparison_id, item_mapping["split"],
                                         "treatment" if label == treatment_label else "baseline"), [])
                    for label in ("A", "B")
                },
            })
        judgments.append({
            "judge_id": judge_id,
            "provenance": native_provenance("judge"),
            "comparisons": comparisons,
        })
    return {"version": 2, "judgments": judgments}


class V2Tests(unittest.TestCase):
    def test_position_is_counterbalanced_and_runs_include_transcript_and_outcome(self):
        packet, key = gate.prepare(v2_input(judge_count=3), "fixed-seed")
        labels = {}
        for item in key["mappings"]:
            labels.setdefault(item["comparison_id"], []).append(item["treatment_label"])
        for positions in labels.values():
            self.assertLessEqual(abs(positions.count("A") - positions.count("B")), 1)
            self.assertEqual({"A", "B"}, set(positions))
        first = packet["judge_packets"][0]["comparisons"][0]["answers"][0]
        self.assertIn("transcript", first)
        self.assertIn("outcome", first)
        self.assertIn("grader_result", first)
        self.assertNotIn("provenance", first)
        self.assertEqual("host-native-subagent", key["runner_provenance"][0]["baseline"]["mechanism"])

    def test_recursive_cli_runner_provenance_is_rejected(self):
        data = v2_input()
        provenance = data["cases"][0]["trials"][0]["baseline"]["provenance"]
        provenance["mechanism"] = "codex-exec"
        provenance["recursive_ai_cli_spawned"] = True
        with self.assertRaisesRegex(gate.Invalid, "mechanism must be host-native-subagent"):
            gate.prepare(data, "seed")

    def test_wrong_or_missing_execution_policy_is_rejected(self):
        data = v2_input()
        data["execution_policy"]["max_active_agents"] = 16
        with self.assertRaisesRegex(gate.Invalid, "execution_policy must equal"):
            gate.prepare(data, "seed")

    def test_judge_provenance_must_be_native_and_fresh(self):
        packet, key = gate.prepare(v2_input(), "seed")
        judgment = judgment_for(packet, key)
        judgment["judgments"][0]["provenance"]["mechanism"] = "claude-print"
        with self.assertRaisesRegex(gate.Invalid, "mechanism must be host-native-subagent"):
            gate.decide(packet, key, judgment)

        judgment = judgment_for(packet, key)
        judgment["judgments"][0]["provenance"]["context_id"] = (
            key["runner_provenance"][0]["baseline"]["context_id"]
        )
        with self.assertRaisesRegex(gate.Invalid, "fresh and unique"):
            gate.decide(packet, key, judgment)

    def test_heldout_only_gate_ignores_bad_development_results(self):
        packet, key = gate.prepare(v2_input(), "seed")
        scores = {
            "dev-positive::trial-1": {"baseline": (5, 5), "treatment": (0, 0)},
            "held-negative::trial-1": {"baseline": (2, 2), "treatment": (5, 5)},
            "held-negative::trial-2": {"baseline": (2, 2), "treatment": (5, 5)},
            "held-positive::trial-1": {"baseline": (2, 2), "treatment": (5, 5)},
        }
        result = gate.decide(packet, key, judgment_for(packet, key, scores))
        self.assertEqual("keep", result["decision"])
        self.assertEqual("host-native-subagent", result["execution_provenance"]["policy"]["runner_mechanism"])
        self.assertEqual("heldout_only", result["gate_scope"])
        self.assertEqual(0, result["development_case_wins"]["treatment"])
        self.assertGreater(result["score_dispersion"]["heldout"]["treatment"]["stdev"], -1)
        self.assertIn("per_judge", result["judge_agreement"])

    def test_core_regression_retires_even_when_total_improves(self):
        data = v2_input()
        data["rubric"][0]["weight"] = 1
        data["rubric"][1]["weight"] = 4
        packet, key = gate.prepare(data, "seed")
        scores = {
            comparison_id: {"baseline": (5, 1), "treatment": (4, 5)}
            for comparison_id in (
                "dev-positive::trial-1", "held-negative::trial-1", "held-negative::trial-2",
                "held-positive::trial-1",
            )
        }
        result = gate.decide(packet, key, judgment_for(packet, key, scores))
        self.assertEqual("retire", result["decision"])
        self.assertIn("one or more heldout core criteria regressed", result["reasons"])

    def test_any_judge_critical_failure_retires_and_union_deduplicates(self):
        packet, key = gate.prepare(v2_input(), "seed")
        target = "held-negative::trial-1"
        failures = {
            ("judge-1", target, "heldout", "treatment"): ["Unsafe action"],
            ("judge-2", target, "heldout", "treatment"): ["Unsafe action"],
        }
        result = gate.decide(packet, key, judgment_for(packet, key, failures=failures))
        self.assertEqual("retire", result["decision"])
        union = result["critical_failures"]["heldout"]["treatment"]
        self.assertEqual(1, len(union))
        self.assertEqual(["judge-1", "judge-2"], union[0]["judges"])

    def test_stochastic_case_requires_multiple_trials(self):
        data = v2_input()
        data["cases"][1]["trials"] = data["cases"][1]["trials"][:1]
        with self.assertRaisesRegex(gate.Invalid, "requires at least two trials"):
            gate.prepare(data, "seed")

    def test_declared_deterministic_grader_requires_results(self):
        data = v2_input()
        del data["cases"][0]["trials"][0]["baseline"]["grader_result"]
        with self.assertRaisesRegex(gate.Invalid, "grader_result"):
            gate.prepare(data, "seed")

    def test_heldout_split_is_required_but_trigger_tests_are_optional(self):
        data = v2_input()
        data["cases"][1]["split"] = "development"
        data["cases"][2]["split"] = "development"
        with self.assertRaisesRegex(gate.Invalid, "both development and heldout"):
            gate.prepare(data, "seed")
        packet, key = gate.prepare(v2_input(), "seed")
        self.assertNotIn("trigger_tests", packet)
        self.assertEqual([], key["trigger_tests"])

    def test_heldout_trigger_failure_retires_when_optional_tests_are_supplied(self):
        data = v2_input()
        data["trigger_tests"] = [{
            "id": "negative-routing", "split": "heldout", "input": "unrelated request",
            "expected_trigger": False, "observed_trigger": True, "details": "candidate loaded",
        }]
        packet, key = gate.prepare(data, "seed")
        result = gate.decide(packet, key, judgment_for(packet, key))
        self.assertEqual("retire", result["decision"])
        self.assertIn("one or more heldout trigger tests failed", result["reasons"])

    def test_heldout_treatment_deterministic_failure_retires(self):
        data = v2_input()
        case = data["cases"][2]
        case["deterministic_grader"] = "exact check"
        case["trials"][0]["baseline"]["grader_result"] = {"passed": True, "details": "baseline passes"}
        case["trials"][0]["treatment"]["grader_result"] = {"passed": False, "details": "missing required file"}
        packet, key = gate.prepare(data, "seed")
        result = gate.decide(packet, key, judgment_for(packet, key))
        self.assertEqual("retire", result["decision"])
        self.assertIn("treatment has heldout deterministic grader failures", result["reasons"])
        self.assertEqual("missing required file", result["deterministic_grader_failures"]["heldout"]["treatment"][0]["details"])

    def test_unknown_critical_failure_is_rejected(self):
        packet, key = gate.prepare(v2_input(), "seed")
        judgment = judgment_for(packet, key)
        judgment["judgments"][0]["comparisons"][0]["critical_failures"]["A"] = ["Invented category"]
        with self.assertRaisesRegex(gate.Invalid, "outside the frozen taxonomy"):
            gate.decide(packet, key, judgment)

    def test_winner_must_match_weighted_scores_and_equal_scores_require_tie(self):
        packet, key = gate.prepare(v2_input(), "seed")
        judgment = judgment_for(packet, key)
        judgment["judgments"][0]["comparisons"][0]["winner"] = "A" if judgment["judgments"][0]["comparisons"][0]["winner"] != "A" else "B"
        with self.assertRaisesRegex(gate.Invalid, "winner does not agree"):
            gate.decide(packet, key, judgment)
        equal = {comparison["comparison_id"]: {"baseline": (4, 4), "treatment": (4, 4)}
                 for comparison in packet["judge_packets"][0]["comparisons"]}
        judgment = judgment_for(packet, key, equal)
        judgment["judgments"][0]["comparisons"][0]["winner"] = "A"
        with self.assertRaisesRegex(gate.Invalid, "expected tie"):
            gate.decide(packet, key, judgment)

    def test_evidence_quote_must_occur_in_matching_answer(self):
        packet, key = gate.prepare(v2_input(), "seed")
        judgment = judgment_for(packet, key)
        packet_comparison = packet["judge_packets"][0]["comparisons"][0]
        answers = {answer["label"]: answer for answer in packet_comparison["answers"]}
        judgment["judgments"][0]["comparisons"][0]["scores"]["A"]["core"]["evidence_quote"] = answers["B"]["outcome"]
        with self.assertRaisesRegex(gate.Invalid, "does not occur in that answer"):
            gate.decide(packet, key, judgment)

    def test_malformed_judgment_is_rejected(self):
        packet, key = gate.prepare(v2_input(), "seed")
        judgment = judgment_for(packet, key)
        judgment["judgments"][0]["comparisons"].pop()
        with self.assertRaisesRegex(gate.Invalid, "every comparison exactly once"):
            gate.decide(packet, key, judgment)

    def test_malformed_key_metadata_is_rejected(self):
        packet, key = gate.prepare(v2_input(), "seed")
        key["mappings"][0]["split"] = "heldout"
        with self.assertRaisesRegex(gate.Invalid, "metadata does not match"):
            gate.decide(packet, key, judgment_for(packet, key))

    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            packet_path = root / "packet.json"
            key_path = root / "key.json"
            input_path.write_text(json.dumps(v2_input()), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), "prepare", "--input", str(input_path),
                       "--packet", str(packet_path), "--key", str(key_path), "--seed", "seed"]
            self.assertEqual(0, subprocess.run(command, capture_output=True).returncode)
            rerun = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(2, rerun.returncode)
            self.assertIn("refusing to overwrite", rerun.stderr)

    def test_cli_decide_refuses_overwrite(self):
        packet, key = gate.prepare(v2_input(), "seed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            key_path = root / "key.json"
            judgment_path = root / "judgment.json"
            output_path = root / "decision.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            key_path.write_text(json.dumps(key), encoding="utf-8")
            judgment_path.write_text(json.dumps(judgment_for(packet, key)), encoding="utf-8")
            output_path.write_text("sentinel", encoding="utf-8")
            command = [sys.executable, str(SCRIPT), "decide", "--packet", str(packet_path),
                       "--key", str(key_path), "--judgment", str(judgment_path),
                       "--output", str(output_path)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertIn("refusing to overwrite", result.stderr)
            self.assertEqual("sentinel", output_path.read_text(encoding="utf-8"))


class V1CompatibilityTests(unittest.TestCase):
    def test_v1_prepare_and_decide_remain_compatible(self):
        data = {
            "version": 1, "title": "Legacy",
            "rubric": [{"id": "core", "label": "Core", "weight": 1, "max_score": 5, "core": True}],
            "critical_failures": [], "gate": {"minimum_overall_delta": 5},
            "cases": [{"id": "one", "input": "request", "expected": "result",
                       "baseline": "old", "treatment": "new"}],
        }
        packet, key = gate.prepare(data, "legacy-seed")
        self.assertEqual(1, packet["version"])
        treatment = key["pairs"][0]["treatment_label"]
        baseline = "B" if treatment == "A" else "A"
        judgment = {
            "version": 1, "pairs": [{
                "case_id": "one", "winner": treatment,
                "scores": {
                    treatment: {"core": {"score": 5, "reason": "new succeeds"}},
                    baseline: {"core": {"score": 2, "reason": "old fails"}},
                },
                "critical_failures": {"A": [], "B": []},
            }]
        }
        result = gate.decide(packet, key, judgment)
        self.assertEqual(1, result["version"])
        self.assertEqual("keep", result["decision"])


if __name__ == "__main__":
    unittest.main()
