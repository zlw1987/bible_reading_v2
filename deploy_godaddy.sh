#!/bin/bash
set -euo pipefail

REPOPATH="/home/rsnwvvl103hc/repositories/app_read"
DEPLOYPATH="/home/rsnwvvl103hc/app_read"
PYTHON="/home/rsnwvvl103hc/virtualenv/app_read/3.11/bin/python"
LOGFILE="$DEPLOYPATH/deploy.log"
SETTINGS="config.settings_godaddy"
DB_PATH="$DEPLOYPATH/db.sqlite3"
BACKUP_DIR="$DEPLOYPATH/backups"

run_manage() {
  echo ">>> $PYTHON manage.py $* --settings=$SETTINGS" | tee -a "$LOGFILE"
  $PYTHON manage.py "$@" --settings="$SETTINGS" 2>&1 | tee -a "$LOGFILE"
}

sqlite_quick_check() {
  local label="$1"
  local db_file="$2"

  echo "Running SQLite quick_check for $label: $db_file" | tee -a "$LOGFILE"
  $PYTHON - "$db_file" "$label" <<'PY' 2>&1 | tee -a "$LOGFILE"
import sqlite3
import sys

db_file = sys.argv[1]
label = sys.argv[2]

with sqlite3.connect(db_file) as connection:
    result = connection.execute("PRAGMA quick_check").fetchone()

status = result[0] if result else None
print(f"{label} quick_check: {status}")
if status != "ok":
    raise SystemExit(1)
PY
}

run_legacy_structure_preflight() {
  echo "Running legacy structure preflight guard before migrate..." | tee -a "$LOGFILE"
  run_manage check
  run_manage showmigrations accounts
  run_manage migrate --plan
  run_manage audit_legacy_structure_object_row_retirement --verbose --limit 50 --fail-on-blockers
  run_manage audit_legacy_structure_schema_retirement_readiness --verbose --limit 50
  run_manage audit_legacy_structure_retirement_readiness --verbose --limit 50 --fail-on-blockers
}

run_legacy_structure_post_checks() {
  echo "Running legacy structure post-migration verification..." | tee -a "$LOGFILE"
  run_manage check
  run_manage makemigrations --check --dry-run
  run_manage showmigrations accounts
  run_manage audit_legacy_structure_object_row_retirement --verbose --limit 50 --fail-on-blockers
  run_manage audit_legacy_structure_schema_retirement_readiness --verbose --limit 50
  run_manage audit_legacy_structure_retirement_readiness --verbose --limit 50 --fail-on-blockers
}

mkdir -p "$DEPLOYPATH"

echo "===== DEPLOY START $(date) =====" | tee "$LOGFILE"
echo "Repo path: $REPOPATH" | tee -a "$LOGFILE"
echo "Deploy path: $DEPLOYPATH" | tee -a "$LOGFILE"
echo "Python: $PYTHON" | tee -a "$LOGFILE"

echo "Checking source repo..." | tee -a "$LOGFILE"
if [ ! -d "$REPOPATH" ]; then
  echo "ERROR: Repo path does not exist: $REPOPATH" | tee -a "$LOGFILE"
  exit 1
fi

if [ ! -f "$REPOPATH/manage.py" ]; then
  echo "ERROR: manage.py not found in repo path: $REPOPATH" | tee -a "$LOGFILE"
  exit 1
fi

if [ ! -f "$REPOPATH/passenger_wsgi.py" ]; then
  echo "ERROR: passenger_wsgi.py not found in repo path: $REPOPATH" | tee -a "$LOGFILE"
  exit 1
fi

echo "Syncing files from repo to app directory..." | tee -a "$LOGFILE"
/bin/rsync -av --delete \
  --no-perms \
  --no-owner \
  --no-group \
  --chmod=D755,F644 \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.env' \
  --exclude='db.sqlite3' \
  --exclude='media/' \
  --exclude='tmp/' \
  --exclude='backups/' \
  --exclude='deploy.log' \
  --exclude='passenger.log' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  "$REPOPATH/" "$DEPLOYPATH/" 2>&1 | tee -a "$LOGFILE"

echo "Fixing permissions..." | tee -a "$LOGFILE"
/bin/chmod 755 "$DEPLOYPATH"
/usr/bin/find "$DEPLOYPATH" -type d -exec chmod 755 {} \;
/usr/bin/find "$DEPLOYPATH" -type f -exec chmod 644 {} \;
/bin/chmod 755 "$DEPLOYPATH/manage.py" || true
/bin/chmod 644 "$DEPLOYPATH/passenger_wsgi.py" || true
/bin/mkdir -p "$DEPLOYPATH/tmp"
/bin/chmod 755 "$DEPLOYPATH/tmp"

cd "$DEPLOYPATH"

echo "Python version..." | tee -a "$LOGFILE"
$PYTHON --version 2>&1 | tee -a "$LOGFILE"

echo "Checking effective Django static settings..." | tee -a "$LOGFILE"
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

echo "Preparing legacy structure final migration guard..." | tee -a "$LOGFILE"
if [ ! -f "$DB_PATH" ]; then
  echo "ERROR: Expected GoDaddy SQLite DB is missing: $DB_PATH" | tee -a "$LOGFILE"
  exit 1
fi

if [ ! -s "$DB_PATH" ]; then
  echo "ERROR: Expected GoDaddy SQLite DB is empty: $DB_PATH" | tee -a "$LOGFILE"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
BACKUP_TIMESTAMP="$(date +%Y%m%d%H%M%S)"
BACKUP_PATH="$BACKUP_DIR/db.pre_legacy_structure_migration.$BACKUP_TIMESTAMP.sqlite3"

echo "Creating pre-migration DB backup: $BACKUP_PATH" | tee -a "$LOGFILE"
cp "$DB_PATH" "$BACKUP_PATH"

if [ ! -s "$BACKUP_PATH" ]; then
  echo "ERROR: Pre-migration DB backup is missing or empty: $BACKUP_PATH" | tee -a "$LOGFILE"
  exit 1
fi

sqlite_quick_check "source DB" "$DB_PATH"
sqlite_quick_check "pre-migration backup" "$BACKUP_PATH"

run_legacy_structure_preflight

echo "Running migrations after backup, integrity check, and preflight pass..." | tee -a "$LOGFILE"
run_manage migrate --noinput

run_legacy_structure_post_checks

echo "Collecting static files..." | tee -a "$LOGFILE"
run_manage collectstatic --noinput --clear --verbosity 2

echo "Checking generated public static file..." | tee -a "$LOGFILE"
if [ -f "/home/rsnwvvl103hc/public_html/app_read/static/css/app.css" ]; then
  ls -l /home/rsnwvvl103hc/public_html/app_read/static/css/app.css 2>&1 | tee -a "$LOGFILE"
  grep -n "reading-calendar" /home/rsnwvvl103hc/public_html/app_read/static/css/app.css 2>&1 | tee -a "$LOGFILE" || true
else
  echo "WARNING: public static css/app.css not found." | tee -a "$LOGFILE"
fi

echo "Restarting Passenger..." | tee -a "$LOGFILE"
mkdir -p "$DEPLOYPATH/tmp"
touch "$DEPLOYPATH/tmp/restart.txt"

echo "===== DEPLOY DONE $(date) =====" | tee -a "$LOGFILE"
