import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.fever_intake import router as fever_intake_router
from src.api.routers.result import router as result_router
from src.api.routes import router
from src.config import get_settings
from src.database import configure_database, create_tables, dispose_database
from src.middleware.auth import RoleAuthorizationMiddleware
from src.services.infra import provider_router
from src.ui.static_files import build_demo_static_app


def _configure_app_logging(level: str) -> None:
    """Cho log của chính dự án (`vmedtriage.*`) hiện ra khi chạy bằng `uvicorn src.main:app`.

    Uvicorn chỉ cấu hình logger của riêng nó; mọi logger khác rơi về root logger, mặc định ở mức
    WARNING và không có handler - nên `graph_triage.decided`/`graph_triage.model` (đều là INFO) biến
    mất hoàn toàn và chỉ khi HỎNG mới thấy gì đó. Gọi ở lifespan, tức là SAU khi uvicorn đã dựng
    xong cấu hình logging của nó, nên handler thêm ở đây không bị ghi đè.

    Đặt trên logger `vmedtriage` thay vì root: bật INFO cho root sẽ kéo theo log nội bộ của httpx,
    sqlalchemy, transformers... làm ngập terminal.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", datefmt="%H:%M:%S"))
    project_logger = logging.getLogger("vmedtriage")
    project_logger.handlers.clear()
    project_logger.addHandler(handler)
    project_logger.setLevel(level)
    project_logger.propagate = False

    # Ở mức DEBUG, mở thêm `httpx` - thư viện mà cả openai lẫn google-genai dùng để gọi API. Đây là
    # thứ duy nhất cho thấy TỪNG lời gọi DeepSeek/OpenAI thật sự đi ra, kèm mã HTTP trả về. Không bật
    # ở INFO vì mỗi lượt hỏi-đáp cũng gọi LLM một lần, 45 lượt là 45 dòng lấp mất log của dự án.
    http_logger = logging.getLogger("httpx")
    http_logger.handlers.clear()
    http_logger.addHandler(handler)
    http_logger.setLevel(logging.INFO if level == "DEBUG" else logging.WARNING)
    http_logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.app_env == "production":
        if settings.jwt_secret_key == "development-only-change-before-production":
            raise RuntimeError("JWT_SECRET_KEY must be changed in production")
        if not settings.nurse_registration_code:
            raise RuntimeError("NURSE_REGISTRATION_CODE must be configured in production")
    _configure_app_logging(settings.log_level)
    configure_database(settings.database_url)
    create_tables()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    # In cấu hình LLM ngay lúc khởi động: sai model/thiếu key là lỗi cấu hình hay gặp nhất, và triệu
    # chứng của nó (agent trả lời bằng câu mẫu) rất giống lỗi logic nếu không thấy dòng này.
    print(f"LLM: {provider_router.describe_selection()}")
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

# Luồng bệnh nhân khai triệu chứng là POST /chat (trong `router`) - xem docstring `routes.chat`.
# `cases_router` (POST /cases, POST /cases/{id}/responses) và `intake_router` (/intake/*) đã bị gỡ
# ngày 2026-08-16: cả hai chạy pipeline rule-based cũ / luồng demo, không frontend hay test nào gọi.
app.include_router(router, prefix="/api/v1")
app.include_router(result_router, prefix="/api/v1")
app.include_router(fever_intake_router, prefix="/api/v1")


@app.middleware("http")
async def prevent_demo_asset_caching(request, call_next):
    """Ensure the demo cannot keep running stale JavaScript after an update."""
    response = await call_next(request)
    if request.url.path in {"/", "/index.html"} or request.url.path.endswith((".js", ".css")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


app.mount("/", build_demo_static_app(), name="demo-ui")
