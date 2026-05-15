#!/bin/bash
set -e

cd /home/rsnwvvl103hc/app_read

PYTHON="/home/rsnwvvl103hc/virtualenv/app_read/3.11/bin/python"

echo "Running Django check..."
$PYTHON manage.py check --settings=config.settings_godaddy

echo "Running migrations..."
$PYTHON manage.py migrate --settings=config.settings_godaddy --noinput

echo "Collecting static files..."
$PYTHON manage.py collectstatic --settings=config.settings_godaddy --noinput --clear

echo "Restarting Passenger..."
mkdir -p tmp
touch tmp/restart.txt

echo "Deployment completed."