"""Command sidebar."""

from PySide6.QtCore import QEvent, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .quick_commands_panel_qt import QuickCommandsPanel
from .send_history_panel_qt import SendHistoryPanel


class CommandPanel(QWidget):
    send_requested = Signal(str, str)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.setFont(QFont(self.font().family(), 7))
        self.quick_commands_panel = QuickCommandsPanel(config_manager, self)
        self.send_history_panel = SendHistoryPanel(config_manager, self)
        self.quick_commands_panel.send_requested.connect(self.send_requested)
        self.send_history_panel.send_requested.connect(self.send_requested)
        self.notebook = QTabWidget()
        self.notebook.setDocumentMode(True)
        self.notebook.setFont(self.font())
        self.notebook.addTab(self.quick_commands_panel, self.tr("Quick commands"))
        self.notebook.addTab(self.send_history_panel, self.tr("Send history"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.notebook)
        self.setFixedWidth(250)

    def refresh_history(self):
        self.send_history_panel.refresh()

    def retranslate_ui(self):
        self.notebook.setTabText(0, self.tr("Quick commands"))
        self.notebook.setTabText(1, self.tr("Send history"))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.LanguageChange and hasattr(self, "notebook"):
            self.retranslate_ui()
