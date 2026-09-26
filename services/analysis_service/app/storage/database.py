from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from .models import Base


def create_database_engine(database_url: str) -> Engine:
    options: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        options["poolclass"] = StaticPool
    return create_engine(database_url, **options)


def initialize_database(engine: Engine) -> None:
    """Apply Alembic for durable databases; use isolated metadata for memory tests."""
    if engine.url.database in (None, ":memory:"):
        Base.metadata.create_all(engine)
        return

    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", "migrations")
    config.set_main_option("sqlalchemy.url", str(engine.url))
    inspector = inspect(engine)
    # The foundation used create_all before Alembic became the runtime owner.
    # Adopt that existing schema at 0001, then apply additive migrations.
    version_table_missing = not inspector.has_table("alembic_version")
    version_table_empty = False
    if not version_table_missing:
        with engine.connect() as connection:
            version_table_empty = connection.execute(
                text("SELECT COUNT(*) FROM alembic_version")
            ).scalar_one() == 0
    if inspector.has_table("analysis_runs") and (version_table_missing or version_table_empty):
        command.stamp(config, "0001")
    command.upgrade(config, "head")
