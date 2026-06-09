import uuid
from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
  access_token: str
  token_type: str


class TokenData(BaseModel):
  username: str | None


class UserCreate(BaseModel):
  username: str = Field(..., min_length=3, max_length=30)
  password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
  id: uuid.UUID
  username: str

  model_config = ConfigDict(from_attributes=True)


class StatResponse(BaseModel):
  elo_rating: int
  wins: int
  losses: int

  model_config = ConfigDict(from_attributes=True)



class UserProfileResponse(BaseModel):
  user: UserResponse
  stats: StatResponse



