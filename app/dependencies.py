from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt
from app.database import get_db
from app import config, models

oauth_scheme = OAuth2PasswordBearer(tokenUrl="/login")

def get_current_user(token: str = Depends(oauth_scheme), db: Session = Depends(get_db)):
  credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"}
  )
  
  try:
    payload = jwt.decode(jwt=token, key=config.SECRET_KEY, algorithms=[config.ALGORITHM])
    username: str = payload.get("sub")
    if not username:
      raise credentials_exception
  except jwt.PyJWTError:
    raise credentials_exception
  
  stmt = select(models.User).where(models.User.username == username)
  user = db.execute(stmt).scalar_one_or_none()

  if not user:
    raise credentials_exception
  
  return user
