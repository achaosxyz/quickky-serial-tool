"""Send history panel."""

from datetime import datetime

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHeaderView, QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class SendHistoryPanel(QWidget):
    send_requested = Signal(str, str)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager, self.items = config_manager, []
        self.table = QTableWidget(0, 2)
        compact_font = QFont(self.table.font().family(), 7)
        self.table.setFont(compact_font)
        self.table.horizontalHeader().setFont(compact_font)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setHorizontalHeaderLabels([self.tr("Time"), self.tr("Data")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.itemDoubleClicked.connect(lambda _item: self._send_selected())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        self.refresh()
    def refresh(self):
        self.table.setRowCount(0)
        self.items = self.config_manager.get_send_history()
        for item in self.items:
            item = {"data": item, "mode": "TEXT", "time": ""} if isinstance(item, str) else item
            row = self.table.rowCount()
            self.table.insertRow(row)
            time = item.get("time", "")
            try: time = datetime.strptime(time, "%Y-%m-%d %H:%M:%S").strftime("%m-%d %H:%M:%S")
            except ValueError: pass
            data = str(item.get("data", "")).replace("\r", "\\r").replace("\n", "\\n")
            data = ("[H] " if item.get("mode") == "HEX" else "[T] ") + data
            self.table.setItem(row, 0, QTableWidgetItem(time))
            self.table.setItem(row, 1, QTableWidgetItem(data))
    def _menu(self, pos):
        item = self.table.itemAt(pos)
        if item: self.table.selectRow(item.row())
        else: self.table.clearSelection(); self.table.setCurrentItem(None)
        menu = QMenu(self)
        row = self.table.currentRow()
        if row >= 0: send = menu.addAction(self.tr("Send")); send.triggered.connect(self._send_selected)
        clear = menu.addAction(self.tr("Clear history"))
        clear.triggered.connect(self._clear)
        menu.exec(self.table.viewport().mapToGlobal(pos))
    def _send_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            return
        item = self.items[row]
        item = {"data": item, "mode": "TEXT"} if isinstance(item, str) else item
        self.send_requested.emit(str(item.get("data", "")), item.get("mode", "TEXT"))
    def _clear(self):
        if QMessageBox.question(self, self.tr("Confirm"), self.tr("Clear all send history?")) == QMessageBox.Yes: self.config_manager.clear_send_history(); self.refresh()

    def retranslate_ui(self):
        self.table.setHorizontalHeaderLabels([self.tr("Time"), self.tr("Data")])

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.LanguageChange and hasattr(self, "table"):
            self.retranslate_ui()
