"""Initial audit persistence tables.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("analysis_id", sa.String(length=80), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("fixture_name", sa.String(length=80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "evidence_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(length=80), sa.ForeignKey("analysis_runs.analysis_id")),
        sa.Column("package_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_snapshots_analysis_id", "evidence_snapshots", ["analysis_id"])
    op.create_table(
        "deterministic_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(length=80), sa.ForeignKey("analysis_runs.analysis_id")),
        sa.Column("findings_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_deterministic_results_analysis_id",
        "deterministic_results",
        ["analysis_id"],
    )
    op.create_table(
        "ai_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(length=80), sa.ForeignKey("analysis_runs.analysis_id")),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_attempts_analysis_id", "ai_attempts", ["analysis_id"])
    op.create_table(
        "analysis_results",
        sa.Column(
            "analysis_id",
            sa.String(length=80),
            sa.ForeignKey("analysis_runs.analysis_id"),
            primary_key=True,
        ),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(length=80), sa.ForeignKey("analysis_runs.analysis_id")),
        sa.Column("finding_id", sa.String(length=120)),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedback_analysis_id", "feedback", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("analysis_results")
    op.drop_table("ai_attempts")
    op.drop_table("deterministic_results")
    op.drop_table("evidence_snapshots")
    op.drop_table("analysis_runs")
