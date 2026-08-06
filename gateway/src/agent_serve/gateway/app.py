from fastapi import FastAPI

from .lifespan import lifespan
from .routes import chat, health, metrics


def create_app() -> FastAPI:
    app = FastAPI(
        title="agent-serve",
        description="Session-affinity LLM serving gateway for agentic traffic",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(chat.router)
    app.include_router(health.router)
    app.include_router(metrics.router)

    return app
