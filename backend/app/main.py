"""ESP32 IoT API 서버.

실행 (backend 폴더에서):
  Supabase 사용:   .venv\\Scripts\\python -m uvicorn app.main:app --reload --env-file .env
  Supabase 없이:   APP_MODE=memory 로 실행 (README 참고)
API 문서: http://127.0.0.1:8000/docs
"""
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from .config import get_settings
from .exceptions import AppError
from .routers import auth, board, devices

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.check()  # 환경 변수가 빠졌으면 서버가 뜨기 전에 알려 준다
    logger.info("APP_MODE=%s, CORS_ORIGINS=%s", settings.app_mode, settings.cors_origins)
    yield


app = FastAPI(
    title="ESP32 IoT API",
    description="XIAO ESP32S3 센서값 수집과 LED 제어. 인증과 저장은 Supabase.",
    version="1.0.0",
    lifespan=lifespan,
)

# 대시보드(Vercel)는 다른 도메인이라 CORS 허용이 필요하다.
# 인증을 쿠키가 아니라 Authorization 헤더로 하므로 allow_credentials는 끈다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, devices, board):
    app.include_router(module.router)


@app.exception_handler(AppError)
async def handle_app_error(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message}, headers=exc.headers)


@app.exception_handler(APIError)
async def handle_db_error(_request: Request, exc: APIError):
    logger.error("Supabase DB 오류: %s", exc)
    return JSONResponse(status_code=502, content={"detail": f"데이터베이스 오류: {exc.message}"})


@app.exception_handler(httpx.HTTPError)
async def handle_network_error(_request: Request, exc: httpx.HTTPError):
    logger.error("Supabase 연결 오류: %s", exc)
    return JSONResponse(status_code=502, content={"detail": "Supabase에 연결하지 못했습니다."})


@app.get("/", include_in_schema=False)
def root():
    return {"name": "ESP32 IoT API", "docs": "/docs"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
