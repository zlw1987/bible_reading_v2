from .settings import *
import os


DEBUG = False

ALLOWED_HOSTS = [
    "4z8.d4d.mytemp.website",
]

CSRF_TRUSTED_ORIGINS = [
    "https://4z8.d4d.mytemp.website",
]

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", SECRET_KEY)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Django is served under https://4z8.d4d.mytemp.website/app_read/
FORCE_SCRIPT_NAME = "/app_read"
PUBLIC_APP_DIR = BASE_DIR.parent / "public_html" / "app_read"

STATIC_URL = "/app_read/static/"
STATIC_ROOT = PUBLIC_APP_DIR / "static"

MEDIA_URL = "/app_read/media/"
MEDIA_ROOT = BASE_DIR / "media"

SESSION_COOKIE_PATH = "/app_read/"
CSRF_COOKIE_PATH = "/app_read/"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = False