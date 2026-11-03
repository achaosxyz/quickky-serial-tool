"""Bounded receive display with level-specific colours and deferred scrolling."""

from PySide6.QtCore import QTimer
from PySide6.QtGui import (
    QAction, QColor, QGuiApplication, QKeySequence, QTextCharFormat, QTextCursor, QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit


class ReceiveTextView(QPlainTextEdit):
    LOG_LEVEL_PROPERTY = int(QTextFormat.UserProperty) + 1
    MAX_BLOCK_CHARS = 1024
    CONTINUATION_BLOCK = 1

    def __init__(self, max_chars=4 * 1024 * 1024, parent=None):
        super().__init__(parent)
        self.max_chars = max_chars
        self._theme_manager = None
        self._auto_scroll = False
        self._scroll_pending = False
        self._formats = {}
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def _color(self, level):
        defaults = {"normal": "#000000", "info": "#0066CC", "error": "#D32F2F", "success": "#388E3C", "warning": "#D32F2F"}
        colors = self._theme_manager.get_theme_colors() if self._theme_manager else {}
        return colors.get("text_fg" if level == "normal" else f"log_{level}_color", defaults[level])

    def append_text(self, text, level="normal", auto_scroll=True, max_blocks=None):
        if not text:
            return
        document = self.document()
        if max_blocks is not None and document.maximumBlockCount() != max_blocks:
            document.setMaximumBlockCount(max_blocks)
        if level != "normal" and document.lastBlock().length() > 1 and not text.startswith("\n"):
            text = "\n" + text
        if level not in self._formats:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(self._color(level)))
            fmt.setProperty(self.LOG_LEVEL_PROPERTY, level)
            self._formats[level] = fmt
        fmt = self._formats[level]
        # An independent cursor leaves the user's selection and horizontal scroll intact.
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.End)
        cursor.beginEditBlock()
        self._insert_bounded(cursor, text, fmt)
        excess = document.characterCount() - self.max_chars
        if excess > 0:
            # Jump by UTF-16 position rather than stepping through thousands of glyphs.
            if 0xDC00 <= ord(document.characterAt(excess)) <= 0xDFFF:
                excess += 1
            cursor.setPosition(0)
            cursor.setPosition(excess, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        cursor.endEditBlock()
        self._auto_scroll = auto_scroll
        if auto_scroll and not self._scroll_pending:
            self._scroll_pending = True
            QTimer.singleShot(0, self._scroll_to_bottom)
        return text

    def _insert_bounded(self, cursor, text, fmt):
        """Split pathological TEXT/HEX lines into bounded display-only blocks."""
        units = len(text) if text.isascii() else len(text.encode("utf-16-le")) // 2
        if units <= self.MAX_BLOCK_CHARS - (cursor.block().length() - 1):
            cursor.insertText(text, fmt)
            return
        for index, line in enumerate(text.split("\n")):
            if index:
                cursor.insertBlock()
                cursor.block().setUserState(-1)
            offset = 0
            while offset < len(line):
                available = self.MAX_BLOCK_CHARS - (cursor.block().length() - 1)
                chunk = line[offset:offset + max(0, available)]
                if not chunk.isascii():
                    # Qt positions count UTF-16 units; never bisect a surrogate pair.
                    chunk = chunk.encode("utf-16-le")[:max(0, available) * 2].decode("utf-16-le", errors="ignore")
                if not chunk:
                    cursor.insertBlock()
                    cursor.block().setUserState(self.CONTINUATION_BLOCK)
                    continue
                if len(chunk) == available:
                    # Keep nearby words and HEX byte tokens together when possible.
                    boundary = max(chunk.rfind(" "), chunk.rfind("\t")) + 1
                    if max(0, len(chunk) - 32) < boundary < len(chunk):
                        chunk = chunk[:boundary]
                cursor.insertText(chunk, fmt)
                offset += len(chunk)
                if offset < len(line):
                    cursor.insertBlock()
                    cursor.block().setUserState(self.CONTINUATION_BLOCK)

    def _plain_text(self, cursor):
        """Export logical text, omitting only our display continuation breaks."""
        # Repositioning a cursor per block forces lazy layouts across a large history.
        parts = cursor.selectedText().split("\u2029")
        block = self.document().findBlock(cursor.selectionStart())
        result = [parts[0]]
        for part in parts[1:]:
            block = block.next()
            if block.userState() != self.CONTINUATION_BLOCK:
                result.append("\n")
            result.append(part)
        return "".join(result)

    def toPlainText(self):
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.Document)
        return self._plain_text(cursor)

    def copy(self):
        if self.textCursor().hasSelection():
            QGuiApplication.clipboard().setText(self._plain_text(self.textCursor()))

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy()
            event.accept()
        else:
            super().keyPressEvent(event)

    def createStandardContextMenu(self, *args):
        menu = super().createStandardContextMenu(*args)
        copy_action = menu.findChild(QAction, "edit-copy")
        copy_action.triggered.disconnect()
        copy_action.triggered.connect(self.copy)
        return menu

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu(event.pos())
        menu.exec(event.globalPos())
        menu.deleteLater()

    def _scroll_to_bottom(self):
        self._scroll_pending = False
        if self._auto_scroll:
            bar = self.verticalScrollBar()
            bar.setValue(bar.maximum())

    def apply_theme(self, theme_manager):
        self._theme_manager = theme_manager
        self._formats.clear()
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
