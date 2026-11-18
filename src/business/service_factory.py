"""
File: service_factory.py
Description: Factory functions for constructing business-layer services
    wired with database repositories.
Author(s): Tyler Black
"""

from src.business.auth_service import AuthService
from src.data.database import db
from src.data.repositories.user_repository import UserRepository


def build_auth_service() -> AuthService:
    """Construct an AuthService instance wired to the database session.

    Returns:
        AuthService configured with UserRepository.
    """
    return AuthService(UserRepository(db.session))
