from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt
import redis

from app import models, schemas, security, config
from app.database import get_db
from app.dependencies import get_current_user
from app.redis_client import get_redis


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

app = FastAPI(title="Matchmaking Engine")


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