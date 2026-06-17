# FastAPI Matchmaking Engine

A high-performance, asynchronous matchmaking backend designed to pair users based on Elo ratings and manage real-time game states via WebSockets. 

This engine is built entirely with asynchronous Python, utilizing a Redis-backed worker queue for matchmaking and settlement, and PostgreSQL for persistent state and user statistics. It is fully containerized and heavily tested to simulate production loads and complete WebSocket lifecycles.

## Features

* **Real-Time WebSocket Management:** Handles live game states, turn validation, and automatic forfeit timers for disconnected players.
* **Asynchronous Matchmaking Worker:** Background Redis worker that continuously scans the queue (ZSET) to pair players within a sliding Elo rating window.
* **Automated Elo Settlement:** Decoupled background worker that processes game results from a Redis queue and mathematically recalculates player ratings.
* **Stateless Authentication:** Secure JWT-based registration and login system with password hashing (`pwdlib`).
* **Concurrency & Rate Limiting:** Implements `fastapi-limiter` across HTTP and WebSocket endpoints to prevent spam and abuse.
* **Automated CI/CD:** GitHub Actions pipeline configured to run the full Pytest suite on every push and pull request, ensuring main branch stability.

## Live Deployment & Infrastructure

The matchmaking engine is currently deployed and fully operational on a production server, handling secure real-time WebSocket connections.

* **Cloud Provider:** Oracle Cloud Infrastructure (OCI) Always Free Tier
* **Operating System:** Ubuntu Linux (Customized `iptables` firewall routing)
* **Reverse Proxy:** Nginx (Configured for HTTP/HTTPS and WebSocket `Upgrade` headers)
* **Security:** Fully encrypted transport layer (SSL/TLS) via Let's Encrypt / Certbot
* **Live API Endpoint:** `https://marwan-engine.duckdns.org`
* **Live WebSocket Endpoint:** `wss://marwan-engine.duckdns.org/ws/match/{match_id}`

## Architecture & Tech Stack

* **Framework:** FastAPI (Python 3.12)
* **Database:** PostgreSQL (with `asyncpg` driver)
* **ORM & Migrations:** SQLAlchemy 2.0 & Alembic
* **Cache & Message Broker:** Redis (`redis.asyncio`)
* **Testing:** Pytest, `httpx`, `pytest-asyncio`, `fakeredis`
* **Deployment:** Docker & Docker Compose, Nginx (Reverse Proxy)

## Local Development Setup

### Prerequisites
* Docker & Docker Compose
* Git

### Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/marwan-esam/fastapi-matchmaking-engine.git](https://github.com/marwan-esam/fastapi-matchmaking-engine.git)
    cd fastapi-matchmaking-engine
    ```

2.  **Configure Environment Variables:**
    Create a `.env` file in the root directory:
    ```env
    POSTGRES_USER=match_user
    POSTGRES_PASSWORD=your_secure_password
    POSTGRES_DB=matchmaking_db
    SQLALCHEMY_DATABASE_URL=postgresql+asyncpg://match_user:your_secure_password@postgres:5432/matchmaking_db

    REDIS_URL=redis://redis:6379

    SECRET_KEY=your_super_secret_jwt_key
    ALGORITHM=HS256
    ACCESS_TOKEN_EXPIRE_MINUTES=30
    ```

3.  **Boot the Infrastructure:**
    Build and start the application, database, and cache containers.
    ```bash
    docker compose up -d --build
    ```

4.  **Verify Status:**
    The API will be available at `http://localhost:8000`. You can view the interactive Swagger documentation at `http://localhost:8000/docs`.

## Testing

The test suite completely isolates the database and cache, utilizing `FakeRedis` and an ephemeral PostgreSQL test database. It includes a rigorous full-lifecycle WebSocket test simulating a complete match between two authenticated clients.

To run the test suite locally:
```bash
docker compose exec api pytest -v
```
*(Note: The CI/CD pipeline handles this automatically on all repository pushes.)*

## Author

**Marwan Esam**
[GitHub Profile](https://github.com/marwan-esam)