from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from typing import AsyncGenerator

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,
    # Supabase pooler in transaction mode requires statement_cache_size=0
    connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def set_user_role(session: AsyncSession, role: str) -> None:
    """Set the RLS app.current_user_role for the current connection."""
    await session.execute(text("SELECT set_config('app.current_user_role', :role, true)"),
                          {"role": role})
