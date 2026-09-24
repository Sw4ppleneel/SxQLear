"""Add persisted metadata embeddings for column discovery.

Revision ID: df5b8e61d9a2
Revises: 45356ae54c90
"""

import sqlalchemy as sa

from alembic import op

revision = "df5b8e61d9a2"
down_revision = "45356ae54c90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "column_search_index",
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("table_name", sa.String(), primary_key=True),
        sa.Column("column_name", sa.String(), primary_key=True),
        sa.Column("snapshot_id", sa.String(), nullable=False),
        sa.Column("document", sa.Text(), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("column_search_index")
