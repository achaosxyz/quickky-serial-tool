# Version and Release SOP

There are exactly two user-facing operations: **prepare release information** and **publish the confirmed release**. The agent handles tests, builds, GitHub Actions, branch/tag updates, and recovery inside these operations; the user does not need to perform those steps manually. Preparation is not an RC publication.

## 1. Pre-release: Prepare Information for Confirmation

**User request:** Ask for release preparation. This does not authorize commits, pushes, tags, workflow dispatch, or publication.

**Agent responsibility:** Review the development state and present one release proposal. Do not publish while waiting for confirmation.

### Development and readiness

- Develop on `develop`; feature branches target `develop`. `main` receives verified releases rather than daily changes.
- Use root `VERSION` as the version source; `version.py` is generated and never committed. Use English Conventional Commits.
- Start from a clean, reviewed `develop` synchronized with `origin/develop` and containing `origin/main`. Report any uncommitted or unpushed work instead of implicitly authorizing its commit/push.
- Check Windows CI and applicable local tests. Serial/GUI behavior changes also need the loopback and visual acceptance in [E2E testing](E2E_TESTING.md); hosted startup smoke is not a substitute.
- Review user-visible changes since the latest stable tag. For the first release, describe the current implementation without assuming a previous tag exists.
- Record additions, improvements, and fixes in concise Markdown notes, not a raw commit log or an internal refactoring inventory.

### Confirmation information

Present the version, stable/RC type, full source commit SHA, user-facing release notes, test results and gaps, expected tag and ZIP name, and the resulting development version.

| Development target | Confirmed release | Published result | Development after success |
| --- | --- | --- | --- |
| `3.0.0-snapshot` | `3.0.0` | Stable `v3.0.0`, `QSerial_v3.0.0.zip` | `3.0.1-snapshot` |
| `3.0.0-snapshot` | `3.0.0-rc.1` | Prerelease `v3.0.0-rc.1` | `3.0.0-rc.1`, no patch bump |

The release must match the major/minor/patch under development. Set a new minor or major target on `develop` before preparing that release. A later RC or stable release can share the same base version.

The agent saves the proposed dispatch inputs as `dist/release-request/release_request.json` using the helper below. `RELEASE_VERSION` and `RELEASE_NOTES` contain the proposal being presented; the helper records the current full SHA and does not commit or publish.

```powershell
python3 scripts/release.py request --directory dist/release-request
```

The saved file contains exactly `version`, `source`, and `notes`. User confirmation applies to these values, not to whatever happens to be on `develop` later. Changing the version, notes, or source requires renewed confirmation. Stop after presenting the proposal and wait for the user's publish instruction.

## 2. Formal Release: Publish the Confirmed Information

**User request:** Confirm the proposal and ask to publish. This authorizes the documented release branch/tag updates, GitHub publication, and post-release development-version commit for that proposal only.

**Agent responsibility:** Use the unchanged confirmed inputs, run the release, handle ordinary internal steps, and report the published version, tag, URL, ZIP, validation results, and final branch versions. Do not ask the user to build, click through Actions, or manage internal steps.

### Internal automation

1. Dispatch `.github/workflows/release.yml` from `main` with the confirmed `version`, full `source` SHA, and `notes`. The Actions UI and authenticated `gh workflow run release.yml --ref main` are implementation options, not additional user-facing SOPs.
2. A read-only Windows job checks out the confirmed source and requires it still to be current `origin/develop`, containing `origin/main`, with a clean tree, matching version, and unused tag. It creates a local release-version commit without changing the remote.
3. Run unit/component tests, localhost TCP serial GUI E2E, `build.bat`, and the packaged ZIP smoke test on Python 3.11 x64, `windows-2022`. The extracted EXE must initialize English and Chinese, capture windows, clean up, exit 0, and write a fresh report with the expected version. The package smoke test does not open a serial port.
4. Transfer the tested commit in a Git bundle together with the exact ZIP, notes, and metadata. The publishing job runs orchestration from the original `main` checkout; it does not execute candidate code or rebuild the package.
5. Recheck remote state, then atomically fast-forward `main` and push annotated `v<version>`. Never force-push or move an existing version tag.
6. Create or resume a draft GitHub Release, upload the tested ZIP, and publish it with the confirmed title, notes, and stable/RC type. RCs are prereleases, not latest; stable releases are marked latest. Verify that public information matches the confirmation and that the expected ZIP exists before advancing development.
7. Fast-forward `develop` through the release commit. A stable release adds `chore: start <next-patch> development` with the next `-snapshot`; an RC does not increment the patch.

Only the publishing job has `contents: write`. One non-canceling release concurrency group serializes publication. Tag pushes are not used to trigger a second workflow. Ordinary pushes run `.github/workflows/ci.yml` unit/component and TCP GUI E2E tests and isolated source startup smoke; local builds and version edits never publish.

Release lookup resolves both drafts and public releases through GraphQL, then reads their REST metadata by release ID; the REST tag endpoint only resolves published releases. API/authentication errors stop the operation rather than being treated as a missing release.

Release ZIPs contain only `QSerial.exe`, `LICENSE`, and `licenses/`. Development configuration, environment files, reports, Git bundles, and release notes are not included. Smoke PNG/JSON evidence is retained as a separate Actions artifact; capture alone is not visual review.

### Internal setup and recovery

- **Orchestration synchronization:** Initially land the workflows and helpers on both branches through separately authorized bootstrap synchronization; keep `main` as GitHub's default branch and dispatch Release from it. Later changes to `.github/workflows/` or `scripts/release.py` must also be synchronized before preparing a release: the publisher runs the trusted `main` script and must share its preparation contract, and the normal `GITHUB_TOKEN` cannot introduce workflow-file changes. This infrastructure exception to release-only `main` does not publish anything or authorize bypassing branch rules.
- **Repository access:** GitHub is the only destination (`achaosxyz/quickky-serial-tool`). Actions and the official checkout/Python/artifact actions must be allowed. Publishing uses `GITHUB_TOKEN`, not a broad personal token. Branch/tag rules must permit the intended bot updates; do not disable protections to get a release through.
- **Before publication:** A failed test, build, or smoke leaves remote branches, tags, and releases unchanged. Fix and review on `develop`; any new source or notes require a new proposal and confirmation.
- **Source changed:** Do not substitute a newer commit or reuse the old ZIP for different code. Prepare new information for confirmation.
- **Main/tag pushed, publication failed:** Retain the tested artifact and tag. Retry only the failed publishing job with the same inputs and artifact; it resumes its draft without recreating or moving the tag.
- **Already public:** Never overwrite its ZIP, notes, or tag. A retry verifies the existing publication before finishing development advancement; changed public title, notes, or release type blocks automatic recovery and must be reported for review.
- **Development advanced after publication:** Keep the valid release. Do not reset development. Report the recovery needed: merge the published tag on clean `develop`, resolve its intended snapshot/RC version, test, and obtain authorization for the recovery commit/push.
- **Already advanced:** Recognize the release commit and expected development version; do not bump twice.
- **Blocked or expired:** Report protection/authentication failures or expired artifacts. Do not bypass controls, silently replace a public package, or invent a successful hosted run.

For local package diagnosis, run `build.bat`, then `python3 scripts/smoke_windows.py dist/QSerial_v<version>.zip --version <version> --output <temporary-report-directory>`. The build uses `python3` by default; `PYTHON` can select another interpreter. GitHub Actions uses its setup-python interpreter. Source smoke is `python3 src/main/app_qt.py --smoke-test <temporary-report-directory>` after version/translation generation. Set `QT_QPA_PLATFORM=offscreen` and `QT_QPA_FONTDIR` to the Windows fonts directory for source screenshots; the package helper and Windows CI configure these for readable bilingual captures. Neither smoke test claims clean-machine, physical-hardware, or interactive desktop acceptance.
