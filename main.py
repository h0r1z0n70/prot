# made by horizon from scratch ;)

from __future__ import annotations
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lib.monitor import start_monitor, stop_monitor
from lib.logger import get_logger
from api import dispatch, health, token

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("up")
    start_monitor()
    yield
    stop_monitor()
    logger.info("down")


app = FastAPI(
    title="what are you doing here?",
    description="system",
    version="3.0.0",
    lifespan=lifespan,
    # Don't expose /docs or /redoc in production
    docs_url=None if os.environ.get("ENV") == "production" else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(dispatch.router)
app.include_router(health.router)
app.include_router(token.router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "Horizon Protector v3",
        "status": "operational",
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "5000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
