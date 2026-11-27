"""
File: test_database.py
Description: Integration tests for database session lifecycle, transaction
    rollback isolation, and Alembic migration reversibility.
Author(s): Tyler Black, Steph Rivera
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from flask import Flask
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from src.data.database import Database, db
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture(autouse=True, scope="module")
def setup_probe_table(engine: Engine) -> Iterator[None]:
    """Create a persistent probe table and tear it down after module runs."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS rollback_probe "
                "(id serial primary key, val text)"
            )
        )
    yield
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS rollback_probe"))


def test_session_can_select_one(db_session: Session) -> None:
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_migrations_are_reversible(engine: Engine) -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")


def test_check_scripts_only_migration_keeps_gradable_data(
    engine: Engine,
) -> None:
    """0006 deletes ungradable campaigns and their runs, keeps the rest.

    Runs inside one rolled-back transaction, so the shared test schema
    is left at head with no rows added. Test 0006 in isolation.
    """
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        alembic_cfg.attributes["connection"] = connection
        command.downgrade(alembic_cfg, "0005_stage_check_script")
        user = connection.execute(
            text(
                "INSERT INTO users (username, password_hash) "
                "VALUES ('migrator', 'x') RETURNING id"
            )
        ).scalar_one()
        ids = {}
        for slug, script in (("old", None), ("new", "def check(game): ...")):
            ids[slug] = connection.execute(
                text(
                    "INSERT INTO campaigns (title, difficulty, slug, "
                    "content_hash) VALUES (:slug, 'beginner', :slug, 'h') "
                    "RETURNING id"
                ),
                {"slug": f"migration/{slug}"},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO stages (campaign_id, number, prompt, "
                    "starter_code, reference_solution, check_script) "
                    "VALUES (:id, 1, 'p', NULL, 'ref', :script)"
                ),
                {"id": ids[slug], "script": script},
            )
        connection.execute(
            text(
                "INSERT INTO game_runs (user_id, campaign_id, difficulty, "
                "status, lives, current_stage, score, started_at, "
                "stage_started_at) VALUES (:user, :campaign, 'beginner', "
                "'in_progress', 4, 1, 0, now(), now())"
            ),
            {"user": user, "campaign": ids["old"]},
        )

        command.upgrade(alembic_cfg, "0006_check_scripts_only")

        slugs = connection.execute(
            text("SELECT slug FROM campaigns WHERE slug LIKE 'migration/%'")
        ).scalars()
        assert list(slugs) == ["migration/new"]
        runs = connection.execute(
            text("SELECT count(*) FROM game_runs WHERE user_id = :user"),
            {"user": user},
        ).scalar_one()
        assert runs == 0
        reference = connection.execute(
            text(
                "SELECT reference_program FROM stages WHERE campaign_id = :id"
            ),
            {"id": ids["new"]},
        ).scalar_one()
        assert reference == "ref"
    finally:
        transaction.rollback()
        connection.close()


def test_stage_input_style_migration_preserves_seed_stages(
    engine: Engine,
) -> None:
    """0007 backfills the shipped stages without replacing their rows."""
    expected = {
        "beginner/traffic_light": ("beginner", ["none", "lines"]),
        "easy/vending_machine": ("easy", ["lines", "lines", "lines"]),
        "medium/pong": ("medium", ["none", "keys", "keys"]),
    }
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        alembic_cfg.attributes["connection"] = connection
        command.downgrade(alembic_cfg, "0006_check_scripts_only")
        rows = {}
        for slug, (difficulty, styles) in expected.items():
            campaign_id = connection.execute(
                text(
                    "INSERT INTO campaigns (title, difficulty, slug, "
                    "content_hash, source) VALUES "
                    "(:slug, :difficulty, :slug, 'h', 'seed') RETURNING id"
                ),
                {"slug": slug, "difficulty": difficulty},
            ).scalar_one()
            for number, style in enumerate(styles, 1):
                stage_id = connection.execute(
                    text(
                        "INSERT INTO stages (campaign_id, number, prompt, "
                        "reference_program, check_script) VALUES "
                        "(:id, :number, 'p', 'ref', 'check') RETURNING id"
                    ),
                    {"id": campaign_id, "number": number},
                ).scalar_one()
                rows[stage_id] = (campaign_id, number, style, "ref", "check")

        command.upgrade(alembic_cfg, "0007_stage_input_style")
        actual = connection.execute(
            text(
                "SELECT id, campaign_id, number, input_style, "
                "reference_program, check_script FROM stages"
            )
        )
        assert {row[0]: tuple(row[1:]) for row in actual} == rows
    finally:
        transaction.rollback()
        connection.close()


def test_alembic_online_without_connection() -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")


def test_alembic_offline_mode() -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head", sql=True)


def test_rollback_first_part_inserts_row(db_session: Session) -> None:
    db_session.execute(
        text("INSERT INTO rollback_probe (val) VALUES ('rollback_marker')")
    )
    db_session.commit()
    count = db_session.execute(
        text(
            "SELECT count(*) FROM rollback_probe WHERE val = 'rollback_marker'"
        )
    ).scalar()
    assert count == 1


def test_rollback_second_part_proves_row_is_absent(
    db_session: Session,
) -> None:
    count = db_session.execute(
        text(
            "SELECT count(*) FROM rollback_probe WHERE val = 'rollback_marker'"
        )
    ).scalar()
    assert count == 0


def test_app_client_session_does_not_leak_rows(
    app: Flask, db_session: Session
) -> None:
    with app.app_context():
        db.session.execute(
            text("INSERT INTO rollback_probe (val) VALUES ('from_client')")
        )
        db.session.commit()
    count = db_session.execute(
        text("SELECT count(*) FROM rollback_probe WHERE val = 'from_client'")
    ).scalar()
    assert count == 1


def test_app_client_session_rows_were_rolled_back(
    db_session: Session,
) -> None:
    count = db_session.execute(
        text("SELECT count(*) FROM rollback_probe WHERE val = 'from_client'")
    ).scalar()
    assert count == 0


def test_database_engine_property(db_session: Session) -> None:
    assert db.engine is not None


def test_database_reinit_disposes_old_engine() -> None:
    custom_db = Database()
    custom_db.init(TEST_DATABASE_URL)
    _ = custom_db.session
    first_engine = custom_db.engine
    assert first_engine is not None

    custom_db.init(TEST_DATABASE_URL)
    assert custom_db.engine is first_engine

    custom_db.init("sqlite:///:memory:")
    assert custom_db.engine is not first_engine
    custom_db.remove()


def test_uninitialized_database_raises_runtime_error() -> None:
    uninit_db = Database()
    with pytest.raises(
        RuntimeError, match="Database has not been initialized."
    ):
        _ = uninit_db.engine
    with pytest.raises(
        RuntimeError, match="Database has not been initialized."
    ):
        _ = uninit_db.session_factory
    with pytest.raises(
        RuntimeError, match="Database has not been initialized."
    ):
        _ = uninit_db.session
    uninit_db.remove()
