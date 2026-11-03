# End-to-End Testing SOP

## 1. Purpose and Scope

End-to-end tests exercise the real QSerial widgets, two serial endpoints, user-visible sending/receiving, and application cleanup. The automated approach uses `PySide6.QtTest.QTest` and a test-owned localhost TCP relay accessed through pyserial `socket://` URLs.

For ordinary in-process GUI behavior, use QTest and `QSignalSpy` in component tests. E2E uses the real serial manager, worker threads, buffers, and GUI with socket endpoints injected into port discovery.

## 2. Local Environment

The test fixture binds two ephemeral ports on `127.0.0.1`, relays bytes in both directions, and closes its sockets and worker on exit. No `dev.env`, virtual COM driver, system port, or external device is required. Socket transport does not model physical baud rate, parity, flow control, modem lines, or UART timing. Physical-device verification remains separate.

## 3. Execution

- `tests/e2e/` automation uses QTest in process with real application widgets and its own socket pair.
- Treat listener or relay errors as test failures; do not silently skip them.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python3 -m unittest tests.e2e.test_loopback -v
```

Run the complete suite, including simulated device removal and automatic reconnect:

```powershell
python3 -m unittest discover -s tests/e2e -p 'test_*.py' -v
```

For readable Windows-native screenshots, use the Windows platform plugin and a disposable artifact directory:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:QSERIAL_VISUAL_DIR = Join-Path $env:TEMP 'qserial-visual-review'
python3 tests/e2e/capture_visual.py
```

Inspect the generated PNGs; this command only captures them and does not perform the review.

To capture the connected TCP endpoint window in both languages and themes, run the real loopback scenario with the Windows plugin:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:QSERIAL_E2E_SCREENSHOT_DIR = Join-Path $env:TEMP 'qserial-tcp-review'
python3 -m unittest tests.e2e.test_loopback -v
```

Inspect the resulting `socket-*.png` images separately. The generic visual capture above does not connect the TCP endpoints.

## 4. Isolation and Preflight

1. Run E2E in a separate test process with a temporary configuration root and log directory. Before creating `MainWindow`, redirect the configuration base path through test setup or an explicit configuration injection point; changing only the working directory is insufficient because the current base path derives from the source location.
2. Create the relay before constructing the window and inject both URLs through its port provider, including for new tabs and refreshes.
3. Verify actual bidirectional traffic and endpoint release, not merely successful TCP connection handshakes.
4. Record the application/build identifier, the test scenario set, and that the link is TCP simulation.
5. Keep unit/component success separate from E2E acceptance and use bounded Qt event waits rather than arbitrary fixed sleeps.

## 5. Core Loopback Scenarios

Automate these scenarios with QTest in `tests/e2e/`:

1. **Launch and connect:** Create the real application/window, two session tabs, select the injected endpoints, and open both sessions.
2. **TEXT A to B:** Send ASCII/UTF-8 text from the TX endpoint and verify exact reception, line-ending behavior, and RX/TX counters on the other tab.
3. **HEX B to A:** Reverse the endpoint roles, send a known HEX byte sequence, and verify exact bytes without newline conversion.
4. **Routing:** Switch the active tab/column and verify quick commands or history reach only the selected session.
5. **Loop send:** Start loop sending, observe repeated bounded reception, cancel it, and verify that sending stops.
6. **Logging:** Enable a log in the disposable directory, send known payloads, close the session, and verify content and clean file shutdown.
7. **Cleanup:** Close tabs and the application, then verify that both endpoints can be reopened and no test worker keeps them occupied.
8. **Removal and automatic reconnect:** Remove one endpoint from discovery, close its listener and active connection, and verify the real GUI disconnects, disables sending, stops loop sending, and releases the session. The other endpoint must remain usable. Observe failed retries while the endpoint is absent, refresh the dropdown, restore the same URL, and verify automatic recovery with exact fresh-session traffic and no replay of absent-session data.
9. **Reconnect cancellation:** Verify that automatic reconnect stays off when disabled, unchecking it cancels scheduled retries, and manual close, explicit selection of another port, and window cleanup prevent the old session from reopening. A manually opened new selection must use its own current settings.
10. **Empty discovery:** Remove both endpoints and refresh to an empty list. After restoration, reconnect must preserve an edited send draft and new receive data rather than reloading per-port presets.

`SocketRelay.set_available(index, False/True)` applies removal/restoration on the relay worker, preventing cross-thread socket-close races. `get_available_ports()` exposes only present endpoints; restoration rebinds the original localhost address. Normal shutdown clears connection and discovery state. Socket EOF is also tested by stopping the entire relay. Unit tests exercise the real COM health-check/receive-loop path with fake enumeration disappearance and device-status errors. These simulations do not validate physical drivers, hardware unplug timing, or UART behavior; do not change unrelated processes or system settings.

To capture the removed and automatically restored GUI states for visual inspection:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:QSERIAL_RECONNECT_SCREENSHOT_DIR = Join-Path $env:TEMP 'qserial-reconnect-review'
python3 -m unittest tests.e2e.test_reconnect -v
```

Inspect `reconnect-removed.png` and `reconnect-restored.png`; capture alone is not visual acceptance.

## 6. Visual Review and Evidence

- Capture relevant widget or window states with `QWidget.grab()` and save PNG images in a temporary test-artifact directory.
- Perform an actual visual review of the captured images with image viewing or human inspection; screenshot creation alone is not visual acceptance.
- Check layout, clipping, spacing, contrast, text readability, active/focus states, and relevant Light/Dark or single/dual-column variants affected by the change.
- Record functional and visual results separately as passed, failed, blocked, or not run, with exact endpoint roles and concrete failure evidence.
- A passing functional assertion does not prove visual quality, and an unexecuted scenario or unreviewed screenshot must not be described as passed.
- After a failure fix, rerun the affected scenario and perform an additional focused review of the fix before final acceptance.

## 7. Receive Performance

Use the test-owned TCP relay and native Windows widgets to measure TEXT with natural newlines, continuous TEXT, and HEX separately:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$output = Join-Path $env:TEMP 'qserial-receive-performance'
foreach ($scenario in @('text-lines', 'text-long', 'hex')) {
    python3 tests/e2e/measure_receive.py --scenario $scenario --kbps 30 --seconds 30 --output $output
    if ($LASTEXITCODE -ne 0) { throw "Receive performance scenario failed: $scenario" }
}
```

The rate is effective payload kilobits/second, excluding UART framing. A separate producer process paces 10 ms writes so GUI/GIL stalls do not throttle the input generator. The GUI runs its normal Qt event loop with a precise 20 ms heartbeat and periodic QTest clicking/typing. JSON reports separate receive/content/interaction correctness from heartbeat gaps, synchronous append/format durations, and GUI-process CPU time. Heartbeat gaps are responsiveness indicators, not measured frame times or input-to-paint latency. A correctness pass alone is not a smoothness pass.

Configuration and logs are isolated in a temporary directory; screenshots and JSON persist in the selected output directory. Inspect the screenshots separately. Use `--log-mode` for timestamps, `--save-log` for file logging (or both), `--no-scroll` for a non-following view, and longer durations for sustained reception. File logs are compared with the formatted append stream after application cleanup; raw callback bytes are compared with the producer payload separately. Timestamp-mode content checks ignore intentional timestamp/newline formatting. Reports also measure receive enqueue/GUI flush/log enqueue costs, receive-thread CPU time and queue peaks; instrumentation itself adds some overhead.

Keep endpoint roles, rate, duration, platform plugin, machine load, theme and build consistent for comparisons. `--block-chars` and `--flush-ms` override display limits/timing only in the test process for tuning. The application display limits still apply, so exact full-content checks require a payload that fits those limits. Compare separate runs rather than running GUI benchmarks concurrently. Do not interpret effective virtual-pair payload rates as proof of physical UART throughput at the selected baud rate.

Use `--prefill-chars 4194304` to exercise reception against an already full display history without a multi-minute warm-up. This preloads display-only cached history before timed input, waits for initial painting, then checks the complete **new-input suffix**, raw input equality, display bounds and (when enabled) the new file-log stream. It does not assert preservation of evicted history.

The runner waits for the final coalesced count-label update and checks it against live totals independently of the receive text. Count-label refresh targets 200 ms; the receive display targets 50 ms. Do not use label repaint frequency as the input byte rate or editor refresh rate.

The runner uses a fixed 1200 × 720 logical-pixel primary-screen window and records start/end dimensions, DPI and tab count. It watches the selected receive tab while timing. Accept CPU/latency comparisons only when `performance_context_stable` is true and contexts match between runs; exit code 2 means functional checks passed but window/tab changes invalidated the performance context. `pass` checks integrity/interactions/cleanup, not a universal smoothness or frame-rate target. Shared-host load can still affect timings.

HEX history preload rounds down to complete `XX ` tokens and records `prefill_inserted_chars`; requests shorter than three characters insert no history and use a full-content assertion. Timestamp-mode checks require an actual timestamp prefix as well as normalized content and, when enabled, exact flushed log text.
