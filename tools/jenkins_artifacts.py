#!/usr/bin/env python3
"""Native Jenkins source evidence and complete, source-pinned release bundles.

The protected Jenkins controller must independently authenticate the event,
verify the producer build succeeded, and bind its numbered artifact archive to
the exact commit. This script validates the archive contents; it never publishes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import release_contract as release

REPOSITORY = "UpperMoon0/PacketWeave"
EVIDENCE_FILE = "ci-source-evidence.json"


def receipt(source_sha: str, version: str, release_type: str) -> dict:
    if not release_sha(source_sha) or release_type not in ("alpha", "beta", "release"):
        raise ValueError("Invalid source or release metadata")
    return {
        "schema_version": 1,
        "repository": REPOSITORY,
        "source_sha": source_sha,
        "version": version,
        "release_type": release_type,
        "targets": ["core", *[item["target"] for item in release.TARGETS]],
    }


def release_sha(value: str) -> bool:
    return len(value) == 40 and all(c in "0123456789abcdef" for c in value) and value != "0" * 40


def checked_out_sha(root: Path) -> str:
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                  text=True).strip()
    if not release_sha(sha):
        raise ValueError("Unable to pin Jenkins checkout to a full Git SHA")
    return sha


def expected_archive_jar(target: str, version: str) -> Path:
    filename = release.filename(target, version)
    return (Path("core/build/libs") if target == "core" else
            Path("targets") / target / "build/libs") / filename


def read_receipt(archive: Path, source_sha: str, values: dict) -> dict:
    evidence = archive / EVIDENCE_FILE
    if evidence.is_symlink() or not evidence.is_file() or evidence.stat().st_size > 16384:
        raise ValueError("CI archive lacks a bounded regular source-evidence receipt")
    data = json.loads(evidence.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data != receipt(
        source_sha, values["mod_version"], values["release_type"]
    ):
        raise ValueError("CI artifact source, version, or target matrix mismatch")
    return data


def bundle_archive(archive: Path, output: Path, source_sha: str,
                   values: dict) -> dict:
    if not release_sha(source_sha):
        raise ValueError("Expected source SHA must be complete and nonzero")
    if archive.is_symlink() or not archive.is_dir():
        raise ValueError("CI artifacts must come from a regular Jenkins archive")
    if output.resolve().is_relative_to(archive.resolve()):
        raise ValueError("Output must be outside the producer artifact archive")
    read_receipt(archive, source_sha, values)
    version = values["mod_version"]
    targets = ["core", *[item["target"] for item in release.TARGETS]]
    expected = [archive / expected_archive_jar(target, version) for target in targets]
    actual = sorted(p for p in archive.rglob("*.jar")
                    if not p.name.endswith("-sources.jar"))
    if set(actual) != set(expected):
        raise ValueError("Producer archive has missing, duplicate, or extra production JARs")
    if any(p.is_symlink() or not p.is_file() for p in expected):
        raise ValueError("Producer archive contains a nonregular production JAR")
    # Recheck metadata/bytecode/licenses before copying anything into dist.
    for path, target in zip(expected, targets):
        release.inspect_jar(path, target, version)
    with tempfile.TemporaryDirectory(prefix="packetweave-jenkins-bundle-") as scratch:
        staging = Path(scratch)
        for path, target in zip(expected, targets):
            directory = staging / f"packetweave-{target}"
            directory.mkdir()
            shutil.copy2(path, directory / path.name)
        return release.bundle(staging, output, version, source_sha)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    evidence = sub.add_parser("evidence", help="Record checked-out source/target matrix in CI")
    evidence.add_argument("--output", default=EVIDENCE_FILE, type=Path)
    bundle = sub.add_parser("bundle", help="Re-validate a numbered Jenkins build archive")
    bundle.add_argument("--archive", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)
    bundle.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    values = release.verify(root)
    actual_sha = checked_out_sha(root)
    if args.command == "evidence":
        if args.output != Path(EVIDENCE_FILE) or args.output.is_symlink():
            raise ValueError("Source receipt must be written at repository root")
        args.output.write_text(json.dumps(
            receipt(actual_sha, values["mod_version"], values["release_type"]),
            sort_keys=True, indent=2
        ) + "\n", encoding="utf-8")
        print(f"Jenkins CI source evidence: {actual_sha}")
    else:
        if args.source_sha != actual_sha:
            raise ValueError("Release checkout differs from admitted exact producer SHA")
        result = bundle_archive(args.archive, args.output, actual_sha, values)
        print(f"Verified {len(result['assets'])} JARs and SHA256/source receipt for {actual_sha}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"Jenkins artifacts refused: {exc}", file=sys.stderr)
        sys.exit(2)
