# What to do after downloading SentinelFlow

Follow these in order. Do not enable live mode during initial setup.

## Part A — Run the application locally

1. Extract the ZIP into a simple path such as `C:\Users\YourName\Desktop\sentinelflow`.
2. Open the extracted folder in VS Code.
3. Open **Terminal → New Terminal**.
4. Confirm `python --version` shows Python 3.12.x.
5. Run:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

6. Start PostgreSQL with `docker compose up -d postgres`, or create the `sentinelflow` database
   using your installed PostgreSQL/pgAdmin.
7. Open `.env` and correct the PostgreSQL username and password if necessary.
8. Run:

```powershell
alembic upgrade head
pytest -q
python scripts/smoke_test.py
```

9. Start the API:

```powershell
uvicorn app.main:app --reload
```

10. Open <http://127.0.0.1:8000/docs>.
11. In a second terminal, activate `.venv` and run:

```powershell
streamlit run app/ui/dashboard.py
```

12. Open <http://localhost:8501>, choose **SOL Accumulation**, and save the replay signal.

## Part B — Add optional Gemini explanations

1. Create a Gemini API key in Google AI Studio.
2. Place only the value in your local `.env`:

```env
GEMINI_API_KEY=your-key-here
```

3. Restart the dashboard. Never commit `.env`.

## Part C — Connect the two MCP servers

1. Configure your MCP host to launch SentinelFlow with the absolute path to `.venv` Python:

```text
C:\full\path\sentinelflow\.venv\Scripts\python.exe -m app.mcp_server.server
```

2. Configure Binance MCP separately using Binance's official instructions and endpoint.
3. Authenticate in the Binance browser page.
4. Grant Market Data, Account and Spot only.
5. Test a read-only market query first.
6. Test Agentic sub-account balance access second.

## Part D — What still requires your action

- Authenticate your own Binance account; nobody can package this authorization for you.
- Add a real recorded Binance replay dataset before final submission.
- Test the current symbol rules/minimum notional before a live order.
- Create a Neon database if you deploy publicly.
- Add your demo video and screenshots to the README.
- Keep real funds out until replay and paper tests pass.

If any command fails, save the complete terminal error and the command that produced it.
