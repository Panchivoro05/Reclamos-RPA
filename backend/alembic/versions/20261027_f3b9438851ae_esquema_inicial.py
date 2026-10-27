"""esquema inicial

Revision ID: f3b9438851ae
Revises:
Create Date: 2026-10-27 04:40:55.203736+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3b9438851ae"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tipos enum de PostgreSQL. Se crean una sola vez (estado_reclamo lo usan dos tablas)
# y por eso las columnas los referencian con create_type=False.
CATEGORIA_PRODUCTO = postgresql.ENUM(
    "hamburguesa",
    "combo",
    "acompañamiento",
    "bebida",
    "postre",
    name="categoria_producto",
    create_type=False,
)
ESTADO_PEDIDO = postgresql.ENUM(
    "en_preparacion", "en_camino", "entregado", "cancelado", name="estado_pedido", create_type=False
)
TIPO_RECLAMO = postgresql.ENUM(
    "producto_equivocado",
    "pedido_incompleto",
    "mal_estado",
    "demora",
    name="tipo_reclamo",
    create_type=False,
)
ESTADO_RECLAMO = postgresql.ENUM(
    "recibido",
    "en_validacion",
    "validado",
    "en_resolucion",
    "resuelto",
    "cerrado",
    "escalado",
    name="estado_reclamo",
    create_type=False,
)
ACTOR_EVENTO = postgresql.ENUM(
    "cliente", "sistema", "bot", "ia", "agente", name="actor_evento", create_type=False
)

ENUMS = (CATEGORIA_PRODUCTO, ESTADO_PEDIDO, TIPO_RECLAMO, ESTADO_RECLAMO, ACTOR_EVENTO)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)
    # Correlativo del código visible RC-AAAA-NNNNNN (ver app/models/reclamo.py).
    op.execute(sa.schema.CreateSequence(sa.Sequence("reclamo_codigo_seq")))

    op.create_table(
        "clientes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("firebase_uid", sa.String(length=128), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("telefono_whatsapp", sa.String(length=20), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clientes")),
        sa.UniqueConstraint("email", name=op.f("uq_clientes_email")),
        sa.UniqueConstraint("firebase_uid", name=op.f("uq_clientes_firebase_uid")),
    )
    op.create_table(
        "productos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column(
            "categoria",
            CATEGORIA_PRODUCTO,
            nullable=False,
        ),
        sa.Column("precio", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_productos")),
        sa.UniqueConstraint("nombre", name=op.f("uq_productos_nombre")),
    )
    op.create_table(
        "pedidos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            ESTADO_PEDIDO,
            nullable=False,
        ),
        sa.Column("total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("direccion_entrega", sa.String(length=255), nullable=False),
        sa.Column("local", sa.String(length=120), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("entregado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name=op.f("fk_pedidos_cliente_id_clientes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedidos")),
        sa.UniqueConstraint("codigo", name=op.f("uq_pedidos_codigo")),
    )
    op.create_index(op.f("ix_pedidos_cliente_id"), "pedidos", ["cliente_id"], unique=False)
    op.create_table(
        "pedido_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pedido_id", sa.Integer(), nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["pedidos.id"],
            name=op.f("fk_pedido_items_pedido_id_pedidos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["producto_id"], ["productos.id"], name=op.f("fk_pedido_items_producto_id_productos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido_items")),
    )
    op.create_index(op.f("ix_pedido_items_pedido_id"), "pedido_items", ["pedido_id"], unique=False)
    op.create_table(
        "reclamos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("pedido_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            TIPO_RECLAMO,
            nullable=False,
        ),
        sa.Column(
            "estado",
            ESTADO_RECLAMO,
            nullable=False,
        ),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("foto_ruta", sa.String(length=255), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name=op.f("fk_reclamos_cliente_id_clientes")
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"], ["pedidos.id"], name=op.f("fk_reclamos_pedido_id_pedidos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reclamos")),
        sa.UniqueConstraint("codigo", name=op.f("uq_reclamos_codigo")),
    )
    op.create_index(op.f("ix_reclamos_cliente_id"), "reclamos", ["cliente_id"], unique=False)
    op.create_index(op.f("ix_reclamos_pedido_id"), "reclamos", ["pedido_id"], unique=False)
    op.create_table(
        "reclamo_eventos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reclamo_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            ESTADO_RECLAMO,
            nullable=False,
        ),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column(
            "actor",
            ACTOR_EVENTO,
            nullable=False,
        ),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["reclamo_id"],
            ["reclamos.id"],
            name=op.f("fk_reclamo_eventos_reclamo_id_reclamos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reclamo_eventos")),
    )
    op.create_index(
        op.f("ix_reclamo_eventos_reclamo_id"), "reclamo_eventos", ["reclamo_id"], unique=False
    )
    op.create_table(
        "reclamo_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reclamo_id", sa.Integer(), nullable=False),
        sa.Column("pedido_item_id", sa.Integer(), nullable=False),
        sa.Column("cantidad_afectada", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pedido_item_id"],
            ["pedido_items.id"],
            name=op.f("fk_reclamo_items_pedido_item_id_pedido_items"),
        ),
        sa.ForeignKeyConstraint(
            ["reclamo_id"],
            ["reclamos.id"],
            name=op.f("fk_reclamo_items_reclamo_id_reclamos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reclamo_items")),
    )
    op.create_index(
        op.f("ix_reclamo_items_reclamo_id"), "reclamo_items", ["reclamo_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reclamo_items_reclamo_id"), table_name="reclamo_items")
    op.drop_table("reclamo_items")
    op.drop_index(op.f("ix_reclamo_eventos_reclamo_id"), table_name="reclamo_eventos")
    op.drop_table("reclamo_eventos")
    op.drop_index(op.f("ix_reclamos_pedido_id"), table_name="reclamos")
    op.drop_index(op.f("ix_reclamos_cliente_id"), table_name="reclamos")
    op.drop_table("reclamos")
    op.drop_index(op.f("ix_pedido_items_pedido_id"), table_name="pedido_items")
    op.drop_table("pedido_items")
    op.drop_index(op.f("ix_pedidos_cliente_id"), table_name="pedidos")
    op.drop_table("pedidos")
    op.drop_table("productos")
    op.drop_table("clientes")
    op.execute(sa.schema.DropSequence(sa.Sequence("reclamo_codigo_seq")))
    bind = op.get_bind()
    for enum in ENUMS:
        enum.drop(bind, checkfirst=True)
