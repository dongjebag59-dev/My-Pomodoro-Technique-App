from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, extract
from db import get_db, StudyRecord
from user import get_current_user
from datetime import date
from pydantic import BaseModel
from typing import Dict

router = APIRouter()
stats_router = APIRouter(prefix="/stats")

# 요청 스키마
class SessionRequest(BaseModel):
    target_date: date
    total_minutes: int
    completed_sessions: int

# 세션 저장
@router.post("/sessions")
async def create_session(
    body: SessionRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == current_user.id,
            StudyRecord.date == body.target_date
        )
    )
    record = result.scalars().first()

    if record:
        record.total_minutes = min(record.total_minutes + body.total_minutes, 1440)
        record.completed_sessions += body.completed_sessions
    else:
        record = StudyRecord(
            user_id=current_user.id,
            date=body.target_date,
            total_minutes=min(body.total_minutes, 1440),
            completed_sessions=body.completed_sessions,
            goal_achieved=False
        )
        db.add(record)

    record.goal_achieved = (record.total_minutes >= current_user.goal_minutes)

    await db.commit()
    return {"message": "저장 완료", "goal_achieved": record.goal_achieved}

# 일별 통계
@stats_router.get("/daily")
async def get_daily_stats(
    target_date: date,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == current_user.id,
            StudyRecord.date == target_date
        )
    )
    return result.scalars().first()

# 주간 통계
@stats_router.get("/weekly")
async def get_weekly_stats(
    year: int,
    week: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == current_user.id,
            extract("year", StudyRecord.date) == year,
            extract("week", StudyRecord.date) == week
        )
    )
    return result.scalars().all()

# 월간 통계
@stats_router.get("/monthly")
async def get_monthly_stats(
    year: int,
    month: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == current_user.id,
            extract("year", StudyRecord.date) == year,
            extract("month", StudyRecord.date) == month
        )
    )
    return result.scalars().all()

# 년간 통계
@stats_router.get("/yearly")
async def get_yearly_stats(
    year: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == current_user.id,
            extract("year", StudyRecord.date) == year
        )
    )
    return result.scalars().all()


@stats_router.get("/heatmap", response_model=Dict[str, int])
async def get_heatmap(
    year: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(StudyRecord.date, StudyRecord.total_minutes).where(
            StudyRecord.user_id == current_user.id,
            extract("year", StudyRecord.date) == year
        )
    )
    rows = result.all()
    return {str(row[0]): row[1] for row in rows}
