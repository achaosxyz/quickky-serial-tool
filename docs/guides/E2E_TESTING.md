# End-to-End Testing SOP

## 1. Purpose and Scope

End-to-end tests exercise the real QSerial widgets, two serial endpoints, user-visible sending/receiving, and application cleanup. The automated approach is `PySide6.QtTest.QTest` with a virtual loopback serial pair; a real hardware loopback may be used by overriding the local environment.

For ordinary in-process GUI behavior, use QTest and `QSignalSpy` in component tests. Reuse the same deterministic widget automation for E2E while replacing fake serial endpoints with the configured real or virtual pair.

## 2. Local Environment

If `dev.env` does not exist, copy the tracked template to the ignored local file; otherwise keep and edit the existing local file instead of overwriting it:

```powershell
Copy-Item dev.env.template dev.env
```

The tracked template uses this example pair:

```dotenv
QSERIAL_E2E_TX_PORT=COM1
QSERIAL_E2E_RX_PORT=COM2
```

The configured endpoints must be the two ends of one user-provided virtual loopback pair: bytes written to one endpoint arrive at the other. The current local `dev.env` overrides the template with virtual pair `COM20`/`COM21`. Swap endpoint roles in scenario code for the opposite-direction test; do not rewrite `dev.env` during a test. For a real hardware loopback, replace both values in `dev.env` with the connected local endpoints.

The template contains no credentials. Keep local environment values in `dev.env`; do not commit that file. Do not install a virtual-serial driver, create system ports, or change hardware configuration without separate explicit authorization.

## 3. Execution

- `tests/e2e/` automation uses QTest in process with real application widgets and the configured serial pair.
- If the serial pair is unavailable, mark affected E2E scenarios as blocked or not run with the concrete reason.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python3 -m unittest tests.e2e.test_loopback -v
```

For readable Windows-native screenshots, use the Windows platform plugin and a disposable artifact directory:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:QSERIAL_VISUAL_DIR = Join-Path $env:TEMP 'qserial-visual-review'
python3 tests/e2e/capture_visual.py
```

Inspect the generated PNGs; this command only captures them and does not perform the review.

## 4. Isolation and Preflight

1. Run E2E in a separate test process with a temporary configuration root and log directory. Before creating `MainWindow`, redirect the configuration base path through test setup or an explicit configuration injection point; changing only the working directory is insufficient because the current base path derives from the source location.
2. Read the two endpoint values from `dev.env`; fail preflight if either value is missing.
3. Verify both endpoints exist and are available to the test instance. Do not confuse port enumeration with proof of loopback connectivity.
4. Record whether the link is virtual or hardware, the application/build identifier, and the test scenario set.
5. Keep unit/component success separate from E2E acceptance and use bounded Qt event waits rather than arbitrary fixed sleeps.

## 5. Core Loopback Scenarios

Automate these scenarios with QTest in `tests/e2e/`:

1. **Launch and connect:** Create the real application/window, two session tabs, select the configured endpoints, and open both sessions with matching settings.
2. **TEXT A to B:** Send ASCII/UTF-8 text from the TX endpoint and verify exact reception, line-ending behavior, and RX/TX counters on the other tab.
3. **HEX B to A:** Reverse the configured roles, send a known HEX byte sequence, and verify exact bytes without newline conversion.
4. **Routing:** Switch the active tab/column and verify quick commands or history reach only the selected session.
5. **Loop send:** Start loop sending, observe repeated bounded reception, cancel it, and verify that sending stops.
6. **Logging:** Enable a log in the disposable directory, send known payloads, close the session, and verify content and clean file shutdown.
7. **Cleanup:** Close tabs and the application, then verify that both endpoints can be reopened and no test worker keeps them occupied.

Disconnect/reconnect and driver-failure scenarios require a separately controllable test link and explicit authorization for that action; do not simulate them by killing unrelated processes or changing system settings.

## 6. Visual Review and Evidence

- Capture relevant widget or window states with `QWidget.grab()` and save PNG images in a temporary test-artifact directory.
- Perform an actual visual review of the captured images with image viewing or human inspection; screenshot creation alone is not visual acceptance.
- Check layout, clipping, spacing, contrast, text readability, active/focus states, and relevant Light/Dark or single/dual-column variants affected by the change.
- Record functional and visual results separately as passed, failed, blocked, or not run, with exact endpoint roles and concrete failure evidence.
- A passing functional assertion does not prove visual quality, and an unexecuted scenario or unreviewed screenshot must not be described as passed.
- After a failure fix, rerun the affected scenario and perform an additional focused review of the fix before final acceptance.
