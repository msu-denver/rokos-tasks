"""
File: service_factory.py
Description: Factory functions for constructing business-layer services
    wired with database repositories.
Author(s): Tyler Black
"""

from datetime import UTC, datetime
from functools import partial

from src.business.auth_service import AuthService
from src.business.campaign_selector import CampaignSelector
from src.business.game_service import GameService
from src.data.database import db
from src.data.repositories.campaign_repository import CampaignRepository
from src.data.repositories.run_repository import RunRepository
from src.data.repositories.user_repository import UserRepository


def build_auth_service() -> AuthService:
    """Construct an AuthService instance wired to the database session.

    Returns:
        AuthService configured with UserRepository.
    """
    return AuthService(UserRepository(db.session))


def build_game_service() -> GameService:
    """Construct the game service with a shared session and a UTC clock."""
    session = db.session
    runs = RunRepository(session)
    selector = CampaignSelector(CampaignRepository(session), runs)
    return GameService(selector, runs, partial(datetime.now, UTC))
