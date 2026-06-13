import asyncio
from fastapi import Depends
import redis.asyncio as redis
import uuid
import logging
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession 

from app.db.database import SessionLocal
from app.domain import models
from app.db.redis_client import get_redis

# from app.redis_client import redis_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def matchmaking_queue(redis_client: redis.Redis):
  # redis_client = Redis(connection_pool=redis_pool)
  # redis_client = await get_redis()

  logger.info("Matchmaker worker started. Scanning arena queue...")
  try:
    while True:
      queue = await redis_client.zrange("matchmaking_queue", 0, -1, withscores=True) # Returns ZSET in tuples [(key1, val1), (key2, val2)]
      if len(queue) >= 2:
        for i in range(1, len(queue)): # Sliding window to matchmake adjacent players with elo ratings close to each other, which would work since they're sorted 
          player1_id, player1_elo = queue[i - 1]
          player2_id, player2_elo = queue[i]

          if(player2_elo - player1_elo <= 50): # Match players with max elo rating difference of 50
            
            await redis_client.zrem("matchmaking_queue", player1_id, player2_id)

            match_id = str(uuid.uuid4())
            match_data = {
              "player1": player1_id,
              "player2": player2_id,
              "status": "awaiting_connection"
            }

            await redis_client.hset(f"match:{match_id}", mapping=match_data)
            await redis_client.set(f"match_user:{player1_id}", match_id, ex=3600)
            await redis_client.set(f"match_user:{player2_id}", match_id, ex=3600)
            logger.info(f"Match provisioned! {player1_id} vs {player2_id} -> Match ID: {match_id}")

      await asyncio.sleep(2)
    
  except asyncio.CancelledError:
    logger.info("Matchmaking worker shutting down.")
    # pass # Matchmaking worker shutting down
      


def calculate_new_elo(winner_elo: int, loser_elo: int) -> tuple[int, int]:
  K = 32
  expected_win = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))

  new_winner_elo = round(winner_elo + K * (1 - expected_win))
  new_loser_elo = round(loser_elo + K * (0 - (1 - expected_win)))

  return new_winner_elo, new_loser_elo


async def settlement_worker_loop(redis_client: redis.Redis):
  # redis_client = Redis(connection_pool=redis_pool)
  # redis_client = await get_redis()

  try:
    while True:
      # BLPOP blocks connection until an item appears in the queue
      queue_name, raw_data = await redis_client.blpop("settlement_queue", 0)

      payload = json.loads(raw_data)

      if not payload["is_draw"]:
          try:
            async with SessionLocal() as db:
                # Fetch winner
                stmt = select(models.User).where(models.User.username == payload["winner"])
                result = await db.execute(stmt)
                winner_user = result.scalar_one_or_none()
                # Fetch loser
                stmt = select(models.User).where(models.User.username == payload["loser"])
                result = await db.execute(stmt)
                loser_user = result.scalar_one_or_none()

                if winner_user and loser_user:
                  # Fetch winner stats
                  stmt = select(models.Stat).where(models.Stat.user_id == winner_user.id)
                  result = await db.execute(stmt)
                  winner_stats = result.scalar_one_or_none()
                  # Fetch loser stats
                  stmt = select(models.Stat).where(models.Stat.user_id == loser_user.id)
                  result = await db.execute(stmt)
                  loser_stats = result.scalar_one_or_none()

                  new_winner_elo, new_loser_elo = calculate_new_elo(winner_stats.elo_rating, loser_stats.elo_rating)

                  winner_stats.elo_rating = new_winner_elo
                  loser_stats.elo_rating = new_loser_elo

                  await db.commit()
          except Exception as e:
            await db.rollback()
  except asyncio.CancelledError:
    pass



  