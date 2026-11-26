"""
File: test_dev_setup.py
Description: Unit tests for the `make dev` setup: it runs Flask in the
    Compose web-dev service, which waits for the db and the runner and
    joins the sandbox network, while the runner stays internal-only, and
    `make down` removes web-dev too.
Author(s): Tyler Black, Richard Hall
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def make_recipe(target: str) -> str:
    """Return the recipe lines of a Makefile target as one string."""
    lines = MAKEFILE.read_text().splitlines()
    start = lines.index(f"{target}:") + 1
    recipe = []
    for line in lines[start:]:
        if not line.startswith("\t"):
            break
        recipe.append(line.strip())
    return "\n".join(recipe)


def compose_block(name: str, indent: int = 2) -> str:
    """Return the lines of a top-level Compose entry as one string.

    Args:
        name: The service or network name, for example ``"web-dev"``.
        indent: How far the entry's key is indented.
    """
    lines = COMPOSE_FILE.read_text().splitlines()
    start = lines.index(" " * indent + f"{name}:") + 1
    block = []
    for line in lines[start:]:
        stripped = line.lstrip()
        depth = len(line) - len(stripped)
        if stripped and not stripped.startswith("#") and depth <= indent:
            break
        block.append(line)
    return "\n".join(block)


def test_make_dev_starts_web_dev_service_through_compose() -> None:
    """`make dev` brings up web-dev with the dev profile, rebuilding."""
    recipe = make_recipe("dev")
    assert "docker compose --profile dev up --build web-dev" in recipe


def test_make_dev_skips_docker_in_ci() -> None:
    """With CI=true, `make dev` runs Flask on the host, not Docker."""
    recipe = make_recipe("dev")
    ci_branch, _, other_branch = recipe.partition("else")
    assert '"$$CI" = "true"' in ci_branch
    assert "docker" not in ci_branch
    assert "create_dev_app" in ci_branch
    assert "docker compose" in other_branch


def test_make_down_includes_dev_profile() -> None:
    """`make down` also removes web-dev, which is in the dev profile."""
    recipe = make_recipe("down")
    assert "docker compose --profile dev down" in recipe


def test_web_dev_waits_for_healthy_db_and_runner() -> None:
    """Flask only starts once Postgres and the runner are healthy."""
    block = compose_block("web-dev")
    depends = block.split("depends_on:")[1].split("environment:")[0]
    assert "db:\n        condition: service_healthy" in depends
    assert "runner:\n        condition: service_healthy" in depends


def test_web_dev_joins_sandbox_network_and_points_at_runner() -> None:
    """web-dev can reach the runner the same way `web` does."""
    block = compose_block("web-dev")
    networks = block.split("networks:")[1]
    assert "- sandbox" in networks
    assert "RUNNER_URL: ${RUNNER_URL:-http://runner:9000}" in block


def test_web_dev_reloads_mounted_source_without_debugger() -> None:
    """Source is mounted for reloads; the debugger console is off."""
    block = compose_block("web-dev")
    assert "- ./src:/app/src" in block
    assert '"src.app:create_dev_app"' in block
    assert '"--debug"' in block
    assert '"--no-debugger"' in block


def test_web_dev_is_local_only_and_opt_in() -> None:
    """Port 8001 is bound to localhost and `make up` doesn't start it."""
    block = compose_block("web-dev")
    assert '- "127.0.0.1:8001:8001"' in block
    assert 'profiles: ["dev"]' in block


def test_runner_stays_internal_only() -> None:
    """The runner publishes no port and its network has no internet."""
    assert "ports:" not in compose_block("runner")
    assert "internal: true" in compose_block("sandbox")
