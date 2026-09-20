import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("eval_gate", ROOT / "scripts/eval_gate.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def sample():
    return {
        "version": 1, "title": "Test",
        "rubric": [
            {"id": "correct", "label": "Correct", "weight": 2, "max_score": 5, "core": True},
            {"id": "clear", "label": "Clear", "weight": 1, "max_score": 5, "core": False},
        ],
        "critical_failures": ["Fabrication"], "gate": {"minimum_overall_delta": 5},
        "cases": [
            {"id": "one", "input": "Do the task", "expected": "Correct and clear", "baseline": "base one", "treatment": "skill one"},
            {"id": "two", "input": "Do another task", "expected": "Correct and clear", "baseline": "base two", "treatment": "skill two"},
        ],
    }


def judgment(packet, key, treatment_score=5, baseline_score=3, critical=False):
    labels = {p["case_id"]: p["treatment_label"] for p in key["pairs"]}
    pairs = []
    for pair in packet["pairs"]:
        treatment = labels[pair["case_id"]]
        baseline = "B" if treatment == "A" else "A"
        scores = {}
        for label, value in ((treatment, treatment_score), (baseline, baseline_score)):
            scores[label] = {r["id"]: {"score": value, "reason": f"quoted evidence for {label}"} for r in packet["rubric"]}
        pairs.append({
            "case_id": pair["case_id"], "winner": treatment if treatment_score > baseline_score else "tie",
            "scores": scores,
            "critical_failures": {treatment: ["Fabrication"] if critical else [], baseline: []},
        })
    return {"version": 1, "pairs": pairs}


class EvalGateTests(unittest.TestCase):
    def test_prepare_blinds_and_hashes(self):
        packet, key = MOD.prepare(sample(), "fixed")
        self.assertNotIn("treatment", packet["judge_instruction"].lower())
        self.assertNotIn("baseline", packet["judge_instruction"].lower())
        for pair in packet["pairs"]:
            self.assertNotIn("treatment", pair)
            self.assertNotIn("baseline", pair)
        self.assertEqual(key["packet_hash"], MOD.digest(packet))
        self.assertEqual({a["label"] for a in packet["pairs"][0]["answers"]}, {"A", "B"})

    def test_clear_improvement_is_kept(self):
        packet, key = MOD.prepare(sample(), "fixed")
        result = MOD.decide(packet, key, judgment(packet, key))
        self.assertEqual(result["decision"], "keep")
        self.assertGreater(result["treatment_delta"], 5)

    def test_tie_is_retired(self):
        packet, key = MOD.prepare(sample(), "fixed")
        result = MOD.decide(packet, key, judgment(packet, key, 4, 4))
        self.assertEqual(result["decision"], "retire")
        self.assertIn("treatment did not win more cases than baseline", result["reasons"])

    def test_perfect_core_tie_can_pass_when_another_core_improves(self):
        packet, key = MOD.prepare(sample(), "fixed")
        value = judgment(packet, key, 5, 4)
        for pair in value["pairs"]:
            treatment = {p["case_id"]: p["treatment_label"] for p in key["pairs"]}[pair["case_id"]]
            baseline = "B" if treatment == "A" else "A"
            pair["scores"][baseline]["clear"]["score"] = 5
            pair["scores"][treatment]["clear"]["score"] = 5
        result = MOD.decide(packet, key, value)
        self.assertEqual(result["decision"], "keep")

    def test_any_core_regression_is_retired(self):
        packet, key = MOD.prepare(sample(), "fixed")
        value = judgment(packet, key, 5, 4)
        for pair in value["pairs"]:
            treatment = {p["case_id"]: p["treatment_label"] for p in key["pairs"]}[pair["case_id"]]
            baseline = "B" if treatment == "A" else "A"
            pair["scores"][baseline]["correct"]["score"] = 5
            pair["scores"][treatment]["correct"]["score"] = 4
        result = MOD.decide(packet, key, value)
        self.assertEqual(result["decision"], "retire")
        self.assertIn("one or more core criteria regressed", result["reasons"])

    def test_critical_failure_is_retired(self):
        packet, key = MOD.prepare(sample(), "fixed")
        result = MOD.decide(packet, key, judgment(packet, key, critical=True))
        self.assertEqual(result["decision"], "retire")
        self.assertIn("treatment has critical failures", result["reasons"])

    def test_incomplete_judgment_is_rejected(self):
        packet, key = MOD.prepare(sample(), "fixed")
        value = judgment(packet, key)
        value["pairs"].pop()
        with self.assertRaises(MOD.Invalid):
            MOD.decide(packet, key, value)

    def test_write_new_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            MOD.write_new(path, {"ok": True})
            with self.assertRaises(MOD.Invalid):
                MOD.write_new(path, {"ok": False})


if __name__ == "__main__":
    unittest.main()
