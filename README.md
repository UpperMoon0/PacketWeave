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

## Features

- Namespaced transfer IDs associated with a server-authenticated sender UUID.
- Explicit transfer authorization hooks on begin, chunk receive, and completion.
- Indexed chunk reassembly, including out-of-order packets and duplicate rejection.
- Bounded receive mode for existing indexed protocols without an exact-length header.
- File and byte-array senders with stable chunk geometry, short-read handling, and file-change detection.
- Bounded per-transfer, per-owner, global session, and total memory budgets.
- Expiration, cancellation, owner-disconnect cleanup, and SHA-256 digest utility.
- Tests for resource limits, permissions, replay/duplicate chunks and expiration.

### Transfer API

PacketWeave exposes a public Java API packaged as native loader mods. It manages transfer sessions, indexed chunk assembly, resource budgets, authorization callbacks, and cleanup. File and byte-array senders support bounded dispatch through an executor.

The API integrates with native loader packets. Bind each transfer owner to the authenticated connection and apply permission and content-validation policies through the integration.

## Installation

Install the **native loader jar** matching your Minecraft version and loader in `mods` on the client, server, or both, as required by the integration. The `packetweave-core` jar is a development/library artifact, not a substitute for the native mod jar.

PacketWeave has no Architectury API or Fabric API requirement of its own. Download from approved [CurseForge files](https://www.curseforge.com/minecraft/mc-mods/packetweave/files) or [GitHub release assets](https://github.com/UpperMoon0/PacketWeave/releases); do not mix loader/game-version artifacts.

## Runtime library integration

Use the public `com.nstut.packetweave.api` package supplied by the standalone mod and declare `packetweave` as a **required** dependency in every consuming loader descriptor. Declare the corresponding required dependency on CurseForge release files too; CurseForge relations identify the project while loader metadata enforces the minimum version.

For builds without a published Maven repository, pin this repository as a Git submodule and compile `core/src/main/java` into a separate compile-only API project. Unit tests may use that project's runtime output. Do not put those classes in the consuming mod's production jar. Development game launches still require the matching native PacketWeave jar.

If an integration deliberately embeds the MIT core, it must relocate the entire public package to its own private namespace and include `LICENSE`. Shipping unrelocated copies alongside the standalone mod (or another embedding consumer) creates split-package failures on Forge/NeoForge.

Use `beginBounded(id, totalChunks, trustedByteLimit)` only for legacy packets without an exact byte length. The receiver supplies the limit. `contains(id)` reaps expired state before metadata lookup; `clear()` releases all sessions on connection shutdown. Reject changed packet metadata and authorize every chunk in the adapter. Prefer `begin` when the wire protocol declares an exact length.

`ChunkedTransfer.send` and `streamFile` emit nonempty chunks up to `CHUNK_BYTES`. Both reject empty files; streaming fills short reads and reports files that shrink or grow. Worker-to-game-thread dispatch can use `ChunkedTransfer.onExecutor` to bound outstanding chunks and abort stalled dispatch. This acknowledges local submission, not remote receipt; bandwidth pacing and remote acknowledgements remain the adapter’s responsibility.

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

## Releases and publishing

CI tests the core and release tooling, builds all eight targets, and checks the production jars' metadata, core classes and MIT license. PRs that change release configuration also run the complete release bundle dry run.

Changing root `mod_version` on `main` triggers verified GitHub release assets and optional CurseForge uploads. Configure the repository variable `CURSEFORGE_PROJECT_ID` and secret `CURSEFORGE_API_TOKEN` when the listing is available. GitHub releases work while the project ID is unset; manual publishing on `main` can upload the same version after it is supplied.

See [RELEASING.md](RELEASING.md) for version/changelog requirements, dry runs, publish receipts, and all required configuration.

MIT licensed.
