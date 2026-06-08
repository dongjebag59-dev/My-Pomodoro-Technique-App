import asyncio
from collections.abc import AsyncGenerator, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from db import Base, User, get_db


@pytest.fixture(scope="function")
def test_db_url(tmp_path) -> str:
    db_file = tmp_path / "test.db"
    return f"sqlite+aiosqlite:///{db_file}"


@pytest.fixture(scope="function")
def test_engine(test_db_url: str):
    engine = create_async_engine(test_db_url, echo=False)
    try:
        yield engine
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture(scope="function")
def testing_session_local(test_engine):
    return sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest.fixture(scope="function", autouse=True)
def reset_test_db(test_engine):
    async def _reset() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())
    yield


@pytest.fixture(scope="function")
def override_get_db(testing_session_local) -> Callable[[], AsyncGenerator[AsyncSession, None]]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with testing_session_local() as session:
            yield session

    return _override_get_db


@pytest.fixture(scope="function")
def app_factory(override_get_db):
    def _build_app(*routers, dependency_overrides: dict | None = None) -> FastAPI:
        app = FastAPI()

        for router in routers:
            app.include_router(router)

        app.dependency_overrides[get_db] = override_get_db

        if dependency_overrides:
            app.dependency_overrides.update(dependency_overrides)

        return app

    return _build_app


@pytest.fixture(scope="function")
def client_factory():
    def _build_client(app: FastAPI) -> TestClient:
        return TestClient(app)

    return _build_client


@pytest.fixture(scope="function")
def create_user(testing_session_local):
    def _create_user(
        *,
        id: int | None = None,
        email: str = "test@example.com",
        password: str = "hashed-password",
        nickname: str = "tester",
        goal_minutes: int = 120,
        default_focus_time: int = 25,
        default_break_time: int = 5,
        ai_mode: str | None = None,
        exp: int = 0,
    ) -> User:
        async def _inner() -> User:
            async with testing_session_local() as session:
                user = User(
                    email=email,
                    password=password,
                    nickname=nickname,
                    goal_minutes=goal_minutes,
                    default_focus_time=default_focus_time,
                    default_break_time=default_break_time,
                    ai_mode=ai_mode,
                    exp=exp,
                )
                if id is not None:
                    user.id = id

                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user

        return asyncio.run(_inner())

    return _create_user


@pytest.fixture(scope="function")
def get_user_by_email(testing_session_local):
    def _get_user_by_email(email: str) -> User | None:
        async def _inner() -> User | None:
            async with testing_session_local() as session:
                result = await session.execute(select(User).where(User.email == email))
                return result.scalar_one_or_none()

        return asyncio.run(_inner())

    return _get_user_by_email


@pytest.fixture(scope="function")
def current_user_override_factory(testing_session_local):
    def _factory(
        *,
        email: str = "test@example.com",
        password: str = "hashed-password",
        nickname: str = "tester",
        goal_minutes: int = 120,
        default_focus_time: int = 25,
        default_break_time: int = 5,
        ai_mode: str | None = None,
        exp: int = 0,
    ):
        async def _override_current_user() -> User:
            async with testing_session_local() as session:
                result = await session.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()

                if user is None:
                    user = User(
                        email=email,
                        password=password,
                        nickname=nickname,
                        goal_minutes=goal_minutes,
                        default_focus_time=default_focus_time,
                        default_break_time=default_break_time,
                        ai_mode=ai_mode,
                        exp=exp,
                    )
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)

                return user

        return _override_current_user

    return _factory


@pytest.fixture(scope="function")
def auth_headers_factory(app_factory, client_factory):
    def _factory(
        router,
        *,
        email: str = "test@example.com",
        password: str = "123456",
        nickname: str = "tester",
    ):
        app = app_factory(router)
        client = client_factory(app)

        signup_response = client.post(
            "/users/signup",
            json={
                "email": email,
                "password": password,
                "nickname": nickname,
            },
        )
        assert signup_response.status_code == 200

        login_response = client.post(
            "/users/login",
            json={
                "email": email,
                "password": password,
            },
        )
        assert login_response.status_code == 200

        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _factory
