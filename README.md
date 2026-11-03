# QSerial

**A focused, multi-session serial debugging tool for Windows.**

[English](README.md) | [简体中文](README.zh-CN.md)

[![Platform: Windows](https://img.shields.io/badge/platform-Windows-blue)](#installation)
[![Python 3](https://img.shields.io/badge/python-3-blue)](#run-from-source)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

QSerial helps embedded developers, hardware engineers, and testers connect to serial devices, exchange TEXT or HEX data, repeat commands, and capture communication logs. It keeps the serial workflow direct: choose a port, match the device settings, open the connection, and inspect exactly what is sent and received.

## Design Philosophy

- **Focused serial debugging:** Keep connection, data transfer, and logging straightforward.
- **Dual-column, multi-tab workspace:** Debug multiple serial ports in independent tabs and compare sessions side by side.

## Core Features

- **Multi-session debugging:** Open multiple serial ports in tabs and compare two sessions side by side in dual-column mode.
- **Complete serial settings:** Configure port, baud rate, data bits, parity, stop bits, and hardware/software flow control.
- **TEXT and HEX transfer:** Switch input and display modes, select UTF-8 or ASCII text encoding, and control CR, LF, or CRLF line endings.
- **Repeated and reusable commands:** Send at a fixed interval, organize quick commands into groups, and resend successful requests from history.
- **Receive logging:** Save communication to a file, optionally add receive timestamps, and surface write, overflow, and shutdown failures.
- **Operational conveniences:** Automatic reconnect, automatic scrolling, RX/TX counters, per-port drafts, and configuration import/export.
- **Adaptable workspace:** Light/Dark themes and English/Simplified Chinese UI, following the system language by default.

## Installation

### Use the Windows Package

1. Download the latest `QSerial_v<version>.zip` from [GitHub Releases](https://github.com/achaosxyz/quickky-serial-tool/releases).
2. Extract the ZIP into a writable local folder.
3. Run `QSerial.exe`.

The packaged application does not require a separate Python installation. Keep the executable in a writable folder because runtime configuration is stored beside it.

### Run from Source

Requirements: Windows, Python 3, and a connected serial device or a user-provided virtual serial pair.

```powershell
git clone https://github.com/achaosxyz/quickky-serial-tool.git
cd quickky-serial-tool
pip3 install -r requirements.txt
.\run.bat
```

To start the application directly, generate the translation resource first:

```powershell
python3 scripts/generate_translations.py
python3 src/main/app_qt.py
```

## First Serial Connection

1. Connect the serial device and identify its COM port in Windows.
2. Select the port in a QSerial tab. Open the port dropdown again to refresh the available-port list.
3. Set the baud rate, data bits, parity, stop bits, and flow control to match the device.
4. Select **Open port**. The connection controls and status reflect opening, connected, closing, and failure states.
5. Choose the receive mode, enter a payload in the send editor, and select **Send**.
6. Use the RX/TX counters and receive view to confirm activity. Enable **Save log file** before the exchange when a persistent record is needed.

Only one application can normally open a given Windows COM port at a time. Close the port in other tools before connecting with QSerial.

## Sending and Receiving Data

| Mode | Use it for | Behavior |
| --- | --- | --- |
| TEXT | Commands, terminal output, and human-readable protocols | Select UTF-8 or ASCII and the required CR, LF, or CRLF line ending. QSerial does not append an extra line ending. |
| HEX | Binary protocols and byte-level inspection | Enter exact bytes such as `01 03 00 00 00 02`; whitespace, commas, hyphens, colons, and `0x` prefixes are accepted. |

- **Loop send:** Repeats the current payload at the configured millisecond interval. Closing or losing the connection stops the loop.
- **Quick commands:** Store reusable TEXT or HEX payloads in named groups and send them to the active session.
- **Send history:** Successful sends are recorded for reuse; failed or empty sends are not recorded as successful history.
- **Timestamped log mode:** Adds receive timestamps to make separated bursts easier to inspect in the log.

## Configuration and Logs

The source-tree application stores `config.json` in the project root; the packaged application stores it beside `QSerial.exe`. Use **File → Export configuration** and **File → Import configuration** to back up or move settings.

If an existing configuration cannot be read, QSerial preserves the original file and blocks normal writes. Import a valid configuration to restore saving instead of silently replacing the damaged file.

Log files are written only when file logging is enabled for a session. Choose a writable destination and review any logging warnings before relying on the captured record.

## Report an Issue

Report problems through [GitHub Issues](https://github.com/achaosxyz/quickky-serial-tool/issues). Include the QSerial version, Windows version, serial settings, reproduction steps, and relevant redacted logs.

## License

Project code is available under the [MIT License](LICENSE). PySide6/Qt is used under LGPLv3; distributions must retain the [third-party notices](licenses/THIRD_PARTY_NOTICES.md) and include the required license texts and Qt/PySide6 source information.
