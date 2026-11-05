"""Real template engineering-policy gates; no network or external dependencies."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/DEV-WORKFLOW-v1.0.md"
AGENTS = ROOT / "AGENTS.md"
WORKFLOW = ROOT / ".github/workflows/ci.yml"
README = ROOT / "README.md"
INIT = ROOT / "tools/mac-init-template-audit.py"


class DevelopmentPolicyGate(unittest.TestCase):
    def test_policy_and_adapters_are_installed(self):
        text = POLICY.read_text(encoding="utf-8")
        summary = AGENTS.read_text(encoding="utf-8")
        self.assertIn("Phase D", text)
        self.assertIn("Phase V", text)
        self.assertIn("Phase R", text)
        self.assertIn("Do **not** run unit, integration, smoke or acceptance tests", text)
        self.assertIn("work-in-progress SOT", text)
        self.assertIn("do not run tests", summary)
        self.assertIn("docs/DEV-WORKFLOW-v1.0.md", summary)
        self.assertIn("docs/DEV-WORKFLOW-v1.0.md", README.read_text(encoding="utf-8"))

    def test_template_ci_excludes_development_branch_push(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        event_block = text.split("\non:\n", 1)[1].split("\njobs:\n", 1)[0]
        self.assertRegex(event_block, r"(?m)^  push:\s*$")
        self.assertRegex(event_block, r"(?m)^  pull_request:\s*$")
        self.assertRegex(event_block, r"(?m)^  workflow_dispatch:\s*$")
        self.assertEqual(re.findall(r"(?m)^    branches:\s*(.*)$", event_block),
                         ["[main]", "[main]"])
        self.assertNotRegex(event_block, r"(?i)feat/|feature/|fix/|research/|\*\*")

    def test_scaffold_ci_invokes_real_policy_contract_test(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = (ROOT / ".github/project-tests.sh").read_text(encoding="utf-8")
        self.assertIn("bash .github/project-tests.sh", workflow)
        self.assertIn("python3 -m unittest discover -s tests -v", script)

    def test_legacy_bootstrap_cannot_write_to_github(self):
        script = INIT.read_text(encoding="utf-8")
        self.assertIn("TEMPLATE_AUDIT_ONLY", script)
        self.assertNotIn("git push", script)
        self.assertNotIn('"--method", "PUT"', script)
        self.assertNotIn("repos/{REPO}/contents/{path}", script.split("def main",1)[1])


if __name__ == "__main__":
    unittest.main()
