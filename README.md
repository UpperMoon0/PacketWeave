# PacketWeave

A focused transfer library for **bounded binary asset transfers** between Minecraft clients and servers.
It is designed to be useful for media, structure files, and other mod-defined payloads.

## Target matrix

| Minecraft | Fabric | Forge | NeoForge | Java |
|---|---|---|---|---|
| 1.12.2 | - | yes | - | 8 |
| 1.16.5 | yes | yes | - | 8 |
| 1.20.1 | yes | yes | - | 17 |
| 1.21.1 | yes | - | yes | 21 |
| 26.1.2 | yes | - | yes | 25 |
| 26.2 | yes | - | yes | 25 |

Eleven independent native projects live under `targets/`. This is intentional: ForgeGradle 3/6, ModDevGradle 2, obfuscated Fabric Loom, and non-obfuscated Fabric Loom must be able to evolve separately.

**No Architectury API or Architectury Loom dependency.** The implementation uses native loader toolchains and a shared Java 8-compatible core from `core/src/main/java`. The core sources are compiled into each target jar; no separate core jar is needed at runtime.

Fabric is not an official 1.12.2 loader lane; no Legacy Fabric artifact is included. See [PORTING.md](PORTING.md) for the target toolchains, API/lifecycle contract, and verification boundaries.

## Features

- Namespaced transfer IDs associated with a server-authenticated sender UUID.
- Explicit transfer authorization hooks on begin, chunk receive, and completion.
- Contextual transfer registries pin trusted consumer metadata to transfer lifetime and release it on completion, expiry, rejection, disconnect or cancellation.
- Indexed chunk reassembly, including out-of-order packets and duplicate rejection.
- Bounded receive mode for existing indexed protocols without an exact-length header.
- Background file ingestion with indexed single-flight admission and remote-receipt backpressure.
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

`BoundedFileReceiver` owns a dedicated writer and enforces one pending chunk per
session plus global/per-owner limits. `begin` and `accept` do not perform I/O or
wait for disk. Bind `TransferId.owner()` to the authenticated connection, supply
trusted unique temporary paths and declared lengths, and cancel rejected chunks.
Its callbacks run on the writer; dispatch game changes explicitly. The committed
callback receives cumulative bytes and completion, after the write (and final
close). Final validation inside that callback remains within the session budget.
Successful files belong to the integration; partial files are cleaned on the worker.
`close` stops admission without blocking the caller, and cleanup waits for any
current filesystem call to return.

Use `ReceiptGate.expect(cumulativeBytes)` before sending each chunk and
`await(timeout)` on the sending worker. Feed authenticated server write receipts
to `acknowledge`; stale and out-of-window values cannot advance the sender.
This bounds payload memory independently of total file size. It trades throughput
for latency isolation: a single window sends at most one chunk per round trip.

## Developer example

Use `OutboundTransfers.shared().start(connection, transferId, path, byteLimit,
gameExecutor, packetSink, completion)` for receipt-driven native transfers. The
shared scheduler admits at most two transfers per connection and 32 globally,
with no waiting work queue. Each sends at most one 4 KiB chunk before waiting for
an authenticated cumulative-byte receipt. Feed native receipt packets to
`acknowledge(connection, transferId, bytes)`; a negative value rejects a transfer.
Cancel with `cancel` or `cancelPeer` on lifecycle changes. Use the same actual
connection object in every integration so their budgets are shared. Each retry
needs a new transfer UUID. Missing receipts abort after ten seconds; this fails
the transfer, never disconnects the player. Severe underlying network outages
can still time out Minecraft itself.

Dispatch reservations also limit tasks retained by a stalled game executor. A
timed-out worker releases its active session and payload; its queued task keeps a
reservation until it runs or its discarded queue is collected. Admission can
therefore remain busy while an executor is stalled. The shared scheduler does not
retain abandoned connection/executor graphs. Receipt windows open at dispatch,
so receipts sent while a chunk is still queued cannot advance it. Receipts bind
the authenticated connection and transfer ID; recipients must acknowledge
honestly after committing bytes, since byte counts alone do not prove possession.

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

Use Java 8 to run the Forge 1.12.2 Gradle 5.6.4 build, Java 17 to run the Gradle 8.x Forge builds, and Java 25 for Fabric and NeoForge builds. Modern Gradle targets also need their declared compile toolchains. The core suite can additionally run with `:core:testJava8 :core:testJava25` to verify both ends of the supported runtime range. Each target Gradle build compiles classes to Java 8, 17, 21, or 25 as required.

Every target has its own Gradle wrapper. Core and target builds are independent and do not require importing unrelated loader plugins. See `.github/workflows/ci.yml`.

## Releases and publishing

CI tests the core and release tooling, builds all eleven targets, and checks the production jars' metadata, core classes and MIT license. PRs that change release configuration also run the complete release bundle dry run.

Changing root `mod_version` on `main` triggers verified GitHub release assets and optional CurseForge uploads. Configure the repository variable `CURSEFORGE_PROJECT_ID` and secret `CURSEFORGE_API_TOKEN` when the listing is available. GitHub releases work while the project ID is unset; manual publishing on `main` can upload the same version after it is supplied.

See [RELEASING.md](RELEASING.md) for version/changelog requirements, dry runs, publish receipts, and all required configuration.

MIT licensed.
