#!/bin/sh
# Container start: bring the database up to date and add the demo bookings (dates relative to
# today), then run the server. Timetables and documents were loaded when the image was built.
# The database lives inside the container, so a restart begins again from fresh demo data.
# Seeding is safe to repeat: it never overwrites edits and the demo bookings load only once.
set -e
cd /app/backend
alembic upgrade head
python -m app.seed --bookings
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips='*'
