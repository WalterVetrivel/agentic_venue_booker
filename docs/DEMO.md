# Demo script

A walk through every feature, role by role, in about 20 minutes. Every step works without the
assistant; the assistant steps are marked 🤖.

## Before you start

```powershell
cd backend
.venv\Scripts\activate
python -m app.seed --reset --timetables --documents --bookings
uvicorn app.main:app
```

Build the frontend once (`cd frontend; npm run build`) and open http://127.0.0.1:8000. For the
🤖 steps, set a Groq key in **Settings** (as the Director) or `GROQ_API_KEY` in `backend/.env`.
Without one, `LLM_FAKE=1` gives a scripted assistant that still uses the real tools.

All logins use the password `password`. Use a private window per person if you want to switch
quickly.

## 1. A student, not logged in (2 min)

1. **Venues**: open **CC5**. Point out the capacity, the installed software (Power BI, Python…),
   the hardware and who is in charge.
2. **Availability**: pick tomorrow. Classes from the committed timetables show on the lab rows;
   bookings and closures show too. Switch to dark mode with the moon button.
3. 🤖 Ask: *"Is CC5 free tomorrow from 10 to 12?"* The assistant checks the timetable and gives
   the weekday with the date. Ask *"Book CC3 for me"*: it explains that you need to log in.

## 2. Faculty books a seminar hall (3 min)

Log in as `tkcse@kiot.ac.in`.

1. **Book a venue**: D Block Seminar Hall (DSH), a guest lecture for 150 people next week,
   10:00 to 13:00. The form checks the slot as you type: capacity, clashes, and a warning if a
   similar yearly event is usually held then. **Submit request**.
2. **My bookings** shows it waiting for the venue in-charge; the bell shows the notification.
3. Try the same hall and time again: the form offers **Join the waitlist** instead.
4. 🤖 Ask: *"Book COE1 next Tuesday 10:00 to 12:00 for a Python workshop, 30 students."* A draft
   card opens the booking form already filled in; nothing is booked until you submit it.
5. 🤖 Ask: *"Where were Gen-AI workshops held before?"* It searches the past circulars and
   reports and cites their reference numbers.

## 3. Booking a lab that has a class (2 min)

Still as faculty, book **CC1** on a weekday at a time the availability grid shows a class.
The form lists the class and offers, for each one, another free lab with the same software or
BYOD in the classroom. Pick one and submit. This request also needs the HOD, because a class
moves.

## 4. The in-charge and the HOD approve (3 min)

1. Log in as `sh.dblock@kiot.ac.in` (D Block hall in-charge). **Approvals** lists the guest
   lecture with notes worked out for you: capacity, clashes, short notice and anyone on the
   waitlist. Approve it.
2. Log in as `hod.cse@kiot.ac.in`. **Approvals** shows the CC1 request from step 3 (the class
   move needs the HOD). Approve it: the class moves on the timetable for that day only.
3. 🤖 As the HOD, ask *"What is waiting for my approval?"* and then *"Assess BK-…"* for a
   briefing. Approving from the assistant shows a card; nothing changes until you press it.
4. As the faculty member, cancel the guest lecture from **My bookings**. The person on the
   waitlist is offered the slot and has 24 hours to **Confirm the slot**.

## 5. Equipment (1 min)

Log in as `swvcse@kiot.ac.in` (CC10 in-charge). On **Venues › CC10**, mark the smart board
faulty. 🤖 Or ask *"Mark the smart board in CC10 as faulty"* and confirm the card; the audit log
records it as done through the assistant.

## 6. The OA uploads timetables and documents (3 min)

Log in as `cseoa@kiot.ac.in`.

1. **Timetables**: upload a PDF from `data/mock/timetables`. Review the lab sessions it read,
   fix any highlighted slot and commit. The sessions appear on the availability grid.
2. **Past events**: upload a circular and its report from `data/mock/circulars` and
   `data/mock/reports`. They are matched into one event with its date, venue and attendance.
3. 🤖 Drop a timetable PDF into the chat: it goes to review in the same way.

## 7. Reports (3 min)

1. Log in as `dirim@kiot.ac.in` (Director IM). **Reports** opens on the term so far for all
   venues: utilisation split into classes and events, events by month, type and department,
   approval turnaround per step, waitlist outcomes and equipment out of service.
2. Switch the utilisation chart to **Table**, choose **Last month**, and download a CSV; it
   opens in Excel.
3. Log in as `sh.dblock@kiot.ac.in`: the same page shows only D Block Seminar Hall. The HOD
   sees only CSE venues.
4. 🤖 As the Director, ask *"How busy were the labs this month?"* The assistant uses the report
   tool and links to the page for the same dates.

## 8. Settings and MCP (1 min)

As the Director, **Settings** sets the default model (Groq or Ollama), tests the connection and
creates an MCP token with a ready-made Claude Desktop config. The same tools, with the same
permissions, are then available in Claude Desktop.

## Checklist

- [ ] Student: venue details, availability, 🤖 availability question
- [ ] Faculty: booking, waitlist, 🤖 draft card, 🤖 past events search
- [ ] Class displacement with relocation or BYOD
- [ ] In-charge approval with notes, HOD approval, waitlist offer after a cancellation
- [ ] Equipment status, 🤖 proposal card
- [ ] OA: timetable upload and commit, circular and report upload
- [ ] Reports for Director, in-charge and HOD, CSV download, 🤖 report question
- [ ] Settings and MCP token
