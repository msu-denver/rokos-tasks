"""
File: test_user_repository.py
Description: Integration tests for UserRepository persistence, case-insensitive
    lookup, and database-level unique constraint handling.
Author(s): Tyler Black
"""

import pytest
from sqlalchemy.orm import Session

from src.data.models.user import User
from src.data.repositories.user_repository import (
    DuplicateUsernameError,
    UserRepository,
)


def test_user_model_auth_properties() -> None:
    """Verify User model implements Flask-Login property protocol."""
    user = User(id=42, username="PlayerOne", password_hash="hashed_secret")

    assert user.is_authenticated is True
    assert user.is_active is True
    assert user.is_anonymous is False
    assert user.get_id() == "42"


def test_user_repository_add_and_lookup_by_username(
    db_session: Session,
) -> None:
    """Verify repository persists and retrieves users case-insensitively."""
    repo = UserRepository(db_session)
    user = User(username="Tyler", password_hash="hash_val")
    persisted = repo.add(user)

    assert persisted.id is not None
    assert repo.get_by_username("Tyler") == persisted
    assert repo.get_by_username("tyler") == persisted
    assert repo.get_by_username("TYLER") == persisted
    assert repo.get_by_username("nonexistent") is None
    assert repo.get_by_id(persisted.id) == persisted


def test_user_repository_enforces_case_insensitive_unique_constraint(
    db_session: Session,
) -> None:
    """Verify database unique constraint raises DuplicateUsernameError."""
    repo = UserRepository(db_session)
    repo.add(User(username="Tyler", password_hash="hash_alpha"))

    with pytest.raises(DuplicateUsernameError) as exc_info:
        repo.add(User(username="tyler", password_hash="hash_beta"))

    assert "already taken" in str(exc_info.value)


def test_user_repository_savepoint_rollback_preserves_outer_transaction(
    db_session: Session,
) -> None:
    """Verify savepoint rollback does not discard prior transaction changes."""
    repo = UserRepository(db_session)
    valid_user = repo.add(User(username="Survivor", password_hash="hash_one"))

    with pytest.raises(DuplicateUsernameError):
        repo.add(User(username="survivor", password_hash="hash_two"))

    assert repo.get_by_id(valid_user.id) is not None
    assert valid_user in db_session
