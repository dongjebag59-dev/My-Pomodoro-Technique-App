from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

import ai_service
import db
import my_calendar
import stats
import study_room
import timer
import user
import bgm_import
from limiter import limiter

_SECRET_KEY = os.getenv("SECRET_KEY")
if not _SECRET_KEY:
    raise RuntimeError("SECRET_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")


# 기존 테이블 컬럼 추가 + 외래키 CASCADE 보강
_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS level           INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS streak          INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_study_date DATE",
    # ondelete CASCADE 보강 (기존 FK 삭제 후 재생성)
    "ALTER TABLE memos            DROP CONSTRAINT IF EXISTS memos_user_id_fkey",
    "ALTER TABLE memos            ADD  CONSTRAINT memos_user_id_fkey            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE todos             DROP CONSTRAINT IF EXISTS todos_user_id_fkey",
    "ALTER TABLE todos             ADD  CONSTRAINT todos_user_id_fkey             FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE study_records     DROP CONSTRAINT IF EXISTS study_records_user_id_fkey",
    "ALTER TABLE study_records     ADD  CONSTRAINT study_records_user_id_fkey     FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE pomodoro_sessions DROP CONSTRAINT IF EXISTS pomodoro_sessions_user_id_fkey",
    "ALTER TABLE pomodoro_sessions ADD  CONSTRAINT pomodoro_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE room_members      DROP CONSTRAINT IF EXISTS room_members_user_id_fkey",
    "ALTER TABLE room_members      ADD  CONSTRAINT room_members_user_id_fkey      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE study_rooms       DROP CONSTRAINT IF EXISTS study_rooms_host_user_id_fkey",
    "ALTER TABLE study_rooms       ADD  CONSTRAINT study_rooms_host_user_id_fkey  FOREIGN KEY (host_user_id) REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE ai_logs           DROP CONSTRAINT IF EXISTS ai_logs_user_id_fkey",
    "ALTER TABLE ai_logs           ADD  CONSTRAINT ai_logs_user_id_fkey           FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE user_track_setting DROP CONSTRAINT IF EXISTS user_track_setting_user_id_fkey",
    "ALTER TABLE user_track_setting ADD  CONSTRAINT user_track_setting_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
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
app.include_router(my_calendar.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/timer")
