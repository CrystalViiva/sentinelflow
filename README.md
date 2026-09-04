# SentinelFlow

**Explainable market surveillance. Deterministic risk controls. Human-approved execution.**

SentinelFlow analyzes market observations for unusual accumulation, explains the evidence,
creates tightly bounded Spot proposals, and records every risk decision in PostgreSQL. It is
designed to run beside Binance's official Agentic MCP connection in an MCP-compatible host.

> Safety: replay is the default mode. This repository never stores Binance credentials and
> never calls the Binance Agentic endpoint as if it were a normal REST API. Approval inside
> SentinelFlow does not execute a trade; Binance MCP still requires its own user confirmation.

## What is implemented

- Deterministic volume, price, volatility, spread, liquidity and order-book features
- Explainable 100-point accumulation score
- Optional Isolation Forest anomaly detector
- Three replay datasets and deterministic replay loader
- Deterministic Risk Gate with nine checks
- Versioned trade-proposal state machine
- Caller-controlled idempotency request IDs, database uniqueness and client-order identifiers
- PostgreSQL JSONB audit storage
- SQLAlchemy repositories and Alembic migration
- FastAPI endpoints and OpenAPI documentation
- Streamlit review/approval dashboard
- SentinelFlow MCP server using the official Python MCP SDK
- Optional Gemini 2.5 Flash explanations with a no-LLM fallback
- Unit tests, Docker database and Windows launch scripts

## Intentionally excluded

Futures, Margin, arbitrage, autonomous execution, news analysis, Telegram notifications,
portfolio rebalancing, custom-model training and Skills Hub integration.

## Architecture

```text
MCP-compatible host
  ├── SentinelFlow MCP -> analytics -> Risk Gate -> PostgreSQL -> Streamlit
  └── Official Binance MCP -> Agentic sub-account -> Binance confirmation
```

The MCP host orchestrates both servers. SentinelFlow returns an approved, unexpired proposal;
the host then uses Binance MCP for the final user-confirmed action. There is deliberately no
home-made Binance OAuth implementation in this repository.

## Windows quick start

### 1. Install prerequisites

- Python 3.12
- Git
- PostgreSQL 16, or Docker Desktop
- An MCP-compatible client supported by Binance

Confirm Python:

```powershell
python --version
```

### 2. Create the virtual environment

Open PowerShell inside this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Create the environment file

```powershell
Copy-Item .env.example .env
```

Keep these safety defaults:

```env
APP_MODE=replay
LIVE_TRADING_ENABLED=false
```

### 4. Start PostgreSQL

With Docker Desktop:

```powershell
docker compose up -d postgres
docker compose ps
```

Or create a local database named `sentinelflow` and update `DATABASE_URL` in `.env`.

### 5. Run migrations

```powershell
alembic upgrade head
```

### 6. Run tests

```powershell
pytest -q
```

Then run the real PostgreSQL/API smoke flow:

```powershell
python scripts/smoke_test.py
```

The smoke test applies migrations, creates a replay signal through FastAPI, creates and retries
the same proposal, verifies that both calls return the same proposal, approves it and checks its
audit timeline.

To include the disposable-database integration test in pytest:

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/sentinelflow_test"
pytest -m integration -q
```

### 7. Start the API

```powershell
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs>.

### 8. Start the dashboard

Open another PowerShell window, activate the environment, then run:

```powershell
streamlit run app/ui/dashboard.py
```

Open <http://localhost:8501> and run the SOL accumulation replay.

### 9. Start SentinelFlow MCP

Your MCP host should launch:

```powershell
C:\full\path\to\sentinelflow\.venv\Scripts\python.exe -m app.mcp_server.server
```

The exact host configuration differs between Codex, Claude, ChatGPT, VS Code and Grok. Use an
absolute Windows path and set the working directory to this project folder.

### 10. Connect Binance's official MCP separately

Use Binance's documented endpoint in your supported client:

```text
https://agent.binance.com/mcp/agentic
```

Authorize only Market Data, Account and Spot Trade. Do not place secrets in `.env` or source
code. Confirm public market access and the Agentic balance before attempting any action.

## Neon deployment database

Create a free Neon PostgreSQL project, copy its connection URL, ensure it uses TLS, then set:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Run `alembic upgrade head` against it before starting the deployed application.

## API routes

- `GET /api/health`
- `POST /api/replay/analyze`
- `GET /api/signals`
- `POST /api/proposals`
- `POST /api/proposals/{id}/decision`
- `GET /api/proposals`
- `GET /api/proposals/{id}/audit`

Proposal creation requires a caller-generated `request_id` UUID. Retrying the same request with
the same UUID returns the original proposal; reusing it with different inputs is rejected.

## MCP tools

- `analyze_replay`
- `create_paper_proposal`
- `approve_proposal`
- `get_approved_proposal`
- `reserve_approved_execution`
- `record_execution_result`
- `get_audit_timeline`

## Live-mode checklist

Do not enable live mode until all items pass:

1. Tests pass.
2. PostgreSQL migrations are current.
3. Replay and paper demonstrations work.
4. Binance MCP is authenticated in its supported host.
5. An isolated Agentic sub-account exists.
6. Only Market Data, Account and Spot scopes are granted.
7. The current symbol filters and minimum notional were fetched from Binance.
8. The proposal passed every deterministic check.
9. The proposal is approved and unexpired.
10. The user verifies Binance's final confirmation details.

## Important demo-data note

The bundled datasets are explicitly labelled synthetic so the project is runnable immediately.
Before submission, record and add a genuine historical Binance dataset with source timestamps,
then retain the synthetic datasets as safety-test fixtures. Never misrepresent synthetic data as
historical exchange data.

## Disclaimer

SentinelFlow is a hackathon prototype for market surveillance and controlled tool orchestration.
It is not financial advice and does not promise profitable results. Crypto trading can result in
loss of capital.
