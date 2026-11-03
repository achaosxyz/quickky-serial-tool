"""Test-owned, bidirectional localhost serial endpoint relay."""

import select
import socket
import threading
from queue import Empty, Queue


class SocketRelay:
    """Relay two independent socket:// clients without system serial ports."""

    def __init__(self):
        self._listeners = []
        self._clients = [None, None]
        self.connected = [threading.Event(), threading.Event()]
        self.available = [threading.Event(), threading.Event()]
        self._pending = [bytearray(), bytearray()]
        self.discarded = [0, 0]
        self._commands = Queue()
        self._stop = threading.Event()
        self._error = None
        try:
            for _ in range(2):
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._listeners.append(listener)
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.setblocking(False)
        except BaseException:
            for listener in self._listeners:
                listener.close()
            raise
        self.endpoints = tuple(f"socket://127.0.0.1:{s.getsockname()[1]}" for s in self._listeners)
        self._addresses = tuple(s.getsockname() for s in self._listeners)
        for event in self.available:
            event.set()
        self._thread = threading.Thread(target=self._run, name="test-socket-relay", daemon=True)
        self._thread.start()

    def _run(self):
        try:
            while not self._stop.is_set():
                self._process_commands()
                clients = [client for client in self._clients if client is not None]
                writable = [client for i, client in enumerate(self._clients)
                            if client is not None and self._pending[i]]
                listeners = [listener for listener in self._listeners if listener is not None]
                if not listeners and not clients:
                    self._stop.wait(0.05)
                    continue
                readable, ready_write, _ = select.select(listeners + clients, writable, [], 0.05)
                for index, listener in enumerate(self._listeners):
                    if listener is not None and listener in readable:
                        client, _ = listener.accept()
                        client.setblocking(False)
                        if self._clients[index] is None:
                            self._clients[index] = client
                            self.connected[index].set()
                        else:
                            client.close()
                for index, client in enumerate(self._clients):
                    if client is None:
                        continue
                    if client in readable:
                        try:
                            data = client.recv(65536)
                        except (ConnectionResetError, ConnectionAbortedError):
                            data = b""
                        if not data:
                            client.close()
                            self._clients[index] = None
                            self.connected[index].clear()
                            self._pending[index].clear()
                            continue
                        if self._clients[1 - index] is not None:
                            self._pending[1 - index].extend(data)
                        else:
                            self.discarded[index] += len(data)
                    if client in ready_write and self._pending[index]:
                        try:
                            sent = client.send(self._pending[index])
                            del self._pending[index][:sent]
                        except (ConnectionResetError, ConnectionAbortedError):
                            client.close()
                            self._clients[index] = None
                            self.connected[index].clear()
                            self._pending[index].clear()
        except Exception as error:
            self._error = error
        finally:
            for index, client in enumerate(self._clients):
                if client is not None:
                    client.close()
                self._clients[index] = None
                self.connected[index].clear()
            for index, listener in enumerate(self._listeners):
                if listener is not None:
                    listener.close()
                self._listeners[index] = None
                self.available[index].clear()

    def _process_commands(self):
        while True:
            try:
                action, index, done, result = self._commands.get_nowait()
            except Empty:
                return
            try:
                if action == "remove":
                    if self._listeners[index] is not None:
                        self._listeners[index].close()
                        self._listeners[index] = None
                        self.available[index].clear()
                    client = self._clients[index]
                    if client is not None:
                        try:
                            client.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass  # The peer may have already disconnected.
                        client.close()
                        self._clients[index] = None
                        self.connected[index].clear()
                    self._pending[0].clear()
                    self._pending[1].clear()
                elif self._listeners[index] is None:
                    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        listener.bind(self._addresses[index])
                        listener.listen(1)
                        listener.setblocking(False)
                    except BaseException:
                        listener.close()
                        raise
                    self._listeners[index] = listener
                    self.available[index].set()
            except Exception as error:
                result.append(error)
            finally:
                done.set()

    def set_available(self, index, available):
        """Remove or restore one endpoint on the relay thread."""
        if index not in (0, 1):
            raise ValueError("Endpoint index must be 0 or 1")
        done, result = threading.Event(), []
        self._commands.put(("restore" if available else "remove", index, done, result))
        if not done.wait(2):
            raise RuntimeError("Relay control timed out")
        if result:
            raise RuntimeError("Relay control failed") from result[0]

    def get_available_ports(self):
        return [endpoint for endpoint, available in zip(self.endpoints, self.available) if available.is_set()]

    def close(self):
        self._stop.set()
        self._thread.join(2)
        if self._thread.is_alive():
            raise RuntimeError("Socket relay did not stop")
        if self._error is not None:
            raise RuntimeError("Socket relay failed") from self._error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
