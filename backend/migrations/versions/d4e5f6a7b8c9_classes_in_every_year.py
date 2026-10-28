"""classes in every year

Revision ID: d4e5f6a7b8c9
Revises: c60f443ade16
Create Date: 2026-10-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c60f443ade16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

YEARS = ("I", "II", "III", "IV")


def upgrade() -> None:
    """Add each department's sections in every year, so first years can be named on a request."""
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT dept, year, section FROM class_sections")).all()
    have = {tuple(r) for r in rows}
    letters: dict[str, set[str]] = {}
    for dept, _, section in rows:
        letters.setdefault(dept, set()).add(section)
    for dept, secs in letters.items():
        for year in YEARS:
            for section in sorted(secs):
                if (dept, year, section) not in have:
                    conn.execute(
                        sa.text(
                            "INSERT INTO class_sections (dept, year, section, strength) "
                            "VALUES (:d, :y, :s, 60)"
                        ),
                        {"d": dept, "y": year, "s": section},
                    )


def downgrade() -> None:
    """Remove the added classes that no timetable or request uses."""
    op.execute(
        "DELETE FROM class_sections WHERE advisor IS NULL "
        "AND id NOT IN (SELECT section_id FROM timetable_slots) "
        "AND id NOT IN (SELECT section_id FROM timetable_uploads WHERE section_id IS NOT NULL) "
        "AND id NOT IN (SELECT section_id FROM booking_students WHERE section_id IS NOT NULL)"
    )
