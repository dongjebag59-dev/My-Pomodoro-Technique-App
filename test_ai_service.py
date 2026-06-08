from fastapi.testclient import TestClient

from ai_service import (
    app,
    StudyType,
    RecommendationFit,
    SessionType,
    generate_study_plan_options,
    LONG_BREAK_MINUTES,
)


client = TestClient(app)


# ----------------------------
# 기본 상태 확인
# ----------------------------
def test_root_endpoint_returns_service_message():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Pomodoro AI Service"}


def test_ai_root_endpoint_returns_running_message():
    response = client.get("/ai_service")
    assert response.status_code == 200
    assert response.json() == {"message": "AI service is running"}


def test_greeting_endpoint_returns_message():
    response = client.get("/ai_service/greeting")
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert isinstance(data["message"], str)
    assert len(data["message"].strip()) > 0


# ----------------------------
# 순수 함수 테스트
# ----------------------------
def test_memorization_exact_match_returns_one_recommendation():
    result = generate_study_plan_options(
        study_type=StudyType.memorization,
        total_study_minutes=120,
    )

    assert result.study_type == StudyType.memorization
    assert result.total_study_minutes == 120
    assert len(result.recommendations) == 1

    rec = result.recommendations[0]
    assert rec.rank == 1
    assert rec.fit_type == RecommendationFit.exact
    assert rec.total_minutes == 120
    assert rec.difference_minutes == 0
    assert rec.long_break_included is False


def test_recommendations_rank_start_from_one_and_increase_in_order():
    result = generate_study_plan_options(
        study_type=StudyType.comprehension,
        total_study_minutes=210,
    )

    ranks = [rec.rank for rec in result.recommendations]
    assert ranks == list(range(1, len(result.recommendations) + 1))


def test_long_break_is_included_for_long_study_time_when_applicable():
    result = generate_study_plan_options(
        study_type=StudyType.comprehension,
        total_study_minutes=210,
    )

    assert len(result.recommendations) >= 1
    assert any(rec.long_break_included for rec in result.recommendations)


def test_long_break_not_included_when_total_time_is_short():
    result = generate_study_plan_options(
        study_type=StudyType.memorization,
        total_study_minutes=90,
    )

    assert all(rec.long_break_included is False for rec in result.recommendations)


def test_schedule_contains_valid_session_types():
    result = generate_study_plan_options(
        study_type=StudyType.problem_solving,
        total_study_minutes=170,
    )

    assert len(result.recommendations) >= 1

    first_schedule = result.recommendations[0].schedule
    assert len(first_schedule) > 0
    assert all(
        item.type in {SessionType.study, SessionType.short_break, SessionType.long_break}
        for item in first_schedule
    )


def test_long_break_minutes_are_applied_correctly_in_schedule():
    result = generate_study_plan_options(
        study_type=StudyType.comprehension,
        total_study_minutes=210,
    )

    schedules_with_long_break = [
        rec.schedule for rec in result.recommendations if rec.long_break_included
    ]

    assert len(schedules_with_long_break) >= 1

    found = False
    for schedule in schedules_with_long_break:
        for item in schedule:
            if item.type == SessionType.long_break:
                assert item.minutes == LONG_BREAK_MINUTES
                found = True

    assert found is True


def test_summary_and_ai_message_are_not_empty():
    result = generate_study_plan_options(
        study_type=StudyType.practice,
        total_study_minutes=150,
    )

    assert isinstance(result.summary, str)
    assert result.summary.strip() != ""
    assert isinstance(result.ai_message, str)
    assert result.ai_message.strip() != ""


# ----------------------------
# API 테스트
# ----------------------------
def test_study_plan_api_returns_valid_response():
    response = client.post(
        "/ai_service/study-plan-options",
        json={
            "study_type": "memorization",
            "total_study_minutes": 120,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["study_type"] == "memorization"
    assert data["total_study_minutes"] == 120
    assert "base_rule" in data
    assert "recommendations" in data
    assert "summary" in data
    assert "ai_message" in data
    assert len(data["recommendations"]) >= 1


def test_study_plan_api_rejects_too_small_total_minutes():
    response = client.post(
        "/ai_service/study-plan-options",
        json={
            "study_type": "memorization",
            "total_study_minutes": 20,
        },
    )

    assert response.status_code == 422


def test_study_plan_api_rejects_too_large_total_minutes():
    response = client.post(
        "/ai_service/study-plan-options",
        json={
            "study_type": "memorization",
            "total_study_minutes": 500,
        },
    )

    assert response.status_code == 422


def test_study_plan_api_rejects_invalid_study_type():
    response = client.post(
        "/ai_service/study-plan-options",
        json={
            "study_type": "invalid_type",
            "total_study_minutes": 120,
        },
    )

    assert response.status_code == 422


def test_exact_match_response_has_single_recommendation_for_120_minutes_memorization():
    response = client.post(
        "/ai_service/study-plan-options",
        json={
            "study_type": "memorization",
            "total_study_minutes": 120,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data["recommendations"]) == 1

    rec = data["recommendations"][0]
    assert rec["rank"] == 1
    assert rec["fit_type"] == "exact"
    assert rec["total_minutes"] == 120
    assert rec["difference_minutes"] == 0
    assert rec["long_break_included"] is False


def test_long_study_time_response_can_include_long_break():
    response = client.post(
        "/ai_service/study-plan-options",
        json={
            "study_type": "comprehension",
            "total_study_minutes": 210,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data["recommendations"]) >= 1
    assert any(rec["long_break_included"] for rec in data["recommendations"])