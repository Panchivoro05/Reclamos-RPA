"""reglas de resolucion y ejecuciones del bot

Revision ID: 3d347c3006ec
Revises: 490e3789f476
Create Date: 2026-11-19 00:11:44.360317+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3d347c3006ec"
down_revision: str | None = "490e3789f476"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# tipo_reclamo ya existe (esquema inicial). Los dos enums nuevos se crean una sola vez:
# solucion_compensacion lo usan dos tablas.
TIPO_RECLAMO = postgresql.ENUM(name="tipo_reclamo", create_type=False)
SOLUCION_COMPENSACION = postgresql.ENUM(
    "reenvio",
    "reembolso_parcial",
    "reembolso_total",
    "cupon",
    name="solucion_compensacion",
    create_type=False,
)
BASE_MONTO = postgresql.ENUM(
    "ninguno",
    "items_afectados",
    "fijo",
    "porcentaje_total",
    "total_pedido",
    name="base_monto",
    create_type=False,
)

# Valores iniciales (acordados en la fase 3). Se cambian con SQL o, en la fase 6, desde el panel.
REGLAS_INICIALES = [
    # Se reenvía el producto correcto: no hay dinero de por medio.
    {
        "tipo": "producto_equivocado",
        "solucion": "reenvio",
        "base_monto": "ninguno",
        "valor": 0,
        "requiere_foto": True,
    },
    # Se devuelve lo que faltó.
    {
        "tipo": "pedido_incompleto",
        "solucion": "reembolso_parcial",
        "base_monto": "items_afectados",
        "valor": 0,
        "requiere_foto": False,
    },
    # Se devuelve lo que llegó en mal estado.
    {
        "tipo": "mal_estado",
        "solucion": "reembolso_parcial",
        "base_monto": "items_afectados",
        "valor": 0,
        "requiere_foto": True,
    },
    # Cupón fijo de S/ 10 para el próximo pedido.
    {
        "tipo": "demora",
        "solucion": "cupon",
        "base_monto": "fijo",
        "valor": 10,
        "requiere_foto": False,
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    SOLUCION_COMPENSACION.create(bind, checkfirst=True)
    BASE_MONTO.create(bind, checkfirst=True)

    reglas = op.create_table(
        "reglas_resolucion",
        sa.Column("tipo", TIPO_RECLAMO, nullable=False),
        sa.Column("solucion", SOLUCION_COMPENSACION, nullable=False),
        sa.Column("base_monto", BASE_MONTO, nullable=False),
        sa.Column("valor", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("requiere_foto", sa.Boolean(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tipo", name=op.f("pk_reglas_resolucion")),
    )
    politica = op.create_table(
        "politica_antifraude",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("monto_maximo_automatico", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("max_reclamos_periodo", sa.Integer(), nullable=False),
        sa.Column("periodo_dias", sa.Integer(), nullable=False),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_politica_antifraude_una_sola_fila")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_politica_antifraude")),
    )
    op.bulk_insert(reglas, REGLAS_INICIALES)
    op.bulk_insert(
        politica,
        [{"id": 1, "monto_maximo_automatico": 40, "max_reclamos_periodo": 3, "periodo_dias": 30}],
    )

    op.create_table(
        "ejecuciones_bot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reclamo_id", sa.Integer(), nullable=False),
        sa.Column("intento", sa.Integer(), nullable=False),
        sa.Column("exito", sa.Boolean(), nullable=False),
        sa.Column("codigo_error", sa.String(length=40), nullable=True),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("numero_operacion", sa.String(length=20), nullable=True),
        sa.Column("duracion_s", sa.Numeric(precision=8, scale=1), nullable=True),
        sa.Column("evidencia", sa.String(length=255), nullable=True),
        sa.Column("video", sa.String(length=255), nullable=True),
        sa.Column("pasos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["reclamo_id"],
            ["reclamos.id"],
            name=op.f("fk_ejecuciones_bot_reclamo_id_reclamos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ejecuciones_bot")),
    )
    op.create_index(
        op.f("ix_ejecuciones_bot_reclamo_id"), "ejecuciones_bot", ["reclamo_id"], unique=False
    )

    op.add_column("reclamos", sa.Column("solucion", SOLUCION_COMPENSACION, nullable=True))
    op.add_column(
        "reclamos",
        sa.Column("monto_compensacion", sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.add_column("reclamos", sa.Column("numero_operacion", sa.String(length=20), nullable=True))
    op.add_column("reclamos", sa.Column("motivo_escalamiento", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reclamos", "motivo_escalamiento")
    op.drop_column("reclamos", "numero_operacion")
    op.drop_column("reclamos", "monto_compensacion")
    op.drop_column("reclamos", "solucion")
    op.drop_index(op.f("ix_ejecuciones_bot_reclamo_id"), table_name="ejecuciones_bot")
    op.drop_table("ejecuciones_bot")
    op.drop_table("politica_antifraude")
    op.drop_table("reglas_resolucion")
    bind = op.get_bind()
    BASE_MONTO.drop(bind, checkfirst=True)
    SOLUCION_COMPENSACION.drop(bind, checkfirst=True)
