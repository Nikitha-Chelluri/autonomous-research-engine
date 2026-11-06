from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.research import router as research_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Autonomous Multi-Agent Research Engine",
    description="LangGraph orchestration for competitive intelligence reports",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(research_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
