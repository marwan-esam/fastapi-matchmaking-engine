import uuid
from sqlalchemy import Uuid, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class User(Base):
  __tablename__ = "users"

  username: Mapped[str] = mapped_column(unique=True, nullable=False)
  hashed_password: Mapped[str] = mapped_column(nullable=False)
  id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid.uuid4)


class Stat(Base):
  __tablename__ = "stats"

  user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), unique=True)
  id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid.uuid4)
  elo_rating: Mapped[int] = mapped_column(default=1000)
  wins: Mapped[int] = mapped_column(default=0)
  losses: Mapped[int] = mapped_column(default=0)
