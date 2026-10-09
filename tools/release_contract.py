#!/usr/bin/env python3
"""Shared CI/release plan and production artifact verification (no publication)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    {"target": f"{loader}-{mc}", "minecraft": mc, "loader": loader,
     "loader_name": {"fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge"}[loader],
     "java": "17" if loader == "forge" else "25", "runtime_java": str(java)}
    for mc, loaders, java in [
        ("1.16.5", ["fabric", "forge"], 8),
        ("1.20.1", ["fabric", "forge"], 17),
        ("1.21.1", ["fabric", "neoforge"], 21),
        ("26.1.2", ["fabric", "neoforge"], 25),
    ] for loader in loaders
]


def properties(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "!")):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            if key in result:
                raise ValueError(f"Duplicate property: {key}")
            result[key] = value.strip()
    return result


def config(root: Path = ROOT) -> dict[str, str]:
    values = properties((root / "gradle.properties").read_text(encoding="utf-8"))
    version = values.get("mod_version", "")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+.][0-9A-Za-z.-]+)?", version):
        raise ValueError(f"Invalid mod_version: {version!r}")
    if values.get("release_type") not in ("alpha", "beta", "release"):
        raise ValueError("release_type must be alpha, beta or release")
    return values


def verify(root: Path = ROOT) -> dict[str, str]:
    values = config(root)
    version = values["mod_version"]
    for target in TARGETS:
        path = root / "targets" / target["target"] / "gradle.properties"
        actual = properties(path.read_text(encoding="utf-8"))
        if actual.get("mod_version") != version or actual.get("minecraft_version") != target["minecraft"]:
            raise ValueError(f"Target version mismatch: {target['target']}")
    if "version = rootProject.mod_version" not in (root / "core/build.gradle").read_text():
        raise ValueError("Core must use the canonical root mod_version")
    changelog = root / "changelog" / f"{version}.md"
    if not changelog.is_file() or not changelog.read_text(encoding="utf-8").strip():
        raise ValueError(f"Missing release changelog: {changelog}")
    return values


def version_changed(current: str, previous_text: str | None, force: bool = False) -> bool:
    return force or previous_text is None or properties(previous_text).get("mod_version") != current


def filename(target: str, version: str) -> str:
    if target != "core" and target not in {item["target"] for item in TARGETS}:
        raise ValueError(f"Unknown target: {target}")
    return f"packetweave-{target}-{version}.jar"


def inspect_jar(jar: Path, target: str, version: str) -> None:
    if jar.name != filename(target, version):
        raise ValueError(f"Unexpected production filename: {jar.name}")
    with zipfile.ZipFile(jar) as archive:
        required = {
            "com/nstut/packetweave/api/TransferRegistry.class",
            "com/nstut/packetweave/api/ChunkedTransfer.class",
            "META-INF/LICENSE-PacketWeave",
        }
        if not required.issubset(archive.namelist()):
            raise ValueError(f"Missing core classes or license: {jar}")
        if not archive.read("META-INF/LICENSE-PacketWeave").startswith(b"MIT License"):
            raise ValueError(f"Invalid license: {jar}")
        if target == "core":
            return
        icon_path = "assets/packetweave/icon.png"
        if icon_path not in archive.namelist() or not archive.read(icon_path).startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"Missing or invalid mod icon: {jar}")
        loader, minecraft = target.split("-", 1)
        entrypoint = {"fabric": "PacketWeaveFabric", "forge": "PacketWeaveForge", "neoforge": "PacketWeaveNeoForge"}[loader]
        if f"com/nstut/packetweave/{loader}/{entrypoint}.class" not in archive.namelist():
            raise ValueError(f"Missing loader entrypoint: {jar}")
        if loader == "forge":
            if "pack.mcmeta" not in archive.namelist():
                raise ValueError(f"Missing Forge pack metadata: {jar}")
            pack = json.loads(archive.read("pack.mcmeta")).get("pack", {})
            expected_format = {"1.16.5": 6, "1.20.1": 15}[minecraft]
            if pack.get("pack_format") != expected_format or not pack.get("description"):
                raise ValueError(f"Incorrect Forge pack metadata: {jar}")
        if loader == "fabric":
            metadata = json.loads(archive.read("fabric.mod.json"))
            if metadata.get("icon") != icon_path:
                raise ValueError(f"Incorrect Fabric icon reference: {jar}")
            if (metadata.get("id"), metadata.get("version"), metadata.get("depends", {}).get("minecraft")) != ("packetweave", version, minecraft):
                raise ValueError(f"Incorrect Fabric metadata: {jar}")
        else:
            name = "mods.toml" if loader == "forge" else "neoforge.mods.toml"
            metadata = tomllib.loads(archive.read(f"META-INF/{name}").decode("utf-8"))
            mods = metadata.get("mods", [])
            if len(mods) == 1 and mods[0].get("logoFile") != icon_path:
                raise ValueError(f"Incorrect loader icon reference: {jar}")
            dependencies = metadata.get("dependencies", {}).get("packetweave", [])
            if len(mods) != 1 or (mods[0].get("modId"), mods[0].get("version")) != ("packetweave", version):
                raise ValueError(f"Incorrect loader metadata: {jar}")
            if not any(dep.get("modId") == "minecraft" and minecraft in dep.get("versionRange", "") for dep in dependencies):
                raise ValueError(f"Missing Minecraft version: {jar}")


def production_jar(directory: Path, target: str, version: str) -> Path:
    jars = sorted(path for path in directory.glob("*.jar") if not path.name.endswith("-sources.jar"))
    if len(jars) != 1:
        raise ValueError(f"Expected exactly one production jar in {directory}; found {len(jars)}")
    inspect_jar(jars[0], target, version)
    return jars[0]


def bundle(artifacts: Path, output: Path, version: str, source_sha: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("A full source commit SHA is required")
    expected = ["core"] + [target["target"] for target in TARGETS]
    selected = [production_jar(artifacts / f"packetweave-{target}", target, version) for target in expected]
    all_jars = list(artifacts.rglob("*.jar"))
    if len(all_jars) != len(selected) or set(all_jars) != set(selected):
        raise ValueError("Release artifacts contain unexpected or duplicate jars")
    # Validate the whole matrix before preparing any release files.
    if output.exists() and any(output.iterdir()):
        raise ValueError("Release output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    assets = []
    for target, jar in zip(expected, selected):
        digest = hashlib.sha256(jar.read_bytes()).hexdigest()
        shutil.copy2(jar, output / jar.name)
        assets.append({"target": target, "file": jar.name, "sha256": digest})
    manifest = {"version": version, "source_sha": source_sha, "assets": assets}
    (output / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "SHA256SUMS").write_text("".join(f"{asset['sha256']}  {asset['file']}\n" for asset in assets))
    return manifest


def github_output(values: dict) -> None:
    for key, value in values.items():
        if isinstance(value, bool):
            value = str(value).lower()
        elif not isinstance(value, str):
            value = json.dumps(value, separators=(",", ":"))
        line = f"{key}={value}\n"
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
                handle.write(line)
        else:
            print(line, end="")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    plan = commands.add_parser("plan")
    plan.add_argument("--before", default="")
    plan.add_argument("--force", action="store_true")
    jar = commands.add_parser("jar")
    jar.add_argument("--target", required=True)
    jar.add_argument("--directory", required=True, type=Path)
    assets = commands.add_parser("bundle")
    assets.add_argument("--artifacts", required=True, type=Path)
    assets.add_argument("--output", required=True, type=Path)
    assets.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    values = verify()
    if args.command == "verify":
        print(f"Release contract verified for {values['mod_version']} and all eight targets")
    elif args.command == "plan":
        previous = None
        if args.before and set(args.before) != {"0"}:
            if not re.fullmatch(r"[0-9a-f]{40}", args.before):
                raise ValueError("Invalid previous commit SHA")
            previous = subprocess.check_output(["git", "show", f"{args.before}:gradle.properties"], cwd=ROOT, text=True)
        github_output({"version": values["mod_version"], "release_type": values["release_type"],
                       "changed": version_changed(values["mod_version"], previous, args.force), "matrix": {"include": TARGETS}})
    elif args.command == "jar":
        github_output({"jar_path": production_jar(args.directory, args.target, values["mod_version"]).as_posix()})
    else:
        bundle(args.artifacts, args.output, values["mod_version"], args.source_sha)
        print("Verified nine release jars, source receipt and checksums")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, zipfile.BadZipFile) as exception:
        sys.exit(str(exception))
