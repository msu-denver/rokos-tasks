"""
File: auth_routes.py
Description: Authentication blueprint handling user registration and session
    state.
Author(s): Tyler Black
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.wrappers import Response

from src.business.auth_service import RegistrationError, is_safe_redirect
from src.business.service_factory import build_auth_service
from src.presentation.forms import LoginForm, RegistrationForm

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


@auth_blueprint.route("/login", methods=["GET", "POST"])
def login() -> Response | str:
    """Handle player authentication and session establishment.

    Returns:
        Rendered login form template or redirect response.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = LoginForm()
    error: str | None = None
    next_url = request.args.get("next") or request.form.get("next")

    if form.validate_on_submit():
        username = form.username.data or ""
        password = form.password.data or ""

        auth_service = build_auth_service()
        user = auth_service.authenticate(username, password)
        if user is not None:
            login_user(user)
            if next_url and is_safe_redirect(next_url):
                return redirect(next_url)
            return redirect(url_for("main.home"))
        error = "Invalid username or password."

    form.password.data = ""

    return render_template(
        "auth/login.html", form=form, error=error, next_url=next_url
    )


@auth_blueprint.post("/logout")
def logout() -> Response:
    """Terminate player session and redirect to login page.

    Returns:
        Redirect response to the login route with flash confirmation.
    """
    logout_user()
    flash("You've been logged out.")
    return redirect(url_for("auth.login"))
