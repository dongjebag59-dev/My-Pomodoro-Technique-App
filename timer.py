from fastapi import APIRouter, Depends, Response
from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func
from datetime import date, datetime
from pydantic import BaseModel
from typing import Optional, List
import os
from db import get_db, User, Memo, PomodoroSession, SessionDetail
from db import Track, UserTrackSetting
from user import get_current_user, calc_level

router = APIRouter(prefix="/timer")

# =====pydantic=====
class SessionResult(BaseModel):
    started_at : datetime
    ended_at : datetime
    duration : int
    exp: int
    session_type: Optional[str] = "focus"

class MemoWrite(BaseModel):
    id: Optional[int] = None
    title: str
    content: str

class TrackCheckUpdate(BaseModel):
    is_checked: bool

class TrackFavoriteUpdate(BaseModel):
    is_favorite: bool

class TrackOrderUpdate(BaseModel):
    track_id: int
    order_index: int


# =======유틸========

# user.py에서 가져오는걸로 변경

# # 임시 테스트용
# async def get_current_user(
#     token: str | None = None,   # 토큰 무시
#     db: AsyncSession = Depends(get_db)
# ) -> User:
#     # 임시로 항상 첫 번째 유저 반환
#     result = await db.execute(select(User).limit(1))
#     user = result.scalar_one_or_none()
#     if user:
#         await db.refresh(user)
#     if not user:
#         # 유저가 없으면 테스트용 더미 유저 생성
#         user = User(
#             email="test@example.com",
#             password="1234",
#             nickname="tester"
#         )
#         db.add(user)
#         await db.commit()
#         await db.refresh(user)

#     return user



# ====엔드포인트====

# 타이틀 페이지(타이머)
@router.get("/")
async def timer_page():
    file_path = os.path.join("templates","timer.html")
    return FileResponse(file_path)

# 모바일 페이지 욕심을 위한 api 분리
@router.get("/api/timer-data")
async def timer_data(current_user: User = Depends(get_current_user)):
    return {
        "logged_in": True,
        "focus_time": current_user.default_focus_time,
        "break_time": current_user.default_break_time,
        "level": calc_level(current_user.exp),
        "streak": current_user.streak or 0,
    }

@router.get("/api/memos")
async def memos_data(current_user: User = Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    result = await db.execute(
        select(Memo.id, Memo.title).filter(Memo.user_id == current_user.id)
    )
    rows = result.mappings().all()
    memos = [{"id": row["id"], "title": row["title"]} for row in rows]
    return {"memos": memos}


#메모 저장시 신규 작성 혹은 수정
@router.put("/memo/write")
async def memo_write(body:MemoWrite, current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):

    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    if body.id:
        memo_id = body.id

        result = await db.execute(
            select(Memo).filter(Memo.id  == memo_id, Memo.user_id == current_user.id)
        )    
        memo = result.scalar_one_or_none()
        if memo:
            memo.title = body.title
            memo.content = body.content
            memo.updated_at = func.now()
        else:
            raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.")
    else:
        memo = Memo(
            user_id = current_user.id,
            title=body.title,
            content=body.content,
        )
        db.add(memo)
    
    await db.commit()
    await db.refresh(memo)
    return {"message":"메모 저장 완료!", "memo": {"id": memo.id, "title": memo.title, "content": memo.content}}

#메모 삭제
@router.delete("/memo/{memo_id}")
async def memo_delete(memo_id: int, current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    result = await db.execute(
        select(Memo).filter(Memo.id == memo_id, Memo.user_id == current_user.id)
    )
    memo = result.scalar_one_or_none()

    if not memo:
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.")

    await db.delete(memo)
    await db.commit()

    return {"message": "메모 삭제 완료!", "id": memo_id}

#프론트에서 메모 타이틀 클릭시 해당 메모 content 호출
@router.get("/memo/{memo_id}")
async def memo_content(memo_id: int, current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    
    result = await db.execute(select(Memo).filter(Memo.id == memo_id, Memo.user_id == current_user.id))
    memo = result.scalar_one_or_none()

    if not memo:
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.")
    
    return {"id": memo.id, "title": memo.title, "content": memo.content}

#프론트에서 타이머 종료시 해당 세션 저장
@router.post("/api/session-end")
async def session_end(body:SessionResult, current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):

    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    
    result = await db.execute(
        select(PomodoroSession).filter(
            PomodoroSession.user_id == current_user.id, 
            PomodoroSession.date == date.today()
            )
        )
    pomodoro_session = result.scalar_one_or_none()

    if not pomodoro_session:
        pomodoro_session = PomodoroSession(
            user_id = current_user.id,
            date=date.today()
        )
        db.add(pomodoro_session)
        await db.commit()
        await db.refresh(pomodoro_session)

    session_detail = SessionDetail(
        session_id = pomodoro_session.id,
        started_at = body.started_at,
        ended_at = body.ended_at,
        duration = body.duration,
        is_completed = True,
        session_type = body.session_type or "focus",
    )
    db.add(session_detail)
    
    pomodoro_session.total_duration += body.duration

    # 경험치 부분
    current_user.exp = (current_user.exp or 0) + max(0, min(body.exp, 500 ))  # 한 세션 최대 경험치 캡 500으로 설정
    db.add(current_user)

    await db.commit()
    await db.refresh(session_detail)
    await db.refresh(pomodoro_session)
    await db.refresh(current_user)
    
    return Response(status_code=204)

# 음원 불러오기
@router.get("/tracks")
async def load_tracks(current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    user_id = current_user.id  # 미리 꺼내서 변수에 저장

    # 모든 트랙 가져오기
    all_tracks = await db.execute(select(Track))
    all_tracks = all_tracks.scalars().all()

    # 유저의 설정 가져오기
    user_settings = await db.execute(
        select(UserTrackSetting).filter(UserTrackSetting.user_id == user_id)
    )
    user_settings = user_settings.scalars().all()
    existing_ids = {s.track_id for s in user_settings}

    # 없는 track_id 자동 추가
    for track in all_tracks:
        if track.id not in existing_ids:
            new_setting = UserTrackSetting(
                user_id=user_id,
                track_id=track.id,
                is_checked=True,
                is_favorite=False,
                order_index=len(user_settings) + 1
            )
            db.add(new_setting)
            user_settings.append(new_setting)

    await db.commit()

    # 조인해서 결과 반환
    result = await db.execute(
        select(UserTrackSetting, Track)
        .join(Track, UserTrackSetting.track_id == Track.id)
        .filter(UserTrackSetting.user_id == user_id)
        .order_by(UserTrackSetting.order_index.asc())
    )
    rows = result.all()

    tracks = []
    for setting, track in rows:
        tracks.append({
            "id": track.id,
            "title": track.title,
            "file_url": track.file_url,
            "is_checked": setting.is_checked,
            "is_favorite": setting.is_favorite,
            "order_index": setting.order_index,
        })
    return {"tracks": tracks}

# 체크 상태 변경시 업데이트
@router.put("/tracks/{track_id}/check")
async def update_track_check(track_id: int, body: TrackCheckUpdate,
                             current_user=Depends(get_current_user),
                             db: AsyncSession=Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    result = await db.execute(
        select(UserTrackSetting).filter(
            UserTrackSetting.user_id == current_user.id,
            UserTrackSetting.track_id == track_id
        )
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="트랙 설정을 찾을 수 없습니다.")

    setting.is_checked = body.is_checked
    await db.commit()
    await db.refresh(setting)

    return {"message": "체크 업데이트 완료", "track_id": track_id, "is_checked": setting.is_checked}

# 즐겨찾기 상태 변경시 업데이트
@router.put("/tracks/{track_id}/favorite")
async def update_track_favorite(track_id: int, body: TrackFavoriteUpdate,
                                current_user=Depends(get_current_user),
                                db: AsyncSession=Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    result = await db.execute(
        select(UserTrackSetting).filter(
            UserTrackSetting.user_id == current_user.id,
            UserTrackSetting.track_id == track_id
        )
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="트랙 설정을 찾을 수 없습니다.")

    setting.is_favorite = body.is_favorite
    await db.commit()
    await db.refresh(setting)

    return {"message": "즐겨찾기 업데이트 완료", "track_id": track_id, "is_favorite": setting.is_favorite}


# 순서 변경시 업데이트
@router.put("/tracks/order")
async def update_track_order(body: List[TrackOrderUpdate],
                             current_user=Depends(get_current_user),
                             db: AsyncSession=Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    for item in body:
        result = await db.execute(
            select(UserTrackSetting).filter(
                UserTrackSetting.user_id == current_user.id,
                UserTrackSetting.track_id == item.track_id
            )
        )
        setting = result.scalar_one_or_none()
        if not setting:
            raise HTTPException(status_code=404, detail=f"track_id {item.track_id}의 트랙 설정을 찾을 수 없습니다.")
        setting.order_index = item.order_index

    await db.commit()
    return {"message": "순서 업데이트 완료", "updated": [item.model_dump() for item in body]}


# 오늘 공부한 사람 수 (소셜 지표)
@router.get("/api/active-users")
async def active_users_today(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(func.count()).select_from(PomodoroSession).where(
            PomodoroSession.date == date.today()
        )
    )
    count = result.scalar() or 0
    return {"count": count}