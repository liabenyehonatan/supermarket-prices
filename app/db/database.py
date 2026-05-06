# app/db/database.py

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.db.base import Base
import os
from dotenv import load_dotenv

# Load the .env file so we can read DATABASE_URL
load_dotenv()

# Read the database URL from your .env file
# This keeps your password out of your code
DATABASE_URL = os.getenv("DATABASE_URL")

# Create the "engine" — this is the object that manages
# the actual connection to PostgreSQL.
# echo=True means SQLAlchemy will print every SQL
# command it runs — very helpful for learning!
engine = create_async_engine(DATABASE_URL, echo=False)

# A "session" is like a temporary workspace for
# database operations. You open one, do your work,
# then close it.
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# This is a FastAPI "dependency" — a function that
# gives each API request its own database session
# and cleans it up automatically when done.
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session