import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_godaddy")

import django
django.setup()

from django.contrib.auth import get_user_model


User = get_user_model()

username = "admin"
email = "admin@example.com"
password = "ChangeThisPasswordImmediately123!"

if User.objects.filter(username=username).exists():
    print("Admin user already exists.")
else:
    User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
    )
    print("Admin user created.")