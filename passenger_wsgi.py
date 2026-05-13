import os
import sys


PROJECT_ROOT = os.path.dirname(__file__)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_godaddy")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()