import pytest

from stats import router, stats_router
from user import get_current_user


@pytest.fixture(scope="function")
def client(app_factory, client_factory, current_user_override_factory):
    override_user = current_user_override_factory(
        email="statsuser@example.com",
        password="hashed-password",
        nickname="statsuser",
        goal_minutes=120,
        default_focus_time=25,
        default_break_time=5,
        ai_mode="focus",
        exp=0,
    )
    app = app_factory(router, stats_router, dependency_overrides={get_current_user: override_user})
    return client_factory(app)


# ----------------------------
# 세션 저장 테스트
# ----------------------------
def test_create_session_creates_new_record(client):
    response = client.post(
        "/sessions",
        json={
            "target_date": "2026-03-31",
            "total_minutes": 60,
            "completed_sessions": 2,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "저장 완료"
    assert data["goal_achieved"] is False


def test_create_session_accumulates_existing_record_and_reaches_goal(client):
    first = client.post(
        "/sessions",
        json={
            "target_date": "2026-03-31",
            "total_minutes": 70,
            "completed_sessions": 2,
        },
    )
    assert first.status_code == 200
    assert first.json()["goal_achieved"] is False

    second = client.post(
        "/sessions",
        json={
            "target_date": "2026-03-31",
            "total_minutes": 60,
            "completed_sessions": 1,
        },
    )
    assert second.status_code == 200
    assert second.json()["goal_achieved"] is True


def test_create_session_caps_total_minutes_at_1440(client):
    response = client.post(
        "/sessions",
        json={
            "target_date": "2026-03-31",
            "total_minutes": 2000,
            "completed_sessions": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["goal_achieved"] is True

    daily = client.get("/stats/daily", params={"target_date": "2026-03-31"})
    assert daily.status_code == 200
    data = daily.json()

    assert data["total_minutes"] == 1440


# ----------------------------
# 일별 통계 테스트
# ----------------------------
def test_get_daily_stats_returns_saved_record(client):
    create_response = client.post(
        "/sessions",
        json={
            "target_date": "2026-03-30",
            "total_minutes": 90,
            "completed_sessions": 3,
        },
    )
    assert create_response.status_code == 200

    response = client.get("/stats/daily", params={"target_date": "2026-03-30"})

    assert response.status_code == 200
    data = response.json()

    assert data["date"] == "2026-03-30"
    assert data["total_minutes"] == 90
    assert data["completed_sessions"] == 3
    assert data["goal_achieved"] is False


def test_get_daily_stats_returns_null_when_no_record_exists(client):
    response = client.get("/stats/daily", params={"target_date": "2026-03-29"})

    assert response.status_code == 200
    assert response.json() is None


# ----------------------------
# 주간 통계 테스트
# ----------------------------
def test_get_weekly_stats_returns_records_in_same_week(client):
    client.post(
        "/sessions",
        json={
            "target_date": "2026-03-30",
            "total_minutes": 60,
            "completed_sessions": 2,
        },
    )
    client.post(
        "/sessions",
        json={
            "target_date": "2026-04-01",
            "total_minutes": 80,
            "completed_sessions": 2,
        },
    )

    response = client.get("/stats/weekly", params={"year": 2026, "week": 13})

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1
    assert all(item["user_id"] == 1 for item in data)


# ----------------------------
# 월간 통계 테스트
# ----------------------------
def test_get_monthly_stats_returns_records_in_same_month(client):
    client.post(
        "/sessions",
        json={
            "target_date": "2026-03-15",
            "total_minutes": 50,
            "completed_sessions": 1,
        },
    )
    client.post(
        "/sessions",
        json={
            "target_date": "2026-03-20",
            "total_minutes": 100,
            "completed_sessions": 3,
        },
    )
    client.post(
        "/sessions",
        json={
            "target_date": "2026-04-01",
            "total_minutes": 120,
            "completed_sessions": 4,
        },
    )

    response = client.get("/stats/monthly", params={"year": 2026, "month": 3})

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) == 2
    assert all(item["date"].startswith("2026-03") for item in data)


# ----------------------------
# 연간 통계 테스트
# ----------------------------
def test_get_yearly_stats_returns_records_in_same_year(client):
    client.post(
        "/sessions",
        json={
            "target_date": "2026-01-10",
            "total_minutes": 40,
            "completed_sessions": 1,
        },
    )
    client.post(
        "/sessions",
        json={
            "target_date": "2026-06-10",
            "total_minutes": 70,
            "completed_sessions": 2,
        },
    )
    client.post(
        "/sessions",
        json={
            "target_date": "2025-12-31",
            "total_minutes": 90,
            "completed_sessions": 3,
        },
    )

    response = client.get("/stats/yearly", params={"year": 2026})

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) == 2
    assert all(item["date"].startswith("2026-") for item in data)
