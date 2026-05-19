#!/bin/bash
set -e

cd /home/rsnwvvl103hc/app_read

PYTHON="/home/rsnwvvl103hc/virtualenv/app_read/3.11/bin/python"
LOGFILE="/home/rsnwvvl103hc/app_read/deploy.log"

echo "===== DEPLOY START $(date) =====" | tee $LOGFILE

echo "Current directory: $(pwd)" | tee -a $LOGFILE
echo "Python: $PYTHON" | tee -a $LOGFILE

echo "Checking effective Django static settings..." | tee -a $LOGFILE
$PYTHON - <<'PY' 2>&1 | tee -a "$LOGFILE"
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_godaddy")

import django
django.setup()

from django.conf import settings
from django.contrib.staticfiles.finders import find

print("DJANGO_SETTINGS_MODULE =", os.environ.get("DJANGO_SETTINGS_MODULE"))
print("BASE_DIR =", settings.BASE_DIR)
print("STATIC_URL =", settings.STATIC_URL)
print("STATIC_ROOT =", settings.STATIC_ROOT)
print("STATICFILES_DIRS =", settings.STATICFILES_DIRS)
print("FOUND css/app.css =", find("css/app.css"))
PY

echo "Running Django check..." | tee -a $LOGFILE
$PYTHON manage.py check --settings=config.settings_godaddy 2>&1 | tee -a $LOGFILE

echo "Running migrations..." | tee -a $LOGFILE
$PYTHON manage.py migrate --settings=config.settings_godaddy --noinput 2>&1 | tee -a $LOGFILE

echo "Collecting static files..." | tee -a $LOGFILE
$PYTHON manage.py collectstatic --settings=config.settings_godaddy --noinput --clear --verbosity 2 2>&1 | tee -a $LOGFILE

echo "Checking generated public static file..." | tee -a $LOGFILE
ls -l /home/rsnwvvl103hc/public_html/app_read/static/css/app.css 2>&1 | tee -a $LOGFILE
grep -n "reading-calendar" /home/rsnwvvl103hc/public_html/app_read/static/css/app.css 2>&1 | tee -a $LOGFILE || true

echo "Restarting Passenger..." | tee -a $LOGFILE
mkdir -p tmp
touch tmp/restart.txt

echo "===== DEPLOY DONE $(date) =====" | tee -a $LOGFILE