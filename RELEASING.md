# PacketWeave — Jenkins release operations

PacketWeave versioning, builds, checks and publishing are being migrated to
**Jenkins-only** execution under [KAN-73](https://nstut.atlassian.net/browse/KAN-73).
GitHub Actions execution is disabled at repository level; never re-enable it,
depend on its status/artifacts, or store a new publishing secret there.

## Native, credential-free verification

The reviewed `Jenkinsfile` uses central `nstut-ci` and a qualified general
Linux executor to run Python release-contract tests, structure verification,
the Java 8/25 core tests and all 11 native loader builds. It archives exact
source evidence and verifies runtime/loader metadata, MIT license and
production JARs. `Jenkinsfile.release` is a **candidate** credential-free
13-stage dry run: same 12 build targets followed by full source-pinned
bundle verification, including `release-manifest.json` and `SHA256SUMS`.
Neither Jenkinsfile injects publishing secrets or writes GitHub/CurseForge
releases.

**Current limitation:** the signed release webhook event route, strict
Jenkins PR/check authority, protected publisher, receipt persistence,
rollbacks and physical retirement of legacy workflow YAMLs are not yet
fully accepted. Do not infer an authorized publication from a successful
build or from this configuration document.

## Production credential source of truth

Only a **root-owned NsTut-CICD protected publishing broker** may retrieve
secrets, and only at the time of an independently verified publication.
The bound reader lives at
`UpperMoon0/NsTut-CICD/jenkins/migration/packetweave/kv_credentials.py`,
using the existing host certificate-backed
`/usr/local/lib/nstut-jenkins/artifacts/identity.py:vault()`.
Azure Key Vault is `https://nstutcommonkv.vault.azure.net`.

| Purpose | Fixed Key Vault secret |
| --- | --- |
| CurseForge upload for PacketWeave | `curseforge-api-token` |
| GitHub tag/release and asset write for PacketWeave only | `packetweave-github-release-token` |

CurseForge project **1735096** is a public, pinned project ID and **not**
a credential. The shared CurseForge token has been read successfully from
Key Vault by the protected NsTut-CICD certificate identity. The dedicated
GitHub Release token is currently unavailable to that identity: provision a
fine-grained credential for `UpperMoon0/PacketWeave` with **Contents: Read
and write**, store it at the fixed Key Vault name and grant the existing
protected identity `Key Vault Secrets User` on **that individual secret**.
Until the secret and actual publisher authorization both pass, GitHub release
publication must fail closed.

The host publisher must not use ambient `gh` login, a local PAT,
`CURSEFORGE_API_TOKEN`, `GITHUB_TOKEN`, GitHub Actions secrets, Jenkins
credential bindings, or another repository's release identity as fallback.
No root or publishing secret is available in a general Linux build worker.
The repository's historic direct CLI upload path is intentionally disabled;
an independent, bounded, reviewed central host integration is required.

## Prepare a release

1. Update `mod_version` in root `gradle.properties` and every
   `targets/*/gradle.properties` file. Keep loader and Minecraft versions
   consistent with the canonical release contract.
2. Write `changelog/<version>.md`, update `CHANGELOG.md`, and choose
   `release_type` = `alpha`, `beta`, or `release`.
3. Run the credential-free Python suites, structure checks, core Java 8/25
   tests, and all native loader targets on approved Jenkins Linux runners.
4. Only a correctly admitted canonical `main` version-change event or
   separately authenticated non-dry-run manual request may become a
   *publication candidate*. All PRs and default manual requests are dry runs.
5. Before any provider call, independently verify Jenkins build number,
   trusted exact source/control SHAs, complete native artifacts, release
   manifest, SHA-256 hashes, changelog and immutable `v<version>` tag.
   A preexisting version tag for another commit must be rejected.
6. On the protected host only, fetch the one allowed Key Vault credential
   for the provider being called, check provider versions/game tags and
   reconcile preserved upload/release receipts before retrying. No untrusted
   build code may execute under the publisher credential.

The bundle includes the 11 runnable native loader JARs, the
`packetweave-core-<version>.jar` development artifact,
`SHA256SUMS` and `release-manifest.json`. Source JARs are excluded.
CurseForge receives only runnable loader JARs. Every confirmed CurseForge
upload has a positive file ID and matching SHA-256 stored in a durable
receipt. A timeout or ambiguous HTTP response **must not** trigger an
automatic duplicate upload; inspect project state and reconcile the original
receipt. Provider moderation/public visibility must be verified separately.

## Local, credential-free verification

```sh
python3 tools/release_contract.py verify
python3 -m unittest discover -s tools -p 'test_*.py' -v
python3 tools/verify_structure.py
./gradlew :core:build :core:testJava8 :core:testJava25 --no-daemon
python3 tools/build_matrix.py build --all
```

Requires matching pinned Java toolchains for legacy and modern loader Gradle
wrappers. These are not publishing commands and require no provider token.

## Rollback and dependency order

If native Jenkins release or protected publication acceptance fails, disable
that protected route; preserve the previous sealed Jenkins archive, provider
receipts and Key Vault secrets. Do **not** revive GitHub Actions or restore
its repository secrets. Do not delete any backup as part of this migration.

PacketWeave versions should be released **before** consumers that require
their API. Confirm exact Minecraft/loader combinations and minimum
PacketWeave dependency metadata on both client and server, plus published
asset hashes and availability. PacketWeave unit CI alone does not prove live
network integration in consumer mods.
