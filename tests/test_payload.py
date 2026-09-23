import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "check_payload.py"
SPEC = importlib.util.spec_from_file_location("check_payload", SCRIPT)
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class PayloadTests(unittest.TestCase):
    def test_matching_payload_passes_and_drift_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "skillsmith"
            for relative in check.PAYLOAD:
                target = installed / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            self.assertEqual([], check.differences(ROOT, installed))
            (installed / "SKILL.md").write_text("drift", encoding="utf-8")
            self.assertEqual(["payload differs SKILL.md"], check.differences(ROOT, installed))


if __name__ == "__main__":
    unittest.main()
