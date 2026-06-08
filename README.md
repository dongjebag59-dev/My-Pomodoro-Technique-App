# ToTi 배포주소
http://3.38.58.74/

# Toti - AI 기반 공부 리듬 추천 서비스

## 1. 프로젝트 소개

Toti는 사용자의 공부 유형과 목표 시간에 맞춰
최적의 학습 리듬(공부 + 휴식)을 자동으로 추천해주는 서비스입니다.

단순한 타이머가 아니라,
**AI 기반으로 개인화된 공부 흐름을 생성**하고
집중과 휴식을 균형 있게 유지할 수 있도록 돕습니다.

## 2. 주요 기능

### 1) 포모도로 타이머

* 추천된 플랜 기반 타이머 실행
* 공부 / 짧은 휴식 / 긴 휴식 구분
* 실제 학습 흐름을 그대로 반영

→ `timer.py`

---

### 2) 사용자 기능

* 회원가입 / 로그인
* JWT 기반 인증
* 사용자 정보 관리

→ `user.py`

---

### 3) 통계 기능

* 학습 기록 기반 통계 제공
* 공부 패턴 분석 가능

→ `stats.py`

---

### 4) BGM 기능

* 공부용 배경음 자동 등록
* 서버 시작 시 음원 DB 초기화

→ `bgm_import.py`

---

### 5) AI 공부 플랜 추천

* 공부 유형별 맞춤 리듬 제공

  * 암기형
  * 이해형
  * 문제풀이형
  * 실습형
* 목표 시간 기반 자동 세션 구성
* 최대 3개의 추천 플랜 제공
* 긴 휴식 자동 포함 로직




## 3. 시스템 구조

Deployment Architecture

서비스는 Docker Compose 기반으로 구성되며, 애플리케이션, 데이터베이스(PostgreSQL), 그리고 Nginx를 포함한 컨테이너 구조로 운영됩니다.
환경 변수는 .env 및 GitHub Secrets를 통해 관리되며, 민감 정보는 저장소에 포함되지 않습니다.

   * .env 필수 내용
    
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    GEMINI_API_KEY
    DATABASE_URL
    SECRET_KEY
    ACCESS_TOKEN_EXPIRE_HOURS=2


### FastAPI 기반 백엔드

* 앱 시작 시 DB 자동 생성 및 초기화
* 라우터 기반 기능 분리

→ `main.py` 

```python
app.include_router(timer.router)
app.include_router(ai_service.router)
app.include_router(user.router)
app.include_router(stats.router)
```

---

### Docker 기반 구성

* app (FastAPI)
* db (PostgreSQL)
* nginx (리버스 프록시)

→ `docker-compose.yml` 

구성 특징:

* app은 8000 포트에서 실행
* nginx가 80 포트로 외부 요청 처리
* db는 PostgreSQL 사용
* 네트워크 분리 (toti-network)

---

### 아키텍처 흐름

```
사용자 → nginx → FastAPI(app) → DB(PostgreSQL)
                        ↓
                    AI 추천 로직
```



## 4. 프로젝트 특징

* 단순 타이머가 아닌 **AI 기반 추천 시스템**
* 공부 유형별 맞춤 로직 설계
* 긴 휴식 포함 조건 자동 판단
* Docker + Nginx + PostgreSQL 실전 배포 구조
* CI/CD 자동화 완료

---

## 5. 향후 개선 방향

* 사용자 맞춤 추천 (학습 데이터 기반)
* 프론트엔드 UI 개선
* 모바일 대응

---



## 6. CI/CD

* 본 프로젝트는 GitHub Actions를 기반으로 CI(지속적 통합)와 CD(지속적 배포)를 구성하였습니다.

### CI (Continuous Integration)

* CI는 main, develop, feature/** 브랜치에 대한 push 및 pull_request 이벤트 시 자동 실행됩니다.
워크플로우는 Python 환경 설정 후 의존성 설치를 수행하고, ruff를 통한 코드 정적 검사, 애플리케이션 import 검증, 그리고 주요 테스트(pytest)를 실행하여 코드 품질과 안정성을 검증합니다.

* CI (테스트 자동화)
ruff lint 검사
FastAPI import 검증
pytest 실행

→ ci.yml

### CD (Continuous Deployment)

* CD는 CI가 성공적으로 완료된 main 브랜치에 대해 자동 실행되며, 필요 시 수동 실행도 가능합니다.
배포 과정에서는 EC2 서버에 SSH로 접속하여 최신 코드를 반영한 후, docker compose를 이용해 기존 컨테이너를 재시작하고 최신 이미지로 서비스를 재배포합니다.

* CD (자동 배포)
main 브랜치 merge 시 자동 배포
EC2 접속 후 docker 재빌드

→ cd.yml


