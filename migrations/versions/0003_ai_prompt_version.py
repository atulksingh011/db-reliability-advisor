"""Add prompt version to AI audit attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("ai_attempts")}
    if "prompt_version" not in columns:
        op.add_column("ai_attempts", sa.Column("prompt_version", sa.String(length=120)))


def downgrade() -> None:
    op.drop_column("ai_attempts", "prompt_version")
