# Agentic Venue Booker — Project Plan & Architecture

**Project:** KIOT agentic venue booking system (CSE pilot)
**Repo:** https://github.com/WalterVetrivel/agentic_venue_booker
**Local folder:** `D:\projects\venue_booking_agent_v2`
**Status:** Draft v1 for review (27 Oct 2026). Nothing is built yet.

---

## 1. Goal in one paragraph

This is a normal web app for booking labs, seminar halls and Centres of Excellence. It knows every class timetable, every venue's capacity, equipment and software, and every past event (from circulars and reports). An AI assistant sits on top of it. The assistant can do anything the logged-in user can do in the app, and nothing more. Every feature works without the assistant. The assistant uses **MCP** tools for live data and actions (availability, bookings, timetables). It uses **RAG** over circulars and reports for history (similar past events, recurring events, past attendance). Timetables are turned into rows in SQLite when they're uploaded, so availability is always answered with a database query, never with RAG.

---

## 2. Users, roles and permissions

| Capability | Student (no login) | Faculty | Lab Technician | Venue In-charge | OA / DEO | HOD | Director IM |
|---|---|---|---|---|---|---|---|
| View venues, equipment, software | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Check availability (any date) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Use the AI assistant | read-only, not saved | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Create, reschedule or cancel own bookings | | ✓ | | ✓ | | ✓ | ✓ |
| Join a waitlist | | ✓ | | ✓ | | ✓ | ✓ |
| Update equipment status | | | own labs | own venues | | | all |
| Update venue details or status | | | | own venues | | | all |
| Add or remove venues | | | | | | | ✓ |
| Approve or reject bookings | | | | own venues | | CSE venues | override all |
| Approve class displacement | | | | | | ✓ | ✓ |
| Upload timetables | | | | | ✓ | ✓ | ✓ |
| Upload circulars and reports | | | | | ✓ | ✓ | ✓ |
| Get notified of events in their lab | | | ✓ | ✓ | | | |
| Utilisation reports | | | | own venues | | CSE venues | all |
| LLM settings and API keys | | | | | | | ✓ |

**One person can hold several roles.** For example, a faculty member can also be an in-charge. Each user has a set of roles, and their permissions are the union of those roles. Separate logins are kept only where you asked for them (`tkcse` and `hod.cse`).

### Seed accounts (all with the password `password`)

| Login | Person | Roles |
|---|---|---|
| `<initials>cse@kiot.ac.in` | the 44 faculty in the sheet (lower-case initials, e.g. `swvcse`, `tkcse`, `prcse`) | Faculty, plus In-charge where assigned |
| `hod.cse@kiot.ac.in` | Mr. T. Karthikeyan | HOD |
| `dirim@kiot.ac.in` | Dr. V. Kumar | Director IM (no faculty login, as agreed) |
| `cseoa@kiot.ac.in` | CSE OA / DEO | OA / DEO |
| *(later)* lab technicians | to be provided | Lab Technician |

Dr. P. Rajendran is a regular faculty member, as agreed. The sheet's "Criteria" column (accreditation duties) is ignored.

**Venue in-charges** are assigned from the faculty list in a seed file, `seed/venues.yaml`, which you can edit. The Director can also change them in the app.

---

## 3. Venues (seed data)

| Venue | Type | Capacity | Notes |
|---|---|---|---|
| CC1, CC2 | Lab | 60 | |
| CC3 to CC12 | Lab | 40 | |
| PG Lab | Lab | 40 | research software, GPU workstations |
| IoT Lab | Lab | 40 | Arduino and Raspberry Pi kits, sensors |
| COE1 to COE4 | Centre of Excellence | 30 | BYOD, so no PCs; power points and Wi-Fi |
| CSE PG Seminar Hall | Seminar hall | 80 | |
| A Block Seminar Hall | Seminar hall | 100 | blocked for admissions every March to July (seasonal rule) |
| D Block Seminar Hall | Seminar hall | 300 | |
| E Block Seminar Hall | Seminar hall | 300 | |
| MBA Seminar Hall | Seminar hall | 100 | |

**Software in the labs (assumed, all Windows):**
- CC1 to CC4 (programming): VS Code, JDK, Python, GCC/MinGW, MySQL, Git
- CC5 to CC8 (data and AI): Anaconda, Jupyter, TensorFlow, PyTorch, Power BI, R
- CC9 and CC10 (web and cloud): Node.js, Docker Desktop, Postman, AWS CLI, MongoDB
- CC11 and CC12 (networks and security): Wireshark, Cisco Packet Tracer, a Kali VM, NS-3
- PG Lab: MATLAB, CUDA toolkit, plus the AI stack above

**Equipment:** projector, smart board, audio system, AC, and video conferencing for some venues. Each item has a status (working, faulty or under repair).

**Venue status:** available, under maintenance, under renovation or closed. Each status has an optional date range.

These are only seed defaults. The real list lives in the database and can be edited in the app.

---

## 4. Architecture

```
┌──────────────────────── Browser (Svelte SPA) ───────────────────────┐
│  Pages: Availability · Venues · Book · My bookings · Approvals ·    │
│         Timetables · Documents · Reports · Settings                 │
│  Right-docked Chat panel (closable, history dropdown, streaming)    │
└───────────────┬───────────────────────────────┬─────────────────────┘
                │ REST (JSON)                   │ SSE (chat stream)
┌───────────────▼───────────────────────────────▼─────────────────────┐
│                       FastAPI backend (Python)                       │
│                                                                      │
│  REST routers ──┐            Agent runtime ──► LLM gateway           │
│                 │            (tool loop)       (Groq | Ollama,       │
│                 │                 │             OpenAI-compatible)   │
│                 │            MCP client                              │
│                 │                 │ (user's token)                   │
│                 │          ┌──────▼───────┐                          │
│                 │          │  MCP server  │  role-filtered tools     │
│                 │          │  (/mcp)      │                          │
│                 ▼          └──────┬───────┘                          │
│        ┌───────────────── Service layer ─────────────────┐          │
│        │ availability · bookings · approvals · waitlist  │          │
│        │ timetables · venues · documents/RAG · reports   │          │
│        │ recommendations · clash/recurrence detection    │          │
│        │ permissions (single source of truth)            │          │
│        └─────────────────────┬───────────────────────────┘          │
│                              │                                       │
│   Ingestion workers: timetable PDF parser · circular/report          │
│   extractor · chunk + embed (Ollama nomic-embed-text)               │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
                 SQLite (app.db): relational tables
                 + FTS5 index + embeddings (BLOB)
```

**Key design rules**

1. **One service layer, two ways in.** The REST routers used by the UI and the MCP tools used by the agent both call the same service functions. The same permission checks run in that layer. This is how the assistant gets exactly the user's access level.
2. **The MCP server is real and runs on its own.** It is mounted at `/mcp` (streamable HTTP) using the official Python `mcp` SDK. The in-app agent connects to it as an MCP client with the user's token. It can also be connected to Claude Desktop or MCP Inspector for demos.
3. **The agent never commits a write by itself.** It makes drafts and proposals, such as a filled booking form, a cancellation or an approval with reasons. The user confirms them in the UI by clicking.
4. **Facts come from the database, history comes from RAG.** Availability, capacity and equipment come from SQL. Past events and recurring patterns come from the documents, through structured extraction plus hybrid search.

---

## 5. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.14, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 | matches your Python setup and has the best MCP and RAG tooling |
| DB | SQLite (one file, WAL mode) with FTS5 | as you asked; FTS5 is built in |
| Vectors | embeddings stored as BLOBs, cosine search with NumPy | there are fewer than 2,000 chunks, so brute force takes milliseconds. This avoids loading SQLite extensions, which is fragile on Windows with Python 3.14. sqlite-vec can be swapped in later. |
| Embeddings | Ollama `nomic-embed-text` | Groq has no embeddings API. If Ollama is down, search falls back to keywords only (FTS5). |
| LLM | Groq (default, key from `.env`) or Ollama. Both are used through the OpenAI-compatible chat API. | One client, and switching provider only changes `base_url`, key and model. |
| Default models | Groq `openai/gpt-oss-20b` (fallback `llama-3.3-70b-versatile`); Ollama `qwen3.5:4b` | all handle tool calling; changeable in Settings. The laptop has 8 GB RAM and no GPU, so `qwen3.5:latest` (6.6 GB) is not the default. |
| MCP | `mcp` Python SDK (FastMCP) | official SDK |
| PDF text | `pypdf` plus `pdfplumber` (keeps table layout) | the timetables are table-shaped |
| Frontend | **Svelte 5 + SvelteKit (static SPA build)**, Tailwind CSS | needs much less code than React for the same UI, so fewer tokens to build and maintain |
| Auth (mock) | bcrypt-hashed passwords, JWT in an httpOnly cookie | simple, but done properly |
| Tests | pytest, httpx, Playwright (end to end) | |
| CI | GitHub Actions: lint, pytest, frontend build, Playwright smoke test | |

In production, FastAPI serves the built SPA, so it's a single process. In development there are two: `uvicorn` and `vite`.

---

## 6. Data model (SQLite)

**People and access**
- `users` (id, name, initials, email, designation, password_hash, active)
- `roles` (key: faculty, technician, incharge, oa, hod, director)
- `user_roles` (user_id, role_key)

**Venues**
- `venues` (id, code, name, type [lab, seminar_hall, coe], block, department, capacity, byod, in_charge_user_id, notes)
- `venue_aliases` (venue_id, alias). For example, "COE2 Lab", "Centre of Excellence (COE3)" and "A Block Seminar Hall" all map to the right venue. Circulars use inconsistent names, so this table is needed.
- `venue_status_periods` (venue_id, status, from, to, reason, set_by)
- `seasonal_rules` (venue_id, months or date range, kind [blocked, soft_warning], reason). For example, A Block Seminar Hall is reserved for admissions from March to July.
- `equipment` (id, venue_id, name, category [hardware, software, av, facility], quantity, status, updated_by, updated_at)

**Academic timetable**
- `academic_terms` (id, name, valid_from, valid_to). For example, 2026-27 ODD runs from 01.07.2026 to 30.11.2026.
- `period_template` (period_no, start, end). This holds 09:00–09:50, 09:50–10:40, and so on, taken from the PDF header.
- `class_sections` (id, dept, year, section, advisor, strength)
- `timetable_uploads` (id, file, uploaded_by, status [parsed, reviewed, committed], parse_report_json)
- `timetable_slots` (id, term_id, section_id, weekday, start, end, subject_code, subject_name, faculty_name, batch [all, B1, B2], venue_id, upload_id)
- `slot_overrides` (slot_id, date, action [relocated, byod_classroom, cancelled], new_venue_id, booking_id, approved_by). This is how a class gets displaced for one date.

**Bookings**
- `bookings` (id, ref, requester_id, venue_id, title, event_type, description, expected_count, start_dt, end_dt, requirements_json, status, created_via [form, assistant], parent_id for reschedules, cancel_reason, timestamps)
- `booking_occurrences` (booking_id, start_dt, end_dt). Multi-day events are split into one row per day.
- `approvals` (booking_id, step [incharge, hod, displacement], approver_id, decision, comment, decided_at)
- `waitlist_entries` (id, booking_id, blocking_booking_id, position, offered_at, offer_expires_at, state)
- `notifications` (id, user_id, kind, payload_json, read_at)
- `audit_log` (actor, action, entity, before, after, via [ui, agent], at)

**Event types (enum, extendable):** workshop, hands-on training, seminar, guest lecture, awareness programme, value-added course, faculty development programme, conference, coding contest, hackathon, inauguration, valedictory, model practical exam, placement training, admission activity, address by HOD, Principal or Chairman, professional elective class, meeting, other.

**Documents and RAG**
- `documents` (id, kind [circular, report], file, ref_no, dept, academic_year, issued_on, uploaded_by, status)
- `past_events` (id, document_id, title, normalised_title, series_key, event_type, organiser_dept, venue_id(s), start_date, end_date, start_time, end_time, audience, expected_count, actual_count, resource_persons, topics, feedback_rating). This is structured data extracted from each document. A circular and its report are linked into one event when possible.
- `doc_chunks` (id, document_id, text, embedding BLOB) plus the FTS5 table `doc_chunks_fts`.

**Assistant**
- `conversations` (id, user_id, title, created_at, updated_at)
- `messages` (id, conversation_id, role, content, tool_calls_json, created_at)
- `settings` (key, value). API keys are encrypted with Fernet using `APP_SECRET` from `.env`.

### Booking state machine

```
draft ──submit──► pending_incharge ──approve──► pending_hod* ──approve──► confirmed
   │                    │                           │                     │
   │                 reject                       reject           cancel / reschedule
   │                    ▼                           ▼                     ▼
   │                 rejected                    rejected        cancelled → promote waitlist
   └─(slot taken)──► waitlisted ──slot frees──► offered (24 h) ──confirm──► pending_incharge
                                                    └──expire──► next in queue
* only for CSE-owned venues, or when a class is displaced
```

A **reschedule** creates a new booking linked to the old one through `parent_id`. The old slot is released only when the new one is confirmed, so the user never ends up with neither slot.

---

## 7. Availability engine

`is_free(venue, start, end)` checks five things, in this order:

1. **Venue status periods.** Maintenance or renovation means the venue is unavailable.
2. **Seasonal rules.** A "blocked" rule means unavailable. A "soft_warning" rule gives a warning only.
3. **Timetable slots** for the term on that weekday, minus any `slot_overrides` for that date. A clash with a class makes the slot **class-occupied**, not hard-blocked.
4. **Confirmed and pending bookings.** A clash makes the slot **booked**. The user can still join the waitlist.
5. **Recurring-event warnings** (see §9). These are advisory only.

The result for each 30-minute cell in a venue × day grid is one of: free, class (with the section and subject), booked, pending, maintenance or blocked, plus any warnings. The same function powers the Availability page, the student view, the booking form and the agent's tools.

**When the slot clashes with a class (your answer 5):** the user may still submit. The request then needs **HOD approval for displacement** in addition to the normal approval. The system offers two options:
- **Relocate.** It finds other labs that are free at that time, have enough capacity for the batch and have the same software. It suggests the best match.
- **BYOD in the classroom.** No new lab is needed.

When approved, a `slot_overrides` row is written. The subject faculty (matched from the timetable's faculty column) and the lab technician are notified.

---

## 8. Timetable ingestion (PDF to SQL)

**What the mock PDFs look like:** one PDF per class section, from CSE, IT, AI&DS and CSBS, years II to IV. Each is a Monday-to-Friday grid with 8 periods and a key mapping subject codes to faculty. Lab periods appear as `OOP LAB (CC1)` or as batch splits like `DBMS (B1, CC1) / DS (B2, CC2)`. A lab session usually spans 2 periods merged across a cell. `timetables/lab_slots_truth.csv` has 124 expected lab-slot rows, which is a ready-made answer key.

**Pipeline**

1. **Extract.** Use pdfplumber to read words with their x/y positions. Use the header row to get period column positions and times. Use the left column to get weekday rows.
2. **Parse with rules first.** A regex picks up venue mentions (`\((B\d),\s*(CC\d+|…)\)` and `LAB \((…)\)`). Each mention is mapped to its period span using its x-range, and merged cells are expanded. The metadata header gives department, year, section, term dates and class advisor.
3. **Fall back to the LLM.** If the rule parser finds a cell it can't read, the cell text and grid context go to the LLM with a strict JSON schema. That output is checked against the period template and the venue aliases.
4. **Human review.** The OA or DEO sees an editable preview grid that highlights conflicts with already-committed timetables, such as two sections in CC1 on Monday in periods 1 and 2. They fix any problems, then commit.
5. **Commit.** Rows are written to `timetable_slots`. Re-uploading the same section replaces that section's rows for the term.

This runs from the Timetables page and also through the assistant ("here's the CSE III-B timetable PDF").

**Quality bar:** a test parses all 22 PDFs and compares the result with `lab_slots_truth.csv`. The target is 100% of rows matching on section, weekday, start, end, batch and venue.

---

## 9. RAG over circulars and reports

**Corpus:** 155 circulars and 121 reports covering 2023-24 to 2026-27. The formats vary: dates appear as "9 August 2025", "18.09.2026" or "18.09.2026 to 19.09.2026". Venues are written in different ways.

**Ingestion (on upload)**
1. Extract the text with pypdf.
2. **Structured extraction.** The LLM fills in a JSON schema: title, event type, department, venue(s), dates, times, audience, expected and actual count, resource persons, topics and rating. Venues are normalised through `venue_aliases`, and dates and times are parsed into ISO format. The result goes into `past_events`. A circular and a report with the same title and dates are merged into one event.
3. **Series key.** A normalised title with years, phases and numbers removed groups recurring events. For example, "KIOT In-house Hackathon 2024", "…2025" and "…2026" all become the series `kiot-in-house-hackathon`. The same works for "Model Practical Examinations", "CodeSprint", "Admission Counselling" and "Placement Training Phase N".
4. **Chunk and embed.** The documents are short, so each one becomes one chunk plus a header line with its metadata. Each chunk gets an embedding (nomic-embed-text) and an FTS5 entry.

**Retrieval** is hybrid. It runs FTS5 BM25 and vector cosine search, merges the results with reciprocal-rank fusion, then filters with metadata from `past_events` (venue, event type, date window). Results always carry citations (document reference number and file), and the UI shows them as links to the PDF.

**What RAG is used for**
- "Where have Gen-AI workshops been held before, and how many came?" leads to a venue recommendation backed by evidence.
- **Recurring-event warnings.** A booking of venue V on date D triggers a warning if a series has happened at V within ±14 days of the same day of the year in 2 or more previous years. Examples are model practical exams in the CC labs and the hackathon in the COEs in mid-September. The warning names the series, lists the past dates with citations, and suggests alternative venues.
- **Approver briefings** (see §11).

**Evaluation:** a set of about 25 hand-written questions with the expected events. The targets are recall@5 of at least 0.9 and 100% of answers having citations.

---

## 10. MCP tool layer (mapped to roles)

Each tool declares the roles that can use it. The MCP server lists **only the tools allowed for the caller's roles**. The service layer checks permissions again on every call, including ownership checks such as "own venue" and "own booking".

| Tool | Kind | Roles |
|---|---|---|
| `list_venues(filters)` | read | all, including students |
| `get_venue(venue)` (equipment, software, status) | read | all |
| `check_availability(venue?, date_range, time_range?, min_capacity?, needs[])` | read | all |
| `find_free_venues(date, start, end, capacity, needs[], type?)` | read | all |
| `get_timetable(section? or venue?)` | read | all |
| `search_past_events(query, filters)` (RAG) | read | staff roles |
| `recommend_venues(event_details)` (ranked, with reasons and warnings) | read | faculty+ |
| `check_clashes(venue, start, end)` (hard clashes, class clashes, recurring warnings, waitlist depth) | read | faculty+ |
| `draft_booking(details)` (makes a draft and returns a link to the prefilled form) | draft | faculty, in-charge, HOD, director |
| `list_my_bookings()` | read | faculty+ |
| `propose_cancel(booking)` / `propose_reschedule(booking, new_slot)` | proposal | owner |
| `join_waitlist(draft)` | proposal | faculty+ |
| `list_pending_approvals()` | read | in-charge, HOD, director |
| `assess_request(booking)` (briefing for approvers) | read | in-charge, HOD, director |
| `propose_decision(booking, approve or reject, comment)` | proposal | in-charge (own venues), HOD, director |
| `suggest_relocation(slot, date)` | read | HOD, director |
| `update_equipment_status(item, status, note)` | proposal | technician (own labs), in-charge (own venues), director |
| `update_venue(venue, fields)` / `set_venue_status(...)` | proposal | in-charge (own venues), director |
| `create_venue(...)` | proposal | director |
| `parse_timetable(upload)` (returns a preview) | read | OA, HOD, director |
| `ingest_document(upload)` | proposal | OA, HOD, director |
| `utilisation_report(scope, period)` | read | in-charge, HOD, director |

A **proposal** tool returns a confirmation card, such as "Cancel booking BK-0142 (Hackathon, COE1, 18 Sep)? [Confirm] [Dismiss]". The write only happens when the user clicks. That click goes through the normal REST endpoint and is logged in `audit_log` with `via=agent`.

---

## 11. Agent design

- **Loop:** a small tool-calling loop of about 200 lines, with no heavy framework. It sends the system prompt, history and the MCP tool list to the LLM, then runs any tool calls through the MCP client and repeats, up to 8 steps. The final answer is streamed over SSE.
- **System prompt** includes the user's name, roles and owned venues, today's date and the current term. It sets these rules:
  - Never guess availability. Always call a tool for it.
  - Cite documents when making claims about history.
  - Use only draft or proposal tools for changes.
  - Ask a follow-up question when key details are missing, such as date, time, headcount or needs.
- **Booking assistance flow:** gather the details, call `recommend_venues` (which runs SQL filters, scoring, RAG evidence and clash checks), show the top 3 with reasons and warnings, call `draft_booking` for the one the user picks, then let the user review and submit the prefilled form.
- **Recommendation score:** first filter out venues that are unavailable, too small or missing required needs. Then rank on:
  - capacity fit (penalise more than 2.5 times oversize)
  - venue type suitability (hands-on goes to a lab or COE, a talk goes to a seminar hall)
  - past use for similar events (RAG)
  - recurring-event penalty
  - department ownership
- **Approver briefing (`assess_request`)** returns facts and recommends approve or reject with reasons:
  - any clashes or displacement needed
  - waitlist depth
  - similar past events at this venue, with their attendance compared to capacity
  - recurring-series warnings
  - the requester's recent no-show or cancellation pattern, if any
- **Students:** the same agent with read-only tools only. There is no login and nothing is saved on the server. The current chat is kept in the browser only and is rate-limited by IP.
- **Provider switch:** a dropdown in the chat header chooses Groq or Ollama and the model, for each user and each conversation. The Settings page (Director only) holds the default provider, the models, the Groq key (with `.env` as the fallback), extra named keys and the Ollama URL. There is a "Test connection" button.

---

## 12. Frontend

- **Svelte 5 + SvelteKit** (built as a static SPA) and Tailwind. Font size is 16px or larger. Spacing is generous, with about 24px card padding. Contrast meets WCAG AA in both themes.
- **Light and dark mode** with a toggle in the top bar. It follows the system setting by default and the choice is saved in localStorage.
- **Layout:**
  - On screens 1280px and wider, the chat panel is docked on the right at about 400px wide, can be closed, and the choice is remembered. Main content reflows next to it.
  - On tablets and phones, the chat opens from a floating button as a full-height sheet.
  - The chat header has a history dropdown (searchable, with rename and delete), a new-chat button and the provider/model picker.
- **Pages:**
  - Availability: grid of venues by day and time, filters, works without login
  - Venue detail
  - Book: form with live clash checks and recommendations
  - My bookings: reschedule, cancel, waitlist position
  - Approvals: queue plus AI briefing
  - Timetables: upload, review grid, commit
  - Documents: upload, list of extracted events, re-run extraction
  - Reports
  - Venues admin
  - Settings
  - Notifications drawer
- **Chat-to-UI handoff:** a draft booking shows up in the chat as a card with a "Review & submit" button that opens the prefilled form. A proposal shows up as a Confirm/Dismiss card.

---

## 13. Reports

- **Utilisation:** per venue and period, the share of available hours that were booked or used by classes, with a split of class time versus events.
- Events by type, by department and by month.
- Approval turnaround time.
- Waitlist conversions.
- Equipment faults.
- Export to CSV. Charts are drawn in the browser.

---

## 14. Repo layout

```
agentic_venue_booker/
├─ backend/
│  ├─ app/
│  │  ├─ main.py  config.py  deps.py
│  │  ├─ db/ (models.py, session.py, migrations/)
│  │  ├─ auth/  permissions.py
│  │  ├─ services/ (availability, bookings, approvals, waitlist, timetables,
│  │  │            venues, documents, rag, recommend, reports, notifications)
│  │  ├─ api/   (REST routers)
│  │  ├─ mcp_server/ (tools.py, server.py)
│  │  ├─ agent/ (loop.py, llm_gateway.py, prompts.py)
│  │  └─ ingest/ (timetable_parser.py, doc_extractor.py, embed.py)
│  ├─ seed/ (venues.yaml, software.yaml, users_from_excel.py)
│  └─ tests/ (unit, integration, eval/)
├─ frontend/ (SvelteKit app)
├─ data/mock/ (timetables/, circulars/, reports/, faculty.xlsx, lab_slots_truth.csv)
├─ docs/PLAN.md
├─ .env.example   README.md   .github/workflows/ci.yml
```

Your mock files are copied into `data/mock/` in the repo, so tests and CI can use them. The originals in your folder are not touched.

---

## 15. Phased build plan

Each phase is one or more PRs. Each has tests and a demo checklist you can try on your laptop before merging.

| Phase | Scope | Tests and exit criteria |
|---|---|---|
| **0. Scaffold** | repo, CI, FastAPI and SvelteKit skeleton, Tailwind theme with light/dark toggle, layout with the empty docked chat panel, mock login, seeded users (from the Excel sheet), roles and venues | CI green; logging in as `swvcse`, `hod.cse`, `dirim` and `cseoa` shows the right menu for each role; the app works on a phone screen |
| **1. Venues and availability** | venue and equipment views and editing (Director, in-charge, technician rules), status periods, seasonal rules, public availability grid for students | permission matrix tests (every role × every action); availability unit tests |
| **2. Timetable ingestion** | PDF parser, review grid, commit, conflict detection; timetable slots shown in the availability grid | **parser matches `lab_slots_truth.csv` 100%**; re-upload replaces rows; a deliberate conflict is flagged |
| **3. Bookings workflow** | booking form, multi-day events, approval chain, cancel and reschedule, waitlist with 24 h offers, class displacement with HOD approval and relocation suggestions, in-app notifications | state-machine tests for every transition; waitlist promotion and expiry tests; Playwright test: faculty books, in-charge approves, HOD approves, faculty cancels, waitlisted user gets the offer |
| **4. Documents and RAG** | upload, extraction into `past_events`, venue alias handling, series keys, hybrid search, recurring-event warnings wired into clash checks, past-events browser | extraction accuracy on 20 hand-checked documents (venue and dates at least 95% right); RAG eval recall@5 of at least 0.9; hackathon-in-COEs-in-September warning fires |
| **5. LLM, MCP and agent** | LLM gateway (Groq/Ollama), Settings page and keys, MCP server with role-filtered tools, agent loop, chat panel with streaming, history and confirmation cards, timetable upload through chat | MCP tool-listing test for each role (a student sees only read-only tools); agent tests with a scripted fake LLM; a live smoke-test set of about 15 prompts on Groq and Ollama |
| **6. Reports and polish** | utilisation and other reports, CSV export, accessibility pass, empty/error states, README and demo script | Lighthouse accessibility score of at least 95; complete demo script run end to end |

**Demo scenarios built up through the phases:**
1. A student asks "Which labs have Power BI free tomorrow afternoon?"
2. Walter asks the assistant for a venue for a 2-day Gen-AI workshop for 55 students. It recommends CC1 with citations, warns about model practicals that week, and drafts the form.
3. The HOD gets a briefing on a request that would displace CSE III-B's ML lab, and the system suggests relocating the class to CC7.
4. A booking is cancelled and the waitlisted request gets an offer.

---

## 16. Dev workflow and laptop sync

- I push each phase as a branch and open a PR to `main` on GitHub. You review and merge.
- **After each merge,** I start a session on your laptop that runs the following in `D:\projects\venue_booking_agent_v2`:
  - `git pull`
  - `pip install -r backend/requirements.txt` (in `.venv`)
  - `npm install` (in `frontend`)
  - `alembic upgrade head`
  - a quick test run

  You may get an approval prompt on your laptop the first time.
- **First-time setup:** because the folder already has files, I'll set it up with `git init`, add the remote, then fetch and check out `main`. Your existing mock files stay where they are as untracked files and are ignored by `.gitignore`.
- **One-time prerequisites:** Ollama with `nomic-embed-text` and `qwen3.5:4b` (both already installed), and your Groq key in `backend/.env`.
- **Running Ollama on the laptop (8 GB RAM, CPU only):**
  - Groq stays the default. Ollama is the offline or privacy option and will be slower, likely several seconds per reply.
  - When Ollama is selected, the agent sends a trimmed setup: shorter system prompt, only the tools for the user's role, and the last few turns of history. The context window is capped at about 8k tokens (`num_ctx`), so the model fits in memory alongside the browser and backend.
  - Embedding the ~280 documents with `nomic-embed-text` is a one-time job of a few minutes. After that, only new uploads are embedded.
  - The Settings page lists the models installed in Ollama, so you can switch to `qwen3.5:latest` on a stronger machine.

---

## 17. Assumptions to confirm

1. The college runs Monday to Friday (the mock timetables have no Saturday). Events may be booked on Saturdays, which have no classes.
2. Bookable hours are 08:00 to 18:00 on weekdays and 08:00 to 17:00 on Saturdays. Hackathons may run overnight if the in-charge approves.
3. "CSE venues", which need HOD approval, are CC1 to CC12, PG Lab, IoT Lab, COE1 to COE4 and CSE PG Seminar Hall. A, D, E and MBA halls need only their in-charge.
4. Class strength defaults to 60 per section (30 per batch). This is used for relocation capacity checks.
5. Professional elective and guest-lecture use of seminar halls is entered as normal bookings with type "professional elective class" or "guest lecture". This can be done for a whole term as a recurring booking.
6. Notifications are in-app only. Email is out of scope.
7. Lab technicians are added later. The role and permissions exist from Phase 0.
