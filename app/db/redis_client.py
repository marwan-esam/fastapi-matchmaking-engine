from redis.asyncio import Redis, ConnectionPool

from app.core import config

redis_client = Redis.from_url(
  config.REDIS_URL,
  decode_responses=True,
  max_connections=20
)

async def get_redis():
  return redis_client


  