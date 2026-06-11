from fastapi import WebSocket

class ConnectionManager:
  def __init__(self):
    self.active_matches: dict[str, list[WebSocket]] = {}
    self.game_states: dict[str, dict] = {}

  async def connect(self, websocket: WebSocket, match_id: str, username: str):
    await websocket.accept()

    if match_id not in self.active_matches:
      self.active_matches[match_id] = []
      self.game_states[match_id] = {
        "board": [None] * 9,
        "players": [],
        "turn_index": 0,
        "symbols": {}
      }

    self.active_matches[match_id].append(websocket)
    state = self.game_states[match_id]
    if username not in state["players"]:
      state["players"].append(username)
      state["symbols"][username] = "X" if len(state["players"]) == 1 else "O"

    if len(self.active_matches[match_id]) == 2:
      await self.broadcast_to_match(match_id, {
        "type": "start",
        "state": state
      })

  def disconnect(self, websocket: WebSocket, match_id: str):
    if match_id in self.active_matches:
      if websocket in self.active_matches[match_id]:
        self.active_matches[match_id].remove(websocket)

    if len(self.active_matches[match_id]) == 0:
      del self.active_matches[match_id]
      if match_id in self.game_states:
        del self.game_states[match_id]


  async def broadcast_to_match(self, match_id: str, message: dict):
    if match_id in self.active_matches:
      for connection in self.active_matches[match_id]:
        await connection.send_json(message)

  def check_win_condition(self, board: list) -> str | None:
    win_lines = [
      [0, 1, 2], [3, 4, 5], [6, 7, 8],
      [0, 3, 6], [1, 4, 7], [2, 5, 8],
      [0, 4, 8], [2, 4, 6]
    ]

    for line in win_lines:
      a, b, c, = line
      if board[a] and board[a] == board[b] == board[c]:
        return board[a]
      
    if None not in board:
      return "Draw"
    
    return None

manager = ConnectionManager()