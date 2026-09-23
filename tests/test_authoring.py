import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lint = load("lint_skill")
inventory = load("inventory")


def write_skill(root: Path, name: str, frontmatter: str, body: str = "# Skill\n") -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")
    return folder


class FrontmatterTests(unittest.TestCase):
    def test_folded_block_scalar_joins_lines(self):
        fields, body = lint.parse_frontmatter("---\nname: demo\ndescription: >-\n  one\n  two\n---\nbody\n")
        self.assertEqual({"name": "demo", "description": "one two"}, fields)
        self.assertEqual("body", body)

    def test_unclosed_frontmatter_is_rejected(self):
        with self.assertRaises(ValueError):
            lint.parse_frontmatter("---\nname: demo\n")


class LintTests(unittest.TestCase):
    def test_this_skill_passes_its_own_lint(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "skillsmith"
            installed.symlink_to(ROOT)
            errors, warnings = lint.lint(installed)
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_good_skill_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_skill(
                Path(directory),
                "fix-flaky-tests",
                "name: fix-flaky-tests\ndescription: Use when a test fails intermittently; not for deterministic failures.",
            )
            self.assertEqual(([], []), lint.lint(folder))

    def test_hard_rules_are_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_skill(
                Path(directory),
                "demo",
                "name: Demo_Skill\ndescription: Use for <thing>.",
                "See [missing](references/missing.md).\n" + "line\n" * 501,
            )
            errors, _ = lint.lint(folder)
        joined = "\n".join(errors)
        self.assertIn("lowercase letters", joined)
        self.assertIn("angle brackets", joined)
        self.assertIn("broken link", joined)
        self.assertIn("body is", joined)

    def test_name_must_match_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_skill(Path(directory), "folder", "name: other\ndescription: Use for x; not y.")
            errors, _ = lint.lint(folder)
        self.assertIn("does not match folder", errors[0])

    def test_weak_trigger_and_policy_mismatch_warn(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_skill(Path(directory), "demo", "name: demo\ndescription: A helpful helper.")
            (folder / "agents").mkdir()
            (folder / "agents" / "openai.yaml").write_text(
                "policy:\n  allow_implicit_invocation: false\n", encoding="utf-8"
            )
            errors, warnings = lint.lint(folder)
        self.assertEqual([], errors)
        joined = "\n".join(warnings)
        self.assertIn("reads as a summary", joined)
        self.assertIn("near-miss", joined)
        self.assertIn("explicit-only", joined)


class InventoryTests(unittest.TestCase):
    def test_collects_repo_skills_once_and_ranks_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            skills = repo / ".claude" / "skills"
            write_skill(skills, "write-email", "name: write-email\ndescription: Draft and polish email replies.")
            write_skill(skills, "trip-planner", "name: trip-planner\ndescription: Plan trips and itineraries.")
            (repo / ".agents").mkdir()
            (repo / ".agents" / "skills").symlink_to(skills)
            (repo / "AGENTS.md").write_text("# Manual\n", encoding="utf-8")
            for nested in ("docs", ".cache/fixture", "node_modules/pkg"):
                (repo / nested).mkdir(parents=True)
                (repo / nested / "AGENTS.md").write_text("# Nested\n", encoding="utf-8")
            found, manuals = inventory.collect(repo, include_global=False, home=repo)
            ranked = inventory.rank(found, "polish an email reply")
        self.assertEqual(["AGENTS.md", "docs/AGENTS.md"], manuals)
        self.assertEqual(2, len(found))
        self.assertEqual("write-email", ranked[0]["name"])
        self.assertGreater(ranked[0]["overlap"], ranked[1]["overlap"])
        self.assertIn("email", ranked[0]["shared_terms"])
        self.assertEqual(0.0, ranked[1]["overlap"])


if __name__ == "__main__":
    unittest.main()
