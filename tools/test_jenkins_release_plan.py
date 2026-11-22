"""Release dry-run pipeline must preserve all native targets without publishing."""
import json
from pathlib import Path
import tempfile
import unittest

import jenkins_release_plan as release_plan
import jenkins_plan


class ReleasePlanTests(unittest.TestCase):
    def test_release_stage_extends_every_ci_target(self):
        ci = jenkins_plan.plan()
        release = release_plan.plan()
        self.assertEqual(len(ci) + 1, len(release))
        self.assertEqual(ci, release[:-1])
        self.assertEqual(12, len(ci))
        self.assertEqual(17, release[-1]["java"])
        self.assertEqual("python3 tools/jenkins_release_dryrun.py", release[-1]["command"])
        self.assertNotIn("publish", release[-1]["command"])

    def test_release_plan_json_can_be_serialized(self):
        result = json.loads(json.dumps(release_plan.plan()))
        self.assertEqual(13, len(result))
        self.assertEqual(len(result), len({part["name"] for part in result}))

    def test_release_job_is_readonly_general_linux(self):
        code = (Path(__file__).resolve().parents[1] / "Jenkinsfile.release").read_text()
        self.assertIn("agentLabel: 'ci-role-general && ci-os-linux && (cloud-1-linux-ci || on-prem-1-linux-ci)'", code)
        self.assertIn("branch: 'main'", code)
        self.assertIn("tools/jenkins_release_plan.py", code)
        self.assertIn("dist/release-manifest.json", code)
        self.assertIn("tools/jenkins_artifacts.py evidence", code)
        self.assertNotIn("CURSEFORGE_API_TOKEN", code)
        self.assertNotIn("GITHUB_TOKEN", code)
        self.assertNotIn("workflow_call", code)

    def test_offline_dryrun_declines_existing_dist(self):
        from jenkins_release_dryrun import offline_bundle
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'dist').mkdir()
            with self.assertRaisesRegex(ValueError, "dist must not already exist"):
                offline_bundle(root,root/'dist')


if __name__ == "__main__":
    unittest.main()
