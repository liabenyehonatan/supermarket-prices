# app/db/database.py

from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app import settings

# DATABASE_URL comes from the environment (.env locally). Keeping it out of the
# code keeps the password out of git.
DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Put it in .env (postgresql+asyncpg://user:password@host/dbname) "
        "or export it in the environment."
    )

_connect_args: dict = {}
if settings.DB_PGBOUNCER:
    # pgbouncer in transaction mode cannot hold asyncpg's prepared statements.
    _connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }

# pool_pre_ping drops connections that died while idle (DB restart, network
# blip) instead of failing the first request that reuses them.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=_connect_args,
)

# A session is a short-lived unit of work: open one, use it, close it.
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# FastAPI dependency: one session per request, closed automatically.
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
