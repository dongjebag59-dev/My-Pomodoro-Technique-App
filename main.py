from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

import ai_service
import db
import stats
import study_room
import timer
import user
import bgm_import


def _get_real_ip(request: Request) -> str:
    return request.headers.get("X-Real-IP") or get_remote_address(request)


limiter = Limiter(key_func=_get_real_ip, default_limits=["120/minute"])


# 기존 테이블에 새 컬럼을 안전하게 추가 (IF NOT EXISTS → 기존 데이터 보존)
_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS level          INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS streak         INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_study_date DATE",
]


async def _run_migrations(conn) -> None:
    for stmt in _MIGRATIONS:
        await conn.execute(text(stmt))


@asynccontextmanager
async def app_life_span(app: FastAPI):
    async with db.engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)  # ① 없는 테이블 생성 (신규 DB)
        await _run_migrations(conn)                        # ② 기존 테이블에 신규 컬럼 추가 (기존 DB)
    await bgm_import.seed_tracks()
    yield


app = FastAPI(lifespan=app_life_span)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.mount("/bgms", StaticFiles(directory="bgms"), name="bgms")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(timer.router)
app.include_router(ai_service.router)
app.include_router(user.router)
app.include_router(stats.router)
app.include_router(stats.stats_router)
app.include_router(study_room.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/timer")
