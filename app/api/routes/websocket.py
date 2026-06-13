from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi_limiter.depends import WebSocketRateLimiter
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt
import json
import redis.asyncio as redis
import asyncio
import redis.asyncio as redis

from app.domain import models
from app.db.database import get_db, SessionLocal
from app.db.redis_client import get_redis
from app.services.socket_manager import manager
from app.core import config

router = APIRouter(tags=["Arena"])

SECRET_KEY = config.SECRET_KEY
ALGORITHM = config.ALGORITHM

async def handle_forfeit_timer(match_id: str, dropped_username: str, dropped_user_id: str, redis_client: redis.Redis):
  await asyncio.sleep(30) # Wait 30 seconds for the disconnected user to come back

  if match_id not in manager.active_matches or len(manager.active_matches[match_id]) == 2:
    return # If either they both leave the match, or the disconnected user comes back, we do nothing
  
  state = manager.game_states.get(match_id)
  if not state:
    return
  
  winner_username = [p for p in state["players"] if p != dropped_username][0]

  async with SessionLocal() as db:
    stmt = select(models.User).where(models.User.username == winner_username)
    result = await db.execute(stmt)
    winner_user = result.scalar_one_or_none()
    winner_id = str(winner_user.id) if winner_user else ""

  settlement_payload = {
    "match_id": match_id,
    "winner": winner_username,
    "loser": dropped_username,
    "is_draw": False
  }

  await redis_client.rpush("settlement_queue", json.dumps(settlement_payload))

  # Delete the 1 house redis lock
  await redis_client.delete(f"match_user:{dropped_user_id}")
  if winner_id:
    await redis_client.delete(f"match_user:{winner_id}")

  await manager.broadcast_to_match(match_id, {
    "type": "game_over",
    "winner": winner_username,
    "system_message": "Opponent abandoned the match. You win by forfeit"
  })

  for ws in list(manager.active_matches.get(match_id, [])):
    try:
      await ws.close()
    except Exception:
      pass

  if match_id in manager.active_matches:
    del manager.active_matches[match_id]
  if match_id in manager.game_states:
    del manager.game_states[match_id]
  

@router.websocket("/ws/match/{match_id}")
async def match_websocket(
  websocket: WebSocket,
  match_id: str,
  db: Session = Depends(get_db),
  redis_client: redis.Redis = Depends(get_redis)
):
  await websocket.accept()
  try:
    auth_data = await websocket.receive_json()

    if auth_data.get("type") != "auth" or not auth_data.get("token"):
      await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
      return
    
    token = auth_data.get("token")
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    username: str = payload.get("sub")
    if not username:
      await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
      return
  
    stmt = select(models.User).where(models.User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
      await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
      return
  except (jwt.PyJWTError, WebSocketDisconnect, json.JSONDecodeError):
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return
  
  await manager.connect(websocket, match_id, user.username)

  ratelimit = WebSocketRateLimiter(times=10, seconds=5)
  try:
    while True:
      data = await websocket.receive_json()
      await ratelimit(websocket, context_key=user.username)

      state = manager.game_states.get(match_id)

      if not state:
        try:
          await websocket.close()
        except Exception:
          pass
        break

      if len(state["players"]) < 2:
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
        if match_id in manager.game_states:
          del manager.game_states[match_id]

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

        await redis_client.rpush("settlement_queue", json.dumps(settlement_payload))

        # await websocket.close()
        
        if match_id in manager.active_matches:
          del manager.active_matches[match_id]
        break 

      
      else:
        state["turn_index"] = 1 - state["turn_index"]

        await manager.broadcast_to_match(match_id, {
          "type": "update",
          "state": state,
          "last_move": {"player": user.username, "position": position}
        })

  except HTTPException as e:
    if e.status_code == 429:
      try:
        await websocket.send_json({"error": "Rate limit exceeded. Slow down!"})
        await websocket.close()
      except Exception:
        pass

      if match_id in manager.game_states:
        manager.disconnect(websocket, match_id)
        if match_id in manager.active_matches:
          await manager.broadcast_to_match(match_id, {
            "type": "error",
            "system_message": f"{user.username} has disconnected. Waiting 30 seconds for reconnection..."
          })

        asyncio.create_task(handle_forfeit_timer(match_id, user.username, str(user.id), redis_client))


  except WebSocketDisconnect:
    if match_id in manager.game_states:
      manager.disconnect(websocket, match_id)
      if match_id in manager.active_matches:
        await manager.broadcast_to_match(match_id, {
          "type": "error",
          "system_message": f"{user.username} was disconnected for spamming. Waiting 30 seconds for reconnection..."
        })

      asyncio.create_task(handle_forfeit_timer(match_id, user.username, str(user.id), redis_client))

