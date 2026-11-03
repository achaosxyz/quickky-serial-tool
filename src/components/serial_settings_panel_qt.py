"""Serial settings panel."""

from PySide6.QtCore import QEvent
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel

from utils.serial_manager import SerialManager


class PortComboBox(QComboBox):
    def __init__(self, refresh_callback, parent=None):
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self):
        self._refresh_callback()
        super().showPopup()


class SerialSettingsPanel(QGroupBox):
    BAUDRATES = ["300", "600", "1200", "2400", "4800", "9600", "14400", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000", "1500000", "2000000"]

    def __init__(self, config_manager, on_change_callback=None, panel_type="main", parent=None, port_provider=None):
        super().__init__(parent)
        self.config_manager, self.on_change_callback, self.panel_type = config_manager, on_change_callback, panel_type
        self.port_provider = port_provider or SerialManager.get_available_ports
        self.port_combo = PortComboBox(self.refresh_ports)
        self.port_combo.setEditable(False)
        self.baudrate_combo = self._combo(self.BAUDRATES, "115200", editable=True)
        self.baudrate_combo.lineEdit().setValidator(QIntValidator(1, 4_000_000, self.baudrate_combo))
        self.parity_combo = self._combo(["None", "Even", "Odd", "Mark", "Space"], "None")
        self.bytesize_combo = self._combo(["5", "6", "7", "8"], "8")
        self.stopbits_combo = self._combo(["1", "1.5", "2"], "1")
        self.flow_control_combo = self._combo(["None", "Hardware", "Software"], "None")
        for combo in (self.parity_combo, self.flow_control_combo):
            for index in range(combo.count()):
                combo.setItemData(index, combo.itemText(index))
        self.form = QFormLayout(self)
        for combo in (self.port_combo, self.baudrate_combo, self.parity_combo, self.bytesize_combo, self.stopbits_combo, self.flow_control_combo):
            self.form.addRow(QLabel(), combo)
        self.retranslate_ui()
        self.port_combo.currentTextChanged.connect(self._on_port_changed)
        for widget in (self.bytesize_combo, self.stopbits_combo):
            widget.currentTextChanged.connect(self._save)
        for widget in (self.parity_combo, self.flow_control_combo):
            widget.currentIndexChanged.connect(self._save)
        self.baudrate_combo.currentTextChanged.connect(self._save_baudrate_if_valid)
        self.baudrate_combo.lineEdit().editingFinished.connect(self._normalize_baudrate_and_save)
        self.refresh_ports()

    @staticmethod
    def _combo(values, current, editable=False):
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentText(current)
        combo.setEditable(editable)
        return combo

    def refresh_ports(self):
        current = self.port_combo.currentText()
        def port_sort_key(value):
            name = value.upper()
            if name.startswith("COM"):
                try:
                    return (0, int(name[3:].strip()))
                except ValueError:
                    pass
            return (1, value)
        ports = sorted(self.port_provider(), key=port_sort_key)
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current in ports:
            self.port_combo.setCurrentText(current)
        else:
            self.port_combo.setCurrentIndex(-1)
        self.port_combo.blockSignals(False)

    def _on_port_changed(self, port):
        if port:
            config = self.config_manager.get_port_config(port)
            self.load_config(config["serial_settings"])
            self.config_manager.set_last_port(port, self.panel_type)
            if self.on_change_callback: self.on_change_callback("port", port)

    def _save(self):
        port = self.get_current_port()
        if port:
            settings = self.get_settings()
            self.config_manager.update_serial_settings(port, settings)
            if self.on_change_callback: self.on_change_callback("settings", settings)

    def _normalize_baudrate_and_save(self):
        if self._baudrate_value() is None:
            self.baudrate_combo.setCurrentText("115200")
        self._save()

    def _save_baudrate_if_valid(self):
        if self._baudrate_value() is not None:
            self._save()

    def _baudrate_value(self):
        try:
            baudrate = int(self.baudrate_combo.currentText())
        except ValueError:
            return None
        return baudrate if 1 <= baudrate <= 4_000_000 else None

    def get_settings(self):
        baudrate = self._baudrate_value()
        if baudrate is None:
            baudrate = 115200
            self.baudrate_combo.setCurrentText(str(baudrate))
        try: stopbits = float(self.stopbits_combo.currentText())
        except ValueError: stopbits = 1
        return {"baudrate": baudrate, "parity": self.parity_combo.currentData(), "bytesize": int(self.bytesize_combo.currentText()), "stopbits": stopbits, "flow_control": self.flow_control_combo.currentData()}

    def load_config(self, config):
        combos = (self.baudrate_combo, self.parity_combo, self.bytesize_combo, self.stopbits_combo, self.flow_control_combo)
        for combo in combos: combo.blockSignals(True)
        try:
            for combo, value in ((self.baudrate_combo, config.get("baudrate", 115200)), (self.bytesize_combo, config.get("bytesize", 8)), (self.stopbits_combo, config.get("stopbits", 1))): combo.setCurrentText(str(int(value) if combo is self.stopbits_combo and isinstance(value, float) and value.is_integer() else value))
            for combo, value in ((self.parity_combo, config.get("parity", "None")), (self.flow_control_combo, config.get("flow_control", "None"))):
                combo.setCurrentIndex(combo.findData(value))
        finally:
            for combo in combos: combo.blockSignals(False)

    def get_current_port(self): return self.port_combo.currentText()
    def set_current_port(self, port, notify=True):
        blocked = self.port_combo.blockSignals(True)
        try:
            if self.port_combo.findText(port) < 0: self.port_combo.addItem(port)
            self.port_combo.setCurrentText(port)
        finally:
            self.port_combo.blockSignals(blocked)
        if notify:
            self._on_port_changed(port)
    def set_enabled(self, enabled): self.setEnabled(enabled)

    def retranslate_ui(self):
        self.setTitle(self.tr("Serial settings"))
        for widget, text in ((self.port_combo, self.tr("Port:")),
                             (self.baudrate_combo, self.tr("Baud rate:")),
                             (self.parity_combo, self.tr("Parity:")),
                             (self.bytesize_combo, self.tr("Data bits:")),
                             (self.stopbits_combo, self.tr("Stop bits:")),
                             (self.flow_control_combo, self.tr("Flow control:"))):
            self.form.labelForField(widget).setText(text)
        for combo, labels in (
            (self.parity_combo, (self.tr("None"), self.tr("Even"), self.tr("Odd"), self.tr("Mark"), self.tr("Space"))),
            (self.flow_control_combo, (self.tr("None"), self.tr("Hardware"), self.tr("Software"))),
        ):
            previous = combo.blockSignals(True)
            try:
                for index, label in enumerate(labels):
                    combo.setItemText(index, label)
            finally:
                combo.blockSignals(previous)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.LanguageChange and hasattr(self, "form"):
            self.retranslate_ui()
