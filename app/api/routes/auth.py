from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt
from app.domain import models, schemas
from app.core import security, config
from app.db.database import get_db

router = APIRouter(tags=["Authentication"])

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




@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
  # CHECK EXISTING USER
  stmt = select(models.User).where(models.User.username == user_data.username)
  result = await db.execute(stmt)
  existing_user = result.scalar_one_or_none()

  if existing_user:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")

  hashed_pw = security.hash_password(user_data.password)


  new_user = models.User(username=user_data.username, hashed_password=hashed_pw)
  db.add(new_user)
  await db.flush()

  new_stat = models.Stat(user_id=new_user.id)
  db.add(new_stat)
  
  # Commit entire transaction
  await db.commit()
  await db.refresh(new_user)

  return new_user


@router.post("/login", response_model=schemas.Token, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
async def login_user(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
  # Verify user exists
  stmt = select(models.User).where(models.User.username == form_data.username)
  result = await db.execute(stmt)
  user = result.scalar_one_or_none()

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