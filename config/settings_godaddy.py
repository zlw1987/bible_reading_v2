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

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = False