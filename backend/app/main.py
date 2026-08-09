from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import current_username, normalize_username, router
from backend.app.core.config import get_settings
from backend.app.db import init_db
from backend.app.mcp_server import peach_mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with peach_mcp.session_manager.run():
        await init_db()
        yield


settings = get_settings()

app = FastAPI(
    title="Peach Interview Companion API",
    description="桃子求职陪练 Agent 后端服务",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def account_context_middleware(request, call_next):
    username = request.headers.get("x-peach-user") or request.query_params.get("username")
    token = current_username.set(normalize_username(username))
    try:
        return await call_next(request)
    finally:
        current_username.reset(token)


app.include_router(router)
app.mount("/mcp", peach_mcp.streamable_http_app())


@app.get("/")
async def root() -> dict:
    return {"name": settings.app_name, "status": "ready"}
