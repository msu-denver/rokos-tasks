"""
File: forms.py
Description: Web form classes for player authentication and input collection.
Author(s): Tyler Black
"""

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField


class RegistrationForm(FlaskForm):
    """Registration form fields for account creation."""

    username = StringField("Username")
    password = PasswordField("Password")
    confirm = PasswordField("Confirm Password")
    submit = SubmitField("Register")
