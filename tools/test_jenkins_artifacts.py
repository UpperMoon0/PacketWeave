"""Native Jenkins evidence and bundle acceptance, including tamper tests."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import jenkins_artifacts as jenkins
import release_contract as release
import test_release_contract as fixtures

SHA = "a" * 40


class JenkinsArtifactTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReleaseTests("test_complete_bundle_has_exact_matrix_checksums_and_source")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archive = Path(self.tmp.name) / "archive"
        self.archive.mkdir()
        self.output = Path(self.tmp.name) / "dist"
        self.version = self.fixture.version
        self.values = release.config()
        self.write_receipt()

    def write_receipt(self):
        (self.archive / jenkins.EVIDENCE_FILE).write_text(json.dumps(
            jenkins.receipt(SHA, self.version, self.values["release_type"])
        ))

    def copy_jars(self):
        for target in ["core", *[item["target"] for item in release.TARGETS]]:
            filename = release.filename(target, self.version)
            src = self.fixture.artifacts / f"packetweave-{target}" / filename
            dest = self.archive / jenkins.expected_archive_jar(target, self.version)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def test_valid_source_receipt_and_full_bundle(self):
        self.copy_jars()
        manifest = jenkins.bundle_archive(self.archive, self.output, SHA, self.values)
        self.assertEqual(SHA, manifest["source_sha"])
        self.assertEqual(12, len(manifest["assets"]))
        self.assertEqual(12, len(list(self.output.glob("*.jar"))))
        self.assertEqual(12, len((self.output / "SHA256SUMS").read_text().splitlines()))

    def test_missing_target_refuses_before_writing(self):
        self.copy_jars()
        (self.archive / jenkins.expected_archive_jar("forge-1.12.2", self.version)).unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            jenkins.bundle_archive(self.archive, self.output, SHA, self.values)
        self.assertFalse(self.output.exists())

    def test_extra_target_jar_refuses(self):
        self.copy_jars()
        (self.archive / "rogue.jar").write_bytes(b"not a jar")
        with self.assertRaisesRegex(ValueError, "extra"):
            jenkins.bundle_archive(self.archive, self.output, SHA, self.values)

    def test_receipt_wrong_source_refuses(self):
        self.copy_jars()
        with self.assertRaisesRegex(ValueError, "mismatch"):
            jenkins.bundle_archive(self.archive, self.output, "b" * 40, self.values)

    def test_receipt_wrong_matrix_refuses(self):
        self.copy_jars()
        data = json.loads((self.archive / jenkins.EVIDENCE_FILE).read_text())
        data["targets"].pop()
        (self.archive / jenkins.EVIDENCE_FILE).write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "mismatch"):
            jenkins.bundle_archive(self.archive, self.output, SHA, self.values)

    def test_damaged_jar_refuses_without_output(self):
        self.copy_jars()
        jar = self.archive / jenkins.expected_archive_jar("core", self.version)
        jar.write_bytes(b"damaged")
        with self.assertRaises(Exception):
            jenkins.bundle_archive(self.archive, self.output, SHA, self.values)
        self.assertFalse(self.output.exists())

    def test_missing_receipt_refuses(self):
        self.copy_jars()
        (self.archive / jenkins.EVIDENCE_FILE).unlink()
        with self.assertRaisesRegex(ValueError, "receipt"):
            jenkins.bundle_archive(self.archive, self.output, SHA, self.values)

    def test_bad_source_sha_denied(self):
        for source in ("0" * 40, "bad", "A" * 40):
            with self.subTest(source=source), self.assertRaises(ValueError):
                jenkins.receipt(source, self.version, "release")


if __name__ == "__main__":
    unittest.main()
