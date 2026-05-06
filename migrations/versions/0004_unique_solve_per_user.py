"""unique solve per (challenge, user)

Revision ID: 0004_unique_solve_per_user
Revises: 0003_announcement_message_id
Create Date: 2026-05-06

Adds a unique constraint on challenge_solves(challenge_id, user_id) so the
same user can't accumulate multiple rows for the same challenge — closes a
race window where concurrent /solve_challenge invocations could double-count.

"""
from alembic import op
import sqlalchemy as sa


revision = "0004_unique_solve_per_user"
down_revision = "0003_announcement_message_id"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_solve_user_challenge"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "challenge_solves" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("challenge_solves")}
    if INDEX_NAME in existing:
        return
    # Modeled as a unique index (rather than ADD CONSTRAINT) so SQLite is
    # happy without a table rebuild. Postgres treats the unique index as
    # equivalent to a unique constraint for conflict detection.
    op.create_index(
        INDEX_NAME,
        "challenge_solves",
        ["challenge_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "challenge_solves" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("challenge_solves")}
    if INDEX_NAME not in existing:
        return
    op.drop_index(INDEX_NAME, table_name="challenge_solves")
