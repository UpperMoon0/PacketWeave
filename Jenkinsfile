@Library('nstut-ci') _

nstutGradle(
    // Only two independently qualified, credential-free Linux workers may
    // produce native cutover evidence. on-prem-2 remains general-purpose but
    // cannot satisfy PacketWeave release/check acceptance.
    agentLabel: 'ci-role-general && ci-os-linux && (cloud-1-linux-ci || on-prem-1-linux-ci)',
    verify: '''python3 -m unittest discover -s tools -p 'test_*.py' -v
python3 tools/verify_structure.py
python3 tools/release_contract.py plan
python3 tools/jenkins_artifacts.py evidence''',
    plan: 'python3 tools/jenkins_plan.py',
    tests: '**/build/test-results/**/*.xml',
    artifacts: 'ci-source-evidence.json,core/build/libs/*.jar,targets/*/build/libs/*.jar',
    diagnostics: '**/build/reports/**'
)
