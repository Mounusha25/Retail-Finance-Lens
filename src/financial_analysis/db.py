from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import PROJECT_ROOT, Settings
from .models import Base


def make_engine(url: str, *, pool_pre_ping: bool = True) -> Engine:
    return create_engine(url, pool_pre_ping=pool_pre_ping)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    install_analytics_views(engine)


def install_analytics_views(engine: Engine) -> None:
    sql_path = PROJECT_ROOT / "sql" / "002_analytics_views.sql"
    sql = sql_path.read_text(encoding="utf-8")
    with engine.begin() as connection:
        connection.execute(text(sql))


def database_available(settings: Settings) -> bool:
    try:
        with make_engine(settings.write_database_url).connect() as connection:
            connection.execute(text("select 1"))
        return True
    except Exception:
        return False
