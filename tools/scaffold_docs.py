from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def write(name,body):
    p=ROOT/name
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(body.strip().replace("DOLLAR_",chr(36)).replace("BTICK",chr(96))+"\n",encoding="utf-8",newline="\n")
    print("created",name)
write("tools/build_matrix.py",r'''
#!/usr/bin/env python3
"""Build native mod jars with independent Forge/Fabric/NeoForge Gradle installations."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
TARGETS=[
"fabric-1.16.5","forge-1.16.5",
"fabric-1.20.1","forge-1.20.1",
"fabric-1.21.1","neoforge-1.21.1",
"fabric-26.1.2","neoforge-26.1.2",
]
def command_for(target, task):
    if target not in TARGETS: raise ValueError(target)
    root=ROOT/"targets"/target
    wrapper=root/("gradlew.bat" if os.name=="nt" else "gradlew")
    return [str(wrapper),task,"--no-daemon","--stacktrace"]
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("task",choices=("build","test","compileJava","tasks"),nargs="?",default="build")
    parser.add_argument("--target",choices=TARGETS)
    parser.add_argument("--all",action="store_true")
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    if not args.all and not args.target:parser.error("specify --target or --all")
    for target in (TARGETS if args.all else [args.target]):
        cmd=command_for(target,args.task)
        print(target, " ".join(cmd),flush=True)
        if not args.dry_run:
            rc=subprocess.call(cmd,cwd=str(ROOT/"targets"/target))
            if rc: return rc
    return 0
if __name__=="__main__":sys.exit(main())
''')
write("tools/verify_structure.py",r'''
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
''')
write(".github/workflows/ci.yml",r'''
name: Build and test
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  core:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Verify target matrix
        run: python3 tools/verify_structure.py
      - name: Core unit tests
        run: ./gradlew :core:test --no-daemon
  matrix:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - {target: fabric-1.16.5, java: '25'}
          - {target: forge-1.16.5, java: '17'}
          - {target: fabric-1.20.1, java: '25'}
          - {target: forge-1.20.1, java: '17'}
          - {target: fabric-1.21.1, java: '25'}
          - {target: neoforge-1.21.1, java: '25'}
          - {target: fabric-26.1.2, java: '25'}
          - {target: neoforge-26.1.2, java: '25'}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: DOLLAR_{{ matrix.java }}
      - uses: gradle/actions/setup-gradle@v4
      - name: Build native loader jar
        working-directory: targets/DOLLAR_{{ matrix.target }}
        run: ./gradlew build --no-daemon --stacktrace
      - uses: actions/upload-artifact@v4
        with:
          name: packetweave-DOLLAR_{{ matrix.target }}
          path: targets/DOLLAR_{{ matrix.target }}/build/libs/packetweave-*.jar
          if-no-files-found: error
''')
write("README.md",r'''
# PacketWeave

A focused transfer library for **bounded binary asset transfers** between Minecraft clients and servers.
It is designed to be useful for media, structure files, and other mod-defined payloads.

## Target matrix

| Minecraft | Fabric | Forge | NeoForge | Java |
|---|---|---|---|---|
| 1.16.5 | yes | yes | - | 8 |
| 1.20.1 | yes | yes | - | 17 |
| 1.21.1 | yes | - | yes | 21 |
| 26.1.2 | yes | - | yes | 25 |

Eight independent native projects live under BTICKtargets/BTICK. This is intentional: ForgeGradle 6, ModDevGradle 2, obfuscated Fabric Loom, and non-obfuscated Fabric Loom must be able to evolve separately.

**No Architectury API or Architectury Loom dependency.** The implementation uses native loader toolchains and a shared Java 8-compatible core from BTICKcore/src/main/javaBTICK. The core sources are compiled into each target jar; no separate core jar is needed at runtime.

## Implemented

- Namespaced transfer IDs associated with a server-authenticated sender UUID.
- Explicit transfer authorization hooks on begin, chunk receive, and completion.
- Indexed chunk reassembly, including out-of-order packets and duplicate rejection.
- Bounded per-transfer, per-owner, global session, and total memory budgets.
- Expiration, cancellation, owner-disconnect cleanup, and SHA-256 digest utility.
- Tests for resource limits, permissions, replay/duplicate chunks and expiration.

### Scope and status

**This initial version is a functional Java transfer core and native multi-platform build structure, not a completed networking release.** Fabric, Forge and NeoForge loader entrypoints are scaffolded, but do not yet register an on-wire transfer protocol. Future code must add native packet registration, server-client integration tests, backpressure, and disk staging. Do not claim that uploads or cross-loader networking work yet.

Minecraft version targets use native loader APIs. Client/server permission checks, media decoding and validation remain the responsibility of the consuming mod. A transfer ID owner must be obtained from the authenticated connection, **never accepted from an untrusted packet**.

## Developer example

BTICKBTICKBTICKjava
TransferRegistry transfers = new TransferRegistry(TransferLimits.defaults(),
    (id, operation) -> myPermissionService.canTransfer(id.owner(), id.namespace(), operation));
TransferId key = new TransferId("your_mod", authenticatedSenderUuid, transferUuid);
if (transfers.begin(key, totalChunks, declaredBytes)) {
    transfers.accept(key, index, bytes);
    byte[] result = transfers.complete(key);
    if (result != null) {
        // Verify expected content digest and validate the file before publishing.
    }
}
BTICKBTICKBTICK

## Build and test

BTICKBTICKBTICKpowershell
.\gradlew.bat :core:test --no-daemon
python tools/verify_structure.py
python tools/build_matrix.py build --target fabric-1.20.1
python tools/build_matrix.py build --all
BTICKBTICKBTICK

Use Java 17 to run the Gradle 8.x Forge builds, and Java 25 for newer Fabric and NeoForge builds. Each target Gradle build compiles classes to Java 8, 17, 21, or 25 as required.

Every target has its own Gradle wrapper. Core and target builds are independent and do not require importing unrelated loader plugins. See BTICK.github/workflows/ci.ymlBTICK.

MIT licensed.
''')
p=ROOT/"core/src/test/java/com/nstut/packetweave/api/TransferRegistryTest.java"
s=p.read_text(encoding="utf-8")
s=s.replace("7192385c3c0605de55bb9476ce1d90748190ecb32a8e66d8c72f2dfb1b2a2b11","7192385c3c0605de55bb9476ce1d90748190ecb32a8eed7f5207b30cf6a1fe89")
p.write_text(s,encoding="utf-8",newline="\n")
print("corrected digest expectation")
