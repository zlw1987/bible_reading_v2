from .settings import *
import os

from django.core.exceptions import ImproperlyConfigured

DEBUG = False

# Comma-separated list of hostnames, sourced from the environment so the real
# production domain can be set at deploy time without a code change. Falls back
# to the temporary domain only when the env var is unset.
# TODO: confirm the real production domain and set DJANGO_ALLOWED_HOSTS before cutover.
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "4z8.d4d.mytemp.website"
    ).split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]

# Require an explicit secret in production; never fall back to the public,
# committed dev key from config/settings.py.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY environment variable is required in production."
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

FORCE_SCRIPT_NAME = "/app_read"

PUBLIC_APP_DIR = BASE_DIR.parent / "public_html" / "app_read"

STATIC_URL = "/app_read/static/"
STATIC_ROOT = PUBLIC_APP_DIR / "static"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/app_read/media/"
MEDIA_ROOT = BASE_DIR / "media"

SESSION_COOKIE_PATH = "/app_read/"
CSRF_COOKIE_PATH = "/app_read/"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = False