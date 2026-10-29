# Requested generation ports

PacketWeave is a functional loader-neutral transfer library, not a standalone
file-sharing protocol. Every native jar compiles the same `core/src/main/java`
API directly into the artifact. No copy of decompiled Minecraft code, runtime
Minecraft binary, or consumer-owned packet codec belongs in this repository.

## New and retained lanes

| Target | Loader/toolchain | Gradle JVM | Bytecode/runtime |
| --- | --- | --- | --- |
| Forge 1.12.2 | Forge 14.23.5.2864, ForgeGradle 3.0.197, MCP stable_39-1.12 | Java 8 / Gradle 5.6.4 | Java 8 |
| Fabric 1.16.5 (retained) | Fabric Loader 0.19.5, remapping Loom 1.17.9 | Java 25 / Gradle 9.7.1 | Java 8 |
| Forge 1.16.5 (retained) | Forge 36.2.42, ForgeGradle 6 | Java 17 / Gradle 8.8 | Java 8 |
| Fabric 26.2 | Fabric Loader 0.19.5, unobfuscated Loom 1.17.9 | Java 25 / Gradle 9.5.1 | Java 25 |
| NeoForge 26.2 | NeoForge 26.2.0.93, ModDevGradle 2.0.148 | Java 25 / Gradle 9.2.1 | Java 25 |

For `tools/build_matrix.py --all`, set `JAVA8_HOME`, `JAVA17_HOME`, and
`JAVA25_HOME` to the installed JDK directories; the runner selects the target
Gradle JVM. It also recognizes GitHub setup-java's `JAVA_HOME_<version>_X64`.
For one target, a suitable `JAVA_HOME` is sufficient.

The legacy Forge build follows the official 1.12.2 MDK, including merged
classes/resources output for development launches. Its entrypoint uses FML's
`@Mod` attributes and `mcmod.info`, not modern `mods.toml`. The 26.2 Fabric
build intentionally has no mappings dependency or remap task.

The official Forge 1.12.2
[download index](https://files.minecraftforge.net/net/minecraftforge/forge/index_1.12.2.html)
and [MDK](https://maven.minecraftforge.net/net/minecraftforge/forge/1.12.2-14.23.5.2864/forge-1.12.2-14.23.5.2864-mdk.zip)
are the loader/build references. The
[Fabric 26.2 porting guidance](https://fabricmc.net/2026/06/15/262.html)
identifies the unobfuscated game and Loom/Gradle generation. Version-specific
source audits were consulted for Java 8 legacy and Java 25 unobfuscated game
provenance; source syntax/coverage checks are not evidence of mod runtime tests.

There is no official Fabric 1.12.2 lane. No Legacy Fabric target is added.
Existing 1.20.1, 1.21.1 and 26.1.2 artifacts remain independent and unchanged.

## Security, wire and lifecycle compatibility

Existing public API behavior remains unchanged. A loader entrypoint
makes these classes discoverable as a dependency but deliberately owns no
independent packet channel or disk receiver. The opt-in shared outbound scheduler
coordinates native consumers without installing its own wire protocol. Consumers
still own their packet codecs and connection lifecycle.

Consumers must:

- Bind transfer owners and receipts to authenticated connections, not packet UUIDs.
- Prefer `OutboundTransfers.shared()` for new receipt-paced native outbound transfers.
  Its connection-identity, per-peer and global budgets compose across consumers.
  A single chunk is outstanding until the authenticated receiver acknowledges
  committed cumulative bytes; cancel via `cancel` or `cancelPeer` on lifecycle
  changes. Reuse the actual authenticated connection object and a fresh transfer ID
  for each retry. Dispatch-only `ChunkedTransfer` helpers do not provide remote
  backpressure.
- Keep their existing packet field order, bounds and chunk geometry; use
  `beginBounded` only when an exact-length header is unavailable.
- Apply trusted limits and authorization on admission, each chunk, and completion.
- Pin consumer metadata in `ContextualTransferRegistry`; reject changed metadata.
- Call `cancelOwner` on disconnect and `clear` on connection/server shutdown.
- Close `BoundedFileReceiver` when its owning connection/service closes and abort
  waiting senders/receipt gates. Dispatch game changes onto the game thread.
- Validate completed content before making it visible. PacketWeave does not
  grant permission merely because a transfer was assembled successfully.

## Verification

`python tools/verify_structure.py` validates the full target matrix, metadata,
legacy/modern separation, independent wrappers and absence of loader dependencies
in the core. `python -m unittest discover -s tools -p 'test_*.py'` checks release
selection, metadata, classfile header compatibility and safe release workflow guards.

The normal core build compiles all sources and tests to Java 8. The same suite
can be exercised on Java 8 and Java 25 with `:core:testJava8 :core:testJava25`.
Artifact checks require all eleven top-level core classes; JVM tests exercise the
actual implementations. Header checks are not a full JVM bytecode verifier.
CI requests all three runtimes and builds/verifies every native target.

Receipt-paced sender tests cover backpressure, timeout, cancellation and
authentication using controlled executors. Passing core tests and native builds
do **not** constitute impaired-network Minecraft runtime qualification; clients
and dedicated servers must still be tested for disconnects and gameplay progress
under packet loss and high latency in each consuming integration.

Compile/package checks and core unit tests do not establish that a Minecraft
client or dedicated server started successfully. Consuming mods still need live
end-to-end transfer tests on each requested loader, including disconnect,
rejection, stale receipt and server restart cases. Runtime acceptance and dependent releases remain the responsibility
of the consuming mod integrations.
