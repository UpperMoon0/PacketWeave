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
    # A failed or unfinished build must never reuse stale dist files.
    if output.exists() or output.is_symlink():
        raise ValueError("Release dist must not already exist before dry-run")
    if output.resolve().parent != root.resolve():
        raise ValueError("Dry-run dist must be directly under this checkout")
    actual_sha = jenkins.checked_out_sha(root)
    values = release.verify(root)
    with tempfile.TemporaryDirectory(prefix="packetweave-release-offline-") as temp:
        scratch = Path(temp)
        archive = scratch / "producer"
        archive.mkdir()
        receipt = root / jenkins.EVIDENCE_FILE
        if receipt.is_symlink() or not receipt.is_file():
            raise ValueError("CI workspace lacks a regular source-evidence receipt")
        shutil.copy2(receipt, archive / receipt.name)

        # Gradle wrapper and Forge tooling JARs are outside the producer's
        # build/libs directories. Keep the strict archive validator's input
        # limited to those directories, including any unexpected JARs in them.
        targets = ["core", *[item["target"] for item in release.TARGETS]]
        for target in targets:
            directory = jenkins.expected_archive_jar(target, values["mod_version"]).parent
            output_directory = archive / directory
            output_directory.mkdir(parents=True)
            for path in (root / directory).glob("*.jar"):
                if path.is_symlink() or not path.is_file():
                    raise ValueError("CI workspace contains a nonregular build JAR")
                shutil.copy2(path, output_directory / path.name)

        stage = scratch / "dist"
        manifest = jenkins.bundle_archive(archive, stage, actual_sha, values)
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
