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


if __name__ == "__main__":
    unittest.main()
