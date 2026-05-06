"""add role_id to ctfs

Revision ID: 0002_ctf_role_id
Revises: 0001_challenge_channel_id
Create Date: 2026-05-06

No-op on fresh databases where ``ctfs.role_id`` was already created via
``Base.metadata.create_all``.

"""
from alembic import op
import sqlalchemy as sa


revision = "0002_ctf_role_id"
down_revision = "0001_challenge_channel_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ctfs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("ctfs")}
    if "role_id" in cols:
        return
    with op.batch_alter_table("ctfs") as batch:
        batch.add_column(sa.Column("role_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ctfs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("ctfs")}
    if "role_id" not in cols:
        return
    with op.batch_alter_table("ctfs") as batch:
        batch.drop_column("role_id")
