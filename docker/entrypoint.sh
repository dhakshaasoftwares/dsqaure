#!/bin/sh
set -e
python manage.py migrate --noinput
# Adds default roles, units, stages, numbering and agreement template if missing.
# Company name and the owner login are created in the browser by the setup wizard.
python manage.py setup_defaults
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_WORKERS:-3} --timeout 120
