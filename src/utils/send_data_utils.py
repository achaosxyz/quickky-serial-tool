"""Shared send-data conversion helpers."""

from utils.hex_utils import HexUtils


class SendDataUtils:
    """Prepare line endings, hexadecimal data and text encoding."""

    LINE_ENDINGS = {"CR": "\r", "LF": "\n", "CRLF": "\r\n"}

    @classmethod
    def prepare(cls, data, mode, encoding, line_ending="CRLF"):
        if mode == "HEX":
            return cls.parse_hex(data)
        if mode == "TEXT":
            return cls.encode_text(data, encoding, line_ending)[2]
        raise ValueError("Unsupported send mode")

    @staticmethod
    def normalize_text_newlines(text):
        """Normalize editor newlines to internal CRLF."""
        return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

    @classmethod
    def apply_line_ending(cls, text, line_ending="CRLF"):
        """Convert internal CRLF to the selected serial line ending."""
        if line_ending not in cls.LINE_ENDINGS:
            raise ValueError("Unsupported send line ending")
        return cls.normalize_text_newlines(text).replace("\r\n", cls.LINE_ENDINGS[line_ending])

    @classmethod
    def restore_line_ending(cls, text, line_ending="CRLF"):
        """Restore the selected line ending to editor CRLF."""
        if line_ending not in cls.LINE_ENDINGS:
            raise ValueError("Unsupported send line ending")
        return cls.normalize_text_newlines(text.replace(cls.LINE_ENDINGS[line_ending], "\n"))

    @staticmethod
    def get_encoding_candidates(encoding):
        """Return the supported encoding candidates in order."""
        return (encoding, "GB2312", "GBK") if encoding.upper() == "ASCII" else (encoding,)

    @staticmethod
    def parse_hex(text):
        """Parse hexadecimal text with supported separators and prefixes."""
        cleaned = HexUtils.clean_hex_string(text)
        if not cleaned:
            raise ValueError("Hexadecimal content cannot be empty")
        return bytes.fromhex(cleaned)

    @classmethod
    def text_to_hex(cls, text, encoding="utf-8", line_ending="CRLF"):
        """Convert text to hexadecimal using the selected line ending."""
        return cls.apply_line_ending(text, line_ending).encode(encoding).hex(" ").upper()

    @classmethod
    def hex_to_text(cls, text, encoding="utf-8", line_ending="CRLF"):
        """Convert hexadecimal to CRLF text, replacing undecodable bytes."""
        return cls.restore_line_ending(cls.parse_hex(text).decode(encoding, errors="replace"), line_ending)

    @classmethod
    def encode_text(cls, text, encoding, line_ending="CRLF"):
        """Return the converted text, selected encoding and encoded bytes."""
        normalized = cls.apply_line_ending(text, line_ending)
        for candidate in cls.get_encoding_candidates(encoding):
            try:
                return normalized, candidate, normalized.encode(candidate.replace("-", "").lower())
            except (LookupError, UnicodeEncodeError):
                continue
        raise UnicodeEncodeError(encoding, text, 0, len(text), "Cannot encode send data")
