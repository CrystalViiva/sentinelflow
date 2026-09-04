# Changelog

## 0.2.0

- Replaced row-generated idempotency values with caller-controlled request UUIDs.
- Idempotent retries now return the original proposal.
- Reusing a request UUID with a changed signal or amount is rejected.
- Database uniqueness remains the final concurrency guard.
- Added MCP tool-discovery coverage using the real installed MCP client/server runtime.
- Added an optional disposable-PostgreSQL integration test.
- Added a one-command smoke test covering migrations, FastAPI, proposal retry, conflict rejection,
  approval and audit history.

## 0.1.0

- Initial hackathon-ready replay, scoring, risk, proposal, audit, API, dashboard and MCP build.
