"""Add lifecycle, provider, validation and fallback audit detail."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for _name, column in [
        ("target", sa.Column("target", sa.String(length=200))),
        ("replayed_from", sa.Column("replayed_from", sa.String(length=80))),
        ("started_at", sa.Column("started_at", sa.DateTime(timezone=True))),
        ("completed_at", sa.Column("completed_at", sa.DateTime(timezone=True))),
        ("failed_at", sa.Column("failed_at", sa.DateTime(timezone=True))),
    ]:
        op.add_column("analysis_runs", column)
    with op.batch_alter_table("analysis_runs") as batch:
        batch.create_foreign_key(
            "fk_analysis_runs_replayed_from",
            "analysis_runs",
            ["replayed_from"],
            ["analysis_id"],
        )
    op.create_index("ix_analysis_runs_replayed_from", "analysis_runs", ["replayed_from"])

    op.create_table(
        "analysis_lifecycle_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(length=80), sa.ForeignKey("analysis_runs.analysis_id")),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_analysis_lifecycle_events_analysis_id", "analysis_lifecycle_events", ["analysis_id"]
    )

    for _name, column in [
        ("attempt_number", sa.Column("attempt_number", sa.Integer(), nullable=True)),
        ("model", sa.Column("model", sa.String(length=120))),
        ("error_category", sa.Column("error_category", sa.String(length=80))),
        ("started_at", sa.Column("started_at", sa.DateTime(timezone=True))),
        ("completed_at", sa.Column("completed_at", sa.DateTime(timezone=True))),
    ]:
        op.add_column("ai_attempts", column)
    op.execute("UPDATE ai_attempts SET attempt_number = id WHERE attempt_number IS NULL")
    with op.batch_alter_table("ai_attempts") as batch:
        batch.alter_column("attempt_number", existing_type=sa.Integer(), nullable=False)

    op.create_table(
        "validation_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(length=80), sa.ForeignKey("analysis_runs.analysis_id")),
        sa.Column("ai_attempt_id", sa.Integer(), sa.ForeignKey("ai_attempts.id")),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("repair_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_validation_outcomes_analysis_id", "validation_outcomes", ["analysis_id"])
    op.create_table(
        "fallback_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(length=80), sa.ForeignKey("analysis_runs.analysis_id")),
        sa.Column("reason", sa.JSON(), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fallback_outcomes_analysis_id", "fallback_outcomes", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_fallback_outcomes_analysis_id", table_name="fallback_outcomes")
    op.drop_table("fallback_outcomes")
    op.drop_index("ix_validation_outcomes_analysis_id", table_name="validation_outcomes")
    op.drop_table("validation_outcomes")
    op.drop_column("ai_attempts", "completed_at")
    op.drop_column("ai_attempts", "started_at")
    op.drop_column("ai_attempts", "error_category")
    op.drop_column("ai_attempts", "model")
    op.drop_column("ai_attempts", "attempt_number")
    op.drop_index(
        "ix_analysis_lifecycle_events_analysis_id", table_name="analysis_lifecycle_events"
    )
    op.drop_table("analysis_lifecycle_events")
    op.drop_index("ix_analysis_runs_replayed_from", table_name="analysis_runs")
    with op.batch_alter_table("analysis_runs") as batch:
        batch.drop_constraint("fk_analysis_runs_replayed_from", type_="foreignkey")
    for column in ("failed_at", "completed_at", "started_at", "replayed_from", "target"):
        op.drop_column("analysis_runs", column)
