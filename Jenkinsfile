@Library('nstut-ci') _

nstutGradle(
    // nstut-ci's ci-memory-large default is not present on the qualified
    // 2 GiB general Linux executor; the library explicitly permits this pool.
    agentLabel: 'ci-linux-container',
    verify: '''python3 -m unittest discover -s tools -p 'test_*.py' -v
python3 tools/verify_structure.py
python3 tools/release_contract.py plan
python3 tools/jenkins_artifacts.py evidence''',
    plan: 'python3 tools/jenkins_plan.py',
    tests: '**/build/test-results/**/*.xml',
    artifacts: 'ci-source-evidence.json,core/build/libs/*.jar,targets/*/build/libs/*.jar',
    diagnostics: '**/build/reports/**'
)
