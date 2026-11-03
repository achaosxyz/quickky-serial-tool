# Logging Design

## 1. Scope

This document defines current serial log-file selection, timestamp formatting, asynchronous writes, bounded queues, generations, error collection, and shutdown behavior.

## 2. Session Ownership

Each `WorkTab` owns one `LogWriter`, the selected `log_file_path`, a log-enabled flag, and a monotonically increasing log generation. `LogWriter` owns its background thread, queue, active file stream, dropped-byte count, and collected errors.

Changing the port, disabling file logging, suspending a hidden secondary tab, or cleaning up a tab closes the current log session so bytes from different serial sessions do not share a file unintentionally.

## 3. File Selection

The file dialog suggests a port-and-timestamp-based name and starts in the last selected log directory when available. Selection immediately verifies that the path can be opened for append; the directory is saved, while the concrete file path remains runtime-only.

The writer then opens the selected file in its background thread. If asynchronous open fails, the tab collects the error, disables logging, clears the save-log checkbox, and displays the reason.

## 4. Timestamped Log Mode

Timestamped mode is a receive-formatting option independent of whether file logging is enabled. `ReceiveLogFormatter` tracks line endings and the last timestamp. It prefixes new lines with millisecond timestamps and inserts a new timestamped line when continuous data exceeds 100 ms. The same formatted text is used for the receive editor and file logging.

## 5. Bounded Background Writes

`LogWriter` uses a condition variable and FIFO deque for open, write, close, and stop commands.

- Maximum queued write payload: 4 MiB.
- Queue capacity counts UTF-8 payload bytes, not text character count.
- Overflow drops the new write, increments dropped-byte statistics, and does not block the UI thread.
- The active stream remains open across writes to avoid repeated file open/close in the receive path.
- Writes and close operations are tagged with their log generation; writes from an older generation are not applied to a newer stream.
- The UI consumes generation-tagged errors from all sessions. Errors from the current session disable logging; older close errors are reported without disabling a newer session.

Queue overflow disables the current logging session, clears its checkbox, and reports the dropped byte count. File open, write, flush, and close exceptions are converted into Qt-translatable diagnostic error messages rather than terminating the worker.

## 6. Close and Shutdown

Normal log close is queued behind earlier writes, then flushes and closes the active stream. Final `stop()` appends a stop command, prevents new queue entries, and waits up to one second for queued work and stream cleanup. WorkTab cleanup returns a list containing any serial, logging timeout, overflow, or unconsumed flush/close errors for its owner to aggregate.

The receive UI does not perform continuous file writes or flushes. Shutdown prioritizes a bounded, explicit result over indefinite waiting on a failed filesystem or driver.
