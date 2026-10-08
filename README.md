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

Eight independent native projects live under `targets/`. This is intentional: ForgeGradle 6, ModDevGradle 2, obfuscated Fabric Loom, and non-obfuscated Fabric Loom must be able to evolve separately.

**No Architectury API or Architectury Loom dependency.** The implementation uses native loader toolchains and a shared Java 8-compatible core from `core/src/main/java`. The core sources are compiled into each target jar; no separate core jar is needed at runtime.

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

```java
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
```

## Build and test

```powershell
.\gradlew.bat :core:test --no-daemon
python tools/verify_structure.py
python tools/build_matrix.py build --target fabric-1.20.1
python tools/build_matrix.py build --all
```

Use Java 17 to run the Gradle 8.x Forge builds, and Java 25 for newer Fabric and NeoForge builds. Each target Gradle build compiles classes to Java 8, 17, 21, or 25 as required.

Every target has its own Gradle wrapper. Core and target builds are independent and do not require importing unrelated loader plugins. See `.github/workflows/ci.yml`.

MIT licensed.
