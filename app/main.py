from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt
import json
import redis
from contextlib import asynccontextmanager
import asyncio
from redis import Redis

from app.worker import matchmaking_queue, settlement_worker_loop
from app import models, schemas, security, config
from app.database import get_db
from app.dependencies import get_current_user
from app.redis_client import get_redis
from app.socket_manager import manager


# CONFIG
SECRET_KEY = config.SECRET_KEY
ALGORITHM = config.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = int(config.ACCESS_TOKEN_EXPIRE_MINUTES)


# JWT
def create_access_token(data: dict):
  to_encode = data.copy()
  expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
  to_encode.update({"exp": expire})
  return jwt.encode(payload=to_encode, key=SECRET_KEY, algorithm=ALGORITHM)


@asynccontextmanager
async def lifespan(app: FastAPI):
  # Create the background task to push it to the event loop
  matchmaker_task = asyncio.create_task(matchmaking_queue())
  settlement_task = asyncio.create_task(settlement_worker_loop())
  yield

  # SHUTDOWN
  matchmaker_task.cancel()
  settlement_task.cancel()
  try:
    await asyncio.gather(matchmaker_task, settlement_task)
  except asyncio.CancelledError:
    pass

app = FastAPI(title="Matchmaking Engine", lifespan=lifespan)


# ROUTERS
@app.get("/")
def health_check():
  return {"status": "Ready"}


@app.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
  # CHECK EXISTING USER
  stmt = select(models.User).where(models.User.username == user_data.username)
  existing_user = db.execute(stmt).scalar_one_or_none()

  if existing_user:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")

  hashed_pw = security.hash_password(user_data.password)


  new_user = models.User(username=user_data.username, hashed_password=hashed_pw)
  db.add(new_user)
  db.flush()

  new_stat = models.Stat(user_id=new_user.id)
  db.add(new_stat)
  
  # Commit entire transaction
  db.commit()
  db.refresh(new_user)

  return new_user


@app.post("/login", response_model=schemas.Token)
def login_user(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
  # Verify user exists
  stmt = select(models.User).where(models.User.username == form_data.username)
  user = db.execute(stmt).scalar_one_or_none()

  if not user or not security.verify_password(form_data.password, user.hashed_password):
    raise HTTPException (
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Incorrect username or password",
      headers={"WWW-Authenticate": "Bearer"}
    )
  
  # Generate and return the stateless JWT
  access_token = create_access_token({"sub": user.username})

  return {
    "access_token": access_token,
    "token_type": "bearer"
  }


@app.post("/find-match", status_code=status.HTTP_202_ACCEPTED)
def find_match(
  current_user: models.User = Depends(get_current_user),
  db: Session = Depends(get_db),
  redis_client: redis.Redis = Depends(get_redis)
):
  # Fetch user stats
  stmt = select(models.Stat).where(models.Stat.user_id == current_user.id)
  user_stats = db.execute(stmt).scalar_one_or_none()

  if not user_stats:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND, 
      detail="Player stats not found"
    )
  
  if redis_client.zscore("matchmaking_queue", str(current_user.id)):
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=f"Player already in the matchmaking queue"
    )
  
  # Add player into Redis Sorted Set (ZSET)
  redis_client.zadd("matchmaking_queue", {str(current_user.id): user_stats.elo_rating})

  return {
    "status": "searching",
    "message": "Added to the arena queue",
    "current_elo": user_stats.elo_rating
  }

@app.post("/cancel-match", status_code=status.HTTP_200_OK)
def cancel_match(
  current_user: models.User = Depends(get_current_user),
  redis_client: redis.Redis = Depends(get_redis)
):
  removed_count = redis_client.zrem("matchmaking_queue", str(current_user.id))

  if removed_count == 0:
    raise HTTPException (
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="You are not currently in the matchmaking queue"
    )
  
  return {
    "status": "cancelled",
    "message": "Successfully left the arena queue"
  }


@app.websocket("/ws/match/{match_id}")
async def match_websocket(
  websocket: WebSocket,
  match_id: str,
  token: str,
  db: Session = Depends(get_db),
  redis_client: Redis = Depends(get_redis)
):
  try:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    username: str = payload.get("sub")
    if not username:
      await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
      return
  except jwt.PyJWTError:
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return
  
  stmt = select(models.User).where(models.User.username == username)
  user = db.execute(stmt).scalar_one_or_none()

  if not user:
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return
  
  await manager.connect(websocket, match_id)

  try:
    while True:
      data = await websocket.receive_json()

      state = manager.game_states[match_id]

      if not state or len(state["players"]) < 2:
        await websocket.send_json({"error": "Waiting for opponent"})
        continue

      current_turn_player = state["players"][state["turn_index"]]

      if current_turn_player != user.username:
        await websocket.send_json({"error": "It's not your turn yet"})
        continue

      position = data.get("position") # We should get the board square position from the frontend
      if type(position) is not int or position < 0 or position > 8 or state["board"][position] != None:
        await websocket.send_json({"error": "Invalid move"})
        continue

      symbol = state["symbols"][user.username]
      state["board"][position] = symbol

      result = manager.check_win_condition(state["board"])

      if result:
        await manager.broadcast_to_match(match_id, {
          "type": "game_over",
          "winner": result,
          "state": state
        })

        winner_username = None
        loser_username = None

        for player, symbol in state["symbols"].items():
          if symbol == result:
            winner_username = player
          else:
            loser_username = player

        settlement_payload = {
          "match_id": match_id,
          "winner": winner_username,
          "loser": loser_username,
          "is_draw": result == "Draw"
        }

        redis_client.rpush("settlement_queue", json.dumps(settlement_payload))

        manager.disconnect(websocket)

        await websocket.close()
        break 

      
      else:
        state["turn_index"] = 1 - state["turn_index"]

        await manager.broadcast_to_match(match_id, {
          "type": "update",
          "state": state,
          "last_move": {"player": user.username, "position": position}
        })

  except WebSocketDisconnect:
    await manager.disconnect(websocket)

    if match_id in manager.active_matches:
      await manager.broadcast_to_match(match_id, {"system_message": f"{user.username} has disconnected"})

@app.get("/match-status", status_code=status.HTTP_200_OK)
def get_match_status(
    current_user: models.User = Depends(get_current_user),
    redis_client: Redis = Depends(get_redis)
):
  user_id = str(current_user.id)
  match_id = redis_client.get(f"match_user:{user_id}")

  if match_id:
    return {
      "status": "found",
      "match_id": match_id
    }
  
  if redis_client.zscore("matchmaking_queue", user_id) is not None:
    return {
      "status": "searching"
    }
  
  return {
    "status": "idle"
  }