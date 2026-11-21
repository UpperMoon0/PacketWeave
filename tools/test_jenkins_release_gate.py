"""Negative and positive acceptance for Jenkins-only release admission."""
import unittest
from jenkins_release_gate import release_decision, relevant, valid_paths

S = "a" * 40
M = "b" * 40


def decide(**overrides):
    options = dict(event="push", ref="refs/heads/main", source_sha=S,
                   main_sha=S, changed_paths=["gradle.properties"],
                   version="0.1.6", release_type="release",
                   prior_version="0.1.5")
    options.update(overrides)
    return release_decision(**options)


class JenkinsReleaseGateTests(unittest.TestCase):
    def test_main_version_push_publishes(self):
        self.assertTrue(decide()["publish"])

    def test_no_version_bump_never_publishes(self):
        self.assertFalse(decide(prior_version="0.1.6")["build"])
        self.assertEqual(decide(prior_version="0.1.6")["reason"], "version-unchanged")

    def test_main_unrelated_path_is_filtered(self):
        self.assertFalse(decide(changed_paths=["README.md"], prior_version=None)["eligible"])

    def test_main_mismatch_refuses(self):
        for opts in (dict(main_sha=M), dict(ref="refs/heads/dev")):
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                decide(**opts)

    def test_previous_sha_missing_refuses(self):
        with self.assertRaises(ValueError):
            decide(prior_version=None)

    def test_manual_defaults_to_dry_run(self):
        d = decide(event="workflow_dispatch", prior_version=None, changed_paths=[])
        self.assertTrue(d["build"])
        self.assertFalse(d["publish"])

    def test_explicit_trusted_main_manual_can_publish(self):
        d = decide(event="workflow_dispatch", prior_version=None,
                   changed_paths=[], dry_run=False)
        self.assertTrue(d["publish"])

    def test_non_main_manual_publish_refused(self):
        with self.assertRaises(ValueError):
            decide(event="workflow_dispatch", ref="refs/heads/dev",
                   main_sha=M, dry_run=False)

    def test_non_main_dry_run_works(self):
        d = decide(event="workflow_dispatch", ref="refs/heads/dev",
                   main_sha=M, changed_paths=[], dry_run=True)
        self.assertFalse(d["publish"])

    def test_pr_paths_and_never_publish(self):
        for path in ("tools/release_contract.py", "core/build.gradle",
                     "targets/fabric-1.20.1/src/main/resources/fabric.mod.json",
                     "changelog/0.1.6.md", ".github/workflows/release.yml"):
            with self.subTest(path=path):
                self.assertTrue(decide(event="pull_request", ref="refs/pull/42/head",
                                       main_sha=M, prior_version=None,
                                       changed_paths=[path])["build"])
                self.assertFalse(decide(event="pull_request", ref="refs/pull/42/head",
                                        main_sha=M, prior_version=None,
                                        changed_paths=[path])["publish"])

    def test_pr_unmatched_path(self):
        self.assertFalse(decide(event="pull_request", ref="refs/pull/42/head",
                                main_sha=M, prior_version=None,
                                changed_paths=["README.md"])["eligible"])

    def test_foreign_pr_rejected(self):
        with self.assertRaises(ValueError):
            decide(event="pull_request", head_repository="hostile/PacketWeave",
                   ref="refs/pull/42/head", main_sha=M, prior_version=None)

    def test_existing_foreign_tag_refused(self):
        with self.assertRaises(ValueError):
            decide(tag_sha=M)
        self.assertTrue(decide(tag_sha=S)["publish"])

    def test_invalid_sha_and_source_zero_denied(self):
        for value in ("0" * 40, "abc", "A" * 40):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decide(source_sha=value)

    def test_changed_paths_validation(self):
        for path in ("../gradle.properties", "/gradle.properties", "foo//bar", "foo\\bar", "foo/*.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                valid_paths([path])

    def test_event_filter_specificity(self):
        self.assertTrue(relevant("push", ["gradle.properties"]))
        self.assertFalse(relevant("push", ["tools/jenkins_release_gate.py"]))
        self.assertFalse(relevant("pull_request", ["docs/readme.md"]))
        self.assertTrue(relevant("workflow_dispatch", []))


if __name__ == "__main__":
    unittest.main()
