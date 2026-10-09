#!/usr/bin/env python3
"""Publish only verified native release jars; persist confirmed uploads for run retries."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from release_contract import ROOT, TARGETS, filename, inspect_jar, verify

API = "https://minecraft.curseforge.com/api"


def request_json(path: str, token: str, data: bytes | None = None, content_type: str | None = None) -> dict | list:
    headers = {"X-Api-Token": token, "Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(API + path, data=data, headers=headers, method="GET" if data is None else "POST")
    # GET retries are safe. An ambiguous POST must be inspected, never uploaded repeatedly.
    for attempt in range(3 if data is None else 1):
        try:
            with urlopen(request, timeout=45) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise ValueError("CurseForge response is oversized")
                return json.loads(body)
        except (HTTPError, URLError) as exception:
            retryable = not isinstance(exception, HTTPError) or exception.code in (429, 500, 502, 503, 504)
            if data is None and retryable and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            # No raw response/request dump: it may contain account data or echoed credentials.
            raise ValueError(f"CurseForge request failed ({getattr(exception, 'code', 'connection error')}); inspect the run before retrying") from None
    raise AssertionError("unreachable")


def release_assets(directory: Path, source_sha: str, root: Path = ROOT) -> tuple[dict, dict[str, str]]:
    values = verify(root)
    manifest = json.loads((directory / "release-manifest.json").read_text())
    if manifest.get("version") != values["mod_version"] or manifest.get("source_sha") != source_sha:
        raise ValueError("Release bundle is from a different source or version")
    assets = manifest.get("assets", [])
    expected = {"core"} | {target["target"] for target in TARGETS}
    if len(assets) != len(expected) or {asset["target"] for asset in assets} != expected:
        raise ValueError("Release manifest must contain exactly the core and all eight native targets")
    for asset in assets:
        target = asset["target"]
        if asset.get("file") != filename(target, values["mod_version"]):
            raise ValueError("Unexpected release asset name")
        jar = directory / asset["file"]
        inspect_jar(jar, target, values["mod_version"])
        if hashlib.sha256(jar.read_bytes()).hexdigest() != asset.get("sha256"):
            raise ValueError(f"Release checksum mismatch: {jar.name}")
    return manifest, values


def metadata(target: dict, version: str, release_type: str, changelog: str) -> dict:
    return {
        "changelog": changelog, "changelogType": "markdown",
        "displayName": f"PacketWeave {version} - {target['loader_name']} {target['minecraft']}",
        "gameVersionNames": [target["minecraft"], target["loader_name"], f"Java {target['runtime_java']}", "Client", "Server"],
        "releaseType": release_type,
        # Loader APIs are native: do not inherit Screens' Architectury/OpenUI/Fabric API relations.
        "relations": {"projects": []},
    }


def multipart(metadata_value: dict, jar: Path) -> tuple[bytes, str]:
    boundary = "packetweave-" + uuid.uuid4().hex
    fields = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'.encode(),
        json.dumps(metadata_value).encode("utf-8"),
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{jar.name}"\r\nContent-Type: application/java-archive\r\n\r\n'.encode(),
        jar.read_bytes(), f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(fields), f"multipart/form-data; boundary={boundary}"


def save_receipt(path: Path, receipt: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt, indent=2) + "\n")
    temporary.replace(path)


def publish(directory: Path, receipt_path: Path, project_id: str, token: str, source_sha: str,
            root: Path = ROOT, api=request_json) -> dict:
    if not re.fullmatch(r"[1-9][0-9]*", project_id):
        raise ValueError("Set repository variable CURSEFORGE_PROJECT_ID to the numeric project ID")
    if not token:
        raise ValueError("Missing required GitHub secret CURSEFORGE_API_TOKEN")
    manifest, values = release_assets(directory, source_sha, root)
    changelog = (root / "changelog" / f"{values['mod_version']}.md").read_text(encoding="utf-8")
    plans = {target["target"]: metadata(target, values["mod_version"], values["release_type"], changelog) for target in TARGETS}
    available = api("/game/versions", token)
    if not isinstance(available, list):
        raise ValueError("Unexpected CurseForge version response")
    names = {item.get("name") for item in available if isinstance(item, dict)}
    unknown = set().union(*(set(plan["gameVersionNames"]) for plan in plans.values())) - names
    if unknown:
        raise ValueError(f"Unknown CurseForge tags: {sorted(unknown)}")
    identity = {"project_id": project_id, "source_sha": source_sha, "version": values["mod_version"]}
    receipt = {**identity, "uploads": {}}
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if any(receipt.get(key) != value for key, value in identity.items()):
            raise ValueError("Previous upload receipts belong to another source, version or project")
        if not isinstance(receipt.get("uploads"), dict) or set(receipt["uploads"]) - set(plans):
            raise ValueError("Invalid upload receipts")
    assets = {asset["target"]: asset for asset in manifest["assets"]}
    # Validate every saved receipt before making any new upload.
    for target, upload in receipt["uploads"].items():
        if not isinstance(upload, dict) or upload.get("sha256") != assets[target]["sha256"] or type(upload.get("file_id")) is not int or upload["file_id"] <= 0:
            raise ValueError("Saved upload receipt does not match the verified jar")
    save_receipt(receipt_path, receipt)
    for target, plan in plans.items():
        if target in receipt["uploads"]:
            print(f"{target}: confirmed upload retained from previous run attempt")
            continue
        jar = directory / assets[target]["file"]
        body, content_type = multipart(plan, jar)
        response = api(f"/projects/{project_id}/upload-file", token, body, content_type)
        if not isinstance(response, dict) or type(response.get("id")) is not int or response["id"] <= 0:
            raise ValueError("CurseForge did not confirm a positive uploaded file ID; inspect the project before retrying")
        receipt["uploads"][target] = {"file_id": response["id"], "sha256": assets[target]["sha256"]}
        save_receipt(receipt_path, receipt)
        print(f"{target}: confirmed CurseForge file {response['id']}")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    publish(args.bundle, args.receipt, os.environ.get("CURSEFORGE_PROJECT_ID", ""),
            os.environ.get("CURSEFORGE_API_TOKEN", ""), os.environ.get("SOURCE_SHA", ""))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as exception:
        sys.exit(str(exception))
