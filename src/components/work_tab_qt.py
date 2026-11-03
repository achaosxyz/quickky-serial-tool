"""Qt serial session tab with bounded, batched receive updates."""

from datetime import datetime
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QSplitter, QVBoxLayout, QWidget)

from components.receive_settings_panel_qt import ReceiveSettingsPanel
from components.receive_text_view_qt import ReceiveTextView
from components.send_settings_panel_qt import SendSettingsPanel
from components.serial_settings_panel_qt import SerialSettingsPanel
from utils.log_writer import LogWriter
from utils.receive_data_utils import ReceivePipeline
from utils.serial_manager_qt import SerialManagerQt
from utils.send_data_utils import SendDataUtils


class ConnectionState(Enum):
    DISCONNECTED = auto()
    OPENING = auto()
    OPEN = auto()
    CLOSING = auto()
    CLOSE_FAILED = auto()


class WorkTab(QWidget):
    """Coordinate a serial session and periodically drain received data."""

    port_changed = Signal(str)

    FLUSH_INTERVAL_MS = 50
    COUNT_INTERVAL_MS = 200
    MAX_FLUSH_BYTES = 32 * 1024
    MAX_DISPLAY_CHARS = 4 * 1024 * 1024

    def __init__(self, config_manager, is_first_tab=False,
                 on_data_sent=None, panel_type="main", parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.on_data_sent = on_data_sent
        self.panel_type = panel_type
        self.is_first_tab = is_first_tab
        self.serial_manager = SerialManagerQt(); self.serial_manager.disconnected.connect(self._on_disconnected)
        self.serial_manager.operation_completed.connect(self._on_operation_completed)
        self.log_writer = LogWriter(); self.log_file_path = None; self._log_enabled = False; self._log_generation = 0; self.rx_count = self.tx_count = 0
        self._theme_manager = None
        self.receive_pipeline = ReceivePipeline(); self._send_in_flight = False; self._pending_send = None; self._loop_send_cancelled = False; self._manual_close = False
        self.connection_state = ConnectionState.DISCONNECTED
        self._cleaning_up = False
        self._cleanup_errors = None
        self.flush_timer = QTimer(self); self.flush_timer.timeout.connect(self._flush_receive)
        self.count_timer = QTimer(self)
        self.count_timer.setSingleShot(True)
        self.count_timer.setInterval(self.COUNT_INTERVAL_MS)
        self.count_timer.timeout.connect(self._update_counts)
        self.loop_timer = QTimer(self); self.loop_timer.timeout.connect(lambda: self._send_data(from_timer=True))
        self.reconnect_timer = QTimer(self); self.reconnect_timer.setSingleShot(True); self.reconnect_timer.timeout.connect(self._try_reconnect)
        self._build_ui()
        self.flush_timer.start(self.FLUSH_INTERVAL_MS)

    def _build_ui(self):
        self.serial_settings = SerialSettingsPanel(self.config_manager, self._serial_changed, self.panel_type, self)
        self.receive_settings = ReceiveSettingsPanel(self.config_manager, self._receive_changed, self._choose_log_file, self)
        self.send_settings = SendSettingsPanel(self.config_manager, self._send_settings_changed, self._on_send_mode_changed, self)
        self.connect_btn = QPushButton(); self.connect_btn.clicked.connect(self._toggle_connection)
        left = QWidget(); left.setFixedWidth(240); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(4, 4, 4, 4)
        for widget in (self.serial_settings, self.connect_btn, self.receive_settings, self.send_settings): left_layout.addWidget(widget)
        left_layout.addStretch()
        self.receive_text = ReceiveTextView(self.MAX_DISPLAY_CHARS); self.receive_text.setFont(QFont("Consolas", self.config_manager.get_font_size()))
        self.send_text = QPlainTextEdit(); self.send_text.setFont(QFont("Consolas", self.config_manager.get_font_size())); self.send_text.textChanged.connect(self._save_send_draft)
        self.send_btn = QPushButton(); self.send_btn.setEnabled(False); self.send_btn.clicked.connect(lambda: self._send_data())
        self.clear_receive_btn, self.clear_send_btn, self.reset_count_btn = self._link_button(""), self._link_button(""), self._link_button("")
        self.clear_receive_btn.clicked.connect(self._clear_receive); self.clear_send_btn.clicked.connect(self.send_text.clear); self.reset_count_btn.clicked.connect(self._reset_counts)
        self.count_label = QLabel("RX: 0  TX: 0")
        right = QWidget(); right_layout = QVBoxLayout(right); right_layout.setContentsMargins(4, 4, 4, 4)
        receive_actions = QHBoxLayout(); receive_actions.addWidget(self.clear_receive_btn); receive_actions.addStretch()
        send_actions = QHBoxLayout(); send_actions.addWidget(self.clear_send_btn); send_actions.addStretch(); send_actions.addWidget(self.send_btn)
        status_actions = QHBoxLayout(); status_actions.addWidget(self.count_label); status_actions.addStretch(); status_actions.addWidget(self.reset_count_btn)
        self.receive_label = QLabel(); self.send_label = QLabel()
        right_layout.addWidget(self.receive_label); right_layout.addWidget(self.receive_text, 3); right_layout.addLayout(receive_actions); right_layout.addWidget(self.send_label); right_layout.addWidget(self.send_text, 1); right_layout.addLayout(send_actions); right_layout.addLayout(status_actions)
        splitter = QSplitter(Qt.Horizontal); splitter.setChildrenCollapsible(False); splitter.addWidget(left); splitter.addWidget(right); splitter.setCollapsible(0, False); splitter.setCollapsible(1, False); splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(splitter)
        self.retranslate_ui()
        # Only the first tab restores the previous port selection.
        if self.is_first_tab:
            port = self.config_manager.get_last_port(self.panel_type)
            if port:
                self.serial_settings.set_current_port(port)
            elif self.serial_settings.port_combo.count() > 0:
                self.serial_settings.set_current_port(self.serial_settings.port_combo.itemText(0))

    @staticmethod
    def _link_button(text):
        button = QPushButton(text); button.setFlat(True); button.setProperty("linkButton", True); button.setCursor(Qt.PointingHandCursor); font = button.font(); font.setUnderline(True); button.setFont(font); return button

    def _serial_changed(self, kind, value):
        if kind == "port":
            self._reset_receive_session()
            self._close_log_writer()
            config = self.config_manager.get_port_config(value)
            self.receive_settings.load_config(value, config["receive_settings"])
            self.send_settings.load_config(value, config["send_settings"])
            self.send_text.blockSignals(True); self.send_text.setPlainText(config.get("send_text", "")); self.send_text.blockSignals(False)
            self.port_changed.emit(value)

    def _receive_changed(self, settings):
        if not settings["save_log"] and self._log_enabled:
            self._close_log_writer()
        if not settings["auto_reconnect"]:
            self.reconnect_timer.stop()

    def _close_log_writer(self):
        """Close the log session so another port cannot reuse its path."""
        self._log_enabled = False
        self.log_file_path = None
        self.log_writer.close(self._log_generation)
        self._log_generation += 1

    def suspend(self):
        """Close session resources while retaining the tab for reuse."""
        self._manual_close = True
        self._stop_loop_send()
        self.reconnect_timer.stop()
        self._reset_receive_session()
        self._close_log_writer()
        checkbox = self.receive_settings.save_log_check
        if checkbox.isChecked():
            checkbox.setChecked(False)
        if self.connection_state != ConnectionState.DISCONNECTED:
            self._close_connection()
        else:
            self._apply_connection_state(ConnectionState.DISCONNECTED)
    def _send_settings_changed(self, settings):
        if not settings["loop_send"]:
            self._loop_send_cancelled = True
            if self.loop_timer.isActive(): self.loop_timer.stop(); self.send_btn.setText(self.tr("Send"))
        elif settings["loop_send"] and self.loop_timer.isActive():
            self.loop_timer.start(settings["loop_period_ms"])
    def _on_send_mode_changed(self, old_mode, new_mode):
        text = self.send_text.toPlainText()
        if not text: return
        line_ending = self.send_settings.get_settings()["line_ending"]
        encoding = self.receive_settings.get_settings()["encoding"].replace("-", "").lower()
        try:
            if old_mode == "TEXT" and new_mode == "HEX":
                converted = SendDataUtils.text_to_hex(text, encoding, line_ending)
            elif old_mode == "HEX" and new_mode == "TEXT":
                converted = SendDataUtils.hex_to_text(text, encoding, line_ending)
            else: return
        except ValueError:
            return
        self.send_text.setPlainText(converted)

    def _toggle_connection(self):
        if self.connection_state in (ConnectionState.OPENING, ConnectionState.CLOSING): return
        if self.connection_state in (ConnectionState.OPEN, ConnectionState.CLOSE_FAILED): self._close_connection(); return
        port = self.serial_settings.get_current_port()
        if not port: self._append_system(self.tr("[Error] Select a serial port first\n"), "error"); return
        self._manual_close = False
        self._open_connection(port)

    def _open_connection(self, port):
        self._reset_receive_session()
        self._apply_connection_state(ConnectionState.OPENING)
        if not self.serial_manager.open_async(port=port, **self.serial_settings.get_settings()):
            self._apply_connection_state(ConnectionState.DISCONNECTED)
            self._append_system(self.tr("[Error] Open request rejected\n"), "error")

    def _close_connection(self):
        self._manual_close = True; self._stop_loop_send(); self.reconnect_timer.stop(); self._reset_receive_session()
        if self.connection_state == ConnectionState.CLOSING:
            return
        self._apply_connection_state(ConnectionState.CLOSING)
        if not self.serial_manager.close_async():
            self._apply_connection_state(ConnectionState.CLOSE_FAILED)
            self._append_system(self.tr("[Error] Close request rejected\n"), "error")

    def _reset_receive_session(self):
        """Reset receive session state without clearing visible history."""
        self.serial_manager.clear_pending()
        self.receive_pipeline.reset()

    def _stop_loop_send(self):
        self._loop_send_cancelled = True
        self.loop_timer.stop()
        self.send_btn.setText(self.tr("Send"))

    def _apply_connection_state(self, state):
        self.connection_state = state
        labels = {ConnectionState.DISCONNECTED: self.tr("Open port"), ConnectionState.OPENING: self.tr("Open port"), ConnectionState.OPEN: self.tr("Close port"), ConnectionState.CLOSING: self.tr("Close port"), ConnectionState.CLOSE_FAILED: self.tr("Retry close")}
        self.connect_btn.setText(labels[state])
        self.connect_btn.setEnabled(state not in (ConnectionState.OPENING, ConnectionState.CLOSING))
        self.send_btn.setEnabled(state == ConnectionState.OPEN)
        self.serial_settings.set_enabled(state == ConnectionState.DISCONNECTED)

    def _on_disconnected(self):
        if self._cleaning_up or self.connection_state == ConnectionState.CLOSING:
            return
        self._stop_loop_send(); self._reset_receive_session()
        state = ConnectionState.CLOSE_FAILED if self.serial_manager.has_port_ownership() else ConnectionState.DISCONNECTED
        self._apply_connection_state(state)
        self._append_system(self.tr("[Warning] Serial port disconnected unexpectedly\n"), "warning")
        if state == ConnectionState.DISCONNECTED and not self._manual_close and self.receive_settings.get_settings()["auto_reconnect"]: self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._manual_close:
            return
        interval = self.config_manager.get_global_settings().get("reconnect_interval", 5)
        self.reconnect_timer.start(int(interval * 1000))

    def _try_reconnect(self):
        if self._manual_close or not self.receive_settings.get_settings()["auto_reconnect"] or self.connection_state != ConnectionState.DISCONNECTED: return
        port = self.serial_settings.get_current_port()
        if port:
            self._open_connection(port)
        else:
            self._append_system(self.tr("[Warning] Reconnection failed; retrying later\n"), "warning"); self._schedule_reconnect()

    def _flush_receive(self):
        data, dropped = self.serial_manager.drain(self.MAX_FLUSH_BYTES)
        if dropped:
            self.rx_count += dropped
            self._schedule_count_update()
            self._append_text(self.tr("[Warning] Receive buffer full; dropped {count} bytes\n").format(count=dropped), force=True, level="warning")
        log_dropped = self.log_writer.take_dropped_bytes()
        if log_dropped:
            self._disable_logging(self.tr("Log buffer full; dropped {count} bytes").format(count=log_dropped))
        for generation, message in self.log_writer.take_error_events():
            if generation == self._log_generation and self._log_enabled:
                self._disable_logging(message)
            else:
                self._append_text(self.tr("[Error] {message}\n").format(message=message), force=True, level="error", write_log=False)
        if not data:
            return
        self.rx_count += len(data)
        self._schedule_count_update()
        settings = self.receive_settings.get_settings()
        self._append_text(self.receive_pipeline.process(data, settings), format_log=False)

    def _append_system(self, text, level="info"):
        self._append_text(text, force=True, level=level)

    def _disable_logging(self, error):
        self._close_log_writer()
        checkbox = self.receive_settings.save_log_check
        if checkbox.isChecked():
            checkbox.setChecked(False)
        self._append_text(self.tr("[Error] {message}\n").format(message=error), force=True, level="error", write_log=False)

    def _append_text(self, text, force=False, level="normal", write_log=True, format_log=True):
        if not text:
            return
        settings = self.receive_settings.get_settings()
        if format_log:
            text = self.receive_pipeline.format_system(text, settings["log_mode"])
        displayed = self.receive_text.append_text(
            text, level=level if force else "normal",
            auto_scroll=settings["auto_scroll"],
            max_blocks=self.config_manager.get_global_settings().get("receive_buffer_size", 10000))
        if write_log and self._log_enabled:
            if not self.log_writer.write(displayed, self._log_generation):
                dropped = self.log_writer.take_dropped_bytes()
                self._disable_logging(self.tr("Log buffer full; dropped {count} bytes").format(count=dropped))

    def _send_data(self, override_mode=None, add_to_history=True, from_timer=False):
        if from_timer and self._loop_send_cancelled: return
        if self.loop_timer.isActive() and not from_timer and override_mode is None:
            self._loop_send_cancelled = True; self.loop_timer.stop(); self.send_btn.setText(self.tr("Send")); return
        if not from_timer and override_mode is None: self._loop_send_cancelled = False
        if self._send_in_flight: return
        data = self.send_text.toPlainText(); settings = self.send_settings.get_settings(); mode = override_mode or settings["mode"]
        if not data: return
        if self.connection_state != ConnectionState.OPEN: self._stop_loop_send(); self._append_system(self.tr("[Error] Port is not open; cannot send\n"), "error"); return
        encoding = self.receive_settings.get_settings()["encoding"]
        try:
            encoded = SendDataUtils.prepare(data, mode, encoding, settings["line_ending"])
            byte_count = len(encoded)
        except (ValueError, UnicodeEncodeError): self._append_system(self.tr("[Error] Invalid send data\n"), "error"); return
        self._send_in_flight = True; self._pending_send = (data, mode, byte_count, add_to_history, settings, override_mode)
        if not self.serial_manager.send_async(encoded):
            self._send_in_flight = False
            self._pending_send = None
            self._stop_loop_send()
            self._append_system(self.tr("[Error] Send request rejected\n"), "error")

    def send_data(self, data, mode, add_to_history=True): self.send_text.setPlainText(data); self._send_data(mode, add_to_history=add_to_history)
    def _save_send_draft(self):
        port = self.serial_settings.get_current_port()
        if port: self.config_manager.set_send_text(port, self.send_text.toPlainText())
    def _on_operation_completed(self, operation, result):
        if self._cleaning_up:
            return
        success = result.success
        if operation == "open":
            if self.connection_state != ConnectionState.OPENING:
                return
            if success: self._apply_connection_state(ConnectionState.OPEN); self._append_system(self.tr("[Info] Port opened: {port}\n").format(port=self.serial_settings.get_current_port()), "success")
            else:
                state = ConnectionState.CLOSE_FAILED if self.serial_manager.has_port_ownership() else ConnectionState.DISCONNECTED
                self._apply_connection_state(state)
                self._append_system(self.tr("[Error] Could not open port: {error}\n").format(error=result.error), "error")
                if state == ConnectionState.DISCONNECTED and self.receive_settings.get_settings()["auto_reconnect"]: self._schedule_reconnect()
        elif operation == "close":
            if self.connection_state != ConnectionState.CLOSING:
                return
            self._reset_receive_session()
            if success:
                self._apply_connection_state(ConnectionState.DISCONNECTED)
                self._append_system(self.tr("[Info] Port closed\n"), "info")
            else:
                self._apply_connection_state(ConnectionState.CLOSE_FAILED)
                self._append_system(self.tr("[Error] Could not close port: {error}\n").format(error=result.error), "error")
        elif operation == "send":
            self._send_in_flight = False
            if not self._pending_send: return
            data, mode, byte_count, add_to_history, settings, override_mode = self._pending_send; self._pending_send = None
            if success:
                self.tx_count += byte_count; self._update_counts()
                if add_to_history: self.config_manager.add_send_history(data, mode)
                if self.on_data_sent: self.on_data_sent()
                if not override_mode and settings["loop_send"] and not self._loop_send_cancelled and not self.loop_timer.isActive(): self.loop_timer.start(settings["loop_period_ms"]); self.send_btn.setText(self.tr("Cancel sending"))
            else: self._stop_loop_send(); self._append_system(self.tr("[Error] Send failed: {error}\n").format(error=result.error), "error")
    def _choose_log_file(self):
        suggested_name = f"{self.serial_settings.get_current_port()}-{datetime.now():%Y%m%d%H%M%S}.log"
        last_directory = self.config_manager.get_last_log_directory()
        initial_path = str(Path(last_directory) / suggested_name) if last_directory else suggested_name
        filename, _ = QFileDialog.getSaveFileName(self, self.tr("Save log file"), initial_path, self.tr("Log files (*.log);;Text files (*.txt);;All files (*.*)"))
        if not filename: return False
        try:
            # Validate the selected file before enabling logging.
            with Path(filename).open("a", encoding="utf-8"):
                pass
        except OSError as error:
            self._append_system(self.tr("[Error] Could not create log file: {error}\n").format(error=error), "error")
            return False
        self.config_manager.set_last_log_directory(str(Path(filename).parent))
        self.log_file_path = filename; self._log_enabled = self.log_writer.open(filename, self._log_generation); self._append_system(self.tr("[Info] Log file: {filename}\n").format(filename=filename), "info"); return self._log_enabled
    def _clear_receive(self): self.receive_text.clear(); self.receive_pipeline.reset()
    def _reset_counts(self): self.rx_count = self.tx_count = 0; self._update_counts()

    def _schedule_count_update(self):
        # Changing QLabel text invalidates the surrounding layout; coalesce RX paints.
        if not self.count_timer.isActive():
            self.count_timer.start()

    def _update_counts(self):
        self.count_timer.stop()
        self.count_label.setText(f"RX: {self.rx_count}  TX: {self.tx_count}")

    def apply_theme(self, theme_manager, font_size=9):
        self._theme_manager = theme_manager
        self.receive_text.setFont(QFont("Consolas", font_size)); self.send_text.setFont(QFont("Consolas", font_size)); self.receive_text.apply_theme(theme_manager)
    def retranslate_ui(self):
        self.receive_label.setText(self.tr("Receive data"))
        self.send_label.setText(self.tr("Send data"))
        self.clear_receive_btn.setText(self.tr("Clear receive"))
        self.clear_send_btn.setText(self.tr("Clear send"))
        self.reset_count_btn.setText(self.tr("Reset counts"))
        self.send_btn.setText(self.tr("Cancel sending") if self.loop_timer.isActive() else self.tr("Send"))
        self._apply_connection_state(self.connection_state)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.LanguageChange and hasattr(self, "receive_label"):
            self.retranslate_ui()

    def cleanup(self):
        if self._cleanup_errors is not None:
            return list(self._cleanup_errors)
        self._cleaning_up = True
        self.count_timer.stop()
        self.flush_timer.stop(); self._stop_loop_send(); self.reconnect_timer.stop(); self._reset_receive_session()
        self.serial_manager.dispose()
        result = self.serial_manager.wait_disposed(2.0)
        errors = [] if result.success else [self.tr("Could not close port: {error}").format(error=result.error)]
        self._log_enabled = False
        if not self.log_writer.stop():
            errors.append(self.tr("Log writer timed out; queued data may not have been written"))
        errors.extend(message for _, message in self.log_writer.take_error_events())
        dropped = self.log_writer.take_dropped_bytes()
        if dropped:
            errors.append(self.tr("Log buffer full; dropped {count} bytes").format(count=dropped))
        self._cleanup_errors = errors
        return list(errors)
