"""Verify the Jenkins release gate against real Git history after Actions retirement.

These cases previously executed shell fragments extracted from the deleted
.github/workflows/release.yml. Their live authority is now the credential-free
Jenkins release gate, so tests must not depend on retired workflow YAML.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import jenkins_release_gate as gate
import release_contract as release


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.version = release.config()["mod_version"]
        paths = ["gradle.properties", "core/build.gradle", "tools/release_contract.py",
                 f"changelog/{self.version}.md"]
        paths += [f"targets/{item['target']}/gradle.properties" for item in release.TARGETS]
        for name in paths:
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(release.ROOT / name, destination)
        self.git("init", "--quiet")
        self.before = self.commit("Released version")
        self.git("tag", f"v{self.version}")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-c", "user.name=Jenkins release test",
             "-c", "user.email=jenkins-test@example.invalid", *args],
            cwd=self.root, text=True).strip()

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")

    def change_property(self):
        properties = self.root / "gradle.properties"
        properties.write_text(properties.read_text().replace("-Xmx2G", "-Xmx3G"))
        return self.commit("Change only the Gradle heap size")

    def change_version(self):
        version = "9.9.9"
        for path in [self.root / "gradle.properties", *self.root.glob("targets/*/gradle.properties")]:
            path.write_text(path.read_text().replace(f"mod_version={self.version}", f"mod_version={version}"))
        (self.root / "changelog" / f"{version}.md").write_text("New release\n")
        return version, self.commit("Change release version")

    def decide(self, event="push", *, publish_allowed=True, changed_paths=None):
        head = self.git("rev-parse", "HEAD")
        version = release.verify(self.root)["mod_version"]
        paths = ["gradle.properties"] if changed_paths is None else changed_paths
        prior = (gate.previous_version(self.root, self.before, head)
                 if event == "push" and gate.relevant(event, paths) else None)
        return gate.release_decision(
            event=event, ref=("refs/pull/15/head" if event == "pull_request"
                              else "refs/heads/main"),
            source_sha=head, main_sha=head,
            changed_paths=paths, version=version,
            release_type=release.config(self.root)["release_type"],
            prior_version=prior, dry_run=not publish_allowed,
            tag_sha=gate.version_tag(self.root, version),
        )

    def test_gate_uses_real_version_change_and_pinned_ancestor(self):
        self.assertFalse(release.version_changed(self.version,
                         (self.root / "gradle.properties").read_text()))
        version, head = self.change_version()
        self.assertEqual(head, self.git("rev-parse", "HEAD"))
        self.assertEqual(self.version, gate.previous_version(self.root, self.before, head))
        self.assertTrue(release.version_changed(
            version, self.git("show", f"{self.before}:gradle.properties")))

    def test_unchanged_version_main_push_after_release_is_noop(self):
        self.change_property()
        result = self.decide()
        self.assertFalse(result["build"])
        self.assertFalse(result["publish"])
        self.assertEqual("version-unchanged", result["reason"])

    def test_changed_version_main_push_rejects_conflicting_tag(self):
        version, _ = self.change_version()
        self.git("tag", f"v{version}", self.before)
        with self.assertRaisesRegex(ValueError, "Existing version tag belongs"):
            self.decide()

    def test_manual_publication_rejects_conflicting_tag(self):
        self.change_property()
        with self.assertRaisesRegex(ValueError, "Existing version tag belongs"):
            self.decide("workflow_dispatch")

    def test_manual_accepts_matching_lightweight_and_annotated_tags(self):
        self.change_property()
        self.git("tag", "--force", f"v{self.version}")
        for annotated in (False, True):
            with self.subTest(annotated=annotated):
                if annotated:
                    self.git("tag", "--delete", f"v{self.version}")
                    self.git("tag", "--annotate", f"v{self.version}", "-m", "Release")
                result = self.decide("workflow_dispatch")
                self.assertTrue(result["publish"])
                self.assertEqual(self.git("rev-parse", "HEAD"), result["source_sha"])

    def test_new_version_without_tag_can_publish(self):
        self.change_version()
        result = self.decide()
        self.assertTrue(result["publish"])
        self.assertEqual("publish-allowed", result["reason"])

    def test_dry_runs_never_publish_even_with_conflicting_tag(self):
        self.change_property()
        for event in ("pull_request", "workflow_dispatch"):
            with self.subTest(event=event):
                result = self.decide(event, publish_allowed=False)
                self.assertTrue(result["build"])
                self.assertFalse(result["publish"])
                self.assertEqual("dry-run-only", result["reason"])

    def test_jekins_replaces_retired_yaml_and_preserves_path_filters(self):
        self.assertFalse((release.ROOT / ".github/workflows/release.yml").exists())
        self.assertTrue(gate.relevant("push", ["gradle.properties"]))
        self.assertFalse(gate.relevant("push", ["README.md"]))
        self.assertTrue(gate.relevant("pull_request", ["tools/release_contract.py"]))
        self.assertFalse(gate.relevant("pull_request", ["README.md"]))


if __name__ == "__main__":
    unittest.main()
