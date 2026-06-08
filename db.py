from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, Text, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func  
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# 비동기 엔진
engine = create_async_engine(DATABASE_URL, echo=True)

# 비동기 세션
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False
)

# Base 클래스
Base = declarative_base()

# 의존성 주입용
async def get_db():
    async with SessionLocal() as db:
        yield db

# 모델 클래스들
class User(Base):                                                 # 유저 테이블
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(200), nullable=False)
    nickname = Column(String(50), nullable=False)
    goal_minutes = Column(Integer, default=120)
    default_focus_time = Column(Integer, default=25)
    default_break_time = Column(Integer, default=5)
    ai_mode = Column(String(20))
    created_at = Column(DateTime, default=func.now())
    exp = Column(Integer, default=0, nullable=False)

class PomodoroSession(Base):                                     # 포모도로 세션 테이블
    __tablename__ = "pomodoro_sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    total_duration = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("user_id", "date"),)

class SessionDetail(Base):                                       # 세션 상세 테이블
    __tablename__ = "session_details"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("pomodoro_sessions.id"))
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    duration = Column(Integer)
    is_completed = Column(Boolean, default=False)
    session_type = Column(String(10))

class Memo(Base):                                                # 메모 테이블
    __tablename__ = "memos"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(Text)
    content = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now())

class Todo(Base):                                                # 투두 테이블
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    content = Column(Text)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

class StudyRecord(Base):                                         # 공부기록 테이블
    __tablename__ = "study_records"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    total_minutes = Column(Integer, default=0)
    completed_sessions = Column(Integer, default=0)
    goal_achieved = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("user_id", "date"),)

class AiLog(Base):                                              # AI 로그 테이블
    __tablename__ = "ai_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    mode = Column(String(20))
    created_at = Column(DateTime, default=func.now())

class Track(Base):                                               # 트랙 테이블
    __tablename__ = "track"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    file_url = Column(String, nullable=False)


class UserTrackSetting(Base):                                    # 유저별 트랙 세팅 테이블
    __tablename__ = "user_track_setting"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    track_id = Column(Integer, ForeignKey("track.id"), nullable=False)
    is_checked = Column(Boolean, default=False)
    is_favorite = Column(Boolean, default=False)
    order_index = Column(Integer)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "track_id", name="uq_user_track"),
    )