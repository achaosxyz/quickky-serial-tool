"""Asynchronous bounded log writer."""

import threading
from collections import deque
from pathlib import Path
from PySide6.QtCore import QCoreApplication


class LogWriter:
    """Write logs in a background thread with a bounded queue."""

    def __init__(self, max_pending_bytes=4 * 1024 * 1024):
        self._queue = deque()
        self._condition = threading.Condition()
        self._pending_bytes = 0
        self._max_pending_bytes = max_pending_bytes
        self._dropped_bytes = 0
        self._errors = deque()
        self._stopped = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _put_control(self, command, value=None, generation=None):
        with self._condition:
            if self._stopped:
                return False
            self._queue.append((command, value, 0, generation))
            self._condition.notify()
            return True

    def open(self, path, generation=None):
        return self._put_control("open", path, generation)

    def write(self, text, generation=None):
        size = len(text.encode("utf-8"))
        with self._condition:
            if self._stopped:
                return False
            if self._pending_bytes + size > self._max_pending_bytes:
                self._dropped_bytes += size
                return False
            self._queue.append(("write", text, size, generation))
            self._pending_bytes += size
            self._condition.notify()
            return True

    def close(self, generation=None):
        return self._put_control("close", generation=generation)

    def stop(self, timeout=1.0):
        """Drain queued content and wait a bounded time for shutdown."""
        with self._condition:
            if not self._stopped:
                self._stopped = True
                self._queue.append(("stop", None, 0, None))
                self._condition.notify()
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def take_dropped_bytes(self):
        with self._condition:
            dropped, self._dropped_bytes = self._dropped_bytes, 0
            return dropped

    def take_errors(self, generation=None):
        """Consume background errors, optionally filtered by generation."""
        with self._condition:
            if generation is None:
                errors = [message for _generation, message in self._errors]
                self._errors.clear()
                return errors
            errors = []
            pending = deque()
            while self._errors:
                error_generation, message = self._errors.popleft()
                if error_generation == generation:
                    errors.append(message)
                else:
                    pending.append((error_generation, message))
            self._errors = pending
            return errors

    def take_error_events(self):
        """Consume all errors, retaining their originating session generation."""
        with self._condition:
            events = list(self._errors)
            self._errors.clear()
            return events

    def _record_error(self, message, generation=None):
        with self._condition:
            self._errors.append((generation, message))

    def _close_stream(self, stream, generation=None):
        if not stream:
            return None
        try:
            stream.flush()
        except OSError as error:
            self._record_error(QCoreApplication.translate("LogWriter", "Could not flush log file: {error}").format(error=error), generation)
        try:
            stream.close()
        except OSError as error:
            self._record_error(QCoreApplication.translate("LogWriter", "Could not close log file: {error}").format(error=error), generation)
        return None

    def _run(self):
        stream = None
        stream_generation = None
        while True:
            with self._condition:
                while not self._queue:
                    self._condition.wait()
                command, value, size, generation = self._queue.popleft()
                self._pending_bytes -= size
            if command == "open":
                if stream:
                    stream = self._close_stream(stream, stream_generation)
                    stream_generation = None
                try:
                    stream = Path(value).open("a", encoding="utf-8")
                    stream_generation = generation
                except OSError as error:
                    stream = None
                    self._record_error(QCoreApplication.translate("LogWriter", "Could not open log file: {error}").format(error=error), generation)
            elif command == "write" and stream and generation == stream_generation:
                try:
                    stream.write(value)
                except OSError as error:
                    stream = self._close_stream(stream, stream_generation)
                    self._record_error(QCoreApplication.translate("LogWriter", "Could not write log file: {error}").format(error=error), stream_generation)
                    stream_generation = None
            elif command == "close" and stream and (generation is None or generation == stream_generation):
                stream = self._close_stream(stream, stream_generation)
                stream_generation = None
            elif command == "stop":
                if stream:
                    self._close_stream(stream, stream_generation)
                return
