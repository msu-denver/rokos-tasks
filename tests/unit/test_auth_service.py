"""
File: test_auth_service.py
Description: Unit tests for AuthService validation rules, password hashing,
    and error reporting using an in-memory repository fake.
Author(s): Tyler Black
"""

import pytest
from werkzeug.security import check_password_hash

from src.business.auth_service import AuthService, RegistrationError
from src.data.models.user import User
from src.data.repositories.user_repository import DuplicateUsernameError

USERNAME_FORMAT_ERROR = (
    "Username must be 3\u201320 characters: letters, numbers, or underscores."
)


class FakeUserRepository:
    """In-memory repository fake for isolated AuthService testing."""

    def __init__(self, users: list[User] | None = None) -> None:
        """Initialize fake repository with optional initial users."""
        self._users: list[User] = users or []
        self.commit_count = 0

    def get_by_username(self, name: str) -> User | None:
        """Retrieve user case-insensitively from memory."""
        for user in self._users:
            if user.username.lower() == name.lower():
                return user
        return None

    def get_by_id(self, user_id: int) -> User | None:
        """Retrieve user by primary key identifier."""
        for user in self._users:
            if user.id == user_id:
                return user
        return None

    def add(self, user: User) -> User:
        """Add user or raise DuplicateUsernameError if duplicate."""
        if self.get_by_username(user.username) is not None:
            raise DuplicateUsernameError("duplicate")
        self._users.append(user)
        return user

    def commit(self) -> None:
        """Record commit operation."""
        self.commit_count += 1


def test_register_creates_user_with_hashed_password() -> None:
    """Verify successful registration hashes password and verifies."""
    repo = FakeUserRepository()
    service = AuthService(repo)

    user = service.register("valid_user", "password123", "password123")

    assert user.username == "valid_user"
    assert user.password_hash != "password123"
    assert check_password_hash(user.password_hash, "password123") is True


def test_register_trims_username() -> None:
    """Verify whitespace is trimmed from registered username."""
    repo = FakeUserRepository()
    service = AuthService(repo)

    user = service.register("   spaced_user   ", "password123", "password123")

    assert user.username == "spaced_user"


def test_register_rejects_short_username() -> None:
    """Verify username under 3 characters is rejected."""
    service = AuthService(FakeUserRepository())

    with pytest.raises(RegistrationError) as exc_info:
        service.register("ab", "password123", "password123")

    assert "username" in exc_info.value.errors
    assert exc_info.value.errors["username"] == USERNAME_FORMAT_ERROR


def test_register_rejects_long_username() -> None:
    """Verify username over 20 characters is rejected."""
    service = AuthService(FakeUserRepository())

    with pytest.raises(RegistrationError) as exc_info:
        service.register("a" * 21, "password123", "password123")

    assert exc_info.value.errors["username"] == USERNAME_FORMAT_ERROR


@pytest.mark.parametrize(
    "bad_name",
    [
        "user-name",
        "user.name",
        "user@name",
        "user name",
        "user#1",
    ],
)
def test_register_rejects_disallowed_characters(bad_name: str) -> None:
    """Verify username containing invalid symbols is rejected."""
    service = AuthService(FakeUserRepository())

    with pytest.raises(RegistrationError) as exc_info:
        service.register(bad_name, "password123", "password123")

    assert exc_info.value.errors["username"] == USERNAME_FORMAT_ERROR


def test_register_rejects_taken_username() -> None:
    """Verify exact existing username is rejected as taken."""
    existing = User(username="taken_user", password_hash="dummy_hash")
    service = AuthService(FakeUserRepository([existing]))

    with pytest.raises(RegistrationError) as exc_info:
        service.register("taken_user", "password123", "password123")

    assert exc_info.value.errors["username"] == "That username is taken."


def test_register_rejects_case_variant_of_existing_username() -> None:
    """Verify registering Tyler after tyler is rejected as taken."""
    existing = User(username="tyler", password_hash="dummy_hash")
    service = AuthService(FakeUserRepository([existing]))

    with pytest.raises(RegistrationError) as exc_info:
        service.register("Tyler", "password123", "password123")

    assert exc_info.value.errors["username"] == "That username is taken."


def test_register_rejects_short_password() -> None:
    """Verify password shorter than 8 characters is rejected."""
    service = AuthService(FakeUserRepository())

    with pytest.raises(RegistrationError) as exc_info:
        service.register("valid_user", "short", "short")

    assert (
        exc_info.value.errors["password"]
        == "Password must be at least 8 characters."
    )


def test_register_rejects_long_password() -> None:
    """Verify password longer than 128 characters is rejected."""
    service = AuthService(FakeUserRepository())
    long_password = "p" * 129

    with pytest.raises(RegistrationError) as exc_info:
        service.register("valid_user", long_password, long_password)

    assert (
        exc_info.value.errors["password"]
        == "Password must be 128 characters or fewer."
    )


def test_register_rejects_mismatched_confirmation() -> None:
    """Verify password mismatch raises confirm field error."""
    service = AuthService(FakeUserRepository())

    with pytest.raises(RegistrationError) as exc_info:
        service.register("valid_user", "password123", "different_pass")

    assert exc_info.value.errors["confirm"] == "Passwords don't match."


def test_register_reports_all_failing_fields() -> None:
    """Verify multiple failing fields return one message per field."""
    service = AuthService(FakeUserRepository())

    with pytest.raises(RegistrationError) as exc_info:
        service.register("ab", "short", "mismatch")

    errors = exc_info.value.errors
    assert "username" in errors
    assert "password" in errors
    assert "confirm" in errors
    assert errors["username"] == USERNAME_FORMAT_ERROR


def test_register_commits_via_repository_on_success() -> None:
    """Verify successful registration commits through the repository."""
    repo = FakeUserRepository()
    service = AuthService(repo)

    service.register("valid_user", "password123", "password123")

    assert repo.commit_count == 1


def test_get_user_returns_user_or_none() -> None:
    """Verify get_user retrieves user by id or returns None if missing."""
    existing = User(id=42, username="existing_user", password_hash="hash")
    repo = FakeUserRepository([existing])
    service = AuthService(repo)

    assert service.get_user(42) == existing
    assert service.get_user(999) is None


def test_register_handles_race_condition_duplicate_from_repository() -> None:
    """Verify repository DuplicateUsernameError translates to taken error."""

    class DuplicateRaisingRepo:
        def __init__(self) -> None:
            self.commit_count = 0

        def get_by_username(self, name: str) -> User | None:
            return None

        def get_by_id(self, user_id: int) -> User | None:
            return None

        def add(self, user: User) -> User:
            raise DuplicateUsernameError("race collision")

        def commit(self) -> None:
            self.commit_count += 1

    repo = DuplicateRaisingRepo()
    service = AuthService(repo)

    with pytest.raises(RegistrationError) as exc_info:
        service.register("race_user", "password123", "password123")

    assert exc_info.value.errors["username"] == "That username is taken."
    assert repo.commit_count == 0
