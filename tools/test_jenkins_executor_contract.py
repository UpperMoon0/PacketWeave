"""Ensure PacketWeave selects actual qualified Kaggle Linux fleet labels."""
from pathlib import Path
import unittest


class JenkinsExecutorContractTests(unittest.TestCase):
    def test_portable_general_linux_worker_is_explicit(self):
        jenkinsfile = (Path(__file__).resolve().parents[1] / "Jenkinsfile").read_text()
        self.assertIn("agentLabel: 'ci-role-general && ci-os-linux'", jenkinsfile)
        self.assertIn("nstutGradle(", jenkinsfile)
        self.assertNotIn("ci-linux-container", jenkinsfile)
        self.assertNotIn("ci-memory-large", jenkinsfile)


if __name__ == "__main__":
    unittest.main()
