import json

from google import genai

from app.config import get_settings


def explain_signal(symbol: str, evidence: dict, counter_evidence: list[str]) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        return "AI explanation unavailable. Deterministic analysis and safety controls remain operational."
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = (
        "You are explaining a market-surveillance result, not giving financial advice. "
        "Use only the supplied values, mention uncertainty, make no profit claim, and write at most "
        f"four sentences. Symbol: {symbol}. Evidence: {json.dumps(evidence, default=str)}. "
        f"Counter-evidence: {json.dumps(counter_evidence)}."
    )
    response = client.models.generate_content(model=settings.gemini_model, contents=prompt)
    return response.text or "No explanation was generated."
