# 🍅 토티 (Toti) — 뽀모도로 타이머

> AI가 공부 패턴을 분석해 최적의 집중·휴식 리듬을 추천해주는 뽀모도로 서비스

**박동제**

---

## 목차

1. [프로젝트 소개](#1-프로젝트-소개)
2. [주요 기능](#2-주요-기능)
3. [기술 스택](#3-기술-스택)
4. [시스템 아키텍처](#4-시스템-아키텍처)
5. [시작하기](#5-시작하기)
6. [환경 변수](#6-환경-변수)
7. [CI/CD](#7-cicd)

---

## 1. 프로젝트 소개

공부를 시작할 때 가장 어려운 건 **"얼마나, 어떻게 할까"** 입니다.  
토티는 공부 유형과 목표 시간을 입력하면 AI가 집중·휴식 세션을 자동으로 구성해주고,  
지금까지의 학습 이력까지 반영해 점점 더 나에게 맞는 리듬을 제안합니다.

---

## 2. 주요 기능

### ⏱️ 뽀모도로 타이머
- 집중 / 짧은 휴식 / 긴 휴식 자동 전환
- 원하는 집중 시간·횟수 직접 설정
- **세션 전환 시 브라우저 알림** (탭 이탈 중에도 알림 수신)
- 오늘 공부한 인원 실시간 표시 (소셜 지표)

### 🤖 AI 플랜 추천 (Gemini 2.5)
- 공부 유형 4가지 지원: 암기형 · 이해형 · 문제풀이형 · 실습형
- 목표 시간 기반으로 최대 3가지 플랜 자동 생성
- **로그인 시 최근 2주 학습 이력을 반영한 개인화 추천**
- 긴 휴식 포함 여부 자동 판단

### 📊 통계
- 일별·주간·월간·연간 학습 시간 차트
- **GitHub 잔디 스타일 히트맵** — 365일 공부 패턴 한눈에 확인

### 🎵 ASMR 플레이어
- **Player 모드**: 셔플·반복·즐겨찾기·드래그 순서 변경
- **Mix 모드**: 여러 트랙 동시 재생 + 개별 볼륨 슬라이더 (소리 믹싱)

### 📝 메모
- 드래그 가능한 플로팅 메모창
- 메모 생성·수정·삭제, 서버 저장

### 📱 PWA (Progressive Web App)
- 홈화면 추가로 앱처럼 사용 가능
- 정적 리소스 오프라인 캐시

---

## 3. 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | FastAPI, SQLAlchemy (async), PostgreSQL |
| Auth | JWT (python-jose), bcrypt |
| AI | Google Gemini 2.5 Flash |
| Frontend | Vanilla JS, HTML/CSS, Chart.js |
| Infra | Docker, Docker Compose, Nginx, AWS EC2 |
| HTTPS | Let's Encrypt (Certbot) |
| CI/CD | GitHub Actions |

---

## 4. 시스템 아키텍처

```
사용자 브라우저
    │
    ▼
Nginx (80 / 443)  ←── Let's Encrypt SSL
    │
    ▼
FastAPI (port 8000)
    ├── /timer      타이머·메모·BGM
    ├── /users      회원가입·로그인·마이페이지
    ├── /stats      일별·주간·월간·연간·히트맵
    └── /ai_service AI 플랜 추천 (일반 / 개인화)
    │
    ▼
PostgreSQL (Docker volume)
```

### 컨테이너 구성

| 컨테이너 | 역할 |
|----------|------|
| `toti-app` | FastAPI 애플리케이션 |
| `toti-db` | PostgreSQL 16 |
| `toti-nginx` | 리버스 프록시 + SSL |
| `toti-certbot` | Let's Encrypt 인증서 자동 갱신 |

---

## 5. 시작하기

### 사전 요구사항
- Docker & Docker Compose
- `.env` 파일 (아래 환경 변수 참고)

### 실행

```bash
git clone https://github.com/dongjebag59-dev/My-Pomodoro-Technique-App.git
cd My-Pomodoro-Technique-App

# .env 파일 작성 후
docker compose up -d --build
```

서버 시작 시 DB 테이블 자동 생성 및 BGM 트랙 초기화가 실행됩니다.

### HTTPS 적용 (운영 환경)

```bash
# 1. nginx/default.conf 에서 HTTP 블록의 yourdomain.com 수정
# 2. 인증서 발급
docker compose run --rm certbot certonly --webroot \
  --webroot-path=/var/www/certbot -d yourdomain.com

# 3. nginx/default.conf 에서 HTTPS 블록 주석 해제
# 4. nginx 재시작
docker compose restart nginx
```

---

## 6. 환경 변수

`.env` 파일을 프로젝트 루트에 생성하세요.

```env
# Database
POSTGRES_DB=toti
POSTGRES_USER=toti_user
POSTGRES_PASSWORD=your_password
DATABASE_URL=postgresql+asyncpg://toti_user:your_password@db:5432/toti

# Auth
SECRET_KEY=your_secret_key_here
ACCESS_TOKEN_EXPIRE_HOURS=2

# AI
GEMINI_API_KEY=your_gemini_api_key
```

---

## 7. CI/CD

GitHub Actions 기반으로 CI/CD가 자동화되어 있습니다.

### CI — 코드 품질 검증
`main`, `develop`, `feature/**` 브랜치 push · PR 시 실행

- `ruff` 린트 검사
- FastAPI import 검증
- `pytest` 테스트

### CD — 자동 배포
CI 통과 후 `main` 브랜치 merge 시 실행

- EC2 SSH 접속
- 최신 코드 pull
- `docker compose up -d --build` 재배포

---

## 배포 주소

- **서비스**: http://3.38.58.74/
- **GitHub**: https://github.com/dongjebag59-dev/My-Pomodoro-Technique-App
