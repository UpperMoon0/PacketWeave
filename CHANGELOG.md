# Changelog

## 0.1.4

- Add native Forge 1.12.2 and Fabric/NeoForge 26.2 library artifacts while preserving the shared Java 8 API and existing 1.16.5 lanes.
- Extend CI and artifact verification to eleven native targets, including legacy FML metadata and bytecode compatibility checks.
- Run the shared bounds, authorization, transfer and lifecycle test suite on Java 8, 17 and 25.

## 0.1.2

- Add nonblocking, bounded background file ingestion with one outstanding indexed chunk per transfer.
- Enforce global/per-owner session limits without retaining whole asset files.
- Add cumulative remote-receipt waiting with timeout, cancellation and stale receipt rejection.
- Clean partial files off the caller thread after cancellation, disconnect, expiry and shutdown.
- Test 60 MiB content parity, blocked disk backpressure, limits, replay/order, failure and cleanup.
- Keep cancellation effective through final validation and retry partial-file cleanup within session limits.
- Add bounded multi-packet executor batches for latency-sensitive file downloads.

## 0.1.1

- Add bounded receive mode for existing indexed packet adapters.
- Share file and memory chunk senders, including short-read and file-change checks.
- Bound worker-to-game-thread dispatch and check trusted file size limits at stream open.
- Add expiry-aware session lookup and connection-wide cleanup.
- Test bounded legacy transfers, limits, sender parity, and cancellation.
- Add release contracts, all-target packaging, source checksums, GitHub releases and configurable CurseForge publishing.
- Include version-correct Forge resource-pack metadata so normal client startup does not stop at a missing-metadata warning.
- Document standalone public-API consumption, required loader/CurseForge dependencies, and safe relocation requirements for optional private embedding.
