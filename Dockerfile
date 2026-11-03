# One container for the whole app: the SvelteKit frontend is built here and served by FastAPI,
# the same way `npm run build` + `uvicorn app.main:app` works on the laptop.
# Works on Google Cloud Run, Render and Hugging Face Spaces (they all set or accept $PORT).
# No secrets are baked in: pass GROQ_API_KEY and APP_SECRET as env vars when deploying.

# ---- 1. Build the frontend ----
FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Backend + built frontend ----
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    # The app uses local time for "today" and "now"; the cloud runs on UTC otherwise.
    TZ=Asia/Kolkata \
    # No Ollama in the cloud: keyword search only, Groq for the assistant.
    EMBEDDINGS=off \
    DEFAULT_LLM_PROVIDER=groq \
    COOKIE_SECURE=true

# Hugging Face Spaces runs the container as uid 1000; Cloud Run and Render don't mind.
RUN useradd --create-home --uid 1000 app
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY --chown=app:app backend/ ./
COPY --chown=app:app data/ /app/data/
COPY --from=frontend --chown=app:app /src/frontend/build /app/frontend/build
COPY --chown=app:app deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh && mkdir -p storage && chown app:app storage

USER app
# Timetables, circulars and reports don't depend on the date, so load them now (about 40 s)
# rather than on every start. Demo bookings are relative to today, so start.sh adds those.
RUN alembic upgrade head && python -m app.seed --timetables --documents

EXPOSE 8080
CMD ["/app/start.sh"]
