import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import User
from app.services import reports as svc

router = APIRouter(prefix="/api/reports", tags=["reports"])


def reporter(user: User = Depends(get_current_user)) -> User:
    if not svc.can_report(user):
        raise HTTPException(403, "You don't have access to reports")
    return user


def _period(db: Session, start: date | None, end: date | None) -> tuple[date, date, str | None]:
    if start and end:
        return start, end, None
    d_start, d_end, label = svc.default_period(db, date.today())
    return start or d_start, end or d_end, label if not (start or end) else None


@router.get("/summary")
def summary(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(reporter),
) -> dict:
    start, end, label = _period(db, start, end)
    try:
        return {"period_label": label, **svc.summary(db, user, start, end)}
    except svc.ReportError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/{section}.csv")
def export_csv(
    section: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(reporter),
) -> Response:
    if section not in svc.CSV_COLUMNS:
        raise HTTPException(404, "No such report")
    start, end, _ = _period(db, start, end)
    try:
        rows = svc.section_rows(db, user, section, start, end)
    except svc.ReportError as e:
        raise HTTPException(422, str(e)) from e
    columns = svc.CSV_COLUMNS[section]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([heading for _, heading in columns])
    for row in rows:
        writer.writerow(
            ["yes" if row[k] is True else "no" if row[k] is False else row[k] for k, _ in columns]
        )
    filename = f"{section}-{start.isoformat()}-to-{end.isoformat()}.csv"
    # A byte-order mark so Excel opens the file as UTF-8 (names and titles use non-ASCII quotes).
    return Response(
        "﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
