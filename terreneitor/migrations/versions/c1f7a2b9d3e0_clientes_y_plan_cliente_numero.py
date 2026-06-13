"""Catálogo de clientes + cliente/numero en planes_trabajo

Revision ID: c1f7a2b9d3e0
Revises: e96b12de3437
Create Date: 2026-06-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1f7a2b9d3e0"
down_revision: Union[str, Sequence[str], None] = "e96b12de3437"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, col: str) -> bool:
    return col in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    """Upgrade schema (idempotente: dev ya aplicó esto a mano)."""
    bind = op.get_bind()
    if not _has_table(bind, "clientes"):
        op.create_table(
            "clientes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nombre", sa.String(), nullable=False, unique=True),
        )
    if not _has_column(bind, "planes_trabajo", "cliente"):
        op.add_column(
            "planes_trabajo", sa.Column("cliente", sa.String(), nullable=True)
        )
    if not _has_column(bind, "planes_trabajo", "numero"):
        op.add_column(
            "planes_trabajo", sa.Column("numero", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("planes_trabajo", "numero")
    op.drop_column("planes_trabajo", "cliente")
    op.drop_table("clientes")
