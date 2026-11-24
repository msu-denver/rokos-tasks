"""
File: test_output_normalizer.py
Description: Tests program output normalization.
Author(s): Steph Rivera
"""

import pytest

from src.business.output_normalizer import OutputNormalizer


@pytest.mark.parametrize(
    "actual, expected",
    [
        ("Hello\r\nWorld", "Hello\nWorld"),
        ("Hello   \nWorld  ", "Hello\nWorld"),
        ("Hello\n\n\n", "Hello"),
        ("Hello\n\nWorld", "Hello\n\nWorld"),
        ("  Hello", "  Hello"),
        ("Hello\t", "Hello"),
        ("", ""),
        ("   \n\n", ""),
        ("Hello", "Hello"),
    ],
)
def test_normalize(actual: str, expected: str) -> None:
    """Verify that output follows the normalization rules."""
    assert OutputNormalizer.normalize(actual) == expected
