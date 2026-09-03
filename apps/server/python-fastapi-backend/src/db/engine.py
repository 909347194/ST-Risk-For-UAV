"""SQLAlchemy 2.0 异步引擎 — PostgreSQL + PostGIS + pgvector"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.utils.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入用"""
    async with AsyncSessionLocal() as session:
        yield session
