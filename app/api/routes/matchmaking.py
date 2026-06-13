from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select
from sqlalchemy.orm import Session
import redis.asyncio as redis
import redis.asyncio as redis

from app.domain import models
from app.db.database import get_db
from app.api.dependencies import get_current_user
from app.db.redis_client import get_redis

router = APIRouter(tags=["Matchmaking Queue"])

@router.post("/find-match", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(RateLimiter(times=1, seconds=3))])
async def find_match(
  current_user: models.User = Depends(get_current_user),
  db: Session = Depends(get_db),
  redis_client: redis.Redis = Depends(get_redis)
):
  # Fetch user stats
  stmt = select(models.Stat).where(models.Stat.user_id == current_user.id)
  result = await db.execute(stmt)
  user_stats = result.scalar_one_or_none()

  if not user_stats:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND, 
      detail="Player stats not found"
    )
  
  if await redis_client.get(f"match_user:{current_user.id}"):
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="Player already in a match"
    )
  
  if await redis_client.zscore("matchmaking_queue", str(current_user.id)):
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=f"Player already in the matchmaking queue"
    )
  
  # Add player into Redis Sorted Set (ZSET)
  await redis_client.zadd("matchmaking_queue", {str(current_user.id): user_stats.elo_rating})

  return {
    "status": "searching",
    "message": "Added to the arena queue",
    "current_elo": user_stats.elo_rating
  }

@router.post("/cancel-match", status_code=status.HTTP_200_OK)
async def cancel_match(
  current_user: models.User = Depends(get_current_user),
  redis_client: redis.Redis = Depends(get_redis)
):
  removed_count = await redis_client.zrem("matchmaking_queue", str(current_user.id))

  if removed_count == 0:
    raise HTTPException (
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="You are not currently in the matchmaking queue"
    )
  
  return {
    "status": "cancelled",
    "message": "Successfully left the arena queue"
  }

@router.get("/match-status", status_code=status.HTTP_200_OK)
async def get_match_status(
    current_user: models.User = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis)
):
  user_id = str(current_user.id)
  match_id = await redis_client.get(f"match_user:{user_id}")

  if match_id:
    return {
      "status": "found",
      "match_id": match_id
    }
  
  if await redis_client.zscore("matchmaking_queue", user_id) is not None:
    return {
      "status": "searching"
    }
  
  return {
    "status": "idle"
  }