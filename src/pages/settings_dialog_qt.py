"""Global settings dialog."""

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox


class SettingsDialog(QDialog):
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.config_manager = config_manager
        settings = config_manager.get_global_settings()
        self.buffer_size_spin = self._spin(1000, 100000, settings.get("receive_buffer_size", 10000))
        self.history_max_spin = self._spin(50, 1000, settings.get("send_history_max", 200))
        self.font_size_spin = self._spin(6, 20, settings.get("fontSize", 9))
        self.reconnect_interval_spin = self._spin(1, 30, settings.get("reconnect_interval", 5))
        self.form = QFormLayout(self)
        for widget in (self.buffer_size_spin, self.history_max_spin, self.font_size_spin, self.reconnect_interval_spin):
            self.form.addRow(QLabel(), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.form.addRow(buttons)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.tr("Settings"))
        for widget, text in ((self.buffer_size_spin, self.tr("Receive buffer size:")),
                             (self.history_max_spin, self.tr("Maximum send history:")),
                             (self.font_size_spin, self.tr("Receive font size:")),
                             (self.reconnect_interval_spin, self.tr("Reconnect interval (seconds):"))):
            self.form.labelForField(widget).setText(text)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.LanguageChange and hasattr(self, "form"):
            self.retranslate_ui()
    @staticmethod
    def _spin(minimum, maximum, value):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin
    def _save(self):
        self.config_manager.set_global_settings({
            "receive_buffer_size": self.buffer_size_spin.value(),
            "send_history_max": self.history_max_spin.value(),
            "fontSize": self.font_size_spin.value(),
            "reconnect_interval": self.reconnect_interval_spin.value(),
        })
        self.accept()
