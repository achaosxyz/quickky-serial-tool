# Application and UI Design

## 1. Scope

This document defines the current Qt window composition, widget ownership, workspace behavior, settings panels, command panels, and theme integration. Serial protocols and persistence details live in their respective module designs.

## 2. Entry Point and Main Window

`src/main/app_qt.py` adds `src/` to the import path, creates `QApplication`, shows `MainWindow`, and runs the Qt event loop.

With `--smoke-test REPORT_DIR`, the entry point delegates to `smoke_test_qt.py`, which injects a temporary `ConfigManager` into the real `MainWindow`, initializes both languages, captures windows, checks cleanup, writes a result report, and exits with a test status. This mode never opens a serial port or reads/writes the user's configuration; normal startup still creates its own configuration manager.

`MainWindow` owns `ConfigManager` and `ThemeManagerQt`, constructs `WorkPanel` and `CommandPanel`, and provides application menus for configuration import/export, settings, view modes, themes, help, and exit. It also applies the application palette and stylesheet and coordinates final cleanup.

`AppInfo` centralizes application metadata; window titles and the About dialog display the author as `aCHAOS`.

`LanguageManagerQt` installs both the application catalog and Qt's Simplified Chinese standard-widget catalog, including dialog buttons; packaging includes that Qt catalog. English uses the source strings.

## 3. Workspace Ownership

```text
WorkPanel
  -> main WorkColumn
  -> secondary WorkColumn
       -> QTabWidget
            -> WorkTab per serial session
            -> dedicated "+" page
```

- `WorkPanel` owns dual-column visibility and tracks the active column.
- `WorkColumn` creates, selects, closes, and enumerates tabs and propagates theme, suspension, and cleanup.
- `WorkTab` emits port changes; its owning `WorkColumn` updates the tab title without the tab traversing its parent widgets.
- The final real tab in a column cannot be closed; the dedicated plus page creates another tab.
- Serial tabs use Qt-managed close buttons and `tabCloseRequested`; close controls are enabled only with multiple real tabs, and the plus page never has one. Native buttons are re-registered and explicitly shown after their hit-target size changes so dynamically inserted tabs immediately use the updated geometry without hiding their close controls. Close tooltips follow the application language.
- Each column reserves a 2-DIP activation strip followed by a 4-DIP gap above its tabs. Only the active column is highlighted in dual-column mode; the reserved space remains unchanged in single-column mode and when activation switches.
- Serial-tab selection uses the theme's selected background and a neutral top border, independently of the column activation strip. Other tab bars retain their selected-tab accent.
- Switching to single-column mode hides and suspends the secondary column without destroying its tabs or per-port configuration.
- The active column determines the target of quick-command and history sending.

## 4. WorkTab

A `WorkTab` is the coordinator for one serial session. It owns:

- `SerialManagerQt`, `LogWriter`, receive decoding/formatting state, and connection, flush, loop-send, and reconnect timers.
- Serial, receive, and send settings panels.
- Read-only receive editor, send editor, connection/send buttons, clear/reset actions, and RX/TX counters.
- Connection and reconnect coordination, send preparation, history notification, log selection, and cleanup.

The receive editor disables wrapping and uses both a maximum block count and a 4 MiB character cap. Display appends are batched; system messages use distinct text colors and are separated from unfinished receive lines.

## 5. Settings Panels

- `SerialSettingsPanel` enumerates ports, edits serial parameters, restores per-port configuration, and records the last selected port for its column.
- Parity and flow-control labels are translated independently from their stable configuration and serial-driver values; switching languages does not save settings.
- `ReceiveSettingsPanel` edits TEXT/HEX mode, encoding, timestamped log mode, file logging, automatic reconnect, and automatic scrolling.
- `SendSettingsPanel` edits TEXT/HEX mode, CR/LF/CRLF selection, loop sending, and loop period.
- `SettingsDialog` edits receive line capacity, history capacity, font size, and reconnect interval.
- The main window applies theme and font updates after an accepted settings dialog; the dialog does not invoke its parent.

The panels persist their own configuration sections through `ConfigManager`; `WorkTab` responds to changes that affect active session resources. Loading configuration blocks widget signals so restoration does not trigger unintended writes or resource actions.

## 6. Commands and Send History

`CommandPanel` contains `QuickCommandsPanel` and `SendHistoryPanel` in a fixed-width side panel.

- Quick commands support named groups, group reordering, command editing, drag reordering, and TEXT/HEX sending.
- Send history displays newest successful sends first and supports resending or clearing history.
- History previews are single-line TEXT/HEX labels with visible `\r` and `\n` escapes. Qt elides only the trailing overflow to fit the current column width; previews are not pre-truncated to a fixed character count. The time column fits its contents and the data column stretches into the remaining viewport width. Horizontal scrolling is disabled; vertical scrolling remains available for long histories. Resending uses the complete original payload, not its displayed preview.
- Both child panels emit a send request through `CommandPanel.send_requested`; `MainWindow` connects it to `WorkPanel`. Successful tab sends notify `MainWindow` to refresh history once.
- External sends replace the tab's send draft with the selected command or history payload and record history by default only after success.

## 7. Themes

`ThemeManagerQt` loads `themes/light.json` or `themes/dark.json`, exposes its current theme and colors, builds a `QPalette`, and generates the widget stylesheet. Theme actions retain their configuration key in `QAction.data()`. `MainWindow` applies application-wide styling, while `WorkColumn` and `WorkTab` update active-column borders, editor fonts, and existing receive-message colors.

The `serialTabBar` stylesheet scope keeps Qt's native tab-close subcontrol transparent in normal, hover, and pressed states. Serial tabs keep a 20-DIP minimum content height so enabling or disabling close controls does not shift the workspace. Qt-managed close buttons keep a 20-DIP click target within their tab around a compact 8-DIP glyph and use theme-appropriate PNG glyphs from `themes/icons/`, including `@2x` assets for high-DPI displays. Qt still owns button painting, layout, and interaction; no custom paint event or SVG runtime plugin is needed. Tab scroll buttons and command-panel tabs are outside this scope. Theme assets are bundled with the existing `themes/` resource directory.

## 8. Language

The window applies the persisted `system`, `zh_CN`, or `en_US` selection through `LanguageManagerQt` before constructing widgets. System language is resolved at runtime; the original selection remains in configuration. English source strings use Qt translation and open widgets retranslate on `LanguageChange`. User-created group names, commands, and history remain data and are not translated.

## 9. UI Thread and Cleanup

Qt widgets are updated on the UI thread. Serial operations and continuous log writes run in background workers; the UI thread performs only bounded queue consumption and coordinated cleanup. Cleanup returns error messages from every tab, deduplicates them at workspace boundaries, and reports them in one dialog. Window shutdown also flushes pending configuration even if cleanup raises.
