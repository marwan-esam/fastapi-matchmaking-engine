from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass
from app.core import config


engine = create_async_engine(
  config.SQLALCHEMY_DATABASE_URL,
  pool_size=20,
  max_overflow=10,
  pool_timeout=30,
  pool_recycle=1800,
  pool_pre_ping=True
)

SessionLocal = async_sessionmaker(
  autocommit=False,
  autoflush=True,
  bind=engine,
  class_=AsyncSession
)

class Base(MappedAsDataclass, DeclarativeBase):
  pass

async def get_db(): # Manage database connections (sessions)
  async with SessionLocal() as db:
    yield db
