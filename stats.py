from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, extract, func
from db import get_db, StudyRecord, User
from user import get_current_user, calc_level
from datetime import date, timedelta
from pydantic import BaseModel
from typing import Dict
from limiter import limiter

router = APIRouter()
stats_router = APIRouter(prefix="/stats")

# 요청 스키마
class SessionRequest(BaseModel):
    total_minutes: int
    completed_sessions: int
    exp: int = 0  # 이 세션에서 획득한 경험치 (timer.py의 /api/session-end를 대체)

# 세션 저장
@router.post("/sessions")
@limiter.limit("30/minute")
async def create_session(
    request: Request,
    body: SessionRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    today = date.today()
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == current_user.id,
            StudyRecord.date == today
        )
    )
    record = result.scalars().first()

    if record:
        record.total_minutes = min(record.total_minutes + body.total_minutes, 1440)
        record.completed_sessions += body.completed_sessions
    else:
        record = StudyRecord(
            user_id=current_user.id,
            date=today,
            total_minutes=min(body.total_minutes, 1440),
            completed_sessions=body.completed_sessions,
            goal_achieved=False
        )
        db.add(record)

    record.goal_achieved = (record.total_minutes >= current_user.goal_minutes)

    # 경험치 + 레벨 (한 세션 최대 500 캡)
    current_user.exp = (current_user.exp or 0) + max(0, min(body.exp, 500))

    # 스트릭 계산
    yesterday = today - timedelta(days=1)
    last_date = current_user.last_study_date
    if last_date == yesterday:
        current_user.streak = (current_user.streak or 0) + 1
    elif last_date == today:
        pass  # 오늘 이미 공부 기록 있으면 유지
    else:
        current_user.streak = 1  # 연속 끊김 또는 첫 공부
    current_user.last_study_date = today
    current_user.level = calc_level(current_user.exp)
    db.add(current_user)

    await db.commit()
    return {"message": "저장 완료", "goal_achieved": record.goal_achieved, "streak": current_user.streak}

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


@stats_router.get("/summary")
async def get_summary(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    week_res = await db.execute(
        select(func.sum(StudyRecord.total_minutes)).where(
            StudyRecord.user_id == current_user.id,
            StudyRecord.date >= week_start,
        )
    )
    month_res = await db.execute(
        select(func.sum(StudyRecord.total_minutes)).where(
            StudyRecord.user_id == current_user.id,
            StudyRecord.date >= month_start,
        )
    )
    # 이번 달 달성률
    total_days_res = await db.execute(
        select(func.count()).where(
            StudyRecord.user_id == current_user.id,
            StudyRecord.date >= month_start,
        )
    )
    achieved_days_res = await db.execute(
        select(func.count()).where(
            StudyRecord.user_id == current_user.id,
            StudyRecord.date >= month_start,
            StudyRecord.goal_achieved == True,
        )
    )
    # 최대 스트릭 계산: User.streak과 동일하게 '공부한 날' 기준 (goal_achieved 무관)
    all_dates = (await db.execute(
        select(StudyRecord.date)
        .where(StudyRecord.user_id == current_user.id)
        .order_by(StudyRecord.date)
    )).scalars().all()

    max_streak = 0
    cur_streak = 0
    prev_date = None
    for rec_date in all_dates:
        if prev_date and (rec_date - prev_date).days == 1:
            cur_streak += 1
        else:
            cur_streak = 1
        max_streak = max(max_streak, cur_streak)
        prev_date = rec_date

    total_days = total_days_res.scalar() or 0
    achieved_days = achieved_days_res.scalar() or 0
    return {
        "week_minutes": week_res.scalar() or 0,
        "month_minutes": month_res.scalar() or 0,
        "month_achievement_rate": round(achieved_days / total_days * 100) if total_days else 0,
        "max_streak": max_streak,
        "current_streak": current_user.streak or 0,
    }


@stats_router.get("/achievement", response_model=Dict[str, bool])
async def get_achievement(
    year: int,
    month: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudyRecord.date, StudyRecord.goal_achieved).where(
            StudyRecord.user_id == current_user.id,
            extract("year", StudyRecord.date) == year,
            extract("month", StudyRecord.date) == month,
        )
    )
    return {str(row[0]): bool(row[1]) for row in result.all()}


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
