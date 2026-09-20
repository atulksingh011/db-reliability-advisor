from sqlalchemy import Engine, create_engine
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
    # Alembic owns production evolution; create_all keeps the foundation runnable
    # for an empty local volume and temporary test databases.
    Base.metadata.create_all(engine)
