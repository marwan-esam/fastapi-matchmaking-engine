import redis
from dotenv import dotenv_values

config = dotenv_values(".env")
REDIS_URL = config["REDIS_URL"]

redis_pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)

def get_redis():
  client = redis.Redis(connection_pool=redis_pool)
  try:
    yield client
  finally:
    client.close()


  