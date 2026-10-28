"""Migrations must keep existing data (regression: batch-altering `venues` used to cascade-delete
equipment, aliases and rules because foreign keys were ON during the migration)."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parent.parent


def run(db_url: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", *args],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": db_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def counts(db_url: str) -> dict[str, int]:
    with create_engine(db_url).connect() as conn:
        return {
            t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
            for t in ("venues", "equipment", "venue_aliases", "seasonal_rules")
        }


def test_upgrading_keeps_existing_rows(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    run(url, "alembic", "upgrade", "a628f5085a64")  # the Phase 0 schema
    # Rows as Phase 0 would have them (raw SQL: today's models expect newer columns)
    with create_engine(url).begin() as conn:
        conn.execute(
            text(
                "INSERT INTO venues (id, code, name, type, capacity, byod, needs_hod_approval) "
                "VALUES (1, 'ASH', 'A Block Seminar Hall', 'seminar_hall', 100, 0, 0)"
            )
        )
        conn.execute(text("INSERT INTO venue_aliases (venue_id, alias) VALUES (1, 'A Block SH')"))
        conn.execute(
            text(
                "INSERT INTO equipment (venue_id, name, category, quantity, status) "
                "VALUES (1, 'Projector', 'av', 1, 'working')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO seasonal_rules (venue_id, start_month, end_month, kind, reason) "
                "VALUES (1, 3, 7, 'blocked', 'Admissions')"
            )
        )
    before = counts(url)
    assert before == {"venues": 1, "equipment": 1, "venue_aliases": 1, "seasonal_rules": 1}

    run(url, "alembic", "upgrade", "head")
    # Nothing lost; the hall gains the projection screen every venue now has.
    assert counts(url) == {**before, "equipment": 2}
