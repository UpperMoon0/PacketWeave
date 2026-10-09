"""Exercise the release workflow's shell steps against real, local Git history."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

import release_contract as release


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workflow = (release.ROOT / ".github/workflows/release.yml").read_text()
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
            ["git", "-c", "user.name=Release workflow test",
             "-c", "user.email=release-test@example.invalid", *args],
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
        return version, self.commit("Change the release version")

    def run_step(self, step_id, **variables):
        # Read the actual workflow shell instead of maintaining a second guard in tests.
        step = self.workflow.split(f"        id: {step_id}\n", 1)[1]
        block = step.split("        run: |\n", 1)[1]
        lines = []
        for line in block.splitlines():
            if line and not line.startswith("          "):
                break
            lines.append(line)
        self.assertTrue(lines, f"Missing shell for workflow step {step_id}")
        output = self.root.parent / f"{self.root.name}-{step_id}-output"
        self.addCleanup(output.unlink, missing_ok=True)
        output.write_text("")
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c",
             textwrap.dedent("\n".join(lines))], cwd=self.root, text=True,
            capture_output=True, env={**os.environ, **variables, "GITHUB_OUTPUT": str(output)})
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        return result, values

    def plan(self, event="push"):
        result, values = self.run_step("plan", BEFORE_SHA=self.before, EVENT_NAME=event)
        self.assertEqual(0, result.returncode, result.stderr)
        return values

    def source(self, plan, publish_allowed="true"):
        return self.run_step("source", VERSION=plan["version"], VERSION_CHANGED=plan["changed"],
                             PUBLISH_ALLOWED=publish_allowed, SOURCE_SHA=self.git("rev-parse", "HEAD"))

    def test_workflow_binds_version_change_to_source_step(self):
        self.assertIn("VERSION_CHANGED: ${{ steps.plan.outputs.changed }}", self.workflow)

    def test_unchanged_version_main_push_after_release_is_a_noop(self):
        self.assertNotEqual(self.before, self.change_property())
        plan = self.plan()
        self.assertEqual("false", plan["changed"])
        result, outputs = self.source(plan)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("false", outputs["publish"])

    def test_changed_version_main_push_still_rejects_a_conflicting_tag(self):
        version, _ = self.change_version()
        self.git("tag", f"v{version}", self.before)
        plan = self.plan()
        self.assertEqual("true", plan["changed"])
        result, _ = self.source(plan)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Version tag already belongs to another source commit", result.stderr)

    def test_manual_publication_still_rejects_a_conflicting_tag(self):
        self.change_property()
        plan = self.plan("workflow_dispatch")
        self.assertEqual("true", plan["changed"])
        result, _ = self.source(plan)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Version tag already belongs to another source commit", result.stderr)

    def test_publication_allows_matching_lightweight_and_annotated_tags(self):
        for annotated in (False, True):
            with self.subTest(annotated=annotated):
                if annotated:
                    self.git("tag", "--delete", f"v{self.version}")
                    self.git("tag", "--annotate", f"v{self.version}", "-m", "Release")
                result, outputs = self.source(self.plan("workflow_dispatch"))
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("true", outputs["publish"])

    def test_new_version_without_a_tag_can_publish(self):
        self.change_version()
        plan = self.plan()
        self.assertEqual("true", plan["changed"])
        result, outputs = self.source(plan)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("true", outputs["publish"])

    def test_dry_runs_skip_tag_conflicts_and_never_publish(self):
        self.change_property()
        for event in ("pull_request", "workflow_dispatch"):
            with self.subTest(event=event):
                plan = self.plan(event)
                self.assertEqual("true", plan["changed"])
                result, outputs = self.source(plan, publish_allowed="false")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("false", outputs["publish"])


if __name__ == "__main__":
    unittest.main()
