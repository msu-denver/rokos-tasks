"""
File: user_repository.py
Description: Repository for user persistence, lookup, and unique constraint
    handling.
Author(s): Tyler Black
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.data.models.user import User
from src.data.repositories.base_repository import BaseRepository


class DuplicateUsernameError(Exception):
    """Raised when an operation violates unique username constraints."""

    pass


class UserRepository(BaseRepository[User]):
    """Repository handling database operations for User records."""

    model_cls = User

    def __init__(self, session: Session) -> None:
        """Initialize UserRepository with a database session.

        Args:
            session: SQLAlchemy session to use for operations.
        """
        super().__init__(session, User)

    def get_by_username(self, name: str) -> User | None:
        """Retrieve a user by username, case-insensitively.

        Args:
            name: Username to look up.

        Returns:
            The User instance if found, None otherwise.
        """
        stmt = select(User).where(
            func.lower(User.username) == func.lower(name)
        )
        return self._session.scalars(stmt).first()

    def get_by_id(self, user_id: int) -> User | None:
        """Retrieve a user by primary key identifier.

        Args:
            user_id: User identifier.

        Returns:
            The User instance if found, None otherwise.
        """
        return self.get(user_id)

    def add(self, user: User) -> User:
        """Persist a new User entity and flush changes.

        Args:
            user: User entity to persist.

        Returns:
            The persisted User entity.

        Raises:
            DuplicateUsernameError: If a user with the same username
                already exists.
        """
        try:
            with self._session.begin_nested():
                return super().add(user)
        except IntegrityError as err:
            raise DuplicateUsernameError(
                f"Username '{user.username}' is already taken."
            ) from err
