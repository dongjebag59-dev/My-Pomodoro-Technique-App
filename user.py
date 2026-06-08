from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
# from typing import Optional
from datetime import datetime, timedelta, timezone
import os

from db import get_db, User

router = APIRouter(prefix="/users", tags=["users"])

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", 2))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


# --- Pydantic 요청 스키마 ---

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, description="비밀번호 (최소 6자)")
    nickname: str = Field(min_length=1, max_length=20, description="닉네임 (1~20자)")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SettingsRequest(BaseModel):
    # 24시간 = 1440분
    goal_minutes: int = Field(gt=0, le=1440, description="목표 시간 (분, 0보다 크고 1440 이하)")
    default_focus_time: int = Field(gt=0, le=1440, description="기본 집중 시간 (분, 0보다 크고 1440 이하)")
    default_break_time: int = Field(gt=0, le=1440, description="기본 휴식 시간 (분, 0보다 크고 1440 이하)")


# --- Pydantic 응답 스키마 ---

class SignupResponse(BaseModel):
    message: str
    user_id: int
    created_at: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str


class MypageResponse(BaseModel):
    email: str
    nickname: str
    goal_minutes: int
    default_focus_time: int
    default_break_time: int
    created_at: str
    experience: int
    level: int


class SettingsResponse(BaseModel):
    message: str


# --- 유틸 함수 ---

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def calc_level(exp: int) -> int:
    # 100분마다 레벨 1 상승, 최초 레벨 1
    return exp // 100 + 1


# --- 의존성: 현재 유저 조회 ---

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


# --- 페이지 라우터 ---

@router.get("/login-page")
async def login_page():
    return FileResponse(os.path.join("templates", "login.html"))

@router.get("/signup-page")
async def signup_page():
    return FileResponse(os.path.join("templates", "signup.html"))

@router.get("/mypage-page")
async def mypage_page():
    return FileResponse(os.path.join("templates", "mypage.html"))

@router.get("/settings-page")
async def settings_page():
    return FileResponse(os.path.join("templates", "settings.html"))


# --- 엔드포인트 ---

# 회원가입
@router.post("/signup", response_model=SignupResponse)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).filter(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    try:
        new_user = User(
            email=body.email,
            password=hash_password(body.password),
            nickname=body.nickname
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Email already exists")

    return SignupResponse(
        message="signup success",
        user_id=new_user.id,
        created_at=new_user.created_at.isoformat()
    )


# 로그인
@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).filter(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")

    token = create_access_token({"user_id": user.id})

    return LoginResponse(access_token=token, token_type="bearer")


# 마이페이지 조회
@router.get("/mypage", response_model=MypageResponse)
async def mypage(user: User = Depends(get_current_user)):
    return MypageResponse(
        email=user.email,
        nickname=user.nickname,
        goal_minutes=user.goal_minutes,
        default_focus_time=user.default_focus_time,
        default_break_time=user.default_break_time,
        created_at=user.created_at.isoformat(),
        experience=user.exp,
        level=calc_level(user.exp)
    )


# 사용자 설정 수정
@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    body: SettingsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user.goal_minutes = body.goal_minutes
    user.default_focus_time = body.default_focus_time
    user.default_break_time = body.default_break_time
    await db.commit()

    return SettingsResponse(message="settings updated")

# 닉네임 수정
class NicknameRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=20, description="닉네임 (1~20자)")

@router.put("/nickname", response_model=SettingsResponse)
async def update_nickname(
    body: NicknameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user.nickname = body.nickname
    await db.commit()
    return SettingsResponse(message="nickname updated")
