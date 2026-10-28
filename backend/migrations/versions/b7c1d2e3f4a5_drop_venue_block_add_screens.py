"""drop venue block; projector and screen in every venue but IOTLAB, CC9 and CC10

Revision ID: b7c1d2e3f4a5
Revises: 900275836fed
Create Date: 2026-10-28 06:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c1d2e3f4a5'
down_revision: Union[str, Sequence[str], None] = '900275836fed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NO_PROJECTOR = ('IOTLAB', 'CC9', 'CC10')


def upgrade() -> None:
    with op.batch_alter_table('venues') as batch:
        batch.drop_column('block')

    # Existing databases: the same equipment the seed now gives new ones.
    conn = op.get_bind()
    venues = conn.execute(sa.text('SELECT id, code FROM venues')).all()
    for venue_id, code in venues:
        names = {
            n.lower()
            for (n,) in conn.execute(
                sa.text('SELECT name FROM equipment WHERE venue_id = :v'), {'v': venue_id}
            )
        }
        if code in NO_PROJECTOR:
            conn.execute(
                sa.text(
                    "DELETE FROM equipment WHERE venue_id = :v "
                    "AND lower(name) IN ('projector', 'projection screen')"
                ),
                {'v': venue_id},
            )
            continue
        for name in ('Projector', 'Projection screen'):
            if name.lower() not in names:
                conn.execute(
                    sa.text(
                        "INSERT INTO equipment (venue_id, name, category, quantity, status, "
                        "updated_at) VALUES (:v, :n, 'av', 1, 'working', CURRENT_TIMESTAMP)"
                    ),
                    {'v': venue_id, 'n': name},
                )


def downgrade() -> None:
    with op.batch_alter_table('venues') as batch:
        batch.add_column(sa.Column('block', sa.String(length=30), nullable=True))
