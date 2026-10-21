import ast
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
import zipfile

import release_contract as release
import publish_curseforge as curseforge


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        shutil.copy(release.ROOT / "gradle.properties", self.root / "gradle.properties")
        (self.root / "core").mkdir()
        shutil.copy(release.ROOT / "core/build.gradle", self.root / "core/build.gradle")
        self.version = release.config(self.root)["mod_version"]
        (self.root / "changelog").mkdir()
        (self.root / "changelog" / f"{self.version}.md").write_text("Release fixture\n")
        for target in release.TARGETS:
            path = self.root / "targets" / target["target"]
            path.mkdir(parents=True)
            (path / "gradle.properties").write_text(f"mod_version={self.version}\nminecraft_version={target['minecraft']}\n")
        self.sha = "a" * 40
        self.artifacts = Path(self.temporary.name) / "artifacts"
        for target in ["core"] + [item["target"] for item in release.TARGETS]:
            directory = self.artifacts / f"packetweave-{target}"
            directory.mkdir(parents=True)
            self.make_jar(directory / release.filename(target, self.version), target)

    def make_jar(self, path, target, version=None):
        version = version or self.version
        with zipfile.ZipFile(path, "w") as archive:
            for name in release.CORE_CLASSES:
                archive.writestr(f"com/nstut/packetweave/api/{name}.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            archive.writestr("META-INF/LICENSE-PacketWeave", "MIT License\n")
            if target == "core":
                return
            archive.writestr("assets/packetweave/icon.png", (release.ROOT / "icon.png").read_bytes())
            loader, minecraft = target.split("-", 1)
            entrypoint = {"fabric": "PacketWeaveFabric", "forge": "PacketWeaveForge", "neoforge": "PacketWeaveNeoForge"}[loader]
            archive.writestr(f"com/nstut/packetweave/{loader}/{entrypoint}.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            if loader == "forge":
                archive.writestr("pack.mcmeta", json.dumps({"pack": {"pack_format": {"1.12.2": 3, "1.16.5": 6, "1.20.1": 15}[minecraft], "description": "PacketWeave resources"}}))
            if loader == "fabric":
                archive.writestr("fabric.mod.json", json.dumps({"id": "packetweave", "version": version, "icon": "assets/packetweave/icon.png", "depends": {"minecraft": minecraft}}))
            elif target == "forge-1.12.2":
                archive.writestr("mcmod.info", json.dumps([{"modid": "packetweave", "version": version, "mcversion": minecraft, "logoFile": "assets/packetweave/icon.png"}]))
            else:
                name = "mods.toml" if loader == "forge" else "neoforge.mods.toml"
                archive.writestr(f"META-INF/{name}", f'[[mods]]\nmodId="packetweave"\nversion="{version}"\n{release.native_icon_field(target)}="assets/packetweave/icon.png"\n[[dependencies.packetweave]]\nmodId="minecraft"\nversionRange="[{minecraft},)"\n')

    def make_bundle(self):
        directory = Path(self.temporary.name) / "bundle"
        release.bundle(self.artifacts, directory, self.version, self.sha)
        return directory

    def available_tags(self):
        names = set().union(*(set(curseforge.metadata(target, self.version, "release", "fixture")["gameVersionNames"]) for target in release.TARGETS))
        return [{"name": name} for name in names]

    def test_repository_release_contract_and_all_requested_targets(self):
        release.verify()
        self.assertEqual(11, len(release.TARGETS))
        self.assertEqual({8, 17, 21, 25}, {int(item["runtime_java"]) for item in release.TARGETS})

    def test_neoforge_262_icon_contract_preserves_older_metadata(self):
        self.assertEqual("iconFile", release.native_icon_field("neoforge-26.2"))
        for target in ("neoforge-26.1.2", "neoforge-1.21.1", "forge-1.20.1", "forge-1.16.5", "forge-1.12.2"):
            self.assertEqual("logoFile", release.native_icon_field(target))
        target = "neoforge-26.2"
        path = self.artifacts / f"packetweave-{target}" / release.filename(target, self.version)
        release.inspect_jar(path, target, self.version)

    def test_neoforge_scaffold_renders_version_specific_icon_field(self):
        # Load only the pure formatter and template, never execute the historical
        # scaffold script's repository-writing top-level code.
        tree = ast.parse((release.ROOT / "tools/scaffold_targets.py").read_text())
        nodes = [node for node in tree.body if
                 isinstance(node, ast.FunctionDef) and node.name == "fmt" or
                 isinstance(node, ast.Assign) and any(isinstance(name, ast.Name) and name.id == "neo_toml" for name in node.targets)]
        namespace = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "scaffold-template", "exec"), namespace)
        for minecraft, upper, expected in [("26.2", "26.3", "iconFile"), ("26.1.2", "26.2", "logoFile"), ("1.21.1", "1.22", "logoFile")]:
            rendered = namespace["fmt"](namespace["neo_toml"], MC=minecraft, UP=upper,
                                        ICONFIELD=release.native_icon_field("neoforge-" + minecraft))
            mod = tomllib.loads(rendered)["mods"][0]
            self.assertEqual(mod[expected], "assets/packetweave/icon.png")
            self.assertNotIn("logoFile" if expected == "iconFile" else "iconFile", mod)

    def test_neoforge_262_rejects_deprecated_logo_at_file_or_mod_level(self):
        target = "neoforge-26.2"
        path = self.artifacts / f"packetweave-{target}" / release.filename(target, self.version)
        key = "META-INF/neoforge.mods.toml"
        for location in ("replacement", "alongside-icon", "file"):
            with self.subTest(location=location):
                self.make_jar(path, target)
                def add_deprecated_metadata(entries):
                    text = entries[key].decode()
                    logo = 'logoFile="assets/packetweave/icon.png"\n'
                    if location == "replacement":
                        text = text.replace("iconFile=", "logoFile=")
                    elif location == "alongside-icon":
                        text = text.replace("[[mods]]\n", "[[mods]]\n" + logo)
                    else:
                        text = logo + text
                    entries[key] = text.encode()
                self.rewrite_jar(path, add_deprecated_metadata)
                with self.assertRaisesRegex(ValueError, "Deprecated NeoForge 26.2 logoFile"):
                    release.inspect_jar(path, target, self.version)

    def test_requested_lanes_select_the_correct_gradle_runtime(self):
        matrix = {item["target"]: item for item in release.TARGETS}
        self.assertEqual("8", matrix["forge-1.12.2"]["java"])
        self.assertEqual("17", matrix["forge-1.16.5"]["java"])
        self.assertEqual("25", matrix["fabric-26.2"]["java"])
        self.assertEqual("25", matrix["neoforge-26.2"]["java"])
        self.assertNotIn("fabric-1.12.2", matrix)

    def rewrite_jar(self, path, transform):
        with zipfile.ZipFile(path) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        transform(entries)
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

    def test_all_functional_api_classes_are_required(self):
        path = self.artifacts / "packetweave-forge-1.12.2" / release.filename("forge-1.12.2", self.version)
        self.rewrite_jar(path, lambda entries: entries.pop("com/nstut/packetweave/api/BoundedFileReceiver.class"))
        with self.assertRaisesRegex(ValueError, "Missing core classes"):
            release.inspect_jar(path, "forge-1.12.2", self.version)

    def test_legacy_jar_rejects_newer_java_bytecode(self):
        path = self.artifacts / "packetweave-forge-1.12.2" / release.filename("forge-1.12.2", self.version)
        def newer_class(entries):
            entries["com/nstut/packetweave/api/TransferRegistry.class"] = bytes.fromhex("cafebabe0000003d")
        self.rewrite_jar(path, newer_class)
        with self.assertRaisesRegex(ValueError, "Class exceeds Java 8"):
            release.inspect_jar(path, "forge-1.12.2", self.version)

    def test_legacy_forge_requires_expanded_mcmod_metadata(self):
        path = self.artifacts / "packetweave-forge-1.12.2" / release.filename("forge-1.12.2", self.version)
        self.make_jar(path, "forge-1.12.2", "${mod_version}")
        with self.assertRaisesRegex(ValueError, "Incorrect legacy Forge metadata"):
            release.inspect_jar(path, "forge-1.12.2", self.version)
        self.make_jar(path, "forge-1.12.2")
        self.rewrite_jar(path, lambda entries: entries.update({"META-INF/mods.toml": b"modern metadata"}))
        with self.assertRaisesRegex(ValueError, "Modern Forge metadata"):
            release.inspect_jar(path, "forge-1.12.2", self.version)

    def test_root_target_core_and_changelog_must_agree(self):
        release.verify(self.root)
        path = self.root / "targets/fabric-1.20.1/gradle.properties"
        path.write_text("mod_version=9.9.9\nminecraft_version=1.20.1\n")
        with self.assertRaisesRegex(ValueError, "Target version mismatch"):
            release.verify(self.root)
        path.write_text(f"mod_version={self.version}\nminecraft_version=1.20.1\n")
        (self.root / "changelog" / f"{self.version}.md").unlink()
        with self.assertRaisesRegex(ValueError, "Missing release changelog"):
            release.verify(self.root)

    def test_invalid_version_release_type_and_duplicate_properties_fail(self):
        for text in ["mod_version=../../bad\nrelease_type=release", "mod_version=0.1.1\nrelease_type=bogus", "mod_version=0.1.1\nmod_version=0.1.2\nrelease_type=release"]:
            (self.root / "gradle.properties").write_text(text)
            with self.assertRaises(ValueError):
                release.config(self.root)

    def test_only_version_changes_or_manual_force_release(self):
        self.assertFalse(release.version_changed(self.version, f"mod_version = {self.version}\n"))
        self.assertTrue(release.version_changed(self.version, "mod_version=0.1.0"))
        self.assertTrue(release.version_changed(self.version, "org.gradle.jvmargs=-Xmx2G"))
        self.assertTrue(release.version_changed(self.version, None))
        self.assertTrue(release.version_changed(self.version, f"mod_version={self.version}", True))

    def test_complete_bundle_has_exact_matrix_checksums_and_source(self):
        directory = self.make_bundle()
        manifest, _ = curseforge.release_assets(directory, self.sha, self.root)
        self.assertEqual(len(release.TARGETS) + 1, len(manifest["assets"]))
        self.assertEqual(self.sha, manifest["source_sha"])
        self.assertEqual(len(release.TARGETS) + 1, len((directory / "SHA256SUMS").read_text().splitlines()))
        self.assertEqual(len(release.TARGETS) + 1, len(list(directory.glob("*.jar"))))

    def test_missing_target_or_stray_jar_cannot_produce_partial_bundle(self):
        path = self.artifacts / "packetweave-fabric-1.20.1"
        jar = path / release.filename("fabric-1.20.1", self.version)
        jar.rename(path / "unexpected.jar")
        output = Path(self.temporary.name) / "output"
        with self.assertRaises(ValueError):
            release.bundle(self.artifacts, output, self.version, self.sha)
        self.assertFalse(output.exists())
        (path / "unexpected.jar").rename(jar)
        shutil.copy(jar, self.artifacts / "stray.jar")
        with self.assertRaisesRegex(ValueError, "unexpected or duplicate"):
            release.bundle(self.artifacts, output, self.version, self.sha)

    def test_sources_are_never_selected_as_runnable_jars(self):
        path = self.artifacts / "packetweave-core"
        shutil.copy(next(path.glob("*.jar")), path / f"packetweave-core-{self.version}-sources.jar")
        self.assertEqual(release.filename("core", self.version), release.production_jar(path, "core", self.version).name)

    def test_wrong_metadata_or_missing_license_cannot_publish(self):
        path = self.artifacts / "packetweave-forge-1.16.5" / release.filename("forge-1.16.5", self.version)
        self.make_jar(path, "forge-1.16.5", "9.9.9")
        with self.assertRaisesRegex(ValueError, "Incorrect loader metadata"):
            release.inspect_jar(path, "forge-1.16.5", self.version)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("com/nstut/packetweave/api/TransferRegistry.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
        with self.assertRaisesRegex(ValueError, "Missing core classes or license"):
            release.inspect_jar(path, "forge-1.16.5", self.version)

    def test_forge_pack_metadata_is_required_and_version_specific(self):
        for target in ("forge-1.12.2", "forge-1.16.5", "forge-1.20.1"):
            path = self.artifacts / f"packetweave-{target}" / release.filename(target, self.version)
            with self.subTest(target=target):
                release.inspect_jar(path, target, self.version)
                with zipfile.ZipFile(path) as archive:
                    entries = {name: archive.read(name) for name in archive.namelist() if name != "pack.mcmeta"}
                for pack in (None, {"pack_format": 1, "description": "wrong version"}, {"pack_format": 6}):
                    with zipfile.ZipFile(path, "w") as archive:
                        for name, data in entries.items():
                            archive.writestr(name, data)
                        if pack is not None:
                            archive.writestr("pack.mcmeta", json.dumps({"pack": pack}))
                    with self.assertRaisesRegex(ValueError, "Forge pack metadata"):
                        release.inspect_jar(path, target, self.version)

    def test_bundle_source_and_hash_drift_fail(self):
        directory = self.make_bundle()
        with self.assertRaisesRegex(ValueError, "different source"):
            curseforge.release_assets(directory, "b" * 40, self.root)
        manifest_path = directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["assets"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            curseforge.release_assets(directory, self.sha, self.root)

    def test_missing_ids_and_token_do_not_touch_network(self):
        def never(*args):
            self.fail("must not contact publisher")
        for project, token in [("", "token"), ("placeholder", "token"), ("123", "")]:
            with self.assertRaises(ValueError):
                curseforge.publish(Path("unused"), Path("unused"), project, token, self.sha, self.root, never)

    def test_every_tag_is_checked_before_any_upload(self):
        directory = self.make_bundle()
        calls = []
        def api(path, *args):
            calls.append(path)
            return []
        with self.assertRaisesRegex(ValueError, "Unknown CurseForge tags"):
            curseforge.publish(directory, directory / "receipt.json", "123", "token", self.sha, self.root, api)
        self.assertEqual(["/game/versions"], calls)

    def test_native_uploads_use_correct_tags_without_screens_dependencies(self):
        directory = self.make_bundle()
        uploads = []
        def api(path, token, *data):
            if path == "/game/versions":
                return self.available_tags()
            self.assertEqual("/projects/123/upload-file", path)
            body, content_type = data
            self.assertIn("multipart/form-data", content_type)
            self.assertNotIn(b'"relations"', body)
            self.assertNotIn(b"architectury-api", body)
            self.assertNotIn(b"openui-mc", body)
            self.assertNotIn(b"fabric-api", body)
            uploads.append(body)
            return {"id": len(uploads)}
        with contextlib.redirect_stdout(io.StringIO()):
            receipt = curseforge.publish(directory, directory / "receipt.json", "123", "token", self.sha, self.root, api)
        self.assertEqual(len(release.TARGETS), len(uploads))
        self.assertEqual(len(release.TARGETS), len(receipt["uploads"]))
        self.assertNotIn("core", receipt["uploads"])

    def test_partial_failure_retry_uses_confirmed_hash_receipts(self):
        directory = self.make_bundle()
        receipt = directory / "receipt.json"
        uploads = []
        def first_api(path, token, *data):
            if path == "/game/versions":
                return self.available_tags()
            uploads.append(path)
            if len(uploads) == 3:
                raise ValueError("upload interrupted")
            return {"id": len(uploads)}
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "interrupted"):
            curseforge.publish(directory, receipt, "123", "token", self.sha, self.root, first_api)
        self.assertEqual(2, len(json.loads(receipt.read_text())["uploads"]))
        retry_uploads = []
        def retry_api(path, token, *data):
            if path == "/game/versions":
                return self.available_tags()
            retry_uploads.append(path)
            return {"id": 100 + len(retry_uploads)}
        with contextlib.redirect_stdout(io.StringIO()):
            curseforge.publish(directory, receipt, "123", "token", self.sha, self.root, retry_api)
        self.assertEqual(len(release.TARGETS) - 2, len(retry_uploads))
        with self.assertRaisesRegex(ValueError, "another source, version or project"):
            curseforge.publish(directory, receipt, "124", "token", self.sha, self.root, retry_api)

    def test_unconfirmed_response_is_not_recorded_as_success(self):
        directory = self.make_bundle()
        receipt = directory / "receipt.json"
        def api(path, token, *data):
            return self.available_tags() if path == "/game/versions" else {"error": "already uploaded"}
        with self.assertRaisesRegex(ValueError, "did not confirm"):
            curseforge.publish(directory, receipt, "123", "token", self.sha, self.root, api)
        self.assertEqual({}, json.loads(receipt.read_text())["uploads"])


if __name__ == "__main__":
    unittest.main()
