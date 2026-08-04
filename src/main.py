from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config import get_settings
from src.database import configure_database, create_tables, dispose_database
from src.middleware.auth import RoleAuthorizationMiddleware
from src.ui.static_files import build_demo_static_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.app_env == "production":
        if settings.jwt_secret_key == "development-only-change-before-production":
            raise RuntimeError("JWT_SECRET_KEY must be changed in production")
        if not settings.nurse_registration_code:
            raise RuntimeError("NURSE_REGISTRATION_CODE must be configured in production")
    configure_database(settings.database_url)
    create_tables()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    yield
    dispose_database()
    print("Shutting down...")


app = FastAPI(
    title="VMedTriage",
    description="Controlled medical triage support pipeline with mandatory human approval",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(RoleAuthorizationMiddleware)
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
