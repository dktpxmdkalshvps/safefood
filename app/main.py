from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import STATIC_DIR, ALLOWED_ORIGINS
from app.routers import menus

app = FastAPI(
    title="SafeMeal — 관광 음식메뉴판 데이터 정제 및 검색 서비스",
    description=(
        "AI Hub 관광 음식메뉴판 데이터의 품질 결함(맵기 결측, 알레르기 오태깅, "
        "번역 왜곡, 요금표 오염)을 오프라인 규칙 기반 엔진으로 방어하는 검색 API."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(menus.router)

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
