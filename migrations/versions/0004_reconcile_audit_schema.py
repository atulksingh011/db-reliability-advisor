"""Reconcile audit databases stamped by earlier schema revisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> dict[str, dict[str, object]]:
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_table_if_missing(table_name: str, *columns: sa.Column) -> None:
    if table_name not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(table_name, *columns)


def _create_index_if_missing(index_name: str, table_name: str, column_name: str) -> None:
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    if index_name not in {index["name"] for index in indexes}:
        op.create_index(index_name, table_name, [column_name])


def upgrade() -> None:
    for table_name, columns in (
        (
            "analysis_runs",
            [
                sa.Column("target", sa.String(length=200)),
                sa.Column("replayed_from", sa.String(length=80)),
                sa.Column("started_at", sa.DateTime(timezone=True)),
                sa.Column("completed_at", sa.DateTime(timezone=True)),
                sa.Column("failed_at", sa.DateTime(timezone=True)),
            ],
        ),
        (
            "ai_attempts",
            [
                sa.Column("attempt_number", sa.Integer(), nullable=True),
                sa.Column("model", sa.String(length=120)),
                sa.Column("error_category", sa.String(length=80)),
                sa.Column("started_at", sa.DateTime(timezone=True)),
                sa.Column("completed_at", sa.DateTime(timezone=True)),
            ],
        ),
    ):
        for column in columns:
            _add_column_if_missing(table_name, column)

    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("analysis_runs")
    if not any(key["constrained_columns"] == ["replayed_from"] for key in foreign_keys):
        with op.batch_alter_table("analysis_runs") as batch:
            batch.create_foreign_key(
                "fk_analysis_runs_replayed_from",
                "analysis_runs",
                ["replayed_from"],
                ["analysis_id"],
            )

    op.execute("UPDATE ai_attempts SET attempt_number = id WHERE attempt_number IS NULL")
    if _columns("ai_attempts")["attempt_number"]["nullable"]:
        with op.batch_alter_table("ai_attempts") as batch:
            batch.alter_column("attempt_number", existing_type=sa.Integer(), nullable=False)

    _create_table_if_missing(
        "analysis_lifecycle_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "analysis_id",
            sa.String(length=80),
            sa.ForeignKey("analysis_runs.analysis_id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_table_if_missing(
        "validation_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "analysis_id",
            sa.String(length=80),
            sa.ForeignKey("analysis_runs.analysis_id"),
            nullable=False,
        ),
        sa.Column("ai_attempt_id", sa.Integer(), sa.ForeignKey("ai_attempts.id")),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("repair_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_table_if_missing(
        "fallback_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "analysis_id",
            sa.String(length=80),
            sa.ForeignKey("analysis_runs.analysis_id"),
            nullable=False,
        ),
        sa.Column("reason", sa.JSON(), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    for index_name, table_name, column_name in (
        ("ix_analysis_runs_replayed_from", "analysis_runs", "replayed_from"),
        (
            "ix_analysis_lifecycle_events_analysis_id",
            "analysis_lifecycle_events",
            "analysis_id",
        ),
        ("ix_validation_outcomes_analysis_id", "validation_outcomes", "analysis_id"),
        ("ix_fallback_outcomes_analysis_id", "fallback_outcomes", "analysis_id"),
    ):
        _create_index_if_missing(index_name, table_name, column_name)


def downgrade() -> None:
    raise RuntimeError("Downgrading this migration could delete audit history.")
