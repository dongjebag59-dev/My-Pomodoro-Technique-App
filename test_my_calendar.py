import asyncio
from datetime import date

import pytest
from sqlalchemy import select

from db import Memo, StudyRecord, Todo
from my_calendar import router


@pytest.fixture(scope="function")
def client(app_factory, client_factory, create_user):
    create_user(
        id=1,
        email="calendaruser@example.com",
        password="hashed-password",
        nickname="calendaruser",
    )
    app = app_factory(router)
    return client_factory(app)


def get_todos_by_date(testing_session_local, target_date: date):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(select(Todo).where(Todo.date == target_date))
            return result.scalars().all()

    return asyncio.run(_inner())


def get_study_records_by_date(testing_session_local, target_date: date):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(select(StudyRecord).where(StudyRecord.date == target_date))
            return result.scalars().all()

    return asyncio.run(_inner())


def get_memo_by_title(testing_session_local, title: str):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(select(Memo).where(Memo.title == title))
            return result.scalars().first()

    return asyncio.run(_inner())


# ----------------------------
# summary / daily 조회
# ----------------------------
def test_get_month_summary_returns_expected_shape(client):
    response = client.get("/summary/2026/3")

    assert response.status_code == 200
    data = response.json()

    assert data["year"] == 2026
    assert data["month"] == 3
    assert "results" in data
    assert isinstance(data["results"], list)
    assert data["results"][0]["day"] == 1
    assert data["results"][0]["status"] == 1


def test_get_daily_info_returns_empty_lists_when_no_data(client):
    response = client.get("/daily/2026-03-31")

    assert response.status_code == 200
    data = response.json()

    assert data["date"] == "2026-03-31"
    assert data["todos"] == []
    assert data["memo"] == "열심히 하자!"


# ----------------------------
# todo 저장 / 조회
# ----------------------------
def test_add_todo_saves_to_db(client):
    response = client.post(
        "/todo",
        params={
            "content": "수학 문제 풀기",
            "date": "2026-03-31",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "DB 저장 완료"
    assert data["data"]["content"] == "수학 문제 풀기"
    assert data["data"]["user_id"] == 1


def test_get_daily_info_returns_saved_todos(client):
    create_response = client.post(
        "/todo",
        params={
            "content": "영어 단어 암기",
            "date": "2026-03-30",
        },
    )
    assert create_response.status_code == 200

    response = client.get("/daily/2026-03-30")

    assert response.status_code == 200
    data = response.json()

    assert data["date"] == "2026-03-30"
    assert len(data["todos"]) == 1
    assert data["todos"][0]["content"] == "영어 단어 암기"


def test_add_multiple_todos_same_date_returns_all_in_daily_info(client):
    client.post(
        "/todo",
        params={
            "content": "국어 독해",
            "date": "2026-04-01",
        },
    )
    client.post(
        "/todo",
        params={
            "content": "과학 복습",
            "date": "2026-04-01",
        },
    )

    response = client.get("/daily/2026-04-01")

    assert response.status_code == 200
    data = response.json()

    assert len(data["todos"]) == 2
    returned_contents = {item["content"] for item in data["todos"]}
    assert returned_contents == {"국어 독해", "과학 복습"}


# ----------------------------
# study-record 저장
# ----------------------------
def test_record_study_saves_record(client, testing_session_local):
    response = client.post(
        "/study-record",
        params={
            "minutes": 90,
            "date": "2026-03-31",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["study_time"] == "90 minutes"
    assert "timestamp" in data

    records = get_study_records_by_date(testing_session_local, date(2026, 3, 31))
    assert len(records) == 1
    assert records[0].user_id == 1


# ----------------------------
# memo 저장 / 조회
# ----------------------------
def test_add_memo_saves_to_db(client, testing_session_local):
    response = client.post(
        "/memo",
        params={
            "title": "오늘 메모",
            "content": "집중 잘 됨",
            "date": "2026-03-31",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["message"] == "메모가 서버에 저장되었습니다!"

    memo = get_memo_by_title(testing_session_local, "오늘 메모")
    assert memo is not None
    assert memo.title == "오늘 메모"
    assert memo.content == "집중 잘 됨"
    assert memo.user_id == 1


def test_get_memo_returns_saved_memo(client):
    create_response = client.post(
        "/memo",
        params={
            "title": "복습 메모",
            "content": "개념 다시 보기",
            "date": "2026-04-02",
        },
    )
    assert create_response.status_code == 200

    response = client.get("/memo/2026-04-02")

    assert response.status_code == 200
    data = response.json()

    assert data["title"] == "복습 메모"
    assert data["content"] == "개념 다시 보기"


def test_get_memo_returns_empty_values_when_missing(client):
    response = client.get("/memo/2026-05-01")

    assert response.status_code == 200
    data = response.json()

    assert data["title"] == ""
    assert data["content"] == ""


# ----------------------------
# DB 직접 확인 보조 테스트
# ----------------------------
def test_todo_is_saved_for_correct_date_only(client, testing_session_local):
    client.post(
        "/todo",
        params={
            "content": "A 일정",
            "date": "2026-06-01",
        },
    )
    client.post(
        "/todo",
        params={
            "content": "B 일정",
            "date": "2026-06-02",
        },
    )

    todos_day1 = get_todos_by_date(testing_session_local, date(2026, 6, 1))
    todos_day2 = get_todos_by_date(testing_session_local, date(2026, 6, 2))

    assert len(todos_day1) == 1
    assert len(todos_day2) == 1
    assert todos_day1[0].content == "A 일정"
    assert todos_day2[0].content == "B 일정"
