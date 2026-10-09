# Releasing PacketWeave

The pipeline follows the Simply Screens release flow: version change, verification, native builds, CurseForge uploads, then a GitHub release. It supports all eight independent native targets plus the loader-neutral core.

## Configuration

Use [`curseforge.md`](curseforge.md) as the CurseForge project description. It is maintained separately from each version's release changelog; the upload workflow does not update the project description.

In GitHub repository **Settings → Secrets and variables → Actions**, add these when the CurseForge project is available:

| Kind | Name | Value |
|---|---|---|
| Repository variable | `CURSEFORGE_PROJECT_ID` | `1735096` (PacketWeave) |
| Repository secret | `CURSEFORGE_API_TOKEN` | CurseForge upload API token |

There is no placeholder or borrowed project ID. Without `CURSEFORGE_PROJECT_ID`, the external upload job is skipped and GitHub releases still work. Once the ID is configured, a missing token fails publishing rather than silently skipping it.

PacketWeave's [CurseForge project](https://www.curseforge.com/minecraft/mc-mods/packetweave) has project ID **1735096**. The repository variable is configured; the upload token must be added as a repository secret before publishing. New projects remain unavailable publicly until CurseForge moderation approves them.

GitHub releases use the workflow's built-in `GITHUB_TOKEN` with `contents: write` limited to the release job. No personal token is required.

The Java package/mod ID stays `packetweave`; the project ID above identifies the CurseForge listing. PacketWeave does not need Screens' Architectury, OpenUI or Fabric API publishing relations.

## Preparing a version

1. Set `mod_version` in the root `gradle.properties` and all eight `targets/*/gradle.properties` files. The core reads the root version directly.
2. Add `changelog/<version>.md` and update `CHANGELOG.md`.
3. Set root `release_type` to `alpha`, `beta` or `release`. Alpha/beta also mark the GitHub release as a prerelease.
4. Open or update the PR. CI checks version consistency, changelog presence, the core tests, eight native builds, expanded loader metadata, packaged core classes and the MIT license.
5. Merge only after the required checks pass. A version change on `main` runs **Build and Release Mod**. A root properties change without a version change does not publish again.

The release dry run runs on PRs that change release tooling/configuration. It executes the same reusable build workflow and assembles the full bundle, but publishing is disabled for PRs and non-main branches.

## Manual runs and supplying the project ID later

Use **Actions → Build and Release Mod → Run workflow** on `main`:

- Leave `dry_run` enabled to build and inspect the artifacts without publishing.
- Disable `dry_run` to publish the current version, including uploading to CurseForge after adding the project ID/token. This works even if the GitHub release was previously created while the project ID was unset.

The `v<version>` tag must point to the tested source commit. The workflow refuses to move a version tag to different code; bump the version for new code.

## Release assets and upload receipts

The verified release bundle contains eight runnable loader jars, `packetweave-core-<version>.jar`, `SHA256SUMS` and `release-manifest.json`. Source/dev jars are excluded. The manifest binds every jar's SHA-256 to the source commit. All nine jars must verify before publishing begins.

Only the eight loader jars go to CurseForge. Every Minecraft, loader, Java, Client and Server tag is checked before the first upload. Each successful upload must return a positive file ID; success is recorded with the jar's hash in a workflow artifact.

Use **Re-run failed jobs** to resume a partially completed upload within the same workflow run. Confirmed receipts from the preceding run attempt prevent uploading the same jars again. A failed or timed-out upload request is not automatically repeated: check the CurseForge project if its outcome was ambiguous. Receipts are only created for confirmed file IDs, and text such as “already uploaded” is not treated as proof of success.

GitHub publication waits for all configured CurseForge uploads to finish. A green PR/build or an accepted upload does not prove that CurseForge moderation has approved the files.

If a previous attempt's receipt artifact is missing, the retry stops before uploading. Inspect the project before starting a fresh run; do not bypass missing receipts after a partially completed publication.

## Local verification

```powershell
python tools/release_contract.py verify
python -m unittest discover -s tools -p 'test_*.py' -v
python tools/verify_structure.py
.\gradlew.bat :core:build --no-daemon
python tools/build_matrix.py build --all
```

Gradle runtime requirements remain Java 17 for Forge and the core, and Java 25 for Fabric and NeoForge targets; native bytecode targets remain Java 8/17/21/25 according to Minecraft version.

The loader mods expose the functional core API without registering an independent wire protocol. The release workflow verifies packaging and the core; it does not replace consuming mods' live networking tests.

## Dependent release order

Release PacketWeave 0.1.1 before Simply Screens 0.8.10. Verify all five native artifacts needed by Screens (Fabric/Forge 1.20.1, Fabric/NeoForge 1.21.1, NeoForge 26.1.2), successful upload receipts, and public CurseForge approval/download availability before publishing the dependent Screens files. An accepted upload or GitHub release does not establish CurseForge moderation status. Screens uses the standalone API, requires PacketWeave on both sides, and must not package duplicate core classes.
