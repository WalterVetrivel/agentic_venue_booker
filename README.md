# Agentic Venue Booker

Venue booking system for KIOT (CSE pilot). It works as a normal web app, with an AI assistant on top that uses **MCP** tools for live data and **RAG** over event circulars and reports.

See [docs/PLAN.md](docs/PLAN.md) for the full plan and architecture.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold, mock login, roles, venues, layout, theme, chat panel shell | ✅ |
| 1 | Venue and equipment management, availability grid | ✅ |
| 2 | Timetable PDF ingestion | ✅ |
| 3 | Bookings, approvals, waitlist, class displacement | ✅ |
| 4 | Circulars and reports, RAG, recurring-event warnings | ✅ |
| 5 | LLM (Groq / Ollama), MCP server, assistant | ✅ |
| 6 | Reports, CSV export, accessibility and polish | ✅ |

## Run it locally (Windows)

Prerequisites: Python 3.12+ (3.14 works), Node 22+, Git.

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env          # then edit APP_SECRET (the Groq key can also be set in Settings)
alembic upgrade head
python -m app.seed              # loads users and venues; add --reset to start over
python -m app.seed --timetables # optional: also commits every mock timetable PDF
python -m app.seed --documents  # optional: loads every mock circular and report (about 15 s)
python -m app.seed --bookings   # optional: demo bookings, approvals, waitlist and equipment faults for the reports
uvicorn app.main:app --reload   # http://127.0.0.1:8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to the backend)
```

Re-running the seed never overwrites your edits, but it does refill a venue's equipment, aliases and seasonal rules if they are empty.

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

### Timetables

Log in as the OA (`cseoa@kiot.ac.in`) and open **Timetables**. Upload one or more PDFs from `data/mock/timetables`. Each one is read, its lab sessions are checked against the venues and against classes already committed, and it waits for review. Fix any highlighted slot, then commit it. Committed lab sessions show on the availability grid. Classes are not a hard block: a booking can still ask to move them (Phase 3). Uploading a class again replaces its pending upload, and committing it replaces its earlier timetable.

### Bookings

1. Log in as a faculty member (for example `tkcse@kiot.ac.in`) and open **Book a venue**, or use the **Book** link on the availability grid or a venue page. Availability is checked as you type.
2. If a timetabled class uses the venue then, choose for each class whether it moves to another free lab (best software match first) or runs as BYOD in the classroom. Moving a class needs the HOD's approval.
3. If another booking holds the slot, you can join the waitlist. When the slot frees up, the first person waiting gets an offer and has 24 hours to confirm it.
4. Requests go to the venue's in-charge, then to the HOD for CSE venues or when a class moves. Approvers see their queue under **Approvals**, with a short list of things to check. A step is skipped when the requester approves it themselves (an in-charge booking their own lab, the HOD or the Director).
5. **My bookings** lists your requests. From a booking you can reschedule it (the old slot is kept until the new one is confirmed) or cancel it.
6. The bell in the top bar shows notifications: approvals needed, decisions, offers, classes moved, and events in a venue you look after.

Try it with `tkcse` booking `CSEPGSH`, then approve as `pvcse@kiot.ac.in` (the hall's in-charge) and `hod.cse@kiot.ac.in`.

### Student requests

Students still don't log in. Under **Book a lab** a group asks for a lab or centre of excellence (never a seminar hall) for project work: what they will work on, their faculty guide, each student's name, class and (optionally) register number, and one contact email. They get a tracking number like `ST-7K3P-9QXA` and follow the request under **Track a request**.

1. The **faculty guide** they chose sees it under **Approvals** and approves or rejects each student (or all at once). Rejecting someone needs a reason. The request goes on with the approved students; if none are approved it is rejected.
2. Then the **venue in-charge** and the **HOD** approve it as usual. If the guide is also that lab's in-charge, the in-charge step is approved with the guide's decision.
3. **Class advisors** (the advisor named on each class timetable) get a notification once their students' outcome is final.
4. The group gets an email at each step. Until a mail server is set up, emails are saved to `backend/storage/outbox`; see [docs/EMAIL.md](docs/EMAIL.md) to send them through Gmail.

Students can only ask for free slots: they can't move a class or join the waitlist. The classes to choose from come from the committed timetables, so run `python -m app.seed --timetables` first. The assistant can also draft a student request ("Book CC5 tomorrow 2 to 4 for our mini project, guide Mrs. B. Ashwini") and look one up by its tracking number.

Try it: request CC5 as a visitor with `Mrs. B. Ashwini` as guide, decide as `bacse@kiot.ac.in`, then approve as `mkscse@kiot.ac.in` (CC5's in-charge) and `hod.cse@kiot.ac.in`.

### Circulars, reports and past events

Run `python -m app.seed --documents`, or log in as the OA and upload PDFs under **Past events → Upload & manage**. Each circular and event report is read without AI: the title, venue, dates, times, audience, attendance and topics come straight from the document's table. A circular and its report become one past event. Uploading a document again replaces the old copy.

- **Search** finds circulars and reports by keywords (SQLite full-text search). If Ollama is running with `nomic-embed-text` (`ollama pull nomic-embed-text`), it also matches by meaning and merges the two rankings. Set `EMBEDDINGS=off` in `backend/.env` to use keywords only. Documents added while Ollama was off can be indexed later with **Index the rest**.
- **Is meaning-based search working?** Run `python -m app.seed --embed` in `backend`: it indexes any documents that aren't yet and says why not if it can't (Ollama not running, `nomic-embed-text` not pulled, too slow). Search uses the Ollama address from **Settings** (the same one the assistant uses), falling back to `OLLAMA_BASE_URL`. On Windows, if `ollama serve` says *Only one usage of each socket address…*, Ollama is already running (usually the tray app): check with `curl http://localhost:11434/api/tags` instead of starting it again.
- **Past events** lists every event with filters for venue, type and academic year. Ten mock documents have an end time before the start time (for example 13:25 to 12:35); their five events are marked **Needs checking** instead of being guessed. The OA, HOD or Director can correct any event, and later uploads won't overwrite the correction.
- **Recurring-event warnings**: when an event series was held in a venue around the same date in at least two earlier years, the booking form, the availability grid and the approver's notes say so, and other free venues are suggested. Try booking `COE1` for mid-September (the in-house hackathon) or `CC1` for mid-November (model practical exams).

The assistant answers questions from the same search and cites the circulars and reports it used.

### The assistant

Open the chat panel (docked on wide screens, **Ask the assistant** on phones). It uses tools for every fact, so it never guesses availability, and it can't change anything by itself:

- **Drafts**: "Book COE1 next Tuesday 10 to 12 for a Python workshop, 30 students" gives a card that opens the booking form already filled in. You check it and submit.
- **Proposals**: cancelling a booking, approving or rejecting a request, and marking equipment faulty come back as a card with a button. Pressing it calls the normal API, and the audit log records it as `via=agent`.
- **Attachments** (logged in): drop a PDF in the chat. The OA's timetables go to review, circulars and reports from people who upload documents go into **Past events**, and anything else is just read so you can ask about it.
- **People** can be named the way the department talks: "Walter sir", "EK ma'am", "KS ma'am", "HOD sir". The assistant finds them by name, part of a name (tolerating spellings like Sowndarya/Sowndharya), initials or role, and asks which one when several match ("Sowndarya ma'am" is Mrs. S. Sowndarya or Mrs. T. Sowndharya). This works for a student group's faculty guide, a teacher's timetable ("EK ma'am's labs this week") and plain "who is…" questions.
- Staff chats are saved: the title menu lists them, with search, rename and delete. Students can use the visitor tools without logging in; their chats aren't saved. If a student says they are faculty, or asks for something only staff can do, the assistant links them to the login page and back to the booking form.

**Rate limits.** The app's own limits on visitors (20 chat questions per 10 minutes per IP, 5 student requests an hour per IP, 3 a day per email) are off for the prototype. Set `RATE_LIMITS=true` in `backend/.env` to turn them on before real use. Groq's own limits apply either way.

**Choosing the model.** The Director sets the default in **Settings**: Groq (online; get a free key at console.groq.com/keys) or Ollama (local). People can switch in the chat panel's model menu. On Ollama, `qwen3.5:4b` works on 8 GB RAM without a GPU but is slow and makes more mistakes; use Groq for demos. If Groq retires the model, the fallback model is used.

**Smoke test with a real model** (about 15 questions; read-only, safe on your normal database):

```powershell
python -m app.agent.smoke                    # default provider
python -m app.agent.smoke --provider ollama
```

**MCP.** The same tools are an MCP server at `http://127.0.0.1:8000/mcp/` (Streamable HTTP). Without a token a client gets the public, read-only tools; with a token it gets the tools that person's roles allow. The Director's **Settings** page creates a token and the Claude Desktop config (it uses `npx mcp-remote`); any logged-in user can get one from `GET /api/auth/mcp-token`. Changes still have to be confirmed in the app.

For browser tests and demos without a model, set `LLM_FAKE=1`: a scripted demo assistant answers a few question shapes using the real tools.

### Reports

**Reports** shows how the venues are used, for the venues you are responsible for: an in-charge sees their own venues, the HOD sees the CSE venues and the Director sees all of them.

- **Utilisation**: the share of open hours taken by timetabled classes and by events (confirmed bookings and past events), per venue, as a chart or a table. Classes moved out for a booking count in the lab they moved to, and maintenance or closed days are left out.
- **Events** by month, type and department; **approval turnaround** per step (from when the request reached that person); **waitlist** outcomes; and **equipment faults** reported in the period, with what is out of service now.
- Pick the term so far, the last 30 days, this or last month, or your own dates. Every section downloads as CSV (opens in Excel).
- The assistant can answer "How busy were the labs this month?" with the `utilisation_report` tool and links to the page.

`python -m app.seed --bookings` adds about three months of demo history (dates are relative to today) so the reports have something to show. It runs once; `--reset` starts over.

### Demo script

[docs/DEMO.md](docs/DEMO.md) walks through every feature in about 20 minutes, role by role.

## Tests

```powershell
cd backend;  pytest -q; ruff check .
cd frontend; npm run check; npm run build
# end-to-end (from frontend; set PYTHON to the backend venv's python)
$env:PYTHON="..\backend\.venv\Scripts\python"; npm run test:e2e
```

The end-to-end tests include automated accessibility checks (axe, WCAG 2.1 AA) on the main pages in light and dark themes. Lighthouse scores 100 for accessibility on every main page.

## Layout

```
backend/   FastAPI app, SQLAlchemy models, Alembic migrations, seed data, tests
frontend/  SvelteKit (Svelte 5) SPA with Tailwind
data/mock/ timetables, circulars, reports and the faculty list used for seeding and tests
docs/      plan and architecture
```
