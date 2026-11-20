"""
File: test_check_headers.py
Description: Unit tests for scripts/check_headers.py, the course header
    comment checker that runs in `make lint`.
Author(s): Tyler Black
"""

from pathlib import Path

import pytest
from check_headers import find_source_files, header_problems, main

GOOD_PYTHON_HEADER = (
    '"""\nFile: {name}\nDescription: Does a thing.\nAuthor(s): Jane Doe\n"""\n'
)


def write(path: Path, text: str) -> Path:
    """Write text to path, creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_good_python_header_has_no_problems(tmp_path: Path):
    path = write(
        tmp_path / "good.py", GOOD_PYTHON_HEADER.format(name="good.py")
    )

    assert header_problems(path) == []


def test_empty_file_is_skipped(tmp_path: Path):
    path = write(tmp_path / "__init__.py", "")

    assert header_problems(path) == []


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("script.js", "/*\nFile: script.js\nDescription: x\nAuthor(s): y\n*/"),
        ("style.css", "/*\nFile: style.css\nDescription: x\nAuthor(s): y\n*/"),
        ("page.html", "{#\nFile: page.html\nDescription: x\nAuthor(s): y\n#}"),
    ],
)
def test_non_python_headers_are_accepted(tmp_path: Path, name, text):
    assert header_problems(write(tmp_path / name, text)) == []


def test_missing_opener_is_reported(tmp_path: Path):
    path = write(tmp_path / "bad.py", "import os\n")

    assert header_problems(path) == [
        f'{path}: header must open the file with """'
    ]


def test_missing_author_is_reported(tmp_path: Path):
    path = write(
        tmp_path / "bad.py",
        '"""\nFile: bad.py\nDescription: Does a thing.\n"""\n',
    )

    assert header_problems(path) == [f"{path}: header is missing 'Author(s):'"]


def test_wrong_file_name_is_reported(tmp_path: Path):
    path = write(
        tmp_path / "real.py", GOOD_PYTHON_HEADER.format(name="other.py")
    )

    assert header_problems(path) == [f"{path}: 'File:' should be 'real.py'"]


def test_find_source_files_only_checks_known_folders(tmp_path: Path):
    inside = write(tmp_path / "src" / "a.py", "")
    write(tmp_path / "docs" / "b.py", "")
    write(tmp_path / "src" / "notes.md", "")

    assert find_source_files(tmp_path) == [inside]


def test_main_returns_zero_when_all_headers_are_fine(tmp_path, capsys):
    write(tmp_path / "src" / "ok.py", GOOD_PYTHON_HEADER.format(name="ok.py"))

    assert main(tmp_path) == 0
    assert "All source file headers OK." in capsys.readouterr().out


def test_main_returns_one_and_lists_problems(tmp_path, capsys):
    write(tmp_path / "tests" / "bad.py", "x = 1\n")

    assert main(tmp_path) == 1
    assert "1 header problem(s)" in capsys.readouterr().out
