# Agentic Venue Booker

Venue booking system for KIOT (CSE pilot). It works as a normal web app, with an AI assistant on top that uses **MCP** tools for live data and **RAG** over event circulars and reports.

See [docs/PLAN.md](docs/PLAN.md) for the full plan and architecture.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold, mock login, roles, venues, layout, theme, chat panel shell | ✅ |
| 1 | Venue and equipment management, availability grid | ✅ |
| 2 | Timetable PDF ingestion | ⏳ |
| 3 | Bookings, approvals, waitlist, class displacement | |
| 4 | Circulars and reports, RAG, recurring-event warnings | |
| 5 | LLM (Groq / Ollama), MCP server, assistant | |
| 6 | Reports and polish | |

## Run it locally (Windows)

Prerequisites: Python 3.12+ (3.14 works), Node 22+, Git.

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env          # then edit APP_SECRET (and GROQ_API_KEY from Phase 5)
alembic upgrade head
python -m app.seed              # loads users and venues; add --reset to start over
uvicorn app.main:app --reload   # http://127.0.0.1:8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to the backend)
```

To serve everything from the backend alone, run `npm run build` in `frontend`, then open http://127.0.0.1:8000.

### Demo logins

All accounts use the password `password`.

| Email | Role |
|---|---|
| `swvcse@kiot.ac.in` | Faculty, CC10 in-charge |
| `tkcse@kiot.ac.in` | Faculty |
| `hod.cse@kiot.ac.in` | HOD |
| `dirim@kiot.ac.in` | Director IM |
| `cseoa@kiot.ac.in` | OA / DEO |
| `sh.ablock@kiot.ac.in` and similar | Seminar hall in-charges for A, D, E and MBA halls |

Every faculty member in `data/mock/faculty.xlsx` has a login made from their initials, like `<initials>cse@kiot.ac.in`. Venue in-charges are set in `backend/app/seed/venues.yaml`.

## Tests

```powershell
cd backend;  pytest -q; ruff check .
cd frontend; npm run check; npm run build
# end-to-end (from frontend; set PYTHON to the backend venv's python)
$env:PYTHON="..\backend\.venv\Scripts\python"; npm run test:e2e
```

## Layout

```
backend/   FastAPI app, SQLAlchemy models, Alembic migrations, seed data, tests
frontend/  SvelteKit (Svelte 5) SPA with Tailwind
data/mock/ timetables, circulars, reports and the faculty list used for seeding and tests
docs/      plan and architecture
```
