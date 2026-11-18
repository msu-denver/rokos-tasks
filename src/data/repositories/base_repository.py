"""
File: base_repository.py
Description: Base repository providing generic CRUD operations with
    session dependency injection.
Author(s): Tyler Black
"""

from typing import Any

from sqlalchemy.orm import Session


class BaseRepository[T]:
    """Generic repository providing basic persistence operations."""

    model_cls: type[T] | None = None

    def __init__(
        self, session: Session, model_cls: type[T] | None = None
    ) -> None:
        """Initialize the repository with a database session.

        Args:
            session: SQLAlchemy session to use for operations.
            model_cls: Optional model class to override or set on instances.
        """
        self._session = session
        if model_cls is not None:
            self.model_cls = model_cls

    def add(self, obj: T) -> T:
        """Add an entity to the session and flush changes.

        Args:
            obj: The entity instance to persist.

        Returns:
            The persisted entity after flush.
        """
        self._session.add(obj)
        self._session.flush()
        return obj

    def get(self, ident: Any) -> T | None:
        """Retrieve an entity by its primary key identifier.

        Args:
            ident: Primary key value.

        Returns:
            The entity if found, None otherwise.

        Raises:
            NotImplementedError: If model_cls is not defined.
        """
        if self.model_cls is None:
            raise NotImplementedError("model_cls must be defined.")
        return self._session.get(self.model_cls, ident)

    def commit(self) -> None:
        """Commit the active database transaction.

        Delegates the commit operation to the underlying database session.
        """
        self._session.commit()

    def rollback(self) -> None:
        """Roll back the active database transaction.

        Delegates the rollback operation to the underlying database session.
        """
        self._session.rollback()
