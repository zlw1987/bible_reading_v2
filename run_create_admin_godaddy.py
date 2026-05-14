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

user, created = User.objects.get_or_create(
    username=username,
    defaults={
        "email": email,
        "is_staff": True,
        "is_superuser": True,
        "is_active": True,
    },
)

user.email = email
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.set_password(password)
user.save()

if created:
    print("Admin user created.")
else:
    print("Admin user already existed and has been reset.")

print(f"Username: {username}")
print(f"Password: {password}")
print(f"is_staff: {user.is_staff}")
print(f"is_superuser: {user.is_superuser}")
print(f"is_active: {user.is_active}")