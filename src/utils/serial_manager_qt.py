"""Qt adapter for background serial operations."""

from collections import deque
import threading

from PySide6.QtCore import QObject, Signal

from .serial_manager import SerialManager, SerialOperationResult


class SerialManagerQt(QObject):
    """Expose serial callbacks as signals and bound pending display data."""

    disconnected = Signal()
    operation_completed = Signal(str, object)

    def __init__(self, max_pending_bytes=4 * 1024 * 1024):
        super().__init__()
        self._manager = SerialManager()
        self._pending = deque()
        self._pending_bytes = 0
        self._max_pending_bytes = max_pending_bytes
        self._lock = threading.Lock()
        self._condition = threading.Condition()
        self._operations = deque()
        self._current_operation = None
        self._disposed = False
        self._dispose_result = None
        self._dispose_done = threading.Event()
        self._dropped_bytes = 0
        self._manager.set_receive_callback(self._enqueue)
        self._manager.set_disconnect_callback(self._emit_disconnected)
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _enqueue(self, data):
        with self._lock:
            if self._pending_bytes + len(data) > self._max_pending_bytes:
                self._dropped_bytes += len(data)
                return
            self._pending.append(data)
            self._pending_bytes += len(data)

    def drain(self, max_bytes=256 * 1024):
        """Return a display batch and the number of dropped bytes."""
        chunks, total = [], 0
        with self._lock:
            while self._pending and total < max_bytes:
                chunk = self._pending.popleft()
                remaining = max_bytes - total
                if len(chunk) > remaining:
                    chunks.append(chunk[:remaining])
                    self._pending.appendleft(chunk[remaining:])
                    self._pending_bytes -= remaining
                    total += remaining
                    break
                chunks.append(chunk)
                total += len(chunk)
                self._pending_bytes -= len(chunk)
            dropped, self._dropped_bytes = self._dropped_bytes, 0
        return b"".join(chunks), dropped

    def clear_pending(self):
        """Discard pending data when the session changes."""
        with self._lock:
            self._pending.clear()
            self._pending_bytes = 0
            self._dropped_bytes = 0

    def _emit_disconnected(self):
        try:
            self.disconnected.emit()
        except RuntimeError:
            # A receive callback can outlive its QObject.
            pass

    def _emit_operation_completed(self, operation, success):
        try:
            self.operation_completed.emit(operation, success)
        except RuntimeError:
            # Ignore late results after QObject destruction.
            pass

    def _submit(self, operation, callback):
        with self._condition:
            if self._disposed:
                return False
            self._operations.append((operation, callback))
            self._condition.notify()
            return True

    def _run(self):
        while True:
            with self._condition:
                while not self._operations:
                    self._condition.wait()
                operation, callback = self._operations.popleft()
                self._current_operation = operation
            try:
                result = callback()
            except Exception as error:
                result = SerialOperationResult(False, str(error))
            with self._condition:
                self._current_operation = None
                final = self._disposed and not self._operations
                if final:
                    self._dispose_result = result
                    self._dispose_done.set()
            self._emit_operation_completed(operation, result)
            if final:
                return

    def dispose(self):
        with self._condition:
            if self._disposed:
                return
            self._disposed = True
            last = self._operations[-1][0] if self._operations else self._current_operation
            if last != "close":
                self._operations.append(("close", self._manager.close))
            self._condition.notify()

    def wait_disposed(self, timeout):
        if not self._dispose_done.wait(timeout):
            return SerialOperationResult(False, self.tr("Timed out waiting for serial disposal"))
        return self._dispose_result

    def open_async(self, **settings):
        return self._submit("open", lambda: self._manager.open(**settings))

    def close_async(self):
        return self._submit("close", self._manager.close)

    def send_async(self, data: bytes):
        if not isinstance(data, bytes):
            raise TypeError("serial data must be bytes")
        return self._submit("send", lambda: self._manager.send(data))

    def is_open(self):
        return self._manager.is_open()

    def has_port_ownership(self):
        return self._manager.has_port_ownership()
