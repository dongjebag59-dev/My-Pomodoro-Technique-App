from __future__ import annotations

import os
from enum import Enum

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from datetime import date, timedelta
from db import get_db, StudyRecord
from user import get_current_user

load_dotenv()

router = APIRouter(prefix="/ai_service", tags=["ai_service"])


# -----------------------------
# Enums
# -----------------------------
class StudyType(str, Enum):
    memorization = "memorization"        # 암기형
    comprehension = "comprehension"      # 이해형
    problem_solving = "problem_solving"  # 문제풀이형
    practice = "practice"                # 실습형


class SessionType(str, Enum):
    study = "study"
    short_break = "short_break"
    long_break = "long_break"


class RecommendationFit(str, Enum):
    exact = "exact"    # 목표 시간과 정확히 일치
    under = "under"    # 목표 시간보다 조금 짧음 (최대 -10분)
    over = "over"      # 목표 시간보다 조금 김 (최대 +20분)


# -----------------------------
# Rules
# -----------------------------
BASE_RULES: dict[StudyType, dict] = {
    StudyType.memorization: {
        "label": "암기형",
        "study_minutes": 25,
        "short_break_minutes": 5,
        "cycle_sessions": 4,
    },
    StudyType.comprehension: {
        "label": "이해형",
        "study_minutes": 40,
        "short_break_minutes": 10,
        "cycle_sessions": 2,
    },
    StudyType.problem_solving: {
        "label": "문제풀이형",
        "study_minutes": 50,
        "short_break_minutes": 10,
        "cycle_sessions": 2,
    },
    StudyType.practice: {
        "label": "실습형",
        "study_minutes": 50,
        "short_break_minutes": 10,
        "cycle_sessions": 2,
    },
}

RECOMMENDATION_PATTERNS: dict[StudyType, list[dict]] = {
    StudyType.memorization: [
        {"study": 25, "break": 5, "label": "기본 리듬"},
        {"study": 20, "break": 5, "label": "짧게 반복"},
        {"study": 30, "break": 5, "label": "조금 길게 집중"},
    ],
    StudyType.comprehension: [
        {"study": 40, "break": 10, "label": "기본 리듬"},
        {"study": 50, "break": 10, "label": "길게 이해"},
        {"study": 30, "break": 5, "label": "짧게 읽기"},
    ],
    StudyType.problem_solving: [
        {"study": 50, "break": 10, "label": "기본 리듬"},
        {"study": 40, "break": 10, "label": "짧게 풀이"},
        {"study": 60, "break": 10, "label": "길게 몰입"},
    ],
    StudyType.practice: [
        {"study": 50, "break": 10, "label": "기본 리듬"},
        {"study": 40, "break": 10, "label": "짧게 실습"},
        {"study": 60, "break": 10, "label": "길게 몰입"},
    ],
}

LONG_BREAK_MINUTES = 30
UNDER_LIMIT = 10
OVER_LIMIT = 20
MAX_SESSIONS = 20
LONG_BREAK_THRESHOLD_MINUTES = 120
LONG_BREAK_REQUIRED_SESSION_COUNT = 6


# -----------------------------
# Request / Response Models
# -----------------------------
class StudyPlanRequest(BaseModel):
    study_type: StudyType = Field(..., description="공부 유형")
    total_study_minutes: int = Field(..., ge=30, le=480, description="총 학습 시간(휴식 포함)")


class BaseRule(BaseModel):
    study_minutes: int
    short_break_minutes: int
    session_total_minutes: int
    cycle_sessions: int
    long_break_minutes: int


class ScheduleItem(BaseModel):
    order: int
    type: SessionType
    minutes: int
    label: str


class PlanRecommendation(BaseModel):
    rank: int
    fit_type: RecommendationFit
    title: str
    pattern_label: str
    study_minutes: int
    short_break_minutes: int
    num_sessions: int
    total_minutes: int
    difference_minutes: int
    long_break_included: bool
    schedule: list[ScheduleItem]


class StudyPlanResponse(BaseModel):
    study_type: StudyType
    total_study_minutes: int
    base_rule: BaseRule
    recommendations: list[PlanRecommendation]
    summary: str
    ai_message: str


class GreetingResponse(BaseModel):
    message: str


# -----------------------------
# Helper Functions
# -----------------------------
def get_base_rule(study_type: StudyType) -> dict:
    return BASE_RULES[study_type]


def build_schedule(
    study_type: StudyType,
    study_minutes: int,
    short_break_minutes: int,
    num_sessions: int,
    include_long_break: bool,
) -> list[ScheduleItem]:
    label = BASE_RULES[study_type]["label"]
    schedule: list[ScheduleItem] = []
    accumulated_minutes = 0

    for i in range(1, num_sessions + 1):
        schedule.append(
            ScheduleItem(
                order=len(schedule) + 1,
                type=SessionType.study,
                minutes=study_minutes,
                label=f"{label} 세션 {i}",
            )
        )
        accumulated_minutes += study_minutes

        schedule.append(
            ScheduleItem(
                order=len(schedule) + 1,
                type=SessionType.short_break,
                minutes=short_break_minutes,
                label="짧은 휴식",
            )
        )
        accumulated_minutes += short_break_minutes

        if include_long_break and i < num_sessions and accumulated_minutes >= LONG_BREAK_THRESHOLD_MINUTES:
            schedule.append(
                ScheduleItem(
                    order=len(schedule) + 1,
                    type=SessionType.long_break,
                    minutes=LONG_BREAK_MINUTES,
                    label="긴 휴식",
                )
            )
            accumulated_minutes = 0

    return schedule


def calculate_total_minutes(
    study_type: StudyType,
    study_minutes: int,
    short_break_minutes: int,
    num_sessions: int,
    include_long_break: bool,
) -> int:
    total = 0
    accumulated_minutes = 0

    for i in range(1, num_sessions + 1):
        total += study_minutes
        accumulated_minutes += study_minutes

        total += short_break_minutes
        accumulated_minutes += short_break_minutes

        if include_long_break and i < num_sessions and accumulated_minutes >= LONG_BREAK_THRESHOLD_MINUTES:
            total += LONG_BREAK_MINUTES
            accumulated_minutes = 0

    return total


def can_include_long_break(
    study_type: StudyType,
    study_minutes: int,
    short_break_minutes: int,
    num_sessions: int,
    target_minutes: int,
) -> bool:
    if target_minutes <= LONG_BREAK_THRESHOLD_MINUTES:
        return False

    session_total = study_minutes + short_break_minutes
    accumulated_minutes = 0

    for i in range(1, num_sessions + 1):
        accumulated_minutes += session_total

        if i >= num_sessions:
            continue

        if accumulated_minutes >= LONG_BREAK_THRESHOLD_MINUTES:
            remaining_after_long_break = target_minutes - accumulated_minutes - LONG_BREAK_MINUTES

            if remaining_after_long_break <= 0:
                continue

            if remaining_after_long_break < session_total:
                continue

            return True

    return False


def fit_type_from_difference(diff: int) -> RecommendationFit:
    if diff == 0:
        return RecommendationFit.exact
    if diff < 0:
        return RecommendationFit.under
    return RecommendationFit.over


def title_from_fit(fit_type: RecommendationFit) -> str:
    return {
        RecommendationFit.exact: "딱 맞는 공부 흐름이에요",
        RecommendationFit.under: "조금 여유 있는 공부 흐름이에요",
        RecommendationFit.over: "조금 길지만 집중하기 좋은 흐름이에요",
    }[fit_type]


def make_candidate_recommendations(study_type: StudyType, target_minutes: int) -> list[PlanRecommendation]:
    candidates: list[PlanRecommendation] = []
    seen_signatures: set[tuple] = set()

    for pattern in RECOMMENDATION_PATTERNS[study_type]:
        study_minutes = pattern["study"]
        short_break_minutes = pattern["break"]
        pattern_label = pattern["label"]

        for num_sessions in range(1, MAX_SESSIONS + 1):
            total_without_long = calculate_total_minutes(
                study_type=study_type,
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                num_sessions=num_sessions,
                include_long_break=False,
            )
            diff_without_long = total_without_long - target_minutes
            sig_without = (study_minutes, short_break_minutes, num_sessions, False, total_without_long)

            if sig_without not in seen_signatures:
                schedule = build_schedule(
                    study_type=study_type,
                    study_minutes=study_minutes,
                    short_break_minutes=short_break_minutes,
                    num_sessions=num_sessions,
                    include_long_break=False,
                )
                candidates.append(
                    PlanRecommendation(
                        rank=0,
                        fit_type=fit_type_from_difference(diff_without_long),
                        title=title_from_fit(fit_type_from_difference(diff_without_long)),
                        pattern_label=pattern_label,
                        study_minutes=study_minutes,
                        short_break_minutes=short_break_minutes,
                        num_sessions=num_sessions,
                        total_minutes=total_without_long,
                        difference_minutes=diff_without_long,
                        long_break_included=False,
                        schedule=schedule,
                    )
                )
                seen_signatures.add(sig_without)

            if can_include_long_break(
                study_type=study_type,
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                num_sessions=num_sessions,
                target_minutes=target_minutes,
            ):
                total_with_long = calculate_total_minutes(
                    study_type=study_type,
                    study_minutes=study_minutes,
                    short_break_minutes=short_break_minutes,
                    num_sessions=num_sessions,
                    include_long_break=True,
                )
                diff_with_long = total_with_long - target_minutes
                sig_with = (study_minutes, short_break_minutes, num_sessions, True, total_with_long)

                if sig_with not in seen_signatures:
                    schedule = build_schedule(
                        study_type=study_type,
                        study_minutes=study_minutes,
                        short_break_minutes=short_break_minutes,
                        num_sessions=num_sessions,
                        include_long_break=True,
                    )
                    candidates.append(
                        PlanRecommendation(
                            rank=0,
                            fit_type=fit_type_from_difference(diff_with_long),
                            title=title_from_fit(fit_type_from_difference(diff_with_long)),
                            pattern_label=pattern_label,
                            study_minutes=study_minutes,
                            short_break_minutes=short_break_minutes,
                            num_sessions=num_sessions,
                            total_minutes=total_with_long,
                            difference_minutes=diff_with_long,
                            long_break_included=True,
                            schedule=schedule,
                        )
                    )
                    seen_signatures.add(sig_with)

    return candidates


def is_one_recommendation_case(study_type: StudyType, target_minutes: int) -> PlanRecommendation | None:
    if target_minutes > LONG_BREAK_THRESHOLD_MINUTES:
        return None

    rule = BASE_RULES[study_type]
    study_minutes = rule["study_minutes"]
    short_break_minutes = rule["short_break_minutes"]

    for num_sessions in range(1, MAX_SESSIONS + 1):
        total_minutes = calculate_total_minutes(
            study_type=study_type,
            study_minutes=study_minutes,
            short_break_minutes=short_break_minutes,
            num_sessions=num_sessions,
            include_long_break=False,
        )

        if total_minutes == target_minutes:
            schedule = build_schedule(
                study_type=study_type,
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                num_sessions=num_sessions,
                include_long_break=False,
            )
            return PlanRecommendation(
                rank=1,
                fit_type=RecommendationFit.exact,
                title=title_from_fit(RecommendationFit.exact),
                pattern_label="기본 리듬",
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                num_sessions=num_sessions,
                total_minutes=target_minutes,
                difference_minutes=0,
                long_break_included=False,
                schedule=schedule,
            )

    return None


def should_exclude_candidate(total_study_minutes: int, candidate: PlanRecommendation) -> bool:
    if total_study_minutes <= LONG_BREAK_THRESHOLD_MINUTES:
        return False

    return candidate.num_sessions >= LONG_BREAK_REQUIRED_SESSION_COUNT and not candidate.long_break_included


# -----------------------------
# Core Logic
# -----------------------------
def generate_study_plan_options(study_type: StudyType, total_study_minutes: int) -> StudyPlanResponse:
    rule = get_base_rule(study_type)
    base_rule = BaseRule(
        study_minutes=rule["study_minutes"],
        short_break_minutes=rule["short_break_minutes"],
        session_total_minutes=rule["study_minutes"] + rule["short_break_minutes"],
        cycle_sessions=rule["cycle_sessions"],
        long_break_minutes=LONG_BREAK_MINUTES,
    )

    exact_one = is_one_recommendation_case(study_type, total_study_minutes)
    if exact_one is not None:
        recommendations = [exact_one]
        summary = f"{rule['label']} 공부 시간에 딱 맞는 구성이라 하나만 추천드렸어요."
        ai_message = generate_ai_message(
            study_type=study_type,
            total_study_minutes=total_study_minutes,
            recommendations=recommendations,
        )
        return StudyPlanResponse(
            study_type=study_type,
            total_study_minutes=total_study_minutes,
            base_rule=base_rule,
            recommendations=recommendations,
            summary=summary,
            ai_message=ai_message,
        )

    candidates = make_candidate_recommendations(study_type, total_study_minutes)

    exact_candidates = [c for c in candidates if c.difference_minutes == 0]
    under_candidates = [c for c in candidates if 0 > c.difference_minutes >= -UNDER_LIMIT]
    over_candidates = [c for c in candidates if 0 < c.difference_minutes <= OVER_LIMIT]

    exact_candidates = [c for c in exact_candidates if not should_exclude_candidate(total_study_minutes, c)]
    under_candidates = [c for c in under_candidates if not should_exclude_candidate(total_study_minutes, c)]
    over_candidates = [c for c in over_candidates if not should_exclude_candidate(total_study_minutes, c)]

    prefer_long_break = total_study_minutes > LONG_BREAK_THRESHOLD_MINUTES

    def long_break_priority(item: PlanRecommendation) -> int:
        if not prefer_long_break:
            return 0
        return 0 if item.long_break_included else 1

    exact_candidates.sort(
        key=lambda x: (
            long_break_priority(x),
            x.total_minutes,
            x.study_minutes,
        )
    )
    under_candidates.sort(
        key=lambda x: (
            long_break_priority(x),
            abs(x.difference_minutes),
            x.total_minutes,
            x.study_minutes,
        )
    )
    over_candidates.sort(
        key=lambda x: (
            long_break_priority(x),
            x.difference_minutes,
            x.total_minutes,
            x.study_minutes,
        )
    )

    recommendations: list[PlanRecommendation] = []
    used_signatures: set[tuple] = set()

    def add_recommendation(item: PlanRecommendation) -> None:
        sig = (
            item.study_minutes,
            item.short_break_minutes,
            item.num_sessions,
            item.total_minutes,
            item.long_break_included,
        )
        if sig not in used_signatures and len(recommendations) < 3:
            recommendations.append(item)
            used_signatures.add(sig)

    top_exact = exact_candidates[:1]
    top_under_long = [c for c in under_candidates if c.long_break_included][:1]
    top_over_long = [c for c in over_candidates if c.long_break_included][:1]
    top_under_any = under_candidates[:1]
    top_over_any = over_candidates[:1]

    # exact가 있으면 항상 1순위로 먼저 넣기
    for item in top_exact:
        add_recommendation(item)

    # 그 다음부터 긴 휴식 포함 후보를 우선 보강
    for item in top_under_long:
        add_recommendation(item)
    for item in top_over_long:
        add_recommendation(item)

    # 남은 자리는 일반 under / over로 채우기
    for item in top_under_any:
        add_recommendation(item)
    for item in top_over_any:
        add_recommendation(item)

    for idx, recommendation in enumerate(recommendations, start=1):
        recommendation.rank = idx

    summary = f"{rule['label']} 공부 시간에 맞는 구성을 비교해 보세요."
    ai_message = generate_ai_message(
        study_type=study_type,
        total_study_minutes=total_study_minutes,
        recommendations=recommendations,
    )

    return StudyPlanResponse(
        study_type=study_type,
        total_study_minutes=total_study_minutes,
        base_rule=base_rule,
        recommendations=recommendations,
        summary=summary,
        ai_message=ai_message,
    )


def _format_recommendations_for_prompt(recommendations: list[PlanRecommendation]) -> str:
    lines = []

    for rec in recommendations:
        lines.append(
            (
                f"- rank={rec.rank}, "
                f"fit_type={rec.fit_type.value}, "
                f"title={rec.title}, "
                f"pattern_label={rec.pattern_label}, "
                f"study={rec.study_minutes}분, "
                f"short_break={rec.short_break_minutes}분, "
                f"num_sessions={rec.num_sessions}, "
                f"total={rec.total_minutes}분, "
                f"difference={rec.difference_minutes}분, "
                f"long_break_included={rec.long_break_included}"
            )
        )

    return "\n".join(lines)


def generate_greeting_message(model_name: str = "gemini-2.5-flash") -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return (
            "안녕하세요, 저는 공부 리듬을 함께 맞춰주는 토티예요. "
            "오늘 공부 시간에 맞는 타이머 구성을 편하게 추천해드릴게요."
        )

    system_instruction = (
        "당신은 포모도로 학습 도우미 AI '토티'입니다. "
        "항상 한국어로 답하세요. "
        "말투는 부드럽고 친절하며, 짧고 자연스럽게 유지하세요. "
        "너무 귀엽거나 유치한 표현은 피하고, 서비스 첫 화면에 어울리는 인사말을 작성하세요. "
        "2~3문장으로 작성하세요. "
        "사용자 입력과 무관한 일반 인사말만 작성하세요. "
        "공부 시작을 부담 없게 도와주는 느낌을 주세요. "
        "이모티콘과 과한 감탄사는 사용하지 마세요."
        
    )

    user_prompt = (
        "사용자에게 보여줄 첫 인사말을 작성하세요. "
        "토티가 공부 리듬을 함께 맞춰주는 서비스라는 점이 자연스럽게 드러나면 좋습니다. "
        "예시: 안녕하세요, 저는 공부 리듬을 함께 맞춰주는 토티예요. 오늘 공부 시간에 맞는 타이머 구성을 편하게 추천해드릴게요."
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.8,
                max_output_tokens=200,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (response.text or "").strip()
        if text:
            return text
    except Exception:
        pass

    return (
        "안녕하세요, 저는 공부 리듬을 함께 맞춰주는 토티예요. "
        "오늘 공부 시간에 맞는 타이머 구성을 편하게 추천해드릴게요."
    )


def generate_ai_message(
    study_type: StudyType,
    total_study_minutes: int,
    recommendations: list[PlanRecommendation],
    model_name: str = "gemini-2.5-flash",
) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return build_fallback_ai_message(
            study_type=study_type,
            total_study_minutes=total_study_minutes,
            recommendations=recommendations,
        )

    if not recommendations:
        return "추천을 준비하고 있어요. 잠시 후 다시 시도해 주세요."

    recommendation_text = _format_recommendations_for_prompt(recommendations)

    system_instruction = (
        "당신은 포모도로 학습 도우미 AI '토티'입니다. "
        "토티는 사용자가 공부를 부담 없이 시작할 수 있도록 도와주는 친근하고 다정한 학습 메이트입니다. "
        "항상 한국어로 답하세요. "
        "말투는 부드럽고 친절하며 짧고 자연스럽게 유지하세요. "
        "너무 귀엽거나 과장된 표현은 피하고 실제 서비스 안내문처럼 편안한 톤을 사용하세요. "
        "답변은 3~5문장으로 구성하세요. "
        "반드시 recommendations에 있는 정보만 사용하세요. "
        "가장 적합한 추천 1개는 recommendations의 첫 번째 항목입니다. "
        "존재하지 않는 시간이나 일정을 지어내지 마세요."
        "total_study_minutes는 사용자가 오늘 공부할 목표 시간입니다. "
        "평소 학습량, 습관, 과거 데이터에 대한 추측은 절대 하지 마세요. "
    )

    user_prompt = f"""
사용자 총 학습 시간: {total_study_minutes}분
이 값은 사용자가 오늘 공부하려는 목표 시간입니다.
추천 목록:
{recommendation_text}

위 추천 목록을 바탕으로 사용자에게 보여줄 안내 메시지를 작성하세요.

출력 조건:
- 한국어
- 3~5문장
- 첫 문장에서는 전체 추천 방향 설명
- 둘째 문장에서는 recommendations의 첫 번째 항목을 자연스럽게 강조
- 셋째 문장 이후에는 휴식 리듬 또는 집중 흐름의 장점 설명
- 마지막 문장에는 짧은 격려 추가
- 마크다운 금지
- 번호 목록 금지
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=220,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (response.text or "").strip()
        if text:
            return text
    except Exception:
        pass

    return build_fallback_ai_message(
        study_type=study_type,
        total_study_minutes=total_study_minutes,
        recommendations=recommendations,
    )


def build_fallback_ai_message(
    study_type: StudyType,
    total_study_minutes: int,
    recommendations: list[PlanRecommendation],
) -> str:
    label = BASE_RULES[study_type]["label"]

    if not recommendations:
        return f"{label} 공부에 맞는 학습 플랜을 다시 계산해 보세요."

    top = recommendations[0]

    if top.fit_type == RecommendationFit.exact:
        first_sentence = "지금 시간에 딱 맞는 구성이에요."
    elif top.fit_type == RecommendationFit.under:
        first_sentence = "부담이 적은 구성이에요."
    elif top.fit_type == RecommendationFit.over:
        first_sentence = "조금 길어도 집중하기 좋은 구성이에요."
    else:
        first_sentence = "균형 있게 공부하기 좋은 구성이에요."

    return (
        f"{first_sentence} "
        f"{top.study_minutes}분 공부, {top.short_break_minutes}분 휴식으로 진행해 보세요. "
        f"부담 없이 한 세션씩 해보세요."
    )


# -----------------------------
# Personalized AI message
# -----------------------------
def generate_ai_message_with_history(
    study_type: StudyType,
    total_study_minutes: int,
    recommendations: list[PlanRecommendation],
    history_context: str,
    nickname: str,
    model_name: str = "gemini-2.5-flash",
) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return build_fallback_ai_message(study_type, total_study_minutes, recommendations)

    if not recommendations:
        return "추천을 준비하고 있어요. 잠시 후 다시 시도해 주세요."

    recommendation_text = _format_recommendations_for_prompt(recommendations)

    system_instruction = (
        "당신은 포모도로 학습 도우미 AI '토티'입니다. "
        "토티는 사용자의 과거 학습 데이터를 참고하여 맞춤형 공부 리듬을 추천합니다. "
        "항상 한국어로 답하세요. "
        "말투는 부드럽고 친절하며 짧고 자연스럽게 유지하세요. "
        "답변은 3~5문장으로 구성하세요. "
        "반드시 recommendations에 있는 정보만 사용하세요. "
        "존재하지 않는 수치를 만들어내지 마세요."
    )

    user_prompt = f"""
사용자 닉네임: {nickname}
{history_context}

오늘 목표 공부 시간: {total_study_minutes}분
추천 목록:
{recommendation_text}

위 사용자의 최근 학습 패턴과 추천 목록을 바탕으로 개인화된 안내 메시지를 작성하세요.

출력 조건:
- 한국어
- 3~5문장
- 첫 문장에서 사용자 닉네임과 최근 학습 패턴을 자연스럽게 언급
- 둘째 문장에서 recommendations의 첫 번째 항목 강조
- 마지막 문장에 격려 추가
- 마크다운 금지
- 번호 목록 금지
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=220,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (response.text or "").strip()
        if text:
            return text
    except Exception:
        pass

    return build_fallback_ai_message(study_type, total_study_minutes, recommendations)


# -----------------------------
# 슬럼프 감지 메시지 생성
# -----------------------------
def generate_slump_message(nickname: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    fallback = (
        f"{nickname}님, 요즘 공부가 좀 힘드셨죠? 괜찮아요. "
        "완벽하게 매일 하지 않아도 됩니다. "
        "오늘은 딱 25분만 시작해보는 건 어때요? 작은 시작이 큰 변화를 만들어요. 💪"
    )
    if not api_key:
        return fallback
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"포모도로 공부 앱 사용자 '{nickname}'님이 최근 3일 연속으로 목표 공부 시간을 채우지 못했습니다. "
                "이 사용자에게 부드럽고 따뜻하게 다시 시작할 용기를 주는 짧은 한국어 격려 메시지를 2~3문장으로 작성해주세요. "
                "너무 가르치듯 하지 말고, 친구처럼 공감하며 말해주세요."
            ),
            config=types.GenerateContentConfig(
                temperature=0.9,
                max_output_tokens=150,
            ),
        )
        return response.text.strip() if response.text else fallback
    except Exception:
        return fallback


# -----------------------------
# Router endpoints
# -----------------------------
@router.get("", summary="AI 서비스 상태 확인")
def ai_root() -> dict[str, str]:
    return {"message": "AI service is running"}


@router.get("/greeting", response_model=GreetingResponse, summary="토티 인사말")
def greeting() -> GreetingResponse:
    return GreetingResponse(message=generate_greeting_message())


@router.post("/study-plan-options", response_model=StudyPlanResponse, summary="포모도로 플랜 추천 생성")
def create_study_plan(request: StudyPlanRequest) -> StudyPlanResponse:
    return generate_study_plan_options(
        study_type=request.study_type,
        total_study_minutes=request.total_study_minutes,
    )


@router.post("/personalized-plan", response_model=StudyPlanResponse, summary="개인 학습 이력 기반 맞춤 플랜")
async def create_personalized_plan(
    request: StudyPlanRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudyPlanResponse:
    two_weeks_ago = date.today() - timedelta(days=14)
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == current_user.id,
            StudyRecord.date >= two_weeks_ago,
        ).order_by(StudyRecord.date.desc())
    )
    records = result.scalars().all()

    history_context = ""
    if records:
        total = sum(r.total_minutes for r in records)
        avg = total / len(records)
        max_min = max(r.total_minutes for r in records)
        study_days = len(records)
        history_context = (
            f"최근 2주 학습 데이터: 총 {study_days}일 공부, "
            f"일 평균 {avg:.0f}분, 최고 기록 {max_min}분"
        )

    plan = generate_study_plan_options(
        study_type=request.study_type,
        total_study_minutes=request.total_study_minutes,
    )

    if history_context:
        plan.ai_message = generate_ai_message_with_history(
            study_type=request.study_type,
            total_study_minutes=request.total_study_minutes,
            recommendations=plan.recommendations,
            history_context=history_context,
            nickname=current_user.nickname,
        )

    return plan


@router.get("/slump-check", summary="슬럼프 감지")
async def slump_check(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    slump = True
    has_records = False
    for i in range(1, 4):
        check_date = today - timedelta(days=i)
        result = await db.execute(
            select(StudyRecord).where(
                StudyRecord.user_id == current_user.id,
                StudyRecord.date == check_date,
            )
        )
        record = result.scalars().first()
        if record:
            has_records = True
            if record.goal_achieved:
                slump = False
                break
    if not has_records:
        slump = False
    message = generate_slump_message(current_user.nickname) if slump else ""
    return {"slump": slump, "message": message}


# -----------------------------
# Standalone app
# uvicorn ai_service:app --reload
# -----------------------------
app = FastAPI(title="Pomodoro AI Service", version="1.0.0")

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Pomodoro AI Service"}
