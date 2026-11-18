"""
File: check_headers.py
Description: Fails when a source file under src/, tests/, or scripts/ is
    missing the course header comment (File, Description, Author(s)).
    Run by `make lint`, so CI enforces it on every pull request.
Author(s): Tyler Black
"""

import sys
from pathlib import Path

CHECKED_DIRECTORIES = ("src", "tests", "scripts")
REQUIRED_FIELDS = ("File:", "Description:", "Author(s):")
HEADER_OPENERS = {
    ".py": '"""',
    ".js": "/*",
    ".css": "/*",
    ".html": "{#",
}
HEADER_SEARCH_LINES = 15


def header_problems(path: Path) -> list[str]:
    """Return what is wrong with a file's header, or an empty list.

    Args:
        path: The source file to check.

    Returns:
        One message per problem. Empty files (such as a bare
        ``__init__.py``) have no problems.
    """
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []

    opener = HEADER_OPENERS[path.suffix]
    if not text.lstrip().startswith(opener):
        return [f"{path}: header must open the file with {opener}"]

    head = "\n".join(text.splitlines()[:HEADER_SEARCH_LINES])
    problems = [
        f"{path}: header is missing '{field}'"
        for field in REQUIRED_FIELDS
        if field not in head
    ]
    if f"File: {path.name}" not in head:
        problems.append(f"{path}: 'File:' should be '{path.name}'")
    return problems


def find_source_files(root: Path) -> list[Path]:
    """List every checked source file under the checked directories.

    Args:
        root: The repository root.

    Returns:
        Source files, sorted for stable output.
    """
    files = []
    for directory in CHECKED_DIRECTORIES:
        for suffix in HEADER_OPENERS:
            files.extend((root / directory).rglob(f"*{suffix}"))
    return sorted(files)


def main(root: Path) -> int:
    """Check every source file and print any problems.

    Args:
        root: The repository root.

    Returns:
        The process exit code: 0 if every header is fine, 1 otherwise.
    """
    problems = []
    for path in find_source_files(root):
        problems.extend(header_problems(path))
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} header problem(s). See docs/roadmap.md §6.1.")
        return 1
    print("All source file headers OK.")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    sys.exit(main(Path.cwd()))
