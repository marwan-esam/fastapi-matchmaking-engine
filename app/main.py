from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter import FastAPILimiter
from contextlib import asynccontextmanager
import asyncio
import os

from app.db.redis_client import redis_client
from app.services.worker import matchmaking_queue, settlement_worker_loop
from app.api.routes import auth, matchmaking, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
  # Create the background task to push it to the event loop
  if not os.getenv("TESTING"):
    await FastAPILimiter.init(redis_client)
    matchmaker_task = asyncio.create_task(matchmaking_queue(redis_client))
    settlement_task = asyncio.create_task(settlement_worker_loop(redis_client))
  else:
    matchmaker_task = settlement_task = None
  yield

  # SHUTDOWN
  matchmaker_task.cancel()
  settlement_task.cancel()
  try:
    await asyncio.gather(matchmaker_task, settlement_task)
  except asyncio.CancelledError:
    pass

  await FastAPILimiter.close()

app = FastAPI(title="Matchmaking Engine", lifespan=lifespan)

origins = [
  "http://localhost:3000",
  "http://127.0.0.1:3000",
]

app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

@app.get("/")
def health_check():
  return {"status": "Ready"}

app.include_router(auth.router)
app.include_router(matchmaking.router)
app.include_router(websocket.router)



