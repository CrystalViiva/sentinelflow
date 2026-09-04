"""Exercise migrations, API routes, idempotency, approval and execution reservation."""

import subprocess
import sys
import uuid

from fastapi.testclient import TestClient


def main() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    from app.main import app

    client = TestClient(app)
    health = client.get("/api/health")
    health.raise_for_status()

    signal_response = client.post(
        "/api/replay/analyze", params={"dataset": "sol_accumulation.json"}
    )
    signal_response.raise_for_status()
    signal = signal_response.json()

    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "signal_id": signal["id"],
        "quote_amount": "10",
        "min_notional": "5",
        "available_balance": "100",
    }
    first = client.post("/api/proposals", json=payload)
    first.raise_for_status()
    repeated = client.post("/api/proposals", json=payload)
    repeated.raise_for_status()
    assert first.json()["id"] == repeated.json()["id"], "Idempotent retry created a new proposal"

    conflicting_payload = {**payload, "quote_amount": "11"}
    conflict = client.post("/api/proposals", json=conflicting_payload)
    assert conflict.status_code == 409, "Reused request_id with changed payload was not rejected"

    proposal = first.json()
    approval = client.post(
        f"/api/proposals/{proposal['id']}/decision",
        json={"expected_version": proposal["version"], "approved": True},
    )
    approval.raise_for_status()
    assert approval.json()["status"] == "APPROVED"

    audit = client.get(f"/api/proposals/{proposal['id']}/audit")
    audit.raise_for_status()
    assert len(audit.json()) >= 3

    print("SMOKE TEST PASSED")
    print(f"Signal: {signal['id']} ({signal['score']}/100)")
    print(f"Proposal: {proposal['id']} (idempotent retry returned same ID)")
    print("Conflicting idempotency payload: REJECTED")
    print(f"Approval: {approval.json()['status']}")
    print(f"Audit events: {len(audit.json())}")


if __name__ == "__main__":
    main()
