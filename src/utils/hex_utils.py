"""
HEX formatting helpers.

Author: aCHAOS
Email: achaosxyz@gmail.com
"""


class HexUtils:
    """HEX formatting helpers."""

    @staticmethod
    def validate_hex_format(hex_string):
        """
        Validate a HEX string.

        Args:
            hex_string: HEX string to validate.

        Returns:
            bool: Whether the format is valid.
        """
        if not hex_string:
            return False

        try:
            # Remove supported separators and prefixes.
            cleaned = hex_string.upper()
            cleaned = cleaned.replace('0X', '')  # Remove 0x prefixes.
            cleaned = cleaned.replace(' ', '')   # Remove spaces.
            cleaned = cleaned.replace(',', '')   # Remove commas.
            cleaned = cleaned.replace('-', '')   # Remove hyphens.
            cleaned = cleaned.replace(':', '')   # Remove colons.
            cleaned = cleaned.replace('\n', '')  # Remove line feeds.
            cleaned = cleaned.replace('\r', '')  # Remove carriage returns.

            # Reject empty input after cleaning.
            if not cleaned:
                return False

            # Every byte requires exactly two hexadecimal characters.
            if len(cleaned) % 2 != 0:
                return False

            # Reject non-hexadecimal characters.
            valid_chars = set('0123456789ABCDEF')
            if not all(c in valid_chars for c in cleaned):
                return False

            # Verify that Python accepts the cleaned byte representation.
            bytes.fromhex(cleaned)
            return True

        except (ValueError, TypeError):
            return False

    @staticmethod
    def get_format_error_message():
        """
        Return the HEX format error message.

        Returns:
            str: Error message.
        """
        return 'HEX格式错误'

    @staticmethod
    def get_format_examples():
        """
        Return valid HEX format examples.

        Returns:
            str: Format examples.
        """
        return """HEX格式错误！

正确格式示例：
• 01 02 03 FF
• 01,02,03,FF
• 010203FF
• 0x01 0x02 0x03 0xFF"""

    @staticmethod
    def clean_hex_string(hex_string):
        """
        Remove supported separators and prefixes from a HEX string.

        Args:
            hex_string: Original HEX string.

        Returns:
            str: Cleaned HEX string.
        """
        if not hex_string:
            return ''

        cleaned = hex_string.upper()
        cleaned = cleaned.replace('0X', '')
        cleaned = cleaned.replace(' ', '')
        cleaned = cleaned.replace(',', '')
        cleaned = cleaned.replace('-', '')
        cleaned = cleaned.replace(':', '')
        cleaned = cleaned.replace('\n', '')
        cleaned = cleaned.replace('\r', '')

        return cleaned
