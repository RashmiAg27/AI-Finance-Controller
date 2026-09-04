#!/usr/bin/env bash
# Render (or any host) start command: seed the demo world if the database is
# empty -- safe on first boot, a redeploy, or a wake from sleep alike, see
# scripts/seed_if_empty.py -- then launch the API.
set -e
python scripts/seed_if_empty.py
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
