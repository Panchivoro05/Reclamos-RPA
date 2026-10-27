"""indice unico de reclamo abierto

Revision ID: 490e3789f476
Revises: f3b9438851ae
Create Date: 2026-10-27 04:50:27.112259+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "490e3789f476"
down_revision: str | None = "f3b9438851ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_reclamos_abierto_pedido_tipo",
        "reclamos",
        ["pedido_id", "tipo"],
        unique=True,
        postgresql_where=sa.text("estado NOT IN ('resuelto', 'cerrado')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reclamos_abierto_pedido_tipo",
        table_name="reclamos",
        postgresql_where=sa.text("estado NOT IN ('resuelto', 'cerrado')"),
    )
