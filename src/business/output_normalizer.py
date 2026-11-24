"""
File: output_normalizer.py
Description: Normalizes program output for consistent comparison.
Author(s): Steph Rivera
"""


class OutputNormalizer:
    """Normalizes program output before comparison."""


    @staticmethod
    def normalize(output: str) -> str:
        """Normalize line endings and remove trailing whitespace."""
        lines = [line.rstrip() for line in output.splitlines()]

        while lines and not lines[-1]:
            lines.pop()

        return "\n".join(lines)
