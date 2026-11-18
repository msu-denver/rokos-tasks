"""
File: database.py
Description: Database engine and session management for the data layer.
Author(s): Tyler Black
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    scoped_session,
    sessionmaker,
)


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy data models."""

    pass


class Database:
    """Manages the SQLAlchemy engine and scoped session lifecycle."""

    def __init__(self) -> None:
        """Initialize an unconfigured Database instance."""
        self._engine: Engine | None = None
        self._session_factory: scoped_session[Session] | None = None
        self._url: str | None = None

    def init(self, url: str) -> None:
        """Configure the engine and scoped session factory.

        Args:
            url: Database connection URL.
        """
        if self._engine is not None and self._url == url:
            return

        if self._engine is not None:
            if self._session_factory is not None:
                self._session_factory.remove()
            self._engine.dispose()

        self._url = url
        self._engine = create_engine(url)
        self._session_factory = scoped_session(sessionmaker(bind=self._engine))

    @property
    def engine(self) -> Engine:
        """Return the configured SQLAlchemy engine.

        Raises:
            RuntimeError: If init() has not been called.
        """
        if self._engine is None:
            raise RuntimeError("Database has not been initialized.")
        return self._engine

    @property
    def session_factory(self) -> scoped_session[Session]:
        """Return the scoped session factory.

        Raises:
            RuntimeError: If init() has not been called.
        """
        if self._session_factory is None:
            raise RuntimeError("Database has not been initialized.")
        return self._session_factory

    @property
    def session(self) -> Session:
        """Return the current thread-local scoped session.

        Raises:
            RuntimeError: If init() has not been called.
        """
        if self._session_factory is None:
            raise RuntimeError("Database has not been initialized.")
        return self._session_factory()

    def remove(self) -> None:
        """Remove the current scoped session."""
        if self._session_factory is not None:
            self._session_factory.remove()


db = Database()
