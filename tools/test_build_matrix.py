import os
import unittest

import build_matrix
import release_contract


class BuildMatrixTests(unittest.TestCase):
    def test_build_and_release_share_exact_target_matrix(self):
        self.assertEqual(build_matrix.TARGETS, [item["target"] for item in release_contract.TARGETS])

    def test_independent_builds_select_gradle_jvm(self):
        environment = {"JAVA8_HOME": "/jdk8", "JAVA17_HOME": "/jdk17", "JAVA25_HOME": "/jdk25", "PATH": "/bin"}
        for target, home in [("forge-1.12.2", "/jdk8"), ("forge-1.16.5", "/jdk17"),
                             ("fabric-1.16.5", "/jdk25"), ("fabric-26.2", "/jdk25"), ("neoforge-26.2", "/jdk25")]:
            with self.subTest(target=target):
                selected = build_matrix.environment_for(target, environment)
                self.assertEqual(home, selected["JAVA_HOME"])
                self.assertTrue(selected["PATH"].endswith(os.pathsep + "/bin"))
        self.assertNotIn("JAVA_HOME", environment)

    def test_setup_java_and_existing_java_home_are_supported(self):
        self.assertEqual("/jdk8", build_matrix.environment_for("forge-1.12.2", {"JAVA_HOME_8_X64": "/jdk8"})["JAVA_HOME"])
        self.assertEqual("/custom", build_matrix.environment_for("fabric-26.2", {"JAVA_HOME": "/custom"})["JAVA_HOME"])
