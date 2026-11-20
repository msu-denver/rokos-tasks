"""
File: test_service_factory.py
Description: Unit tests for business-layer service factory functions.
Author(s): Tyler Black
"""

from unittest.mock import MagicMock

import pytest

from src.business.auth_service import AuthService
from src.business.service_factory import build_auth_service
from src.data.database import Database
from src.data.repositories.user_repository import UserRepository


def test_build_auth_service_wires_user_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify build_auth_service constructs AuthService with UserRepository."""
    fake_session = MagicMock()
    monkeypatch.setattr(
        Database, "session", property(lambda _self: fake_session)
    )

    service = build_auth_service()

    assert isinstance(service, AuthService)
    assert isinstance(service._user_repository, UserRepository)
    assert service._user_repository._session is fake_session
