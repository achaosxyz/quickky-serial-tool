"""Quick-command editor dialog."""

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QComboBox, QMessageBox)

from utils.hex_utils import HexUtils
from utils.send_data_utils import SendDataUtils


class QuickCommandDialog(QDialog):
    def __init__(self, parent=None, command=None):
        super().__init__(parent)
        self.editing = bool(command)
        self.name_text, self.data_text, self.mode_combo = QLineEdit(), QPlainTextEdit(), QComboBox()
        self.mode_combo.addItems(["TEXT", "HEX"])
        self.form = QFormLayout(self)
        for widget in (self.name_text, self.data_text, self.mode_combo):
            self.form.addRow(QLabel(), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.form.addRow(buttons)
        self.retranslate_ui()
        if command: self.name_text.setText(command.get("name", "")); self.data_text.setPlainText(command.get("data", command.get("command", ""))); self.mode_combo.setCurrentText(command.get("mode", "TEXT"))
    def _accept(self):
        data = self.data_text.toPlainText()
        if not self.name_text.text().strip() or not data.strip(): QMessageBox.warning(self, self.tr("Invalid input"), self.tr("Command name and data cannot be empty.")); return
        if self.mode_combo.currentText() == "HEX" and not HexUtils.validate_hex_format(data): QMessageBox.warning(self, self.tr("Invalid input"), self.tr("Invalid HEX format.")); return
        self.accept()
    def get_command(self):
        data = self.data_text.toPlainText()
        mode = self.mode_combo.currentText()
        if mode == "TEXT":
            data = SendDataUtils.normalize_text_newlines(data)
        return {"name": self.name_text.text().strip(), "data": data, "command": data, "mode": mode}

    def retranslate_ui(self):
        self.setWindowTitle(self.tr("Edit command") if self.editing else self.tr("Add command"))
        for widget, text in ((self.name_text, self.tr("Command name:")),
                             (self.data_text, self.tr("Command data:")),
                             (self.mode_combo, self.tr("Send mode:"))):
            self.form.labelForField(widget).setText(text)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.LanguageChange and hasattr(self, "form"):
            self.retranslate_ui()
