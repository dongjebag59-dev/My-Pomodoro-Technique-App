import asyncio
import json
import os
import random
import string

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from db import get_db, StudyRoom, RoomMember, User
from user import get_current_user, SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/room", tags=["room"])

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ==================== 연결 관리자 ====================

class ConnectionManager:
    def __init__(self):
        # room_code -> {user_id -> {ws, nickname, status}}
        self._ws: dict[str, dict[int, dict]] = {}
        # room_code -> subscriber asyncio task
        self._sub_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, room_code: str, websocket: WebSocket, user_id: int, nickname: str):
        await websocket.accept()
        if room_code not in self._ws:
            self._ws[room_code] = {}

        # 재연결: 기존 소켓 닫기
        if user_id in self._ws[room_code]:
            try:
                await self._ws[room_code][user_id]["ws"].close()
            except Exception:
                pass

        self._ws[room_code][user_id] = {"ws": websocket, "nickname": nickname, "status": "idle"}

        # Redis에 멤버 상태 저장 (서버 재시작 시 초기 상태 복원용)
        r = await _get_redis()
        await r.hset(f"room:{room_code}:members", user_id,
                     json.dumps({"nickname": nickname, "status": "idle"}))
        await r.expire(f"room:{room_code}:members", 86400)

        # 이 룸의 pub/sub 수신 태스크가 없으면 시작
        if room_code not in self._sub_tasks:
            self._sub_tasks[room_code] = asyncio.create_task(
                self._subscribe(room_code)
            )

    def disconnect(self, room_code: str, user_id: int):
        if room_code not in self._ws:
            return
        self._ws[room_code].pop(user_id, None)

        asyncio.create_task(self._redis_remove(room_code, user_id))

        if not self._ws[room_code]:
            del self._ws[room_code]
            task = self._sub_tasks.pop(room_code, None)
            if task:
                task.cancel()

    async def _redis_remove(self, room_code: str, user_id: int):
        try:
            r = await _get_redis()
            await r.hdel(f"room:{room_code}:members", user_id)
        except Exception:
            pass

    def get_state(self, room_code: str) -> list[dict]:
        return [
            {"user_id": uid, "nickname": info["nickname"], "status": info["status"]}
            for uid, info in self._ws.get(room_code, {}).items()
        ]

    def set_status(self, room_code: str, user_id: int, status: str):
        if room_code in self._ws and user_id in self._ws[room_code]:
            self._ws[room_code][user_id]["status"] = status
            nickname = self._ws[room_code][user_id]["nickname"]
            asyncio.create_task(self._redis_update_status(room_code, user_id, nickname, status))

    async def _redis_update_status(self, room_code: str, user_id: int, nickname: str, status: str):
        try:
            r = await _get_redis()
            await r.hset(f"room:{room_code}:members", user_id,
                         json.dumps({"nickname": nickname, "status": status}))
        except Exception:
            pass

    async def broadcast(self, room_code: str, message: dict):
        """Redis pub/sub으로 발행 → 모든 워커의 구독자가 수신해 로컬 소켓에 전달."""
        try:
            r = await _get_redis()
            await r.publish(f"room_msg:{room_code}", json.dumps(message))
        except Exception:
            # Redis 장애 시 로컬 직접 전송으로 폴백
            await self._local_send(room_code, message)

    async def _local_send(self, room_code: str, message: dict):
        dead = []
        for uid, info in list(self._ws.get(room_code, {}).items()):
            try:
                await info["ws"].send_json(message)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self._ws.get(room_code, {}).pop(uid, None)

    async def _subscribe(self, room_code: str):
        """Redis 채널 구독 → 메시지 수신 시 이 워커의 소켓들에 전달."""
        try:
            r = await _get_redis()
            async with r.pubsub() as pubsub:
                await pubsub.subscribe(f"room_msg:{room_code}")
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        try:
                            data = json.loads(msg["data"])
                            await self._local_send(room_code, data)
                        except Exception:
                            pass
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


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
        if not (await db.execute(select(StudyRoom).where(StudyRoom.code == code))).scalars().first():
            break

    room = StudyRoom(code=code, host_user_id=current_user.id, name=body.name or "스터디룸")
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return {"code": room.code, "name": room.name}


@router.get("/info/{code}")
async def room_info(code: str, db: AsyncSession = Depends(get_db)):
    room = (await db.execute(
        select(StudyRoom).where(StudyRoom.code == code, StudyRoom.is_active == True)
    )).scalars().first()
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

    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        await websocket.close(code=1008)
        return

    if not (await db.execute(
        select(StudyRoom).where(StudyRoom.code == room_code, StudyRoom.is_active == True)
    )).scalars().first():
        await websocket.close(code=1011)
        return

    # RoomMember 기록 (upsert 방식: 이미 있으면 skip)
    room_row = (await db.execute(
        select(StudyRoom).where(StudyRoom.code == room_code)
    )).scalars().first()
    existing_member = (await db.execute(
        select(RoomMember).where(RoomMember.room_id == room_row.id, RoomMember.user_id == user_id)
    )).scalars().first()
    if not existing_member:
        db.add(RoomMember(room_id=room_row.id, user_id=user_id))
        await db.commit()

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
            if data.get("type") == "status_update":
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
        manager.disconnect(room_code, user_id)
        remaining = manager.get_state(room_code)
        await manager.broadcast(room_code, {
            "type": "member_leave",
            "user_id": user_id,
            "nickname": user.nickname,
            "members": remaining,
        })
        # 호스트 퇴장 또는 마지막 멤버 퇴장 시 방 비활성화
        if not remaining or room_row.host_user_id == user_id:
            room_row.is_active = False
            await db.commit()
