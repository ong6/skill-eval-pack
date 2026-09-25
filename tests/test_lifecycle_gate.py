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

    def decision(self, name, value, candidate_hash="6" * 64, baseline="absent", prompt_set=None):
        path = self.root / name
        evidence = {}
        decision = {"decision": value}
        if value in ("keep", "retire"):
            from test_eval_gate import gate as evaluator, v3_input, judgment_for
            data = v3_input()
            data["condition_manifest"]["treatment_skill_sha256"] = candidate_hash
            data["condition_manifest"]["baseline_skill"] = baseline
            for client in data["client_coverage"].values():
                client["skill_sha256"] = candidate_hash
            for case in data["cases"]:
                case["input"] += " [" + (prompt_set or name) + "]"
                for trial in case["trials"]:
                    trial["treatment"]["provenance"]["skill_sha256"] = candidate_hash
                    trial["baseline"]["provenance"]["skill_sha256"] = baseline["sha256"] if isinstance(baseline, dict) else None
            packet, key = evaluator.prepare(data, "lifecycle-test")
            judgment = judgment_for(packet, key)
            if value == "retire":
                mapping = next(item for item in key["mappings"] if item["judge_id"] == "judge-1" and item["split"] == "heldout")
                comparison = next(item for item in judgment["judgments"][0]["comparisons"]
                                  if item["comparison_id"] == mapping["comparison_id"])
                comparison["critical_failures"][mapping["treatment_label"]] = ["Unsafe action"]
            decision = evaluator.decide(packet, key, judgment)
            for kind, content in (("packet", packet), ("key", key), ("judgment", judgment)):
                artifact = self.root / (path.stem + "-" + kind + ".json")
                artifact.write_text(json.dumps(content), encoding="utf-8")
                evidence[kind + "_artifact"] = artifact.name
                evidence[kind + "_sha256"] = sha(artifact)
        path.write_text(json.dumps(decision), encoding="utf-8")
        return {"decision_artifact": name, "decision_sha256": sha(path), **evidence}

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
                **self.decision(f"decision-{index}.json", decision, f"{index:064x}",
                                "absent" if kind == "new" else
                                {"mode": "prior_version", "version": "git:abc", "sha256": "f" * 64}),
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
        manifest = self.manifest(("keep",))
        decision.write_bytes((self.root / "decision-1.json").read_bytes())
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

    def test_decision_symlink_cannot_escape_evidence_root(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "decision.json"
            target.write_text(json.dumps({"decision": "keep"}), encoding="utf-8")
            (self.root / "escape.json").symlink_to(target)
            manifest = self.manifest(("keep",))
            manifest["attempts"][0].update(decision_artifact="escape.json", decision_sha256=sha(target))
            with self.assertRaisesRegex(gate.Invalid, "evidence root"):
                gate.validate(manifest, self.root)

    def test_boolean_revision_is_not_an_integer_revision(self):
        manifest = self.manifest(("keep",))
        manifest["attempts"][0]["revision"] = True
        with self.assertRaisesRegex(gate.Invalid, "revision"):
            gate.validate(manifest, self.root)

    def test_invalid_evaluation_flag_must_be_boolean(self):
        manifest = self.manifest(("keep",))
        manifest["attempts"][0]["invalid_evaluation"] = "true"
        with self.assertRaisesRegex(gate.Invalid, "invalid_evaluation"):
            gate.validate(manifest, self.root)

    def test_keep_decision_cannot_have_failure_reasons(self):
        manifest = self.manifest(("keep",))
        path = self.root / "decision-1.json"
        path.write_text(json.dumps({"decision": "keep", "reasons": ["heldout critical failure"]}), encoding="utf-8")
        manifest["attempts"][0]["decision_sha256"] = sha(path)
        with self.assertRaisesRegex(gate.Invalid, "keep.*reasons"):
            gate.validate(manifest, self.root)

    def test_candidate_hash_must_match_retained_v3_runner_evidence(self):
        manifest = self.manifest(("keep",))
        manifest["attempts"][0]["candidate_sha256"] = "f" * 64
        with self.assertRaisesRegex(gate.Invalid, "candidate_sha256"):
            gate.validate(manifest, self.root)
        manifest["attempts"][0]["candidate_sha256"] = f"{1:064x}"
        self.assertEqual("activate_candidate", gate.validate(manifest, self.root)["terminal_action"])

    def test_minimal_and_legacy_keeps_cannot_activate(self):
        for version in (None, 1, 2):
            manifest = self.manifest(("keep",))
            path = self.root / "decision-1.json"
            decision = {"decision": "keep"}
            if version is not None:
                decision["version"] = version
            path.write_text(json.dumps(decision), encoding="utf-8")
            manifest["attempts"][0]["decision_sha256"] = sha(path)
            with self.assertRaisesRegex(gate.Invalid, "current v3 decision"):
                gate.validate(manifest, self.root)

    def test_keep_requires_all_replay_artifacts(self):
        manifest = self.manifest(("keep",))
        manifest["attempts"][0].pop("judgment_artifact")
        with self.assertRaisesRegex(gate.Invalid, "judgment_artifact"):
            gate.validate(manifest, self.root)

    def test_replay_rejects_edited_keep_report_with_rehashed_file(self):
        manifest = self.manifest(("keep",))
        path = self.root / "decision-1.json"
        decision = json.loads(path.read_text(encoding="utf-8"))
        decision["treatment_delta"] = 99
        path.write_text(json.dumps(decision), encoding="utf-8")
        manifest["attempts"][0]["decision_sha256"] = sha(path)
        with self.assertRaisesRegex(gate.Invalid, "does not match a replayed"):
            gate.validate(manifest, self.root)

    def test_replay_rejects_critical_failure_hidden_by_keep_report(self):
        manifest = self.manifest(("keep",))
        path = self.root / "decision-1-judgment.json"
        judgment = json.loads(path.read_text(encoding="utf-8"))
        key = json.loads((self.root / "decision-1-key.json").read_text(encoding="utf-8"))
        mapping = next(item for item in key["mappings"] if item["judge_id"] == "judge-1" and item["split"] == "heldout")
        comparison = next(item for item in judgment["judgments"][0]["comparisons"]
                          if item["comparison_id"] == mapping["comparison_id"])
        comparison["critical_failures"][mapping["treatment_label"]] = ["Unsafe action"]
        path.write_text(json.dumps(judgment), encoding="utf-8")
        manifest["attempts"][0]["judgment_sha256"] = sha(path)
        with self.assertRaisesRegex(gate.Invalid, "does not match a replayed"):
            gate.validate(manifest, self.root)

    def test_decision_json_rejects_duplicate_fields(self):
        manifest = self.manifest(("keep",))
        path = self.root / "decision-1.json"
        path.write_text('{"decision":"retire","decision":"keep"}', encoding="utf-8")
        manifest["attempts"][0]["decision_sha256"] = sha(path)
        with self.assertRaisesRegex(gate.Invalid, "duplicate"):
            gate.validate(manifest, self.root)

    def test_existing_revision_requires_matching_proven_baseline(self):
        manifest = self.manifest(("keep",), kind="existing_revision")
        self.assertEqual("activate_candidate", gate.validate(manifest, self.root)["terminal_action"])
        manifest["last_proven_sha256"] = "e" * 64
        with self.assertRaisesRegex(gate.Invalid, "baseline_skill"):
            gate.validate(manifest, self.root)

    def test_existing_revision_cannot_activate_against_no_skill(self):
        manifest = self.manifest(("keep",))
        manifest.update(candidate_kind="existing_revision", last_proven_version="git:abc", last_proven_sha256="f" * 64)
        with self.assertRaisesRegex(gate.Invalid, "baseline_skill"):
            gate.validate(manifest, self.root)

    def test_replayed_history_rejects_renamed_exposed_heldouts(self):
        from test_eval_gate import gate as evaluator
        manifest = self.manifest(("keep",))
        first = manifest["attempts"][0]
        packet = json.loads((self.root / first["packet_artifact"]).read_text(encoding="utf-8"))
        key = json.loads((self.root / first["key_artifact"]).read_text(encoding="utf-8"))
        judgment_path = self.root / first["judgment_artifact"]
        judgment = json.loads(judgment_path.read_text(encoding="utf-8"))
        mapping = next(item for item in key["mappings"] if item["judge_id"] == "judge-1" and item["split"] == "heldout")
        comparison = next(item for item in judgment["judgments"][0]["comparisons"]
                          if item["comparison_id"] == mapping["comparison_id"])
        comparison["critical_failures"][mapping["treatment_label"]] = ["Unsafe action"]
        judgment_path.write_text(json.dumps(judgment), encoding="utf-8")
        decision_path = self.root / first["decision_artifact"]
        decision_path.write_text(json.dumps(evaluator.decide(packet, key, judgment)), encoding="utf-8")
        first.update(judgment_sha256=sha(judgment_path), decision_sha256=sha(decision_path), heldout_retired=True)
        manifest["attempts"].append({
            "revision": 2, "candidate_sha256": f"{2:064x}", "development_evidence": ["dev-2"],
            "change": "Fix observed behavior", "heldout_set": "renamed-heldouts", "heldout_retired": False,
            **self.decision("decision-2.json", "keep", f"{2:064x}", prompt_set="decision-1.json"),
        })
        with self.assertRaisesRegex(gate.Invalid, "heldout inputs reuse exposed cases"):
            gate.validate(manifest, self.root)

    def test_invalid_prior_attempt_still_exposes_its_retained_prompts(self):
        manifest = self.manifest(("retire", "keep"))
        manifest["attempts"][0].update(invalid_evaluation=True, invalid_reason="contaminated judge")
        manifest["attempts"][1].update(self.decision("decision-2.json", "keep", f"{2:064x}", prompt_set="decision-1.json"))
        with self.assertRaisesRegex(gate.Invalid, "heldout inputs reuse exposed cases"):
            gate.validate(manifest, self.root)

    def test_current_retire_cannot_omit_replay_evidence(self):
        manifest = self.manifest(("retire", "keep"))
        for kind in ("packet", "key", "judgment"):
            manifest["attempts"][0].pop(kind + "_artifact")
            manifest["attempts"][0].pop(kind + "_sha256")
        with self.assertRaisesRegex(gate.Invalid, "packet_artifact"):
            gate.validate(manifest, self.root)

    def test_unknown_invalid_exposure_blocks_later_activation(self):
        manifest = self.manifest(("retire", "keep"))
        manifest["attempts"][0].update(invalid_evaluation=True, invalid_reason="missing packet")
        manifest["attempts"][0].pop("packet_artifact")
        with self.assertRaisesRegex(gate.Invalid, "unavailable exposure evidence"):
            gate.validate(manifest, self.root)

    def test_legacy_retire_remains_readable_but_cannot_prove_later_freshness(self):
        manifest = self.manifest(("retire", "keep"))
        first = manifest["attempts"][0]
        for kind in ("packet", "key", "judgment"):
            first.pop(kind + "_artifact")
            first.pop(kind + "_sha256")
        path = self.root / first["decision_artifact"]
        path.write_text(json.dumps({"version": 2, "decision": "retire"}), encoding="utf-8")
        first["decision_sha256"] = sha(path)
        with self.assertRaisesRegex(gate.Invalid, "unavailable exposure evidence"):
            gate.validate(manifest, self.root)
        manifest["attempts"].pop()
        manifest["terminal_action"] = "continue"
        self.assertEqual("continue", gate.validate(manifest, self.root)["terminal_action"])


if __name__ == "__main__":
    unittest.main()
