"""Serial receive formatting and log-mode helpers."""

import codecs
from datetime import datetime


class ReceiveTextDecoder:
    """Incrementally decode serial bytes across batch boundaries."""

    def __init__(self):
        self._encoding = None
        self._decoder = None

    def reset(self):
        """Discard any incomplete multibyte sequence."""
        self._encoding = None
        self._decoder = None

    def decode(self, data, encoding):
        """Decode bytes, falling back from ASCII to GB2312 and GBK."""
        candidates = ReceiveDataUtils.get_encoding_candidates(encoding)
        if self._encoding not in candidates:
            self.reset()
        if self._decoder:
            try:
                return self._decoder.decode(data)
            except UnicodeDecodeError:
                self.reset()
        for candidate in candidates:
            try:
                decoder = codecs.getincrementaldecoder(candidate)(errors="strict")
                text = decoder.decode(data)
            except (LookupError, UnicodeDecodeError):
                continue
            self._encoding = candidate
            self._decoder = decoder
            return text
        return str(data)


class ReceiveTextSegmenter:
    """Filter empty lines while retaining whitespace and line endings."""

    def __init__(self):
        self._line_has_content = False

    def reset(self):
        """Reset the current line state."""
        self._line_has_content = False

    def iter_segments(self, text):
        """Yield display segments, ignoring only genuinely empty lines."""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        for segment in normalized.splitlines(True):
            if segment.endswith("\n"):
                content = segment[:-1]
                if content:
                    yield segment
                elif self._line_has_content:
                    # A separate newline must still terminate the previous text.
                    yield "\n"
                self._line_has_content = False
            elif segment:
                # Spaces and tabs may be protocol data.
                self._line_has_content = True
                yield segment


class ReceiveLogFormatter:
    """Maintain timestamp formatting state across receive batches."""

    MAX_CONTINUOUS_SECONDS = 0.1

    def __init__(self):
        self.reset()

    def reset(self):
        """Make the next log entry start with a timestamp."""
        self.last_timestamp_time = None
        self.last_line_ended = True

    def format(self, text, log_mode, now=None):
        """Format text for display and logging."""
        if not text:
            return ""
        if not log_mode:
            self.last_line_ended = text.endswith("\n")
            self.last_timestamp_time = None
            return text
        now = now or datetime.now()
        needs_timestamp = (
            self.last_line_ended
            or self.last_timestamp_time is None
            or (now - self.last_timestamp_time).total_seconds() > self.MAX_CONTINUOUS_SECONDS
        )
        if needs_timestamp:
            timestamp = now.strftime("[%H:%M:%S.%f")[:-3] + "] "
            prefix = "" if self.last_line_ended or text.startswith("\n") else "\n"
            text = prefix + timestamp + text
            # Measure from the timestamp, not the previous packet.
            self.last_timestamp_time = now
        self.last_line_ended = text.endswith("\n")
        return text


class ReceiveDataUtils:
    """Provide receive data formatting helpers."""

    @staticmethod
    def get_encoding_candidates(encoding):
        normalized = encoding.replace("-", "").lower()
        return (normalized, "gb2312", "gbk") if normalized == "ascii" else (normalized,)

    @staticmethod
    def format_hex(data):
        """Format bytes as space-separated hexadecimal text."""
        return data.hex(" ").upper() + (" " if data else "")


class ReceivePipeline:
    """Own all receive formatting state across batches and system messages."""

    def __init__(self):
        self.decoder = ReceiveTextDecoder()
        self.segmenter = ReceiveTextSegmenter()
        self.formatter = ReceiveLogFormatter()

    def reset(self):
        self.decoder.reset()
        self.segmenter.reset()
        self.formatter.reset()

    def process(self, data, settings):
        if settings["mode"] == "HEX":
            self.decoder.reset()
            self.segmenter.reset()
            return self.formatter.format(ReceiveDataUtils.format_hex(data), settings["log_mode"])
        text = self.decoder.decode(data, settings["encoding"])
        if not settings["log_mode"]:
            return self.formatter.format("".join(self.segmenter.iter_segments(text)), False)
        return "".join(self.formatter.format(part, settings["log_mode"])
                       for part in self.segmenter.iter_segments(text))

    def format_system(self, text, log_mode):
        return self.formatter.format(text, log_mode)
