# my_calendar.py
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db, Todo, StudyRecord, Memo
from fastapi.responses import FileResponse
# from fastapi import Request # Depends 옆에 Request 추가
from db import get_db
from db import Todo, StudyRecord, Memo
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

router = APIRouter()

@router.get("/calendar")
async def get_calendar():
    file_path = os.path.join("templates","calendar.html")
    return FileResponse(file_path)

# 1. 월간 요약 (나중에 DB 연동 가능)
@router.get("/summary/{year}/{month}")
async def get_month_summary(year: int, month: int, db: AsyncSession = Depends(get_db)):
    return {
        "year": year, 
        "month": month, 
        "results": [{"day": 1, "status": 1}]
    }

# 2. 특정 날짜 정보 조회
@router.get("/daily/{date}")
async def get_daily_info(date: str, db: AsyncSession = Depends(get_db)):
    # 1. 문자열 "2026-03-21"을 진짜 날짜 객체로 변환 (중요!)
    target_date = datetime.strptime(date, "%Y-%m-%d").date()

    # 2. Todo 조회 (target_date 객체를 사용해야 함)
    result = await db.execute(select(Todo).where(Todo.date == target_date))
    todos = result.scalars().all()

    # 3. Memo 조회 (기상님 모델에 맞춰 Memo 가져오기)
    from db import Memo
    memo_result = await db.execute(select(Memo))
    memos = memo_result.scalars().all()

    return {
        "date": date,
        "todos": todos,
        "memos": memos
    }

# 3. 진짜 Todo 추가 (DB 저장 적용)
@router.post("/todo")
async def add_todo(content: str, date: str, db: AsyncSession = Depends(get_db)):
    # ✨ 추가: 글자 "2026-03-28"을 진짜 날짜 객체로 변환
    date_obj = datetime.strptime(date, "%Y-%m-%d").date()

    # 2단계: 진짜 DB 객체 생성
    # date=date 대신 date=date_obj를 넣습니다.
    new_todo = Todo(content=content, date=date_obj, user_id=1)

    db.add(new_todo)
    await db.commit()
    await db.refresh(new_todo)

    return {
        "message": "DB 저장 완료",
        "data": new_todo
    }

# 4. 진짜 학습 시간 기록 (DB 저장 적용)
@router.post("/study-record")
async def record_study(minutes: int, date: str, db: AsyncSession = Depends(get_db)):
    new_record = StudyRecord(minutes=minutes, date=date, user_id=1)
    
    db.add(new_record)
    await db.commit()
    
    return {
        "status": "success",
        "study_time": f"{minutes} minutes",
        "timestamp": datetime.now().isoformat() # ISO 8601 형식
    }

# my_calendar.py

@router.post("/memo")
async def add_memo(title: str, content: str, date: str, db: AsyncSession = Depends(get_db)):
    new_memo = Memo(title=title, content=content, created_at=date, user_id=1)
    
    # 1. 날짜 변환 코드는 그대로 둬도 되지만, Memo에는 안 쓰입니다.
    # 2. Memo 객체 생성 (기상님 설계도에 있는 이름만 사용!)
    new_memo = Memo(
        title=title, 
        content=content, 
        user_id=1
        # ❌ 여기에 date=date_obj 를 절대 넣지 마세요!
    )

    db.add(new_memo)
    await db.commit()
    await db.refresh(new_memo)

    return {"status": "success", "message": "메모가 서버에 저장되었습니다!"}

# 6. 특정 날짜의 메모 조회 (화면에 다시 보여주기용)
# my_calendar.py

@router.get("/memo/{date}")
async def get_memo(date: str, db: AsyncSession = Depends(get_db)):
    # 해당 날짜의 메모가 있는지 확인
    result = await db.execute(select(Memo).where(Memo.date == date))
    memo = result.scalars().first()
    
    if not memo:
        return {"title": "", "content": ""} # 메모가 없으면 빈 값 전송
    
    return memo
    # Memo.date 가 없으므로, 일단 모든 메모를 가져오는 방식으로 수정합니다.
    # (나중에 기상님께 특정 날짜 메모만 조회하는 법을 물어보셔야 할 수도 있어요!)
    result = await db.execute(select(Memo)) 
    memos = result.scalars().all()

    return memos

# my_calendar.py 맨 밑에 추가
from datetime import date

@router.get("/monthly/{year}/{month}")
async def get_monthly_info(year: int, month: int, db: AsyncSession = Depends(get_db)):
    # 해당 월의 1일부터 다음 달 1일 전까지 조회
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    # 한 달 동안의 모든 Todo 가져오기
    result = await db.execute(
        select(Todo).where(Todo.date >= start_date, Todo.date < end_date)
    )
    return result.scalars().all()
