# QSerial Project Design

## 1. Purpose and Scope

QSerial (Quickky Serial Tool) is a Windows desktop serial debugging application for developers and testers. It provides multiple serial-session tabs, single- or dual-column workspaces, TEXT/HEX transfer, quick commands, send history, file logging, themes, and local JSON configuration.

The supported runtime is Python 3 with PySide6 and Qt Widgets. The user interface follows the system language by default and supports explicit Simplified Chinese and English selection.

## 2. Design Philosophy

- **Progressive:** Deliver small, runnable increments that preserve behavior and can be reviewed and tested independently.
- **Evidence-based:** Refactor demonstrated coupling, ownership, correctness, or readability problems rather than anticipated needs.
- **Clear ownership:** Each resource or mutable model has one owner; parents compose children and children use explicit callbacks or Qt signals for upward notification.
- **Framework isolation:** Keep serial, conversion, configuration, and file-writing logic independent of Qt unless Qt adaptation is the module's purpose.
- **Current-state documentation:** This tree describes the implementation as it exists now, not planned architecture or historical migrations.

## 3. Technology and Runtime

| Area | Current choice |
| --- | --- |
| Language | Python 3 |
| GUI | PySide6 with Qt Widgets |
| Serial access | pyserial |
| Packaging | PyInstaller Windows one-file application |
| Tests | Layered Python `unittest`, QtTest component tests, and isolated QTest serial-loopback E2E |
| Configuration | `config.json` beside the executable, or the project root during development |
| Version | Root `VERSION` file |

No additional GUI framework or runtime dependency is part of the supported design.

## 4. System Architecture

```text
src/main/app_qt.py
  -> MainWindow
       -> ConfigManager
       -> ThemeManagerQt
       -> LanguageManagerQt
       -> WorkPanel
       |    -> WorkColumn
       |         -> WorkTab
       |              -> SerialManagerQt -> SerialManager
       |              -> LogWriter
       |              -> ReceiveTextView
       |              -> ReceivePipeline and receive/send conversion utilities
       |              -> serial/receive/send settings panels
       -> CommandPanel
            -> QuickCommandsPanel
            -> SendHistoryPanel
```

`MainWindow` composes application services and top-level panels. `WorkPanel` and `WorkColumn` own workspace and tab lifetime. Each `WorkTab` coordinates one serial session and owns its Qt serial adapter, log writer, timers, settings widgets, receive pipeline, and receive view. `CommandPanel` emits send requests upward rather than depending on `MainWindow`.

The detailed boundaries are maintained in the module designs:

| Module design | Scope |
| --- | --- |
| [Application and UI](APPLICATION_UI.md) | Window composition, tabs, commands, settings, and themes |
| [Serial communication](SERIAL_COMMUNICATION.md) | Port lifetime, worker threads, buffering, and TEXT/HEX transfer |
| [Configuration](CONFIGURATION.md) | Data model, normalization, persistence, import, and export |
| [Logging](LOGGING.md) | Log selection, asynchronous writes, generations, and shutdown |

## 5. Shared Data Model

The root configuration contains last selected ports, the last log directory, per-port settings and drafts, quick-command groups, send history, panel visibility, dual-column mode, theme, language (`system`, `zh_CN`, or `en_US`), and global settings. TEXT editor content and quick commands use CRLF internally; conversion to the configured serial line ending occurs only during sending or display-mode conversion.

See [Configuration](CONFIGURATION.md) for the complete current model and validation rules.

## 6. Core Flows

1. **Startup:** `app_qt.py` creates `QApplication` and `MainWindow`; the window loads configuration, applies the selected or system-derived language, constructs the workspace and command panel, applies the theme, and starts the event loop.
2. **Serial session:** A tab submits bytes-only sends and lifecycle operations through the FIFO `SerialManagerQt` worker; background serial work returns explicit results through Qt signals while received bytes enter a bounded queue.
3. **Receive display:** A 25 ms timer drains at most 256 KiB per batch, applies incremental decoding and formatting, updates RX statistics and logging, and appends to the bounded receive editor.
4. **Commands and history:** Quick commands and history target the active work tab; successful sends update history and refresh its table.
5. **Persistence:** Configuration changes use normalized data and atomic replacement; high-frequency history writes are throttled and forced during window close.
6. **Shutdown:** Workspace cleanup stops timers and serial activity, performs bounded log-writer shutdown, flushes configuration, and reports cleanup failures.

The module designs define the detailed behavior without duplicating it in this overview.

## 7. Runtime Resources and Packaging

- `resource_path()` resolves bundled resources from PyInstaller's temporary directory and development resources from the project root.
- `get_base_path()` places user configuration beside a packaged executable and in the project root during development.
- `build.bat` generates the application translation and packages it with Qt's translation catalog, the Qt entry point, version, icon, themes, and Windows/offscreen platform plugins.
- Release ZIP files contain the executable and required license materials, never the development `config.json`.
- `scripts/release.py` records confirmed version/source/notes, prepares a local release commit, transfers the tested commit and ZIP between read-only verification and write-enabled publication, and advances `develop` only after GitHub publication; the two user-facing operations are defined in the [release SOP](../guides/VERSION_RELEASE.md).
- Windows Actions run unit/component tests and isolated startup smoke; releases additionally smoke-test the extracted ZIP executable before changing `main` or its tag.

## 8. Maintenance Contract

Change code and the affected current-state design together. Keep this overview stable and concise; put detailed module contracts in the linked documents and proposed future work in `.plan/`.
