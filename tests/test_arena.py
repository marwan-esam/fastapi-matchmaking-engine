import pytest
import json
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.main import app

pytestmark = pytest.mark.asyncio


async def test_full_match_lifecycle(override_deps, redis_mock):
  transport = ASGIWebSocketTransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as async_client:
    await async_client.post("/register", json={
      "username": "playerX",
      "password": "password123"
    })

    res_x = await async_client.post("/login", data={
      "username": "playerX",
      "password": "password123"
    })

    token_x = res_x.json()["access_token"]

    await async_client.post("/register", json={
      "username": "playerO",
      "password": "password123"
    })

    res_y = await async_client.post("/login", data={
      "username": "playerO",
      "password": "password123"
    })

    token_o = res_y.json()["access_token"]

    match_id = "test-arena-123"

    # async with aconnect_ws(f"/ws/match/{match_id}", async_client) as ws_x:
    ws_x_context = aconnect_ws(f"/ws/match/{match_id}", async_client)
    ws_x = await ws_x_context.__aenter__()
    try:
      await ws_x.send_json({"type": "auth", "token": token_x})

      async with aconnect_ws(f"/ws/match/{match_id}", async_client) as ws_o:
        await ws_o.send_json({"type": "auth", "token": token_o})

        start_x = await ws_x.receive_json()
        start_o = await ws_o.receive_json()

        assert start_x["type"] == "start"
        assert start_o["type"] == "start"


        await ws_x.send_json({"position": 0})
        await ws_o.receive_json()
        await ws_x.receive_json()

        await ws_o.send_json({"position": 3})
        await ws_o.receive_json()
        await ws_x.receive_json()

        await ws_x.send_json({"position": 1})
        await ws_o.receive_json()
        await ws_x.receive_json()
        
        await ws_o.send_json({"position": 4})
        await ws_o.receive_json()
        await ws_x.receive_json()

        await ws_x.send_json({"position": 2})

        game_over_x = await ws_x.receive_json()
        game_over_o = await ws_o.receive_json()

        assert game_over_x["type"] == "game_over"
        assert game_over_x["winner"] == "X"
        assert game_over_o["winner"] == "X"
    finally:
      await ws_x_context.__aexit__(None, None, None)


  raw_payload = await redis_mock.lpop("settlement_queue")
  payload = json.loads(raw_payload)

  assert payload["match_id"] == match_id
  assert payload["winner"] == "playerX"
  assert payload["loser"] == "playerO"
  assert payload["is_draw"] == False

