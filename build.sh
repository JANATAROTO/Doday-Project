#!/usr/bin/env bash
# Build step for the hosting platform (Render runs it on every deploy).
set -o errexit

pip install -r requirements.txt

# Gather and fingerprint the CSS for WhiteNoise.
python manage.py collectstatic --no-input

# Bring the database up to date. Both commands are safe to repeat.
python manage.py migrate --no-input
python manage.py createcachetable
