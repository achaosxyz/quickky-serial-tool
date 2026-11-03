# Configuration Design

## 1. Scope

This document defines the current configuration ownership, JSON data model, normalization, persistence, import/export, and save timing.

## 2. Ownership and Location

`ConfigManager` owns the in-memory configuration and the last successfully persisted snapshot. Public getters return scalars or independent deep snapshots; mutations go through its modification methods. The framework- and I/O-independent `config_schema.py` defines defaults, constraints, and normalization.

- Packaged application: `config.json` beside `QSerial.exe`.
- Development: `config.json` in the project root.
- Export: a user-selected JSON file.
- Log file paths are not persisted; only the last selected log directory is stored.

## 3. Current Data Model

```text
config
|-- last_port_main / last_port_secondary / last_log_directory
|-- port_configs
|   `-- <port>
|       |-- serial_settings
|       |-- receive_settings
|       |-- send_settings
|       `-- send_text
|-- quick_command_groups
|-- send_history
|-- command_panel_visible
|-- dual_panel_mode
|-- theme
|-- language
`-- global_settings
    |-- receive_buffer_size
    |-- send_history_max
    |-- fontSize
    `-- reconnect_interval
```

Serial settings contain baudrate, parity, data bits, stop bits, and flow control. Receive settings contain TEXT/HEX mode, encoding, timestamped log mode, file-log selection, automatic reconnect, and automatic scrolling. Send settings contain TEXT/HEX mode, line ending, loop-send enable, and loop period.

Quick-command entries retain both `data` and the legacy `command` alias during normalization. History entries contain data, mode, and display timestamp. Newest history is stored first; an identical adjacent payload and mode updates the existing timestamp rather than adding a duplicate.

## 4. Defaults and Normalization

Loading and import normalize external JSON into the current model:

- Missing or invalid fields use field-level defaults.
- Unknown structures are discarded.
- Numeric ranges and supported enum values are checked explicitly; booleans must be actual JSON booleans.
- `receive_settings.save_log` always resets to `False` because a file must be selected for each runtime session.
- Themes are restricted to `light` and `dark`.
- Language defaults to `system` and accepts `system`, `zh_CN`, and `en_US`; the selected value is persisted rather than the resolved system language.
- String enums are checked for type before membership; invalid JSON lists, objects, and scalar values fall back to field defaults.
- History is capped by `global_settings.send_history_max`.
- Invalid roots, malformed JSON, and excessively deep structures are treated as invalid configuration.

If the runtime configuration cannot be read or parsed, the application uses defaults, warns the user, and refuses normal writes so initialization and later changes cannot overwrite the original file. A successful explicit import replaces it with the selected valid configuration and re-enables normal writes; unsaved changes remain unsaved until then.

## 5. Persistence

Normal writes use a temporary file in the configuration directory, flush and `fsync` the stream, and atomically replace `config.json` with `os.replace`. Temporary files are removed after write failure where possible.

`ConfigManager` compares the current model with the last successful snapshot and tracks pending writes with `_dirty`. Successful writes replace the snapshot and clear `_dirty`; failed or throttled writes retain it. If normalization of valid loaded JSON needs a write and that write fails, the normalized data remains in memory and a later save retries it. A read or parse failure does not itself mark defaults dirty or overwrite the damaged file.

Send drafts and ordinary settings use immediate change-driven saves. High-frequency send history uses a minimum two-second write interval. `flush_config()` forces pending changes to disk during window close.

## 6. Import and Export

Export serializes the current normalized model to the selected path. Import reads and normalizes the selected file, writes the runtime configuration first, and only then replaces the in-memory model and last-saved snapshot. An import failure leaves the current in-memory configuration intact; the UI requests restart so imported settings are applied coherently.
