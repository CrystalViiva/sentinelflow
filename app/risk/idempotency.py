import uuid


def proposal_idempotency_key(request_id: uuid.UUID) -> str:
    """Build a stable key from a caller-controlled request identifier."""
    return f"sf-proposal:{request_id}"
