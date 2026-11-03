#!/bin/sh
# Container start: bring the database up to date and add the demo bookings (dates relative to
# today), then run the server. Timetables and documents were loaded when the image was built.
# The database lives inside the container, so a restart begins again from fresh demo data.
# Seeding is safe to repeat: it never overwrites edits and the demo bookings load only once.
set -e
cd /app/backend
alembic upgrade head
python -m app.seed --bookings

# With an Ollama sidecar (deploy/cloudrun-gpu.yaml): index the documents for meaning-based
# search, and load the chat model into the GPU so the first question doesn't wait for it.
# Neither stops the app from starting if Ollama isn't there.
if [ "$EMBEDDINGS" = "ollama" ]; then
  python -m app.seed --embed || echo "Couldn't index documents; search uses keywords only."
  python - <<'PY' &
import httpx
from app.config import get_settings

s = get_settings()
try:
    httpx.post(f"{s.ollama_base_url}/api/generate",
               json={"model": s.ollama_model, "keep_alive": -1}, timeout=300)
    print(f"Loaded {s.ollama_model} in Ollama", flush=True)
except Exception as e:
    print(f"Couldn't load {s.ollama_model} in Ollama: {e}", flush=True)
PY
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips='*'
