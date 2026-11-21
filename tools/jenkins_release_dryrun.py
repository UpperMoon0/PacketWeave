#!/usr/bin/env python3
"""Generate an offline release bundle from exactly this Jenkins build workspace."""
from __future__ import annotations

import shutil
from pathlib import Path
import sys
import tempfile

import jenkins_artifacts as jenkins
import release_contract as release


def offline_bundle(root: Path, output: Path) -> dict:
    actual_sha = jenkins.checked_out_sha(root)
    values = release.verify(root)
    # A failed or unfinished build must never reuse stale dist files.
    if output.exists() or output.is_symlink():
        raise ValueError("Release dist must not already exist before dry-run")
    if output.resolve().parent != root.resolve():
        raise ValueError("Dry-run dist must be directly under this checkout")
    with tempfile.TemporaryDirectory(prefix="packetweave-release-offline-") as temp:
        stage = Path(temp) / "dist"
        manifest = jenkins.bundle_archive(root, stage, actual_sha, values)
        # No publication, network calls, or environment credential access.
        shutil.copytree(stage, output, symlinks=False)
    return manifest


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    try:
        result = offline_bundle(root, root / "dist")
        print(f"Jenkins offline release verified: {result['source_sha']} "
              f"({len(result['assets'])} production JARs; no publication)")
    except (ValueError, OSError) as exc:
        print(f"Jenkins offline release refused: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
