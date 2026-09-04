from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="SentinelFlow",
    description="Explainable market surveillance and deterministic trade-risk controls.",
    version="0.2.0",
)
app.include_router(router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "SentinelFlow",
        "docs": "/docs",
        "safety": "Live trading is disabled by default.",
    }
