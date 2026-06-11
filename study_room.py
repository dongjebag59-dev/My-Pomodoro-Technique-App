from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from jose import jwt, JWTError
import random
import string
import os

from db import get_db, StudyRoom, RoomMember, User
from user import get_current_user, SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/room", tags=["room"])


# ==================== 인메모리 연결 관리 ====================

class ConnectionManager:
    def __init__(self):
        # room_code -> list of member dicts
        self.rooms: dict[str, list[dict]] = {}

    async def connect(self, room_code: str, websocket: WebSocket, user_id: int, nickname: str):
        await websocket.accept()
        if room_code not in self.rooms:
            self.rooms[room_code] = []
        # 동일 유저 재연결 처리
        self.rooms[room_code] = [m for m in self.rooms[room_code] if m["user_id"] != user_id]
        self.rooms[room_code].append({
            "ws": websocket,
            "user_id": user_id,
            "nickname": nickname,
            "status": "idle",
        })

    def disconnect(self, room_code: str, websocket: WebSocket):
        if room_code in self.rooms:
            self.rooms[room_code] = [m for m in self.rooms[room_code] if m["ws"] != websocket]
            if not self.rooms[room_code]:
                del self.rooms[room_code]

    def get_state(self, room_code: str) -> list[dict]:
        return [
            {"user_id": m["user_id"], "nickname": m["nickname"], "status": m["status"]}
            for m in self.rooms.get(room_code, [])
        ]

    def set_status(self, room_code: str, user_id: int, status: str):
        for m in self.rooms.get(room_code, []):
            if m["user_id"] == user_id:
                m["status"] = status
                break

    async def broadcast(self, room_code: str, message: dict):
        dead = []
        for member in self.rooms.get(room_code, []):
            try:
                await member["ws"].send_json(message)
            except Exception:
                dead.append(member)
        for m in dead:
            if room_code in self.rooms:
                self.rooms[room_code].remove(m)


manager = ConnectionManager()


# ==================== 유틸 ====================

def _gen_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ==================== REST 엔드포인트 ====================

class CreateRoomRequest(BaseModel):
    name: Optional[str] = "스터디룸"


@router.post("/create")
async def create_room(
    body: CreateRoomRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for _ in range(10):
        code = _gen_code()
        existing = await db.execute(select(StudyRoom).where(StudyRoom.code == code))
        if not existing.scalars().first():
            break

    room = StudyRoom(code=code, host_user_id=current_user.id, name=body.name or "스터디룸")
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return {"code": room.code, "name": room.name}


@router.get("/info/{code}")
async def room_info(code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(StudyRoom).where(StudyRoom.code == code, StudyRoom.is_active == True)
    )
    room = result.scalars().first()
    if not room:
        raise HTTPException(status_code=404, detail="방을 찾을 수 없습니다.")
    return {"code": room.code, "name": room.name, "members": manager.get_state(code)}


# ==================== WebSocket 엔드포인트 ====================

@router.websocket("/ws/{room_code}")
async def room_ws(
    room_code: str,
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # JWT 검증
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        await websocket.close(code=1008)
        return

    room_result = await db.execute(
        select(StudyRoom).where(StudyRoom.code == room_code, StudyRoom.is_active == True)
    )
    if not room_result.scalars().first():
        await websocket.close(code=1011)
        return

    await manager.connect(room_code, websocket, user_id, user.nickname)
    await manager.broadcast(room_code, {
        "type": "member_join",
        "user_id": user_id,
        "nickname": user.nickname,
        "members": manager.get_state(room_code),
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "status_update":
                status = data.get("status", "idle")
                manager.set_status(room_code, user_id, status)
                await manager.broadcast(room_code, {
                    "type": "status_update",
                    "user_id": user_id,
                    "nickname": user.nickname,
                    "status": status,
                    "members": manager.get_state(room_code),
                })

    except WebSocketDisconnect:
        manager.disconnect(room_code, websocket)
        await manager.broadcast(room_code, {
            "type": "member_leave",
            "user_id": user_id,
            "nickname": user.nickname,
            "members": manager.get_state(room_code),
        })
