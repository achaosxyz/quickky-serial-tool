# Agent Maintenance Rules

## Project

QSerial is a Python 3 Windows serial debugging tool using PySide6, Qt Widgets, pyserial, and PyInstaller; the supported application entry point is `src/main/app_qt.py`.

## Required Reading

- Read [PROJECT_DESIGN](docs/design/PROJECT_DESIGN.md) before changing code, then follow its links to the affected module design.
- Read the [Python guide](docs/guides/PYTHON_DEVELOPMENT.md) for implementation and the [release SOP](docs/guides/VERSION_RELEASE.md) before any release work.
- Read the [E2E SOP](docs/guides/E2E_TESTING.md) before serial loopback or end-to-end GUI testing.

## Core Rules

- **Current-state SSOT:** Keep `docs/design/` aligned with the actual code in the same change; plans belong in `.plan/` and are not design facts.
- **Progressive delivery:** Make evidence-based, runnable increments with focused review and tests instead of big-bang rewrites or speculative abstractions.
- **Module boundaries:** Preserve clear ownership and one-way dependencies; update the affected module design whenever structure, responsibilities, data, or core flows change.
- **Dependencies:** Do not add a dependency or GUI framework without explicit user approval and synchronized requirements, README, and design updates.
- **Defensive coding:** Validate real external and concurrency boundaries, but do not add unsupported compatibility paths, blanket fallbacks, or hypothetical extension points.
- **Verification:** Run focused unit/component checks plus QTest loopback E2E as applicable; GUI changes require the visual review in the [E2E SOP](docs/guides/E2E_TESTING.md).
- **Git authorization:** Do not commit, merge, tag, push, or publish unless explicitly requested; [pre-release](docs/guides/VERSION_RELEASE.md) only prepares information, while an explicit publish instruction authorizes the confirmed release and its post-release steps.
- **Branch workflow:** Develop on `develop`; `main` receives verified releases, and successful stable releases advance `develop` to the next patch snapshot as defined in the [release SOP](docs/guides/VERSION_RELEASE.md).
- **Commit language:** When authorized, use English Conventional Commits messages such as `fix: preserve port ownership after close failure`.
- **Documentation language:** Keep design, SOP documents, code comments, and docstrings in English; use English `README.md` with Chinese `README.zh-CN.md`, keeping comments concise and aligned with actual behavior.
- **Script language:** Keep script comments, docstrings, diagnostics, and user-facing output in English.
- **Internationalization:** Use Qt-native translation with English source text, Simplified Chinese resources, and system-language defaulting as defined in the [Python guide](docs/guides/PYTHON_DEVELOPMENT.md).

## Directory Layers

- `src/main/`: Application composition and process entry points.
- `src/pages/`: Top-level windows and dialogs.
- `src/components/`: Qt widgets, workspaces, session tabs, and command panels.
- `src/utils/`: Serial, configuration, logging, theme, conversion, and resource services.
- `themes/`: Runtime Light and Dark JSON themes.
- `scripts/`: Version generation, packaging, license collection, and release automation.
- `tests/`: Layered unit/component tests and QTest serial-loopback E2E scenarios.
- `docs/design/`: Current architecture SSOT, split into overview and module designs.
- `docs/guides/`: English development, testing, and release procedures.
- `.plan/`: Proposed work and review records; never current-state SSOT.
- `.github/workflows/`: Windows CI and the manually triggered GitHub release pipeline.
- `VERSION`: The only source of the project version.
- `licenses/`: Runtime license and third-party notices.

## Documentation Index

- [English README](README.md) and [Chinese README](README.zh-CN.md): Installation, serial workflows, configuration, issue reporting, and license entry points.
- [Overall design](docs/design/PROJECT_DESIGN.md): System scope, architecture, shared data, and links to module designs.
- [Application and UI](docs/design/APPLICATION_UI.md): Window composition, workspace ownership, settings, commands, and themes.
- [Serial communication](docs/design/SERIAL_COMMUNICATION.md): Serial lifecycle, background I/O, receive buffering, and send conversion.
- [Configuration](docs/design/CONFIGURATION.md): JSON model, validation, persistence, import, and export.
- [Logging](docs/design/LOGGING.md): Log sessions, bounded writes, timestamps, and cleanup.
- [Python development](docs/guides/PYTHON_DEVELOPMENT.md): Coding, concurrency, testing, and documentation workflow.
- [E2E testing](docs/guides/E2E_TESTING.md): QTest automation, virtual/real loopback setup, screenshots, and visual review.
- [Version release](docs/guides/VERSION_RELEASE.md): Two SOPs: prepare release information for confirmation, then publish the confirmed information with automated verification and development version advancement.
