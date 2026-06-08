from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import ai_service
import db
# import my_calendar
import stats
import timer
import user
import bgm_import

@asynccontextmanager
async def app_life_span(app: FastAPI):
    async with db.engine.begin() as conn:                  # 종료하면 자동으로 닫힌다.
        await conn.run_sync(db.Base.metadata.create_all)   # 동기 실행 ==> 비동기 실행.
    await bgm_import.seed_tracks()
    yield    

app = FastAPI(lifespan=app_life_span)

app.mount("/bgms", StaticFiles(directory="bgms"), name="bgms")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(timer.router)
# app.include_router(my_calendar.router)
app.include_router(ai_service.router)
app.include_router(user.router)
app.include_router(stats.router)
app.include_router(stats.stats_router)

@app.get("/")
async def root():
    return RedirectResponse(url="/timer")