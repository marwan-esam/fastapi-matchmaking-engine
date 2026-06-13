import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_register_user(async_client: AsyncClient):
  response = await async_client.post("/register", json={
    "username": "testplayer",
    "password": "securepassword123"
  })

  assert response.status_code == 201
  data = response.json()
  assert data["username"] == "testplayer"
  assert "id" in data


async def test_duplicate_registration_fails(async_client: AsyncClient):
  user_data = {"username": "duplicateuser", "password": "password123"}

  await async_client.post("/register", json=user_data)

  response = await async_client.post("/register", json=user_data)

  assert response.status_code == 400
  assert response.json()["detail"] == "Username already registered"


async def test_login_user(async_client: AsyncClient):
  await async_client.post("/register", json={
    "username": "loginplayer",
    "password": "password123"
  })

  response = await async_client.post("/login", data={
    "username": "loginplayer",
    "password": "password123"
  })

  assert response.status_code == 200
  data = response.json()
  assert "access_token" in data
  assert data["token_type"] == "bearer"


async def test_find_match_queue(async_client: AsyncClient):
  await async_client.post("/register", json={
    "username": "queueplayer",
    "password": "password123"
  })

  login_res = await async_client.post("/login", data={
    "username": "queueplayer",
    "password": "password123"
  })

  token = login_res.json()["access_token"]

  headers = {"Authorization": f"Bearer {token}"}

  match_res = await async_client.post("/find-match", headers=headers)

  assert match_res.status_code == 202
  data = match_res.json()
  assert data["status"] == "searching"
  assert "current_elo" in data

  
