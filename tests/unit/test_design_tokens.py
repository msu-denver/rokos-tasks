"""
File: test_design_tokens.py
Description: Unit tests verifying design token declarations in tokens.css
    and guarding presentation templates and stylesheets against hard-coded
    colors, font sizes, and font families.
Author(s): Tyler Black
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKENS_FILE = REPO_ROOT / "src/presentation/static/css/tokens.css"
PRESENTATION_DIR = REPO_ROOT / "src/presentation"

EXPECTED_COLOR_TOKENS = (
    "--bg",
    "--grid",
    "--surface",
    "--surface-raised",
    "--line",
    "--ink",
    "--ink-strong",
    "--muted",
    "--cyan",
    "--magenta",
    "--red",
    "--yellow",
    "--green",
)

EXPECTED_FONT_TOKENS = (
    "--font-display",
    "--font-shout",
    "--font-body",
    "--font-mono",
)

EXPECTED_SIZE_TOKENS = (
    "--text-12",
    "--text-14",
    "--text-17",
    "--text-22",
    "--text-34",
    "--text-64",
)

EXPECTED_SPACING_TOKENS = tuple(f"--space-{index}" for index in range(1, 9))

HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB_PATTERN = re.compile(r"rgba?\(")
FONT_FAMILY_PATTERN = re.compile(r"\b(Syne|Michroma|Geist|Space\s+Mono)\b")
JINJA_COMMENT_PATTERN = re.compile(r"\{#.*?#\}", re.DOTALL)
GOOGLE_FONTS_URL_PATTERN = re.compile(
    r"https://fonts\.googleapis\.com[^\s\"'>]+"
)


def extract_css_custom_properties(css_text: str) -> set[str]:
    """Extract custom property names declared in a CSS string.

    Args:
        css_text: Raw CSS text.

    Returns:
        A set of defined custom property variable names.
    """
    matches = re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", css_text)
    return set(matches)


def test_tokens_css_defines_required_design_tokens() -> None:
    """Verify tokens.css declares color, font, size, and spacing tokens."""
    assert TOKENS_FILE.exists(), f"Missing tokens file at {TOKENS_FILE}"
    content = TOKENS_FILE.read_text(encoding="utf-8")
    declared_tokens = extract_css_custom_properties(content)

    missing_colors = [
        token
        for token in EXPECTED_COLOR_TOKENS
        if token not in declared_tokens
    ]
    assert not missing_colors, f"Missing color tokens: {missing_colors}"

    missing_fonts = [
        token for token in EXPECTED_FONT_TOKENS if token not in declared_tokens
    ]
    assert not missing_fonts, f"Missing font tokens: {missing_fonts}"

    missing_sizes = [
        token for token in EXPECTED_SIZE_TOKENS if token not in declared_tokens
    ]
    assert not missing_sizes, f"Missing size tokens: {missing_sizes}"

    missing_spacings = [
        token
        for token in EXPECTED_SPACING_TOKENS
        if token not in declared_tokens
    ]
    assert not missing_spacings, f"Missing spacing tokens: {missing_spacings}"

    assert "--cut-window" in declared_tokens
    assert "--cut-button" in declared_tokens
    assert "--shadow-offset-window" in declared_tokens
    assert "--shadow-offset-button" in declared_tokens
    assert "--grid-size" in declared_tokens
    assert "--focus-outline" in declared_tokens


def test_guard_against_hardcoded_colors_and_fonts() -> None:
    """Guard templates and stylesheets against hard-coded colors/fonts."""
    checked_files: list[Path] = []
    for search_dir in (
        PRESENTATION_DIR / "templates",
        PRESENTATION_DIR / "static",
    ):
        if search_dir.exists():
            for path in search_dir.rglob("*"):
                if path.is_file() and path.resolve() != TOKENS_FILE.resolve():
                    checked_files.append(path)

    assert checked_files, "Expected presentation files to check"

    violations: list[str] = []
    for file_path in checked_files:
        text = file_path.read_text(encoding="utf-8")
        sanitized = JINJA_COMMENT_PATTERN.sub("", text)

        if file_path.name == "base.html":
            sanitized = GOOGLE_FONTS_URL_PATTERN.sub("", sanitized)

        hex_matches = HEX_PATTERN.findall(sanitized)
        if hex_matches:
            violations.append(
                f"{file_path.name}: disallowed hex color(s): {hex_matches}"
            )

        rgb_matches = RGB_PATTERN.findall(sanitized)
        if rgb_matches:
            violations.append(
                f"{file_path.name}: disallowed rgb/rgba call(s): {rgb_matches}"
            )

        font_matches = FONT_FAMILY_PATTERN.findall(sanitized)
        if font_matches:
            violations.append(
                f"{file_path.name}: disallowed font name(s): {font_matches}"
            )

    assert not violations, "\n".join(violations)
