"""
File: auth_service.py
Description: Authentication service enforcing user registration rules,
    password hashing, account creation, and login.
Author(s): Tyler Black
"""

import re
from typing import Protocol
from urllib.parse import urlsplit

from werkzeug.security import check_password_hash, generate_password_hash

from src.data.models.user import User
from src.data.repositories.user_repository import DuplicateUsernameError

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")
USERNAME_FORMAT_ERROR = (
    "Username must be 3\u201320 characters: letters, numbers, or underscores."
)
USERNAME_TAKEN_ERROR = "That username is taken."
PASSWORD_SHORT_ERROR = "Password must be at least 8 characters."
PASSWORD_LONG_ERROR = "Password must be 128 characters or fewer."
PASSWORD_MISMATCH_ERROR = "Passwords don't match."


class UserRepositoryProtocol(Protocol):
    """Protocol defining user persistence operations needed for auth."""

    def get_by_username(self, name: str) -> User | None:
        """Retrieve user by username."""
        ...

    def get_by_id(self, user_id: int) -> User | None:
        """Retrieve user by primary key identifier."""
        ...

    def add(self, user: User) -> User:
        """Add user to persistence layer."""
        ...

    def commit(self) -> None:
        """Commit persistence transaction."""
        ...


class RegistrationError(Exception):
    """Raised when user registration fails validation rules."""

    def __init__(self, errors: dict[str, str]) -> None:
        """Initialize RegistrationError with field error mapping.

        Args:
            errors: Mapping of field names to error messages.
        """
        super().__init__(str(errors))
        self.errors = errors


class AuthService:
    """Authentication service providing registration and validation logic."""

    def __init__(self, user_repository: UserRepositoryProtocol) -> None:
        """Initialize AuthService with a user repository.

        Args:
            user_repository: Repository for User data operations.
        """
        self._user_repository = user_repository

    def get_user(self, user_id: int) -> User | None:
        """Retrieve user by identifier.

        Args:
            user_id: Primary key user identifier.

        Returns:
            The User instance if found, None otherwise.
        """
        return self._user_repository.get_by_id(user_id)

    def register(self, username: str, password: str, confirm: str) -> User:
        """Register a new user account after validating all constraints.

        Args:
            username: Desired player username.
            password: User password.
            confirm: Password confirmation matching password.

        Returns:
            The newly created and persisted User instance.

        Raises:
            RegistrationError: If any validation rule fails.
        """
        errors: dict[str, str] = {}
        trimmed_username = username.strip() if username else ""

        if not USERNAME_PATTERN.match(trimmed_username):
            errors["username"] = USERNAME_FORMAT_ERROR
        elif (
            self._user_repository.get_by_username(trimmed_username) is not None
        ):
            errors["username"] = USERNAME_TAKEN_ERROR

        pwd = password if password is not None else ""
        if len(pwd) < 8:
            errors["password"] = PASSWORD_SHORT_ERROR
        elif len(pwd) > 128:
            errors["password"] = PASSWORD_LONG_ERROR

        if confirm != password:
            errors["confirm"] = PASSWORD_MISMATCH_ERROR

        if errors:
            raise RegistrationError(errors)

        password_hash = generate_password_hash(password)
        user = User(username=trimmed_username, password_hash=password_hash)

        try:
            persisted_user = self._user_repository.add(user)
            self._user_repository.commit()
            return persisted_user
        except DuplicateUsernameError as err:
            raise RegistrationError(
                {"username": USERNAME_TAKEN_ERROR}
            ) from err

    def authenticate(self, username: str, password: str) -> User | None:
        """Authenticate user credentials case-insensitively.

        Args:
            username: Player username (case-insensitive lookup).
            password: Plaintext password to verify against stored hash.

        Returns:
            The User instance if credentials match, None otherwise.
        """
        trimmed_username = username.strip()
        if not USERNAME_PATTERN.fullmatch(trimmed_username) or not password:
            return None
        user = self._user_repository.get_by_username(trimmed_username)
        if user is None:
            return None
        if not check_password_hash(user.password_hash, password):
            return None
        return user


def is_safe_redirect(target: str | None) -> bool:
    r"""Validate whether a redirect target URL is safe and relative to site.

    Accepts only relative paths starting with a single forward slash.
    Rejects protocol-relative URLs starting with '//' or '/\\', explicit
    URL schemes such as 'javascript:' or 'https:', and targets with a netloc.

    Args:
        target: Candidate redirect target URL string or None.

    Returns:
        True if target is safe to redirect to, False otherwise.
    """
    if not target:
        return False
    if (
        not target.startswith("/")
        or target.startswith("//")
        or target.startswith("/\\")
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in target
        )
    ):
        return False
    try:
        parsed = urlsplit(target)
    except ValueError:
        return False
    if parsed.scheme or parsed.netloc:
        return False
    return True
