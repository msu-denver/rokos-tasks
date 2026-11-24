"""
File: output_normalizer.py
Description: Normalizes program output for consistent comparison.
Author(s): Steph Rivera
"""


class OutputNormalizer:
    """Normalizes program output before comparison."""

    @staticmethod
    def normalize(output: str) -> str:
        """Nomalize line endings and remove trailing whitespace."""
        output = output.replace("\r\n", "\n")
        lines = output.split("\n")
        lines = [line.rstrip() for line in lines]

        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)