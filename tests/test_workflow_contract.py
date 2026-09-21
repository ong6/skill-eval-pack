from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.contract = (ROOT / "references" / "judge-contract.md").read_text(encoding="utf-8")
        cls.skill_flat = " ".join(cls.skill.split())
        cls.contract_flat = " ".join(cls.contract.split())

    def test_default_bound_is_three_serious_revisions(self):
        self.assertIn("at most three serious candidate revisions", self.skill)
        self.assertIn('"maximum_serious_revisions": 3', self.contract)

    def test_failure_uses_development_evidence_before_revision(self):
        self.assertIn("First add or refine development cases that reproduce", self.skill)
        self.assertIn("use the failure to create or refine development coverage before revising", self.contract)

    def test_exposed_heldouts_are_retired_and_replaced(self):
        self.assertIn("mark every exposed heldout and its judge packets retired", self.skill)
        self.assertIn("use an entirely new heldout_set", self.contract)

    def test_new_and_existing_skills_have_different_terminal_actions(self):
        self.assertIn("archive a new skill", self.skill)
        self.assertIn("restore the saved last proven version", self.skill_flat)
        self.assertIn("exhausted + new", self.contract)
        self.assertIn("exhausted + existing_revision", self.contract)

    def test_noisy_scores_stop_the_loop(self):
        self.assertIn("Stop early when the remaining signal is only inconsistent or noisy judge scoring", self.skill)
        self.assertIn("Do not optimize against unexplained score variance", self.contract_flat)

    def test_report_lists_attempted_revisions(self):
        self.assertIn("every attempted revision", self.skill)
        self.assertIn('"attempts": [', self.contract)

    def test_forbids_recursive_agent_clis_and_caps_concurrency(self):
        self.assertIn("Never launch `codex`, `claude`, or another agent CLI", self.skill_flat)
        self.assertIn("at most four evaluation agents active at once", self.skill_flat)
        self.assertIn("host's native subagent tool", self.skill_flat)
        self.assertIn("helper rejects missing, reused, non-native, or recursive-CLI provenance", self.skill_flat)

    def test_v3_requires_receipts_parity_calibration_and_injection_defense(self):
        self.assertIn("A self-attested boolean alone is not current admissible evidence", self.skill_flat)
        self.assertIn("matched condition manifest", self.skill)
        self.assertIn("Calibrate every judge", self.skill_flat)
        self.assertIn("untrusted quoted data", self.skill)
        self.assertIn("minimum_delta_lower_bound", self.contract)

    def test_lifecycle_and_payload_helpers_are_documented(self):
        self.assertIn("scripts/lifecycle_gate.py", self.skill)
        self.assertIn("scripts/check_payload.py", self.skill)


if __name__ == "__main__":
    unittest.main()
