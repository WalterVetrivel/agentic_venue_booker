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
# search, then run one real prompt through the chat model. The GPU's first prompt is slow (about
# 40 s while it sets up), so it happens here instead of on the first question. The prompt is
# about as long as the assistant's and uses the same context size, so the model isn't reloaded.
# Neither stops the app from starting if Ollama isn't there.
if [ "$EMBEDDINGS" = "ollama" ]; then
  python -m app.seed --embed || echo "Couldn't index documents; search uses keywords only."
  python - <<'PY' &
import time

import httpx
from app.config import get_settings

s = get_settings()
started = time.monotonic()
try:
    res = httpx.post(
        f"{s.ollama_base_url}/api/generate",
        json={
            "model": s.ollama_model,
            "prompt": "Venue booking warm-up. " * 400 + "Reply with OK.",
            "think": False,
            "stream": False,
            "keep_alive": -1,
            "options": {"num_ctx": 8192, "num_predict": 8},
        },
        timeout=600,
    )
    res.raise_for_status()
    print(f"Warmed up {s.ollama_model} in {time.monotonic() - started:.0f} s", flush=True)
except Exception as e:
    print(f"Couldn't warm up {s.ollama_model} in Ollama: {e}", flush=True)
PY
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips='*'
