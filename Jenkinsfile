@Library('nstut-ci') _

nstutGradle(
    // Only administrator-qualified, credential-free Linux general workers may
    // produce native cutover evidence. Other general workers remain excluded until
    // cannot satisfy PacketWeave release/check acceptance.
    agentLabel: 'ci-role-general && ci-os-linux && ci-linux-container && ci-native-gradle-ready',
    verify: '''python3 -m unittest discover -s tools -p 'test_*.py' -v
python3 tools/verify_structure.py
python3 tools/release_contract.py plan
python3 tools/jenkins_artifacts.py evidence''',
    plan: 'python3 tools/jenkins_plan.py',
    tests: '**/build/test-results/**/*.xml',
    artifacts: 'ci-source-evidence.json,core/build/libs/*.jar,targets/*/build/libs/*.jar',
    diagnostics: '**/build/reports/**'
)
