"""Bounded receive display with level-specific colours and deferred scrolling."""

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit


class ReceiveTextView(QPlainTextEdit):
    LOG_LEVEL_PROPERTY = int(QTextFormat.UserProperty) + 1

    def __init__(self, max_chars=4 * 1024 * 1024, parent=None):
        super().__init__(parent)
        self.max_chars = max_chars
        self._theme_manager = None
        self._auto_scroll = False
        self._scroll_pending = False
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def _color(self, level):
        defaults = {"normal": "#000000", "info": "#0066CC", "error": "#D32F2F", "success": "#388E3C", "warning": "#D32F2F"}
        colors = self._theme_manager.get_theme_colors() if self._theme_manager else {}
        return colors.get("text_fg" if level == "normal" else f"log_{level}_color", defaults[level])

    def append_text(self, text, level="normal", auto_scroll=True, max_blocks=None):
        if not text:
            return
        if max_blocks is not None and self.document().maximumBlockCount() != max_blocks:
            self.document().setMaximumBlockCount(max_blocks)
        if level != "normal" and self.document().characterCount() > 1 and not self.toPlainText().endswith("\n") and not text.startswith("\n"):
            text = "\n" + text
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._color(level)))
        fmt.setProperty(self.LOG_LEVEL_PROPERTY, level)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text, fmt)
        excess = self.document().characterCount() - self.max_chars
        if excess > 0:
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, excess)
            cursor.removeSelectedText()
        self._auto_scroll = auto_scroll
        if auto_scroll and not self._scroll_pending:
            self._scroll_pending = True
            QTimer.singleShot(0, self._scroll_to_bottom)
        return text

    def _scroll_to_bottom(self):
        self._scroll_pending = False
        if self._auto_scroll:
            bar = self.verticalScrollBar()
            bar.setValue(bar.maximum())

    def apply_theme(self, theme_manager):
        self._theme_manager = theme_manager
        document = self.document()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                level = fragment.charFormat().property(self.LOG_LEVEL_PROPERTY)
                if level:
                    cursor = QTextCursor(document)
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                    fmt = fragment.charFormat()
                    fmt.setForeground(QColor(self._color(level)))
                    cursor.setCharFormat(fmt)
                iterator += 1
            block = block.next()
