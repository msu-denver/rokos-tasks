"""
File: test_database.py
Description: Integration tests for database session lifecycle, transaction
    rollback isolation, and Alembic migration reversibility.
Author(s): Tyler Black
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
