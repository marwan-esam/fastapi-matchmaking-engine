from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, sessionmaker
from dotenv import dotenv_values

config = dotenv_values(".env")

SQLALCHEMY_DATABASE_URL = config["SQLALCHEMY_DATABASE_URL"]

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)

class Base(MappedAsDataclass, DeclarativeBase):
  pass

def get_db(): # Manage database connections (sessions)
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()
