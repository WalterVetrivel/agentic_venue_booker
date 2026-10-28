"""Email for student requests (students have no login, so this is how they hear back).

Emails are queued in `outbox_emails` with the change that caused them and sent after the
request commits, so a slow or broken mail server never holds up a booking. With no SMTP server
set up, each email is saved as an .eml file under storage/outbox instead.
"""

import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting, OutboxEmail

KEYS = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from")


@dataclass
class MailSettings:
    host: str
    port: int
    user: str
    password: str
    from_addr: str
    password_source: str  # settings | env | none

    @property
    def configured(self) -> bool:
        return bool(self.host)


def mail_settings(db: Session) -> MailSettings:
    env = get_settings()
    own = {r.key: r.value for r in db.scalars(select(AppSetting).where(AppSetting.key.in_(KEYS)))}
    password = own.get("smtp_password") or env.smtp_password
    source = "settings" if own.get("smtp_password") else "env" if env.smtp_password else "none"
    user = own.get("smtp_user") or env.smtp_user
    try:
        port = int(own.get("smtp_port") or env.smtp_port)
    except ValueError:
        port = 587
    return MailSettings(
        host=own.get("smtp_host") or env.smtp_host,
        port=port,
        user=user,
        password=password,
        from_addr=own.get("smtp_from") or env.smtp_from or user,
        password_source=source,
    )


def save(db: Session, changes: dict[str, str | None]) -> None:
    """Store settings; an empty value removes the setting so the .env value applies again."""
    for key, value in changes.items():
        if key not in KEYS:
            raise KeyError(key)
        row = db.get(AppSetting, key)
        value = str(value or "").strip()
        if not value:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value


def build(cfg: MailSettings, to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"KIOT Venue Booking <{cfg.from_addr or 'noreply@localhost'}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="venue-booker")
    msg.set_content(body)
    return msg


def smtp_send(cfg: MailSettings, msg: EmailMessage) -> None:
    context = ssl.create_default_context()
    if cfg.port == 465:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, context=context, timeout=20) as smtp:
            if cfg.user:
                smtp.login(cfg.user, cfg.password)
            smtp.send_message(msg)
        return
    with smtplib.SMTP(cfg.host, cfg.port, timeout=20) as smtp:
        smtp.starttls(context=context)
        if cfg.user:
            smtp.login(cfg.user, cfg.password)
        smtp.send_message(msg)


def save_to_outbox(msg: EmailMessage, email_id: int) -> None:
    folder = get_settings().outbox_dir
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{datetime.now():%Y%m%d-%H%M%S}-{email_id}.eml").write_bytes(msg.as_bytes())


# Tests swap this for a function that records what would be sent.
Transport = Callable[[MailSettings, EmailMessage, int], str]


def _default_transport(cfg: MailSettings, msg: EmailMessage, email_id: int) -> str:
    if not cfg.configured:
        save_to_outbox(msg, email_id)
        return "saved"
    smtp_send(cfg, msg)
    return "sent"


_transport: Transport = _default_transport


def set_transport(transport: Transport | None) -> None:
    global _transport
    _transport = transport or _default_transport


def queue(db: Session, to: str, subject: str, body: str, booking_id: int | None = None) -> None:
    db.add(OutboxEmail(to=to, subject=subject, body=body, booking_id=booking_id))


def send_queued(db: Session, limit: int = 50) -> int:
    """Send what is waiting. Returns how many went out (or were saved)."""
    waiting = db.scalars(
        select(OutboxEmail).where(OutboxEmail.status == "queued").order_by(OutboxEmail.id)
    ).all()[:limit]
    if not waiting:
        return 0
    cfg = mail_settings(db)
    done = 0
    for email in waiting:
        try:
            msg = build(cfg, email.to, email.subject, email.body)
            email.status = _transport(cfg, msg, email.id)
            email.sent_at = datetime.now()
            email.error = None
            done += 1
        except (OSError, smtplib.SMTPException) as e:
            email.status = "failed"
            email.error = str(e)[:500]
        db.commit()
    return done


def send_test(db: Session, to: str) -> tuple[bool, str]:
    cfg = mail_settings(db)
    msg = build(
        cfg,
        to,
        "Test email from KIOT Venue Booking",
        "This is a test. If you can read it, student requests will get their emails.",
    )
    try:
        status = _transport(cfg, msg, 0)
    except (OSError, smtplib.SMTPException) as e:
        return False, f"Couldn't send: {e}"
    if status == "saved":
        return True, "No mail server is set up, so the email was saved to storage/outbox."
    return True, f"Sent to {to}."
