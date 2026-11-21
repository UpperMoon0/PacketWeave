"""Build the complete PacketWeave release dry-run on a general Linux executor.

Production release publication is intentionally absent. The protected host
publisher must validate numbered Jenkins artifacts before any side effect.
"""
from __future__ import annotations

import json
from jenkins_plan import plan as ci_plan


BUNDLE = {
    "name": "Verify full release bundle, checksums and source receipt",
    "java": 17,
    "command": "python3 tools/jenkins_release_dryrun.py",
}


def plan() -> list[dict]:
    stages = ci_plan()
    if len(stages) < 2 or len({stage["name"] for stage in stages}) != len(stages):
        raise ValueError("Incomplete or duplicate canonical CI build stages")
    if any("command" not in stage or "java" not in stage for stage in stages):
        raise ValueError("CI matrix lacks an executable pinned Java stage")
    if BUNDLE["name"] in {stage["name"] for stage in stages}:
        raise ValueError("Release bundle stage name must be unique")
    return [*stages, dict(BUNDLE)]


if __name__ == "__main__":
    print(json.dumps(plan()))
