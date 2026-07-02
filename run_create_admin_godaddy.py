"""Safely create or update a GoDaddy deployment superuser.

This script intentionally has no default credentials. It is kept as a small
deployment entry point for environments where invoking Django's interactive
``createsuperuser`` command is inconvenient.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

PASSWORD_ENV = "DJANGO_SUPERUSER_PASSWORD"
USERNAME_ENV = "DJANGO_SUPERUSER_USERNAME"
EMAIL_ENV = "DJANGO_SUPERUSER_EMAIL"


class BootstrapError(RuntimeError):
    """Raised when admin bootstrap cannot proceed safely."""


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Create a superuser, or explicitly update one, without storing or "
            "printing a password."
        )
    )
    parser.add_argument(
        "--username",
        help=f"Superuser username. Falls back to {USERNAME_ENV}.",
    )
    parser.add_argument(
        "--email",
        help=f"Superuser email. Falls back to {EMAIL_ENV}.",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help=(
            "Explicitly allow resetting password and superuser flags when the "
            "username already exists."
        ),
    )
    return parser


def resolve_username(argument_value, environ=None):
    environ = os.environ if environ is None else environ
    username = (argument_value or environ.get(USERNAME_ENV, "")).strip()
    if not username:
        raise BootstrapError(
            f"A username is required via --username or {USERNAME_ENV}."
        )
    return username


def resolve_email(argument_value, environ=None):
    environ = os.environ if environ is None else environ
    return (argument_value or environ.get(EMAIL_ENV, "")).strip()


def resolve_password(
    environ=None,
    *,
    is_interactive=None,
    password_prompt=getpass.getpass,
):
    """Read a password from a protected environment value or secure prompt."""

    environ = os.environ if environ is None else environ
    password = environ.get(PASSWORD_ENV)
    if password:
        return password

    if is_interactive is None:
        is_interactive = sys.stdin.isatty()
    if not is_interactive:
        raise BootstrapError(
            f"No password is available. Set {PASSWORD_ENV} securely or run "
            "this script in an interactive terminal."
        )

    password = password_prompt("New superuser password: ")
    confirmation = password_prompt("Confirm password: ")
    if not password:
        raise BootstrapError("The password cannot be empty.")
    if password != confirmation:
        raise BootstrapError("The password confirmation did not match.")
    return password


def _password_token(value):
    return "".join(character for character in value.casefold() if character.isalnum())


def reject_default_like_password(password, username):
    """Reject obvious bootstrap/default credentials before Django validation."""

    token = _password_token(password)
    username_token = _password_token(username)
    known_defaults = {
        "admin",
        "admin123",
        "changeme",
        "defaultpassword",
        "letmein",
        "password",
        "password123",
        "qwerty",
    }

    if (
        token in known_defaults
        or token.startswith("changethispassword")
        or (username_token and token == username_token)
    ):
        raise BootstrapError(
            "The password looks like a default or matches the username. "
            "Choose a unique passphrase."
        )


def validate_bootstrap_password(password, user):
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    reject_default_like_password(password, user.get_username())
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        raise BootstrapError(
            "Django rejected the password: " + " ".join(exc.messages)
        ) from exc


def bootstrap_superuser(
    User,
    *,
    username,
    email,
    password,
    update_existing=False,
):
    """Create or explicitly update one superuser inside an atomic transaction."""

    from django.db import transaction

    with transaction.atomic():
        user = User.objects.select_for_update().filter(username=username).first()
        created = user is None

        if user is not None and not update_existing:
            raise BootstrapError(
                "That username already exists. Re-run with --update-existing "
                "only if resetting this account is intentional."
            )

        if user is None:
            user = User(username=username)

        if email:
            user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True

        validate_bootstrap_password(password, user)
        user.set_password(password)
        user.save()

    return user, created


def main(argv=None):
    args = build_parser().parse_args(argv)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_godaddy")
    import django

    django.setup()

    from django.contrib.auth import get_user_model

    User = get_user_model()
    username = resolve_username(args.username)
    email = resolve_email(args.email)

    if User.objects.filter(username=username).exists() and not args.update_existing:
        raise BootstrapError(
            "That username already exists. Re-run with --update-existing only "
            "if resetting this account is intentional."
        )

    password = resolve_password()
    user, created = bootstrap_superuser(
        User,
        username=username,
        email=email,
        password=password,
        update_existing=args.update_existing,
    )

    action = "created" if created else "updated"
    print(f"Superuser {action}: {user.get_username()}")
    print("Credential stored securely.")


if __name__ == "__main__":
    try:
        main()
    except BootstrapError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
