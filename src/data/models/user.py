"""
File: user.py
Description: User entity model for authentication and player profiles.
Author(s): Tyler Black
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.data.database import Base


class User(Base):
    """Player account model storing credentials and timestamps."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("uq_users_lower_username", func.lower(username), unique=True),
    )

    @property
    def is_authenticated(self) -> bool:
        """Return True if the user is authenticated."""
        return True

    @property
    def is_active(self) -> bool:
        """Return True if the user account is active."""
        return True

    @property
    def is_anonymous(self) -> bool:
        """Return False for persistent user instances."""
        return False

    def get_id(self) -> str:
        """Return the unique string identifier for Flask-Login.

        Returns:
            String representation of the user primary key.
        """
        return str(self.id)
