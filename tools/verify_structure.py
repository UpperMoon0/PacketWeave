#!/usr/bin/env python3
"""Check target matrix and that API core does not depend on a Minecraft loader."""
from pathlib import Path
import json, struct, tomllib, unittest
ROOT=Path(__file__).resolve().parents[1]
from release_contract import TARGETS as TARGET_MATRIX
TARGETS = {item["target"]: int(item["runtime_java"]) for item in TARGET_MATRIX}
class Verify(unittest.TestCase):
    def test_target_matrix(self):
        for target, java in TARGETS.items():
            base=ROOT/"targets"/target
            with self.subTest(target=target):
                for f in ("settings.gradle","build.gradle","gradle.properties","gradlew","gradlew.bat","gradle/wrapper/gradle-wrapper.jar","gradle/wrapper/gradle-wrapper.properties"):
                    self.assertTrue((base/f).is_file(),str(base/f))
                build=(base/"build.gradle").read_text()
                if target == "forge-1.12.2":
                    self.assertIn("sourceCompatibility = targetCompatibility = '1.8'", build)
                    self.assertIn("ForgeGradle:3.0.197", build)
                else:
                    self.assertIn("JavaLanguageVersion.of("+str(java)+")",build)
                self.assertNotIn("architectury",build.lower())
    def test_loader_metadata(self):
        for target in TARGETS:
            base=ROOT/"targets"/target/"src/main/resources"
            mc=target.split("-",1)[1]
            with self.subTest(target=target):
                if target.startswith("fabric"):
                    metadata=json.loads((base/"fabric.mod.json").read_text())
                    self.assertEqual(metadata["id"],"packetweave")
                    self.assertEqual(metadata["depends"]["minecraft"],mc)
                elif target == "forge-1.12.2":
                    metadata = json.loads((base/"mcmod.info").read_text())[0]
                    self.assertEqual(metadata["modid"], "packetweave")
                    self.assertEqual(metadata["mcversion"], "${minecraft_version}")
                    self.assertEqual(json.loads((base/"pack.mcmeta").read_text())["pack"]["pack_format"], 3)
                else:
                    file="mods.toml" if target.startswith("forge") else "neoforge.mods.toml"
                    metadata=(base/"META-INF"/file).read_text()
                    self.assertIn('modId="packetweave"',metadata)
                    self.assertIn(mc,metadata)
                    if target.startswith("forge-"):
                        pack=json.loads((base/"pack.mcmeta").read_text())["pack"]
                        self.assertEqual({"1.16.5":6,"1.20.1":15}[mc],pack["pack_format"])
                        self.assertTrue(pack["description"])
    def test_requested_lanes_and_independent_toolchains(self):
        self.assertTrue({"forge-1.12.2", "fabric-1.16.5", "forge-1.16.5", "fabric-26.2", "neoforge-26.2"}.issubset(TARGETS))
        self.assertNotIn("fabric-1.12.2", TARGETS)
        self.assertEqual(set(TARGETS), {path.name for path in (ROOT/"targets").iterdir() if path.is_dir()})
        for target, gradle in {"forge-1.12.2": "5.6.4", "fabric-26.2": "9.5.1", "neoforge-26.2": "9.2.1"}.items():
            wrapper = (ROOT/"targets"/target/"gradle/wrapper/gradle-wrapper.properties").read_text()
            self.assertIn("gradle-" + gradle + "-bin.zip", wrapper)
        fabric = (ROOT/"targets/fabric-26.2/build.gradle").read_text()
        self.assertIn("net.fabricmc.fabric-loom'", fabric)
        self.assertNotIn("fabric-loom-remap", fabric)
        self.assertNotIn("mappings ", fabric)

    def test_neoforge_262_uses_square_icon_without_legacy_logo(self):
        metadata = tomllib.loads((ROOT/"targets/neoforge-26.2/src/main/resources/META-INF/neoforge.mods.toml").read_text())
        self.assertEqual(metadata["mods"][0]["iconFile"], "assets/packetweave/icon.png")
        self.assertNotIn("logoFile", metadata)
        self.assertNotIn("logoFile", metadata["mods"][0])
        png = (ROOT/"icon.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        self.assertGreater(width, 0)
        self.assertEqual(width, height)

    def test_core_has_no_loader_dependencies(self):
        for file in (ROOT/"core/src/main/java").rglob("*.java"):
            text=file.read_text()
            for prefix in ("net.minecraft.","net.fabricmc.","net.minecraftforge.","net.neoforged.","dev.architectury."):
                self.assertNotIn(prefix,text,str(file))
    def test_ci_and_readme(self):
        self.assertTrue((ROOT/".github/workflows/ci.yml").exists())
        self.assertTrue((ROOT/"README.md").exists())
if __name__=="__main__":unittest.main()
