# Email for student requests

Students have no login, so each student request gives one contact email. That address gets the
tracking number when the request is sent, then an email at each step: the faculty guide's decision
on each student, the in-charge's and HOD's approvals, the final confirmation or rejection, and a
cancellation.

The app sends mail over plain SMTP, so any provider works. Until a mail server is set up, every
email is saved as an `.eml` file in `backend/storage/outbox/` instead of being sent (open one in
Outlook, Thunderbird or a text editor). Nothing else changes, so you can test the whole flow
without sending real mail. The tests never send mail either.

## Set up Gmail (about 5 minutes)

Use a separate account for the app, not your personal one, for example a new Gmail account such
as `kiot.venuebooking@gmail.com`, or a college Google Workspace account if the admin agrees.
Gmail allows about 500 emails a day from a normal account (about 2,000 from Workspace). Each
request sends 3 to 5 emails, so that is plenty for one department.

1. **Sign in** to that account in a browser.
2. **Turn on 2-Step Verification.** Go to <https://myaccount.google.com/security>, open
   *2-Step Verification* and follow the steps (a phone number is enough). Google only offers app
   passwords once this is on.
3. **Create an app password.** Go to <https://myaccount.google.com/apppasswords>, type a name such
   as `Venue booking`, and press *Create*. Google shows a 16-letter password like
   `abcd efgh ijkl mnop`. Copy it now: it is shown only once. (If the page says the setting isn't
   available, 2-Step Verification is off, or a Workspace admin has turned app passwords off.)
4. **Put it into the app.** Log in as the Director (`dirim@kiot.ac.in`), open **Settings**, and
   fill in **Email for student requests**:

   | Field | Value |
   |---|---|
   | SMTP server | `smtp.gmail.com` |
   | Port | `587` |
   | Username | the Gmail address |
   | Password | the 16-letter app password (spaces are fine) |
   | From address | leave empty (Gmail sends from the username anyway) |

   Press **Save email settings**, then enter your own address under **Send a test email to** and
   press **Send test**. You should get the test email within a minute.

   Instead of the Settings page you can put the same values in `backend/.env` (handy if you
   reset the database often): `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`,
   `SMTP_USER=...`, `SMTP_PASSWORD=...`. Values saved on the Settings page win over `.env`.

5. **Set the link address.** Emails link to the tracking page at `PUBLIC_URL` in
   `backend/.env` (default `http://localhost:8080`, the built app served by `uvicorn --port 8080`). When students open the app at another
   address, for example `http://192.168.1.20:8000`, set `PUBLIC_URL` to that and restart the
   backend.

### If the test fails

- *Username and Password not accepted (535)*: the app password is wrong, or it was made for a
  different account. Make a new one and paste it again.
- *Timed out* or *connection refused*: the network blocks port 587. Try port `465` (the app
  switches to SSL for that port), or test from another network.
- Emails arrive in spam: ask students to mark the first one "Not spam". A college Workspace
  account is less likely to land in spam than a new Gmail account.

## Only college addresses

To accept only `@kiot.ac.in` contact emails, set this in `backend/.env` and restart the backend:

```
STUDENT_EMAIL_DOMAIN=kiot.ac.in
```

Leave it empty (the default) to accept any address while testing. The Settings page shows which
rule is active.

## Limits against misuse

- One contact email can send at most 3 requests a day.
- One computer (IP address) can send at most 5 requests an hour and 60 tracking lookups every
  10 minutes.
- Tracking numbers are random (like `ST-7K3P-9QXA`), so nobody can guess other groups' requests.
