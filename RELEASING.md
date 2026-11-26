# PacketWeave — Jenkins release operations

PacketWeave versioning, builds, checks and publishing use
**Jenkins-only** execution under [KAN-73](https://nstut.atlassian.net/browse/KAN-73).
GitHub Actions execution is disabled at repository level; never re-enable it,
depend on its status/artifacts, or store a new publishing secret there.

## Native, credential-free verification

The reviewed `Jenkinsfile` uses central `nstut-ci` and a qualified general
Linux executor to run Python release-contract tests, structure verification,
the Java 8/25 core tests and all 11 native loader builds. It archives exact
source evidence and verifies runtime/loader metadata, MIT license and
production JARs. The normal native main archive is the release producer.
`Jenkinsfile.release` remains available as a credential-free 13-stage
manual dry run: the same 12 build targets followed by full source-pinned
bundle verification. Neither Jenkinsfile injects publishing secrets or
writes GitHub/CurseForge releases.

## Active cutover

Both legacy Actions workflows have been removed; the repository-level
Actions disablement and strict App-owned `jenkins/packetweave` required
check remain in force. The native main and owner-PR matrices have passed
on qualified Linux runners. The protected release timer verifies the
latest completed native main result, the signed canonical source event,
all twelve artifact hashes, immutable version and tag conditions, and
generates the release manifest/checksums from the already-built bytes.
A signed version change does **not** trigger a second build matrix.

The protected check reconciler reports an exact-head in-progress check
for a signed numbered owner-PR build, then completes the same check
with verified success or failure. It never marks a failed or incomplete
matrix green. The remaining live acceptance is a genuine new-version
provider publication and receipt reconciliation, and observation of the
new check lifecycle on an owner PR. An unchanged version is not eligible
for publication. A green build alone does not grant release authority.

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
| GitHub tag/release and asset write for PacketWeave only | Repository-scoped GitHub App installation token |

CurseForge project **1735096** is a public, pinned project ID and **not**
a credential. The shared CurseForge token has been read successfully from
Key Vault by the protected NsTut-CICD certificate identity. The existing GitHub App `nstut-jenkins-typed-events` (installation
`183318189`) already has **Contents: write** and access to PacketWeave.
The protected publisher reads the **existing**
`nstut-jenkins-github-app-private-key` from Key Vault and mints a
short-lived installation token scoped to `UpperMoon0/PacketWeave` only.
The returned repo ID, permission scope and expiry must be verified before
use. Do **not** provision or retain a PacketWeave PAT. A credential alone
does not authorize publication: signed source evidence, immutable tag,
native Jenkins acceptance and idempotent receipt checks must also pass.

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
4. Only a correctly admitted canonical `main` version-change event may
   become a *publication candidate*. Owner PRs and manual dry runs never
   publish. The protected publisher independently checks admission.
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
