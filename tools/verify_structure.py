#!/usr/bin/env python3
"""Check target matrix and that API core does not depend on a Minecraft loader."""
from pathlib import Path
import json, unittest
ROOT=Path(__file__).resolve().parents[1]
TARGETS={
"fabric-1.16.5":8,"forge-1.16.5":8,
"fabric-1.20.1":17,"forge-1.20.1":17,
"fabric-1.21.1":21,"neoforge-1.21.1":21,
"fabric-26.1.2":25,"neoforge-26.1.2":25,
}
class Verify(unittest.TestCase):
    def test_target_matrix(self):
        for target, java in TARGETS.items():
            base=ROOT/"targets"/target
            with self.subTest(target=target):
                for f in ("settings.gradle","build.gradle","gradle.properties","gradlew","gradlew.bat","gradle/wrapper/gradle-wrapper.jar","gradle/wrapper/gradle-wrapper.properties"):
                    self.assertTrue((base/f).is_file(),str(base/f))
                build=(base/"build.gradle").read_text()
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
                else:
                    file="mods.toml" if target.startswith("forge") else "neoforge.mods.toml"
                    metadata=(base/"META-INF"/file).read_text()
                    self.assertIn('modId="packetweave"',metadata)
                    self.assertIn(mc,metadata)
    def test_core_has_no_loader_dependencies(self):
        for file in (ROOT/"core/src/main/java").rglob("*.java"):
            text=file.read_text()
            for prefix in ("net.minecraft.","net.fabricmc.","net.minecraftforge.","net.neoforged.","dev.architectury."):
                self.assertNotIn(prefix,text,str(file))
    def test_ci_and_readme(self):
        self.assertTrue((ROOT/".github/workflows/ci.yml").exists())
        self.assertTrue((ROOT/"README.md").exists())
if __name__=="__main__":unittest.main()
