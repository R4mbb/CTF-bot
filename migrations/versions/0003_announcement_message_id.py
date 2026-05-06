"""add announcement_message_id to ctfs

Revision ID: 0003_announcement_message_id
Revises: 0002_ctf_role_id
Create Date: 2026-05-06

"""
from alembic import op
import sqlalchemy as sa


revision = "0003_announcement_message_id"
down_revision = "0002_ctf_role_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ctfs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("ctfs")}
    if "announcement_message_id" in cols:
        return
    with op.batch_alter_table("ctfs") as batch:
        batch.add_column(sa.Column("announcement_message_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ctfs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("ctfs")}
    if "announcement_message_id" not in cols:
        return
    with op.batch_alter_table("ctfs") as batch:
        batch.drop_column("announcement_message_id")
