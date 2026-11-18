"""
File: auth_routes.py
Description: Authentication blueprint handling user registration and session
    state.
Author(s): Tyler Black
"""

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_user
from werkzeug.wrappers import Response

from src.business.auth_service import RegistrationError
from src.business.service_factory import build_auth_service
from src.presentation.forms import RegistrationForm

auth_blueprint = Blueprint("auth", __name__)


@auth_blueprint.route("/register", methods=["GET", "POST"])
def register() -> Response | str:
    """Handle player registration and automatic login.

    Returns:
        Rendered registration form template or redirect response.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = RegistrationForm()
    errors: dict[str, str] = {}

    if form.validate_on_submit():
        username = form.username.data or ""
        password = form.password.data or ""
        confirm = form.confirm.data or ""

        auth_service = build_auth_service()
        try:
            user = auth_service.register(username, password, confirm)
            login_user(user)
            return redirect(url_for("main.home"))
        except RegistrationError as err:
            errors = err.errors

    form.password.data = ""
    form.confirm.data = ""

    return render_template("auth/register.html", form=form, errors=errors)
