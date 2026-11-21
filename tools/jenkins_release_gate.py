#!/usr/bin/env python3
"""Fail-closed PacketWeave Jenkins release-event decision.

Inputs must come from an authenticated, source-pinned Jenkins admission broker.
This does NOT authorize private-runner execution, grant publication credentials,
or replace the host's remote tag/source and idempotency checks.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import re
import subprocess
import sys

from release_contract import config, properties, verify

REPOSITORY = "UpperMoon0/PacketWeave"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
RELEASE_PATHS = (
    ".github/workflows/**", "tools/**", "gradle/**",
    "gradle.properties", "build.gradle", "core/build.gradle",
    "targets/**/build.gradle", "targets/**/gradle.properties",
    "targets/**/src/main/resources/**", "icon.png", "changelog/**",
)


def valid_sha(value: str) -> bool:
    return bool(SHA_RE.fullmatch(value)) and value != "0" * 40


def valid_paths(paths: object) -> list[str]:
    if not isinstance(paths, list) or any(
        not isinstance(p, str) or not p or p.startswith("/")
        or "\\" in p or any(segment in ("", ".", "..") for segment in p.split("/"))
        or any(ch in p for ch in "*?[]\n\r")
        for p in paths
    ):
        raise ValueError("Changed paths must be safe relative repository file names")
    return paths


def relevant(event: str, paths: list[str]) -> bool:
    if event == "workflow_dispatch":
        return True
    if event == "push":
        return "gradle.properties" in paths
    if event == "pull_request":
        return any(fnmatch.fnmatchcase(path, pattern)
                   for path in paths for pattern in RELEASE_PATHS)
    raise ValueError("Unsupported release event")


def release_decision(*, event: str, ref: str, source_sha: str, main_sha: str,
                     changed_paths: list[str], version: str, release_type: str,
                     prior_version: str | None = None, dry_run: bool = True,
                     head_repository: str = REPOSITORY, tag_sha: str | None = None) -> dict:
    """Pure decision layer; security-sensitive source checks are repeated by the host."""
    if not valid_sha(source_sha):
        raise ValueError("Source must be pinned to a nonzero full SHA")
    if event not in ("push", "pull_request", "workflow_dispatch"):
        raise ValueError("Unsupported event")
    if head_repository != REPOSITORY:
        raise ValueError("Fork or foreign-repository source is not admitted on private CI")
    if release_type not in ("alpha", "beta", "release"):
        raise ValueError("Unsupported release type")
    valid_paths(changed_paths)
    if event == "push" and (ref != "refs/heads/main" or source_sha != main_sha):
        raise ValueError("Push must be the canonical exact main commit")
    if event == "workflow_dispatch" and not dry_run and (
        ref != "refs/heads/main" or source_sha != main_sha
    ):
        raise ValueError("Non-dry-run dispatch requires the exact trusted main commit")
    if event != "pull_request" and ref == "refs/heads/main" and not valid_sha(main_sha):
        raise ValueError("Canonical main SHA is required")
    if tag_sha is not None and (not valid_sha(tag_sha) or tag_sha != source_sha):
        raise ValueError("Existing version tag belongs to another source")
    eligible = relevant(event, changed_paths)
    if event == "push" and eligible and prior_version is None:
        raise ValueError("Version comparison requires an accessible prior commit")
    changed = eligible and (event != "push" or prior_version != version)
    publish = bool(changed and (
        event == "push" or (
            event == "workflow_dispatch" and not dry_run and ref == "refs/heads/main"
        )
    ))
    return {
        "event": event, "source_sha": source_sha, "version": version,
        "release_type": release_type, "eligible": eligible,
        "build": bool(changed), "publish": publish,
        "reason": ("path-filtered" if not eligible else
                   "version-unchanged" if not changed else
                   "publish-allowed" if publish else "dry-run-only"),
    }


def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", "-C", str(root), *arguments],
                            capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise ValueError("Git source or previous revision cannot be verified")
    return result


def previous_version(root: Path, before: str, source: str) -> str:
    if not valid_sha(before):
        raise ValueError("Previous commit must be a complete nonzero SHA")
    git(root, "merge-base", "--is-ancestor", before, source)
    previous = git(root, "show", f"{before}:gradle.properties").stdout
    value = properties(previous).get("mod_version")
    if not value:
        raise ValueError("Previous version is absent")
    return value


def version_tag(root: Path, version: str) -> str | None:
    tagged = git(root, "rev-parse", "--verify", "--quiet",
                 f"refs/tags/v{version}^{{commit}}", check=False)
    if tagged.returncode:
        return None
    value = tagged.stdout.strip()
    if not valid_sha(value):
        raise ValueError("Cannot verify version tag commit")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True,
                        choices=("push", "pull_request", "workflow_dispatch"))
    parser.add_argument("--ref", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--main-sha", default="")
    parser.add_argument("--head-repository", default=REPOSITORY)
    parser.add_argument("--before", default="")
    parser.add_argument("--changed-paths-json", default="[]")
    parser.add_argument("--dry-run", choices=("true", "false"), default="true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if git(root, "rev-parse", "HEAD").stdout.strip() != args.source_sha:
        raise ValueError("Checked-out source differs from admitted SHA")
    if args.event == "pull_request" and args.head_repository != REPOSITORY:
        raise ValueError("Never execute untrusted fork PR code on private workers")
    values = verify(root)
    paths = valid_paths(json.loads(args.changed_paths_json))
    prior = (previous_version(root, args.before, args.source_sha)
             if args.event == "push" and relevant(args.event, paths) else None)
    decision = release_decision(
        event=args.event, ref=args.ref, source_sha=args.source_sha,
        main_sha=args.main_sha, changed_paths=paths,
        version=values["mod_version"], release_type=values["release_type"],
        prior_version=prior, dry_run=args.dry_run == "true",
        head_repository=args.head_repository,
        tag_sha=version_tag(root, values["mod_version"]),
    )
    print(json.dumps(decision, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"Jenkins release gate refused: {exc}", file=sys.stderr)
        sys.exit(2)
