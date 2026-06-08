import asyncio
from datetime import datetime

import pytest
from sqlalchemy import select

from db import Memo, PomodoroSession, SessionDetail, Track, User, UserTrackSetting
from timer import router
from user import get_current_user


@pytest.fixture(scope="function")
def client(app_factory, client_factory, current_user_override_factory):
    override_user = current_user_override_factory(
        email="timeruser@example.com",
        password="hashed-password",
        nickname="timeruser",
        goal_minutes=120,
        default_focus_time=25,
        default_break_time=5,
        ai_mode="focus",
        exp=0,
    )
    app = app_factory(router, dependency_overrides={get_current_user: override_user})
    return client_factory(app)


def insert_track(testing_session_local, title: str, file_url: str):
    async def _inner():
        async with testing_session_local() as session:
            track = Track(title=title, file_url=file_url)
            session.add(track)
            await session.commit()
            await session.refresh(track)
            return track

    return asyncio.run(_inner())


def get_user(testing_session_local):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(select(User).where(User.email == "timeruser@example.com"))
            return result.scalar_one_or_none()

    return asyncio.run(_inner())


def get_all_user_track_settings(testing_session_local):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(select(UserTrackSetting))
            return result.scalars().all()

    return asyncio.run(_inner())


def get_pomodoro_session_by_date(testing_session_local, user_id, target_date):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(
                select(PomodoroSession).where(
                    PomodoroSession.user_id == user_id,
                    PomodoroSession.date == target_date,
                )
            )
            return result.scalar_one_or_none()

    return asyncio.run(_inner())


def get_session_details(testing_session_local):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(select(SessionDetail))
            return result.scalars().all()

    return asyncio.run(_inner())


def get_memo_by_id(testing_session_local, memo_id: int):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(select(Memo).where(Memo.id == memo_id))
            return result.scalar_one_or_none()

    return asyncio.run(_inner())


def get_track_setting(testing_session_local, user_id: int, track_id: int):
    async def _inner():
        async with testing_session_local() as session:
            result = await session.execute(
                select(UserTrackSetting).where(
                    UserTrackSetting.user_id == user_id,
                    UserTrackSetting.track_id == track_id,
                )
            )
            return result.scalar_one_or_none()

    return asyncio.run(_inner())


# ----------------------------
# 타이머 기본 데이터
# ----------------------------
def test_timer_data_returns_current_user_defaults(client):
    response = client.get("/timer/api/timer-data")

    assert response.status_code == 200
    data = response.json()

    assert data["logged_in"] is True
    assert data["focus_time"] == 25
    assert data["break_time"] == 5


# ----------------------------
# 메모 테스트
# ----------------------------
def test_memos_data_returns_empty_list_initially(client):
    response = client.get("/timer/api/memos")

    assert response.status_code == 200
    assert response.json() == {"memos": []}


def test_memo_write_creates_new_memo(client):
    response = client.put(
        "/timer/memo/write",
        json={
            "title": "첫 메모",
            "content": "내용입니다",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "메모 저장 완료!"
    assert data["memo"]["title"] == "첫 메모"
    assert data["memo"]["content"] == "내용입니다"
    assert "id" in data["memo"]


def test_memo_content_returns_saved_memo(client):
    create_response = client.put(
        "/timer/memo/write",
        json={
            "title": "조회용 메모",
            "content": "조회 내용",
        },
    )
    memo_id = create_response.json()["memo"]["id"]

    response = client.get(f"/timer/memo/{memo_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == memo_id
    assert data["title"] == "조회용 메모"
    assert data["content"] == "조회 내용"


def test_memo_write_updates_existing_memo(client):
    create_response = client.put(
        "/timer/memo/write",
        json={
            "title": "수정 전 제목",
            "content": "수정 전 내용",
        },
    )
    memo_id = create_response.json()["memo"]["id"]

    update_response = client.put(
        "/timer/memo/write",
        json={
            "id": memo_id,
            "title": "수정 후 제목",
            "content": "수정 후 내용",
        },
    )

    assert update_response.status_code == 200
    data = update_response.json()

    assert data["memo"]["id"] == memo_id
    assert data["memo"]["title"] == "수정 후 제목"
    assert data["memo"]["content"] == "수정 후 내용"


def test_memo_delete_removes_memo(client, testing_session_local):
    create_response = client.put(
        "/timer/memo/write",
        json={
            "title": "삭제할 메모",
            "content": "삭제 내용",
        },
    )
    memo_id = create_response.json()["memo"]["id"]

    delete_response = client.delete(f"/timer/memo/{memo_id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "메모 삭제 완료!"
    assert delete_response.json()["id"] == memo_id

    memo = get_memo_by_id(testing_session_local, memo_id)
    assert memo is None


def test_memo_delete_returns_404_for_missing_memo(client):
    response = client.delete("/timer/memo/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "메모를 찾을 수 없습니다."


# ----------------------------
# 세션 종료 저장
# ----------------------------
def test_session_end_creates_daily_session_and_detail_and_updates_exp(client, testing_session_local):
    response = client.post(
        "/timer/api/session-end",
        json={
            "started_at": "2026-03-31T10:00:00",
            "ended_at": "2026-03-31T10:25:00",
            "duration": 25,
            "exp": 30,
        },
    )

    assert response.status_code == 204

    user = get_user(testing_session_local)
    daily_session = get_pomodoro_session_by_date(testing_session_local, user.id, datetime.today().date())
    details = get_session_details(testing_session_local)

    assert daily_session is not None
    assert daily_session.total_duration == 25
    assert len(details) == 1
    assert details[0].duration == 25
    assert details[0].is_completed is True
    assert user.exp == 30


def test_session_end_accumulates_total_duration_and_caps_exp_per_request(client, testing_session_local):
    first = client.post(
        "/timer/api/session-end",
        json={
            "started_at": "2026-03-31T09:00:00",
            "ended_at": "2026-03-31T09:25:00",
            "duration": 25,
            "exp": 50,
        },
    )
    assert first.status_code == 204

    second = client.post(
        "/timer/api/session-end",
        json={
            "started_at": "2026-03-31T10:00:00",
            "ended_at": "2026-03-31T10:30:00",
            "duration": 30,
            "exp": 999,
        },
    )
    assert second.status_code == 204

    user = get_user(testing_session_local)
    daily_session = get_pomodoro_session_by_date(testing_session_local, user.id, datetime.today().date())
    details = get_session_details(testing_session_local)

    assert daily_session is not None
    assert daily_session.total_duration == 55
    assert len(details) == 2
    assert user.exp == 550


# ----------------------------
# 트랙 불러오기/설정
# ----------------------------
def test_load_tracks_returns_tracks_and_creates_user_settings(client, testing_session_local):
    track1 = insert_track(testing_session_local, "rain", "/bgms/rain.mp3")
    track2 = insert_track(testing_session_local, "forest", "/bgms/forest.mp3")

    response = client.get("/timer/tracks")

    assert response.status_code == 200
    data = response.json()

    assert "tracks" in data
    assert len(data["tracks"]) == 2

    returned_titles = {item["title"] for item in data["tracks"]}
    assert returned_titles == {"rain", "forest"}

    settings = get_all_user_track_settings(testing_session_local)
    assert len(settings) == 2

    returned_ids = {item["id"] for item in data["tracks"]}
    assert returned_ids == {track1.id, track2.id}


def test_update_track_check_changes_is_checked_value(client, testing_session_local):
    track = insert_track(testing_session_local, "ocean", "/bgms/ocean.mp3")
    client.get("/timer/tracks")

    response = client.put(
        f"/timer/tracks/{track.id}/check",
        json={"is_checked": False},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "체크 업데이트 완료"
    assert data["track_id"] == track.id
    assert data["is_checked"] is False

    user = get_user(testing_session_local)
    setting = get_track_setting(testing_session_local, user.id, track.id)
    assert setting is not None
    assert setting.is_checked is False


def test_update_track_check_returns_404_when_setting_missing(client, testing_session_local):
    track = insert_track(testing_session_local, "wind", "/bgms/wind.mp3")

    response = client.put(
        f"/timer/tracks/{track.id}/check",
        json={"is_checked": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "트랙 설정을 찾을 수 없습니다."


def test_update_track_favorite_changes_is_favorite_value(client, testing_session_local):
    track = insert_track(testing_session_local, "night", "/bgms/night.mp3")
    client.get("/timer/tracks")

    response = client.put(
        f"/timer/tracks/{track.id}/favorite",
        json={"is_favorite": True},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "즐겨찾기 업데이트 완료"
    assert data["track_id"] == track.id
    assert data["is_favorite"] is True

    user = get_user(testing_session_local)
    setting = get_track_setting(testing_session_local, user.id, track.id)
    assert setting is not None
    assert setting.is_favorite is True


def test_update_track_order_changes_order_indexes(client, testing_session_local):
    track1 = insert_track(testing_session_local, "a", "/bgms/a.mp3")
    track2 = insert_track(testing_session_local, "b", "/bgms/b.mp3")
    client.get("/timer/tracks")

    response = client.put(
        "/timer/tracks/order",
        json=[
            {"track_id": track1.id, "order_index": 2},
            {"track_id": track2.id, "order_index": 1},
        ],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "순서 업데이트 완료"
    assert len(data["updated"]) == 2

    user = get_user(testing_session_local)
    setting1 = get_track_setting(testing_session_local, user.id, track1.id)
    setting2 = get_track_setting(testing_session_local, user.id, track2.id)

    assert setting1.order_index == 2
    assert setting2.order_index == 1


def test_update_track_order_returns_404_for_missing_setting(client, testing_session_local):
    track = insert_track(testing_session_local, "x", "/bgms/x.mp3")

    response = client.put(
        "/timer/tracks/order",
        json=[
            {"track_id": track.id, "order_index": 1},
        ],
    )

    assert response.status_code == 404
    assert f"track_id {track.id}의 트랙 설정을 찾을 수 없습니다." in response.json()["detail"]
