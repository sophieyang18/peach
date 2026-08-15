from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

if settings.database_url.startswith("sqlite"):
    parsed = urlparse(settings.database_url)
    db_path = parsed.path.lstrip("/")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    from backend.app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(ensure_demo_columns)


def ensure_demo_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    if "user_profiles" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("user_profiles")}
    if "username" not in columns:
        sync_conn.execute(text("ALTER TABLE user_profiles ADD COLUMN username VARCHAR(80)"))
    sync_conn.execute(text("UPDATE user_profiles SET username = 'demo' WHERE username IS NULL OR username = ''"))

    if "knowledge_resources" in tables:
        columns = {column["name"] for column in inspector.get_columns("knowledge_resources")}
        if "summary_status" not in columns:
            sync_conn.execute(text("ALTER TABLE knowledge_resources ADD COLUMN summary_status VARCHAR(24)"))
        if "pinned" not in columns:
            sync_conn.execute(text("ALTER TABLE knowledge_resources ADD COLUMN pinned INTEGER"))
        sync_conn.execute(text("UPDATE knowledge_resources SET summary_status = 'ready' WHERE summary_status IS NULL OR summary_status = ''"))
        sync_conn.execute(text("UPDATE knowledge_resources SET pinned = 0 WHERE pinned IS NULL"))

    if "knowledge_folders" in tables:
        columns = {column["name"] for column in inspector.get_columns("knowledge_folders")}
        if "cover" not in columns:
            sync_conn.execute(text("ALTER TABLE knowledge_folders ADD COLUMN cover TEXT"))
        if "description" not in columns:
            sync_conn.execute(text("ALTER TABLE knowledge_folders ADD COLUMN description TEXT"))
        if "recommended_questions" not in columns:
            sync_conn.execute(text("ALTER TABLE knowledge_folders ADD COLUMN recommended_questions JSON"))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
