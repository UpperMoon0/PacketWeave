import unittest
from jenkins_plan import plan


class JenkinsPlanTests(unittest.TestCase):
    def test_new_release_target_is_automatically_built_and_verified(self):
        target = {'target': 'forge-1.99.1', 'java': '17'}
        result = plan([target])
        self.assertEqual(result[-1]['name'], target['target'])
        self.assertIn('targets/forge-1.99.1 && ./gradlew build', result[-1]['command'])
        self.assertIn('jar --target forge-1.99.1', result[-1]['command'])

    def test_unrecognized_runtime_or_unsafe_target_fails_before_commands(self):
        for target in ({'target': '../escape', 'java': '17'}, {'target': 'forge-1.20.1', 'java': '99'}):
            with self.assertRaises(ValueError):
                plan([target])
