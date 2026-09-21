import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "lifecycle_gate.py"
SPEC = importlib.util.spec_from_file_location("lifecycle_gate", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LifecycleGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def decision(self, name, value):
        path = self.root / name
        path.write_text(json.dumps({"decision": value}), encoding="utf-8")
        return {"decision_artifact": name, "decision_sha256": sha(path)}

    def manifest(self, decisions=("retire", "retire", "retire"), kind="new"):
        attempts = []
        for index, decision in enumerate(decisions, 1):
            attempts.append({
                "revision": index,
                "candidate_sha256": f"{index:064x}",
                "development_evidence": [] if index == 1 else [f"dev-{index}"],
                "change": "initial candidate" if index == 1 else f"fix from dev-{index}",
                "heldout_set": f"heldout-{index}",
                "heldout_retired": decision == "retire",
                **self.decision(f"decision-{index}.json", decision),
            })
        terminal = ("activate_candidate" if decisions[-1] == "keep" else
                    "archive_candidate" if len(decisions) == 3 and kind == "new" else
                    "restore_last_proven" if len(decisions) == 3 else "continue")
        result = {
            "version": 1, "candidate_kind": kind,
            "maximum_serious_revisions": 3, "attempts": attempts,
            "terminal_action": terminal,
        }
        if kind == "existing_revision":
            result.update(last_proven_version="git:abc", last_proven_sha256="f" * 64)
        return result

    def test_exhausted_new_candidate_archives(self):
        result = gate.validate(self.manifest(), self.root)
        self.assertEqual("archive_candidate", result["terminal_action"])

    def test_exhausted_existing_revision_restores(self):
        result = gate.validate(self.manifest(kind="existing_revision"), self.root)
        self.assertEqual("restore_last_proven", result["terminal_action"])

    def test_pass_stops_and_activates(self):
        result = gate.validate(self.manifest(("retire", "keep")), self.root)
        self.assertEqual("activate_candidate", result["terminal_action"])

    def test_failed_heldout_must_be_retired(self):
        manifest = self.manifest(("retire",))
        manifest["attempts"][0]["heldout_retired"] = False
        with self.assertRaisesRegex(gate.Invalid, "failed heldout_set must be retired"):
            gate.validate(manifest, self.root)

    def test_exposed_heldout_cannot_be_reused(self):
        manifest = self.manifest(("retire", "retire"))
        manifest["attempts"][1]["heldout_set"] = "heldout-1"
        with self.assertRaisesRegex(gate.Invalid, "reuses an exposed heldout_set"):
            gate.validate(manifest, self.root)

    def test_decision_hash_is_verified(self):
        manifest = self.manifest(("retire",))
        manifest["attempts"][0]["decision_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.Invalid, "hash does not match"):
            gate.validate(manifest, self.root)

    def test_basename_decision_may_be_relative_to_manifest_directory(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        decision = bundle / "decision.json"
        decision.write_text(json.dumps({"decision": "keep"}), encoding="utf-8")
        manifest = self.manifest(("keep",))
        manifest["attempts"][0].update(
            decision_artifact="decision.json", decision_sha256=sha(decision)
        )
        result = gate.validate(manifest, self.root, Path("bundle"))
        self.assertEqual("activate_candidate", result["terminal_action"])

    def test_invalid_evaluation_consumes_revision_slot(self):
        manifest = self.manifest(("retire", "retire", "retire"), kind="existing_revision")
        attempt = manifest["attempts"][2]
        attempt.pop("decision_artifact")
        attempt.pop("decision_sha256")
        attempt.update(invalid_evaluation=True, invalid_reason="reused heldout and missing hash")
        result = gate.validate(manifest, self.root)
        self.assertEqual(["retire", "retire", "invalid"], result["decision_sequence"])
        self.assertEqual("restore_last_proven", result["terminal_action"])

    def test_invalid_evaluation_must_retire_heldout(self):
        manifest = self.manifest(("retire",))
        attempt = manifest["attempts"][0]
        attempt.pop("decision_artifact")
        attempt.pop("decision_sha256")
        attempt.update(invalid_evaluation=True, invalid_reason="contaminated", heldout_retired=False)
        with self.assertRaisesRegex(gate.Invalid, "invalid heldout_set must be retired"):
            gate.validate(manifest, self.root)


if __name__ == "__main__":
    unittest.main()
