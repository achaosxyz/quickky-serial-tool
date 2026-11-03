# Serial Communication Design

## 1. Scope

This document defines the current serial-port ownership, background execution, receive buffering, decoding, sending, counters, and session isolation.

## 2. Module Boundary

```text
WorkTab
  -> SerialManagerQt
       -> SerialManager
            -> pyserial
  -> SendDataUtils / ReceivePipeline / ReceiveTextView
```

`SerialManagerQt` is the Qt adaptation and pending-display buffer. `SerialManager` owns the pyserial object, receive thread, session generation, operation locks, callbacks, and health checks. Serial diagnostics use Qt translation; conversion utilities are independent of Qt and pyserial.

## 3. Open, Close, and Operation Results

- `SerialManagerQt` uses one FIFO worker; submission reports acceptance, and completion emits `operation_completed(operation, result)` with an immutable success/error result. Unexpected disconnects use `disconnected`.
- Disposal rejects later requests, drains accepted requests, and performs one final close, reusing a queued or in-progress close. `wait_disposed` returns the result directly or a timeout.
- `SerialManager.open()` starts a bounded open worker, records a session generation, and starts the receive thread only after the port opens.
- Open, close, and send use a one-second caller timeout. A timed-out open is invalidated so a late port is closed rather than attached to a newer session.
- A new open is rejected while an earlier open, close, or receive thread still owns the preceding session.
- Close invalidates the receive generation and stops reception immediately, but retains the port reference until the port actually closes. A failed close can be retried.
- Send permits one write in flight and rejects concurrent writes until the earlier worker finishes.

The UI derives controls from explicit disconnected, opening, open, closing, and close-failed states. It stops loop sending during close or disconnect and schedules reconnect only when enabled and not manually closed. Cleanup waits at most two seconds for serial disposal.

## 4. Receive Thread and Session Isolation

Each receive loop holds its own port object, stop event, and generation. Before delivering bytes, it verifies that the generation and port still identify the active session. Data read after invalidation is discarded rather than delivered to a new session.

The loop sleeps briefly when no bytes are pending and performs periodic health checks using port enumeration and pyserial status properties. A failed current-session health check closes that port and emits the disconnect callback.

## 5. Bounded Display Buffer

`SerialManagerQt` stores received chunks in a deque protected by a lock:

- Maximum pending data: 4 MiB.
- UI drain interval: 50 ms (20 Hz target), coalescing paints while leaving serial reads independent of GUI refreshes.
- Maximum UI drain: 32 KiB per batch, limiting synchronous decode, insertion and logging work during input bursts. The nominal drain budget exceeds 4-Mbaud 8N1 payload traffic, but physical high-baud throughput still requires separate verification.
- Overflow drops the incoming chunk, accumulates dropped-byte counts, and leaves already queued data intact.
- Session reset clears pending and dropped state so old bytes are not displayed under a new port session.

RX statistics include both displayed and dropped bytes and are accumulated on every drain. The label is coalesced separately at a 200-ms target; TX completion and reset remain immediate. Oversized chunks are split across drains without reordering.

## 6. TEXT and HEX Reception

TEXT reception uses incremental decoding so multibyte characters may cross drain boundaries. UTF-8 uses strict decoding; ASCII follows the existing GB2312/GBK fallback sequence. Valid whitespace is preserved, CRLF/CR are normalized for line processing, and only genuinely empty lines are filtered.

`ReceivePipeline` owns the decoder, segmenter and shared formatter state. Without timestamps, TEXT segments are joined before formatting and no clock is consulted. `ReceiveTextView` owns bounded document insertion, level colours and scrolling. Both TEXT and HEX use display-only continuation blocks for lines over 1,024 UTF-16 units; copying/exporting logical text removes those synthetic breaks, and the text returned for logging never contains them. WorkTab translates its controls on Qt language-change events without replacing user data.

HEX reception formats bytes as uppercase, space-separated values and resets text decoder/segmenter state. There is no fixed byte-count row limit. The receive formatter also supports timestamped log mode; continuous data lasting more than 100 ms starts a new timestamped line.

## 7. Sending

`WorkTab` captures the editor payload and current send settings. `SendDataUtils` normalizes logical newlines to internal CRLF and applies the selected CR, LF, or CRLF only to user-entered logical line breaks. It never appends an extra line ending.

- TEXT uses the selected encoding; ASCII sending follows the existing GB2312/GBK fallback sequence.
- HEX accepts whitespace, commas, hyphens, colons, newlines, and `0x` prefixes, then parses exact bytes without line-ending conversion.
- TEXT/HEX editor conversion uses the same encoding and line-ending rules.
- `SendDataUtils` prepares bytes once; `SerialManager` accepts only bytes and the actual byte count drives TX statistics.
- A successful send updates TX and memory history, notifies the history panel, and starts the next loop-send timer when requested.
- Empty payloads, invalid HEX, encoding failure, a closed port, or an in-flight send do not create successful history entries.
