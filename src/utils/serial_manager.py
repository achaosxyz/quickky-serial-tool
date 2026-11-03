"""Serial port ownership and bounded operations."""

import threading
import time
from dataclasses import dataclass

import serial
import serial.tools.list_ports
from PySide6.QtCore import QCoreApplication

@dataclass(frozen=True)
class SerialOperationResult:
    success: bool
    error: str = ""

    def __bool__(self):
        return self.success


PARITY_MAP = {
    "None": serial.PARITY_NONE,
    "Even": serial.PARITY_EVEN,
    "Odd": serial.PARITY_ODD,
    "Mark": serial.PARITY_MARK,
    "Space": serial.PARITY_SPACE,
}

STOPBITS_MAP = {
    1: serial.STOPBITS_ONE,
    1.5: serial.STOPBITS_ONE_POINT_FIVE,
    2: serial.STOPBITS_TWO,
}

FLOW_CONTROL_MAP = {
    "None": (False, False),
    "Hardware": (True, False),
    "Software": (False, True),
}


class SerialManager:
    """Manage serial operations and isolate late results from new sessions."""

    def __init__(self):
        self.serial_port = None
        self.receive_thread = None
        self.is_running = False
        self.receive_callback = None
        self.disconnect_callback = None
        self.last_config = {}
        self.operation_timeout = 1.0
        self.check_interval = 0.5
        self.last_check_time = 0
        self._operation_lock = threading.RLock()
        self._open_generation = 0
        self._receive_stop_event = None
        self._open_in_flight = False
        self._close_in_flight = False
        self._send_in_flight = False

    @staticmethod
    def get_available_ports():
        return [port.device for port in serial.tools.list_ports.comports()]

    def _is_port_available(self, port_name):
        return port_name in self.get_available_ports()

    def _check_port_health(self, port):
        if not port:
            return False, "Serial port object is missing"
        try:
            if not port.is_open:
                return False, "Serial port is not open"
            port_name = port.port
            if not self._is_port_available(port_name):
                return False, f"Serial port {port_name} was removed"
            try:
                _ = port.cts
                _ = port.dsr
                _ = port.in_waiting
            except (OSError, AttributeError) as error:
                return False, f"Serial port status error: {error}"
            return True, None
        except Exception as error:
            return False, f"Serial port health check failed: {error}"

    @staticmethod
    def _close_port(port):
        try:
            if port and port.is_open:
                port.close()
            return True
        except Exception as error:
            print(f"Error closing serial port: {error}")
            return False

    def _invalidate_open(self, generation):
        """Invalidate an opening session and close any port already attached."""
        port = None
        stop_event = None
        with self._operation_lock:
            if generation != self._open_generation:
                return
            self._open_generation += 1
            self.is_running = False
            stop_event = self._receive_stop_event
            port = self.serial_port
        if stop_event:
            stop_event.set()
        if port:
            self.close()

    def open(self, port, baudrate=115200, parity="None", bytesize=8,
             stopbits=1, flow_control="None"):
        """Open with a timeout and close late-arriving connections."""
        with self._operation_lock:
            # A timeout cannot stop the driver; reject retries until it finishes.
            if self._open_in_flight or self._close_in_flight or (self.receive_thread and self.receive_thread.is_alive()):
                return SerialOperationResult(False, QCoreApplication.translate("SerialManager", "Another serial operation is in progress"))
            if self.serial_port is not None:
                return SerialOperationResult(False, QCoreApplication.translate("SerialManager", "The previous port has not been closed"))
            self._open_generation += 1
            generation = self._open_generation
            self._open_in_flight = True
            self.last_config = {
                "port": port,
                "baudrate": baudrate,
                "parity": parity,
                "bytesize": bytesize,
                "stopbits": stopbits,
                "flow_control": flow_control,
            }

        completed = threading.Event()
        result = {"success": False, "error": None}

        def open_worker():
            opened_port = None
            try:
                rtscts, xonxoff = FLOW_CONTROL_MAP.get(flow_control, (False, False))
                opened_port = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    bytesize=bytesize,
                    parity=PARITY_MAP.get(parity, serial.PARITY_NONE),
                    stopbits=STOPBITS_MAP.get(stopbits, serial.STOPBITS_ONE),
                    timeout=0.1,
                    write_timeout=self.operation_timeout,
                    rtscts=rtscts,
                    xonxoff=xonxoff,
                )
                with self._operation_lock:
                    if generation != self._open_generation:
                        if not self._close_port(opened_port):
                            self.serial_port = opened_port
                        return
                    self.serial_port = opened_port
                    self.is_running = True
                    stop_event = threading.Event()
                    self._receive_stop_event = stop_event
                    self.receive_thread = threading.Thread(
                        target=self._receive_loop,
                        args=(opened_port, stop_event, generation),
                        daemon=True,
                    )
                    self.receive_thread.start()
                    result["success"] = True
            except Exception as error:
                result["error"] = str(error)
                if opened_port:
                    closed = self._close_port(opened_port)
                    with self._operation_lock:
                        if closed and self.serial_port is opened_port:
                            self.serial_port = None
                        elif not closed:
                            self.serial_port = opened_port
            finally:
                with self._operation_lock:
                    self._open_in_flight = False
                completed.set()

        threading.Thread(target=open_worker, daemon=True).start()
        if completed.wait(self.operation_timeout):
            return SerialOperationResult(result["success"], result["error"] or "")
        self._invalidate_open(generation)
        return SerialOperationResult(False, QCoreApplication.translate("SerialManager", "Opening the port timed out after {seconds} seconds").format(seconds=self.operation_timeout))

    def close(self):
        """Close with a timeout and invalidate any ongoing open."""
        caller_thread = threading.current_thread()
        with self._operation_lock:
            if self._close_in_flight:
                return SerialOperationResult(False, QCoreApplication.translate("SerialManager", "A close operation is still in progress"))
            self._open_generation += 1
            self.is_running = False
            receive_thread = self.receive_thread
            stop_event = self._receive_stop_event
            if stop_event:
                stop_event.set()
            port = self.serial_port
            if not port:
                if self._open_in_flight:
                    return SerialOperationResult(False, QCoreApplication.translate("SerialManager", "An open operation is still in progress"))
                return SerialOperationResult(True)
            self._close_in_flight = True

        completed = threading.Event()
        result = {"success": False, "error": None}

        def close_worker():
            try:
                if port.is_open:
                    port.close()
                with self._operation_lock:
                    if self.serial_port is port:
                        self.serial_port = None
                if receive_thread and receive_thread is not caller_thread:
                    # A receiver calling close cannot wait for its own exit.
                    receive_thread.join()
                result["success"] = True
            except Exception as error:
                result["error"] = str(error)
            finally:
                with self._operation_lock:
                    if self.receive_thread is receive_thread and (receive_thread is None or not receive_thread.is_alive()):
                        self.receive_thread = None
                        self._receive_stop_event = None
                    self._close_in_flight = False
                completed.set()

        threading.Thread(target=close_worker, daemon=True).start()
        if completed.wait(self.operation_timeout):
            return SerialOperationResult(result["success"], result["error"] or "")
        return SerialOperationResult(False, QCoreApplication.translate("SerialManager", "Closing the port timed out after {seconds} seconds").format(seconds=self.operation_timeout))

    def _receive_loop(self, port, stop_event, generation):
        """Read only the port belonging to this receive generation."""
        last_check_time = 0
        while not stop_event.is_set():
            try:
                current_time = time.time()
                if current_time - last_check_time > self.check_interval:
                    last_check_time = current_time
                    is_healthy, error_message = self._check_port_health(port)
                    if not is_healthy:
                        if stop_event.is_set():
                            break
                        print(f"Serial port health check failed: {error_message}")
                        raise serial.SerialException(error_message)
                if port.is_open:
                    try:
                        if port.in_waiting:
                            data = port.read(port.in_waiting)
                            with self._operation_lock:
                                is_current = (
                                    not stop_event.is_set()
                                    and generation == self._open_generation
                                    and self.serial_port is port
                                )
                            if is_current and self.receive_callback and data:
                                self.receive_callback(data)
                        else:
                            time.sleep(0.01)
                    except serial.SerialTimeoutException:
                        continue
                    except (OSError, serial.SerialException) as error:
                        if not stop_event.is_set():
                            print(f"Read error: {error}")
                        raise
                elif not stop_event.is_set():
                    raise serial.SerialException("Invalid serial port")
                else:
                    break
            except Exception as error:
                if not stop_event.is_set():
                    print(f"Serial port disconnected: {error}")
                    with self._operation_lock:
                        is_current = generation == self._open_generation and self.serial_port is port
                        if is_current:
                            self.is_running = False
                    if is_current:
                        self.close()
                    if is_current and self.disconnect_callback:
                        self.disconnect_callback()
                break
        with self._operation_lock:
            if self.receive_thread is threading.current_thread():
                self.receive_thread = None
                self._receive_stop_event = None

    def send(self, data: bytes):
        """Write with a timeout and reject concurrent writes until completion."""
        if not isinstance(data, bytes):
            raise TypeError("serial data must be bytes")
        with self._operation_lock:
            if not self.serial_port or not self.serial_port.is_open or self._send_in_flight:
                return SerialOperationResult(False, QCoreApplication.translate("SerialManager", "Port is closed or a send is in progress"))
            self._send_in_flight = True
            port = self.serial_port

        completed = threading.Event()
        result = {"success": False, "error": None}

        def send_worker():
            try:
                written = port.write(data)
                if written != len(data):
                    raise serial.SerialException(QCoreApplication.translate("SerialManager", "Only {written}/{total} bytes were written").format(written=written, total=len(data)))
                result["success"] = True
            except serial.SerialTimeoutException:
                result["error"] = QCoreApplication.translate("SerialManager", "Send timed out")
            except Exception as error:
                result["error"] = str(error)
            finally:
                with self._operation_lock:
                    self._send_in_flight = False
                completed.set()

        threading.Thread(target=send_worker, daemon=True).start()
        if completed.wait(self.operation_timeout):
            return SerialOperationResult(result["success"], result["error"] or "")
        return SerialOperationResult(False, QCoreApplication.translate("SerialManager", "Sending timed out after {seconds} seconds").format(seconds=self.operation_timeout))

    def set_receive_callback(self, callback):
        self.receive_callback = callback

    def set_disconnect_callback(self, callback):
        self.disconnect_callback = callback

    def is_open(self):
        return self.serial_port and self.serial_port.is_open

    def has_port_ownership(self):
        with self._operation_lock:
            return self.serial_port is not None
