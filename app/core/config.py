import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.environ("SQLALCHEMY_DATABASE_URL")
REDIS_URL = os.environ("REDIS_URL", "redis://localhost:6379")
SECRET_KEY = os.environ("SECRET_KEY")
ALGORITHM = os.environ("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = os.environ("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

if not SQLALCHEMY_DATABASE_URL:
  raise ValueError("SQLALCHEMY_DATABASE_URL environment variables is not set")

if not SECRET_KEY:
  raise ValueError("SECRET_KEY environemnt variable is not set")