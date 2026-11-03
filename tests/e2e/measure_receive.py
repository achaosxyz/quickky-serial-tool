"""Measure native GUI responsiveness over the configured serial loopback pair."""

import argparse
import json
import math
import multiprocessing
import os
import queue
import re
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def payload_for(scenario, size):
    pattern = bytes(range(256)) if scenario == "hex" else b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    if scenario == "text-lines":
        pattern += b"\n"
    return (pattern * (size // len(pattern) + 1))[:size]


def produce(port, payload, rate, ready, start, stop, results):
    """Pace input in a separate process, independent of GUI/GIL stalls."""
    import serial

    sent = 0
    started = None
    try:
        with serial.Serial(port, 115200, timeout=0, write_timeout=2) as endpoint:
            ready.set()
            if not start.wait(10):
                raise RuntimeError("GUI did not start the producer")
            started = time.perf_counter()
            packet_size = max(1, round(rate / 100))
            while sent < len(payload) and not stop.is_set():
                delay = started + sent / rate - time.perf_counter()
                if delay > 0 and stop.wait(delay):
                    break
                sent += endpoint.write(payload[sent:sent + packet_size])
        results.put({"sent": sent, "producer_seconds": time.perf_counter() - started})
    except (OSError, RuntimeError) as error:
        results.put({"sent": sent, "error": str(error)})


def distribution(values):
    if not values:
        return {}
    ordered = sorted(values)
    return {name: round(ordered[min(len(ordered) - 1, int(len(ordered) * fraction))], 3)
            for name, fraction in (("p50_ms", .5), ("p95_ms", .95), ("p99_ms", .99), ("max_ms", 1))}


def measure(args):
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    import serial
    from PySide6 import __version__ as qt_version
    from PySide6.QtCore import QPoint, QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from components.work_tab_qt import ConnectionState
    from pages.main_window_qt import MainWindow
    from tests.e2e.environment import ensure_ports_available, load_endpoints

    endpoints = load_endpoints()
    ensure_ports_available(endpoints)
    if endpoints[0].casefold() == endpoints[1].casefold():
        raise RuntimeError("E2E endpoints must be distinct")
    for port in endpoints:
        with serial.Serial(port, timeout=0):
            pass
    app = QApplication.instance() or QApplication([])
    payload = payload_for(args.scenario, round(args.kbps * 1000 / 8 * args.seconds))
    context = multiprocessing.get_context("spawn")
    ready, start, stop = context.Event(), context.Event(), context.Event()
    results = context.Queue()
    producer = context.Process(target=produce, args=(endpoints[0], payload, args.kbps * 1000 / 8,
                                                    ready, start, stop, results))
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"scenario": args.scenario, "kbps": args.kbps, "seconds": args.seconds,
              "endpoints": endpoints, "qt_version": qt_version,
              "version": (ROOT / "VERSION").read_text().strip()}
    with tempfile.TemporaryDirectory(prefix="qserial-perf-") as directory:
        with patch("utils.config_manager.get_base_path", return_value=directory):
            window = MainWindow()
            window.resize(1200, 720)
            window.move(app.primaryScreen().availableGeometry().topLeft() + QPoint(20, 20))
            window.show()
            column = window.work_panel.main_column
            tab = column.get_current_tab()
            if args.block_chars is not None:
                tab.receive_text.MAX_BLOCK_CHARS = args.block_chars
            if args.flush_ms is not None:
                tab.flush_timer.start(args.flush_ms)
            report["block_chars"] = tab.receive_text.MAX_BLOCK_CHARS
            report["flush_ms"] = tab.flush_timer.interval()
            report["max_flush_bytes"] = tab.MAX_FLUSH_BYTES
            tab.serial_settings.port_combo.setCurrentText(endpoints[1])
            tab.receive_settings.hex_radio.setChecked(args.scenario == "hex")
            tab.receive_settings.text_radio.setChecked(args.scenario != "hex")
            tab.receive_settings.auto_scroll_check.setChecked(not args.no_scroll)
            tab.receive_settings.log_mode_check.setChecked(args.log_mode)
            log_path = Path(directory) / "receive.log"
            log_parts = []
            heartbeat_gaps, append_times, format_times = [], [], []
            received_chunks, enqueue_times, reader_cpu = [], [], []
            queue_peak = [0]
            original_enqueue = tab.serial_manager._enqueue

            def measured_enqueue(data):
                reader_cpu.append(time.thread_time())
                received_chunks.append(data)
                before = time.perf_counter()
                original_enqueue(data)
                enqueue_times.append((time.perf_counter() - before) * 1000)
                with tab.serial_manager._lock:
                    queue_peak[0] = max(queue_peak[0], tab.serial_manager._pending_bytes)

            tab.serial_manager._manager.set_receive_callback(measured_enqueue)
            original_append = tab.receive_text.append_text
            original_process = tab.receive_pipeline.process
            original_flush = tab._flush_receive
            original_write = tab.log_writer.write
            flush_times, log_write_times = [], []
            log_queue_peak = [0]

            def measured_flush():
                count = tab.rx_count
                before = time.perf_counter()
                original_flush()
                if tab.rx_count != count:
                    flush_times.append((time.perf_counter() - before) * 1000)

            def measured_write(*values, **options):
                before = time.perf_counter()
                result = original_write(*values, **options)
                log_write_times.append((time.perf_counter() - before) * 1000)
                with tab.log_writer._condition:
                    log_queue_peak[0] = max(log_queue_peak[0], tab.log_writer._pending_bytes)
                return result

            def measured_append(*values, **options):
                before = time.perf_counter()
                result = original_append(*values, **options)
                append_times.append((time.perf_counter() - before) * 1000)
                if tab._log_enabled:
                    log_parts.append(result)
                return result

            def measured_process(*values, **options):
                before = time.perf_counter()
                result = original_process(*values, **options)
                format_times.append((time.perf_counter() - before) * 1000)
                return result

            tab.receive_text.append_text = measured_append
            tab.receive_pipeline.process = measured_process
            tab.log_writer.write = measured_write
            tab.flush_timer.timeout.disconnect(tab._flush_receive)
            tab.flush_timer.timeout.connect(measured_flush)
            state = {"began": None, "last": None, "result": None, "interactions": 0,
                     "deadline": time.perf_counter() + 12, "settled": None, "prepared": None}
            heartbeat = QTimer()
            heartbeat.setTimerType(Qt.PreciseTimer)
            heartbeat.setInterval(20)
            interaction = QTimer()
            interaction.setInterval(1000)
            monitor = QTimer()
            monitor.setInterval(20)

            def tick():
                now = time.perf_counter()
                heartbeat_gaps.append((now - state["last"]) * 1000)
                state["last"] = now

            def interact():
                QTest.mouseClick(tab.send_text.viewport(), Qt.LeftButton)
                QTest.keyClicks(tab.send_text, "x")
                state["interactions"] += 1

            def finish(error=None):
                monitor.stop()
                heartbeat.stop()
                interaction.stop()
                stop.set()
                report["error"] = error
                app.quit()

            def check():
                now = time.perf_counter()
                if state["began"] is None:
                    if ready.is_set() and tab.connection_state == ConnectionState.OPEN:
                        if state["prepared"] is None:
                            if args.save_log:
                                with patch("components.work_tab_qt.QFileDialog.getSaveFileName",
                                           return_value=(str(log_path), "")):
                                    QTest.mouseClick(tab.receive_settings.save_log_check, Qt.LeftButton, pos=QPoint(5, 5))
                                if not tab._log_enabled:
                                    finish("Could not enable the isolated receive log")
                                    return
                            tab._clear_receive()
                            tab._reset_counts()
                            prefill = ("50 " * (args.prefill_chars // 3) if args.scenario == "hex"
                                       else "P" * args.prefill_chars)
                            report["prefill_inserted_chars"] = len(prefill)
                            for offset in range(0, len(prefill), 16 * 1024):
                                original_append(prefill[offset:offset + 16 * 1024], auto_scroll=not args.no_scroll,
                                                max_blocks=10000)
                            state["prepared"] = time.perf_counter()
                            return
                        if now - state["prepared"] < .2:
                            return
                        if column.notebook.currentWidget() is not tab:
                            finish("Measured tab was changed before timing started")
                            return
                        report["window_context"] = [window.width(), window.height(), window.devicePixelRatioF(), column.notebook.count()]
                        report["performance_context_stable"] = True
                        append_times.clear()
                        state["began"] = state["last"] = now
                        state["cpu"] = time.process_time()
                        state["deadline"] = now + args.seconds + 15
                        heartbeat.start()
                        interaction.start()
                        start.set()
                    elif now > state["deadline"]:
                        finish("Serial/producer startup timed out")
                    return
                context = [window.width(), window.height(), window.devicePixelRatioF(), column.notebook.count()]
                if context != report["window_context"] or column.notebook.currentWidget() is not tab:
                    report["performance_context_stable"] = False
                if state["result"] is None:
                    try:
                        state["result"] = results.get_nowait()
                    except queue.Empty:
                        pass
                if state["result"] is not None:
                    if "error" in state["result"]:
                        finish(state["result"]["error"])
                        return
                    if tab.rx_count >= len(payload):
                        if state["settled"] is None:
                            state["settled"] = now
                        elif now - state["settled"] >= .3:
                            finish()
                            return
                if now > state["deadline"]:
                    finish("Timed out waiting for all input")

            heartbeat.timeout.connect(tick)
            interaction.timeout.connect(interact)
            monitor.timeout.connect(check)
            producer.start()
            QTest.mouseClick(tab.connect_btn, Qt.LeftButton)
            monitor.start()
            try:
                app.exec()
                if "error" not in report:
                    report["error"] = "Application event loop exited before the scenario completed"
                if state["began"] is not None:
                    report["gui_cpu_seconds"] = round(time.process_time() - state["cpu"], 3)
                text = tab.receive_text.toPlainText()
                timestamp_pattern = r"\[\d{2}:\d{2}:\d{2}\.\d{3}\] "
                timestamps_present = re.search(timestamp_pattern, text) is not None
                normalized = re.sub(timestamp_pattern, "", text) if args.log_mode else text
                has_history = report.get("prefill_inserted_chars", 0) > 0
                if args.log_mode and args.scenario != "hex":
                    actual, expected = normalized.replace("\n", ""), payload.decode("ascii").replace("\n", "")
                    exact = actual.endswith(expected) if has_history else actual == expected
                elif args.scenario != "hex":
                    expected = payload.decode("ascii")
                    exact = normalized.endswith(expected) if has_history else normalized == expected
                else:
                    try:
                        # Retention may cut the first cached HEX token; only the new suffix is asserted.
                        actual = bytes.fromhex(normalized.partition(" ")[2] if has_history else normalized)
                        exact = actual.endswith(payload) if has_history else actual == payload
                    except ValueError:
                        exact = False
                report.update(state["result"] or {})
                report["final_window_context"] = [window.width(), window.height(), window.devicePixelRatioF(), column.notebook.count()]
                report.update({"received": tab.rx_count, "expected": len(payload), "display_exact": exact,
                               "heartbeat": distribution(heartbeat_gaps),
                               "heartbeat_over_100ms": sum(gap > 100 for gap in heartbeat_gaps),
                               "append": distribution(append_times), "format": distribution(format_times),
                               "flush": distribution(flush_times), "log_enqueue": distribution(log_write_times),
                               "log_queue_peak_bytes": log_queue_peak[0],
                               "append_calls": len(append_times), "append_total_ms": round(sum(append_times), 3),
                               "raw_exact": b"".join(received_chunks) == payload,
                               "reader_callbacks": len(received_chunks), "queue_peak_bytes": queue_peak[0],
                               "prefill_chars": args.prefill_chars,
                               "display_check": "new-input suffix" if has_history else "full content",
                               "display_document_chars": tab.receive_text.document().characterCount(),
                               "display_blocks": tab.receive_text.blockCount(),
                               "enqueue": distribution(enqueue_times),
                               "reader_cpu_seconds": round(reader_cpu[-1] - reader_cpu[0], 4) if reader_cpu else None,
                               "log_mode": args.log_mode, "save_log": args.save_log,
                               "timestamps_present": timestamps_present,
                               "interactions": state["interactions"],
                               "counter_exact": tab.count_label.text() == f"RX: {tab.rx_count}  TX: {tab.tx_count}",
                               "interaction_exact": tab.send_text.toPlainText() == "x" * state["interactions"]})
                report["pass"] = (not report.get("error") and exact and report["raw_exact"] and tab.rx_count == len(payload)
                                  and report["sent"] == len(payload) and report["interaction_exact"] and report["counter_exact"]
                                  and (not args.log_mode or timestamps_present)
                                  and report["display_document_chars"] <= tab.MAX_DISPLAY_CHARS
                                  and report["display_blocks"] <= tab.receive_text.document().maximumBlockCount())
                if not window.grab().save(str(args.output / f"{args.scenario}.png")):
                    raise RuntimeError("Could not save performance screenshot")
            finally:
                stop.set()
                try:
                    producer.join(5)
                    if producer.is_alive():
                        raise RuntimeError("Serial producer did not stop")
                finally:
                    window.close()
                    results.close()
            if args.save_log:
                report["log_exact"] = log_path.is_file() and log_path.read_text(encoding="utf-8") == "".join(log_parts)
                report["pass"] = report["pass"] and report["log_exact"]
    for port in endpoints:
        with serial.Serial(port, timeout=0):
            pass
    (args.output / f"{args.scenario}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    if not report["pass"]:
        return 1
    return 0 if report["performance_context_stable"] else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("text-lines", "text-long", "hex"), required=True)
    parser.add_argument("--kbps", type=float, default=30)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--no-scroll", action="store_true")
    parser.add_argument("--log-mode", action="store_true", help="Enable receive timestamps")
    parser.add_argument("--save-log", action="store_true", help="Write and verify an isolated receive log")
    parser.add_argument("--prefill-chars", type=int, default=0, help="Preload display history before timed reception")
    parser.add_argument("--block-chars", type=int, help="Override the display threshold for tuning")
    parser.add_argument("--flush-ms", type=int, help="Override the receive timer for tuning")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if not all(math.isfinite(value) and value > 0 for value in (options.kbps, options.seconds)):
        parser.error("Rate and duration must be finite and positive")
    if not 0 <= options.prefill_chars <= 4 * 1024 * 1024:
        parser.error("Display history preload must be between zero and the 4 MiB display capacity")
    if ((options.block_chars is not None and options.block_chars < 32)
            or (options.flush_ms is not None and options.flush_ms <= 0)):
        parser.error("Block size must be at least 32 and flush interval must be positive")
    sys.exit(measure(options))
