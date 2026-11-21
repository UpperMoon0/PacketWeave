"""No GitHub Actions, inherited shell token or GitHub repository secret may publish."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import publish_curseforge


class ProtectedPublisherEntrypointTests(unittest.TestCase):
    def test_direct_cli_never_calls_provider_even_with_environment_tokens(self):
        with patch.object(sys, "argv", [
            "publish_curseforge.py", "--bundle", "/tmp/no-bundle",
            "--receipt", "/tmp/no-receipt"
        ]), patch.dict(os.environ, {
            "CURSEFORGE_API_TOKEN": "legacy_token_must_not_be_used",
            "CURSEFORGE_PROJECT_ID": "1735096",
            "GH_TOKEN": "legacy_github_token",
            "GITHUB_TOKEN": "legacy_github_token",
            "SOURCE_SHA": "a" * 40,
        }), patch.object(publish_curseforge, "publish",
                         side_effect=AssertionError("unexpected vendor call")):
            with self.assertRaisesRegex(ValueError, "Direct CLI publishing disabled"):
                publish_curseforge.main()

    def test_explicit_publisher_still_requires_protected_credentials(self):
        with self.assertRaisesRegex(ValueError, "protected Key Vault"):
            publish_curseforge.publish(
                Path("/tmp/absent"), Path("/tmp/absent-receipt"),
                "1735096", "", "a" * 40
            )

    def test_only_central_host_can_supply_live_credential(self):
        source = (Path(__file__).resolve().parent / "publish_curseforge.py").read_text()
        self.assertNotIn("os.environ.get", source)
        self.assertNotIn("secrets.CURSEFORGE_API_TOKEN", source)
        self.assertIn("Direct CLI publishing disabled", source)


if __name__ == "__main__":
    unittest.main()
