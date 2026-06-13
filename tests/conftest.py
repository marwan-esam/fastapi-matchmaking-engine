import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from fakeredis.aioredis import FakeRedis
from fastapi_limiter import FastAPILimiter
import os

from app.main import app
from app.database import Base, get_db
from app.redis_client import get_redis

os.environ["TESTING"] = "1"


TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/matchmaking_test"


@pytest_asyncio.fixture(scope="function")
async def db_engine():
  engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

  async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.drop_all)
    await conn.run_sync(Base.metadata.create_all)

  yield engine

  async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.drop_all)

  await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def redis_mock():
  fake_redis = FakeRedis(decode_responses=True)
  
  await FastAPILimiter.init(fake_redis)

  yield fake_redis
  await FastAPILimiter.close()
  await fake_redis.close()


@pytest_asyncio.fixture(scope="function")
async def override_deps(db_engine, redis_mock):
  TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=True, bind=db_engine)
  async def override_get_db():
    async with TestingSessionLocal() as session:
      yield session

  async def override_get_redis():
    return redis_mock
  
  app.dependency_overrides[get_db] = override_get_db
  app.dependency_overrides[get_redis] = override_get_redis

  yield

  app.dependency_overrides.clear()

@pytest_asyncio.fixture(scope="function")
async def async_client(override_deps):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    
    await client.__aenter__()
    
    try:
        yield client
    finally:
        await client.__aexit__(None, None, None)

  
  
 
  
