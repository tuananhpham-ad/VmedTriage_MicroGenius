from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config import get_settings
from src.ui.static_files import build_demo_static_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("vmedtriage").info(
        "app.start name=%s env=%s",
        settings.app_name,
        settings.app_env,
    )
    yield
    logging.getLogger("vmedtriage").info("app.stop")


app = FastAPI(
    title="VMedTriage",
    description="Controlled medical triage support pipeline with mandatory human approval",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


app.mount("/", build_demo_static_app(), name="demo-ui")
