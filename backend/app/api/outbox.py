from fastapi import BackgroundTasks, Request

from app.db import session_for
from app.services import mailer


def _send(app) -> None:
    with session_for(app) as db:
        mailer.send_queued(db)


def send_mail_after(request: Request, tasks: BackgroundTasks) -> None:
    """Send queued emails once the response has gone out (the change is committed by then)."""
    tasks.add_task(_send, request.app)
