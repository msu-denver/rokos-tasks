"""
File: test_base_repository.py
Description: Unit and integration tests for BaseRepository operations
    (add, flush id assignment, get, commit, rollback, and error handling).
Author(s): Tyler Black
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.data.repositories.base_repository import BaseRepository


class RepoTestBase(DeclarativeBase):
    """Declarative base scoped strictly for test models."""

    pass


class DummyEntity(RepoTestBase):
    """Test entity for repository verification."""

    __tablename__ = "dummy_entity"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(50))


@pytest.fixture(autouse=True, scope="module")
def setup_dummy_table(engine: Engine) -> Iterator[None]:
    """Create test table on engine and drop it after the module."""
    RepoTestBase.metadata.create_all(engine)
    yield
    RepoTestBase.metadata.drop_all(engine)


def test_base_repository_add_and_get(db_session: Session) -> None:
    repo = BaseRepository(db_session, DummyEntity)
    entity = DummyEntity(name="alpha")
    assert entity.id is None

    persisted = repo.add(entity)
    assert persisted.id is not None

    fetched = repo.get(persisted.id)
    assert fetched is not None
    assert fetched.name == "alpha"


def test_base_repository_get_returns_none_for_missing(
    db_session: Session,
) -> None:
    repo = BaseRepository(db_session, DummyEntity)
    result = repo.get(999999)
    assert result is None


def test_base_repository_subclass(db_session: Session) -> None:
    class DummyRepository(BaseRepository[DummyEntity]):
        model_cls = DummyEntity

    repo = DummyRepository(db_session)
    entity = DummyEntity(name="beta")
    repo.add(entity)

    assert entity.id is not None
    fetched = repo.get(entity.id)
    assert fetched is not None
    assert fetched.name == "beta"


def test_base_repository_requires_model_cls(db_session: Session) -> None:
    repo = BaseRepository(db_session)
    with pytest.raises(NotImplementedError):
        repo.get(1)


def test_base_repository_commit_and_rollback(db_session: Session) -> None:
    repo = BaseRepository(db_session, DummyEntity)
    entity = DummyEntity(name="gamma")
    repo.add(entity)
    repo.commit()
    assert repo.get(entity.id) is not None

    entity2 = DummyEntity(name="delta")
    repo.add(entity2)
    repo.rollback()
    assert repo.get(entity2.id) is None
