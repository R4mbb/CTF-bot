"""add channel_id to challenges

Revision ID: 0001_challenge_channel_id
Revises:
Create Date: 2026-05-06

This migration is a no-op on fresh databases where ``challenges`` was just
created by ``Base.metadata.create_all`` with ``channel_id`` already present;
it only acts on pre-existing tables that lack the column.

"""
from alembic import op
import sqlalchemy as sa


revision = "0001_challenge_channel_id"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "challenges" not in insp.get_table_names():
        return  # fresh DB — create_all already established the schema
    cols = {c["name"] for c in insp.get_columns("challenges")}
    if "channel_id" in cols:
        return
    with op.batch_alter_table("challenges") as batch:
        batch.add_column(sa.Column("channel_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "challenges" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("challenges")}
    if "channel_id" not in cols:
        return
    with op.batch_alter_table("challenges") as batch:
        batch.drop_column("channel_id")
