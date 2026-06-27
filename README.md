# 마케팅 자동화 시스템

키워드 하나로 **수집 → 분석 → 콘텐츠 생성 → 리포트 → 모니터링 → 카드뉴스 → 네이버 블로그 → Instagram**까지 완전 자동화하는 8단계 멀티 에이전트 시스템입니다.

GCP VM(`34.11.175.125:5000`)에서 Flask + gunicorn + systemd로 운영 중이며, 승인 게이트·SSE 실시간 스트리밍·멀티 키워드 병렬 처리·웹 예약 관리를 지원합니다.

---

## 파이프라인

### 2단계 승인 게이트

```
키워드 입력 (복수 지원, 쉼표 구분)
    │
    ▼
━━━━━━━━━ Part 1 — 자동 실행 ━━━━━━━━━
①  collector   네이버 검색 API → 포스트 30개 수집  (키워드별)
②  analyzer    Gemini + DataLab → 트렌드·감성 분석 (키워드별)
③  writer      Gemini → 블로그·인스타·광고카피 3종  (키워드별)
④  reporter    Jinja2 + Playwright → HTML/PDF 리포트 (통합 1회)
⑤  monitor     새 포스트 감지 + 중요도 평가          (통합 1회)
⑥  cardnews    Gemini Imagen → 카드뉴스 PNG 4장      (키워드별)
    │
    ▼
auto_post=False?
    │ YES → pending_approval  ← 이메일·슬랙 알림
    │        사용자가 대시보드에서 콘텐츠 검토·수정 후 [승인] 클릭
    │ NO  → 즉시 Part 2 진행
    ▼
━━━━━━━━━ Part 2 — 발행 ━━━━━━━━━
⑦  poster      Playwright → 네이버 블로그 자동 발행 (fatal=False)
⑧  instagram   Graph API v21.0 + 카드뉴스 캐러셀 발행
    │
    ▼
done  →  이메일·슬랙 완료 알림
```

> **poster(⑦)** 는 네이버 봇 감지 정책으로 GCP VM에서 차단될 수 있습니다.  
> 실패해도 파이프라인은 계속 진행되며 `instagram(⑧)` 은 VM에서 정상 동작합니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 멀티 키워드 | 쉼표 구분으로 복수 키워드 동시 처리, 부분 실패 시 나머지 계속 |
| 2단계 승인 게이트 | Part1 자동 실행 후 발행 전 사람이 검토·수정 가능 |
| 카드뉴스 자동 생성 | Gemini Imagen API로 4장 PNG 생성 → Instagram 캐러셀 발행 |
| 캐러셀 캐시 (8h) | `ig_pending_*.json` 캐시로 컨테이너 중복 생성 방지 (API 한도 절약) |
| 실시간 SSE | 파이프라인 진행 상황을 단계·로그·에러로 스트리밍 |
| 로그 키워드 색상 | 멀티 키워드 실행 시 `[키워드]` 로그 라인 색상 구분 |
| 예약 관리 | APScheduler 기반 웹 CRUD — 요일·시각·채널 설정 |
| 콘텐츠 편집 | 승인 전 블로그 제목·인스타 캡션·광고 카피 인라인 수정 |
| 히스토리 & KPI | 실행 기록 테이블, 성공률 도넛 차트, KPI 카드 6개 |
| 에러 로그 조회 | 오류 잡의 🔍 버튼 → DB/Instagram 에러 상세 팝업 |
| 알림 | 완료·승인 대기·오류 발생 시 이메일(Gmail) + 슬랙 Webhook |
| 멀티 유저 | DB 기반 사용자 관리, admin 패널, 로그인 시도 제한(5회/잠금 15분) |
| 구조화 로그 | `logs/app.log` RotatingFileHandler (2MB×5) JSON 지원 |

---

## 보안

| 항목 | 구현 |
|------|------|
| 로그인 인증 | `ADMIN_USER` + 비밀번호 해시(werkzeug) |
| 세션 쿠키 | `SameSite=Lax`, `HttpOnly`, HTTPS 운영 시 `Secure` |
| CSRF 보호 | `X-CSRF-Token` 헤더 검증 (POST/PUT/PATCH/DELETE, `/login`·`X-API-Key` 면제) |
| 브루트포스 방어 | `LoginRateLimiter` — 5회 실패 시 15분 잠금, 서버 재시작 후에도 유지 |
| .env.enc 암호화 | Fernet으로 민감 환경변수 암호화 저장 (`data/.env.enc`) |
| 쿠키 암호화 | `naver_cookies.json` at-rest Fernet 암호화 |
| XSS 방지 | 모든 사용자 데이터 `esc()` 처리, 스케줄 onclick에 `_scheduleCache` 참조 방식 |
| API 키 인증 | `X-API-Key` 헤더 — 프로그래밍 접근 (CSRF 면제) |

자세한 내용은 [`docs/security.md`](docs/security.md) 참고.

---

## 시스템 구성

```
marketing-agent/
├── agents/
│   ├── collector/      # ① 네이버 검색 API 병렬 수집 (30개/키워드)
│   ├── analyzer/       # ② Gemini + DataLab 트렌드·감성 분석
│   ├── writer/         # ③ Gemini 마케팅 콘텐츠 3종 생성
│   ├── reporter/       # ④ Jinja2 HTML → Playwright PDF 리포트
│   ├── monitor/        # ⑤ 새 포스트 감지 + 중요도 평가
│   ├── cardnews/       # ⑥ Gemini Imagen 카드뉴스 PNG 4장
│   ├── poster/         # ⑦ Playwright → 네이버 블로그 발행
│   ├── instagram/      # ⑧ Instagram Graph API 캐러셀 발행
│   ├── sales/          # 부가: 리드 수집·콜드메일 발송
│   └── healthcheck/    # 부가: 파이프라인 산출물 점검
├── utils/
│   ├── auth_guard.py   # LoginRateLimiter (영속 잠금)
│   ├── backup.py       # 상태 파일 백업
│   ├── cleanup.py      # 7일 초과 파일 자동 삭제
│   ├── job_store.py    # SQLite CRUD + FSM 전이 검증
│   ├── logging_setup.py # RotatingFile + JSON 포맷
│   ├── notifier.py     # Gmail SMTP + 슬랙 Webhook 알림
│   ├── schedule_util.py # 스케줄 검증·정규화
│   ├── secrets.py      # Fernet 암호화/복호화 (.env.enc, 쿠키)
│   ├── state_machine.py # FSM — 허용 전이 정의, warn-only 검증
│   └── user_store.py   # 사용자 DB CRUD
├── templates/
│   ├── index.html      # 메인 대시보드 (SSE, 승인 게이트, 예약 관리)
│   ├── admin.html      # 사용자 관리 패널
│   └── login.html      # 로그인 페이지
├── tests/              # pytest 174개 (CI: .github/workflows/ci.yml)
├── scripts/
│   └── encrypt_env.py  # .env → data/.env.enc 최초 암호화 스크립트
├── docs/
│   ├── architecture.md
│   ├── security.md
│   └── harness-engineering.md
├── data/               # 수집·분석 데이터 + 상태 파일 (gitignore)
│   ├── jobs.db         # SQLite — 잡 히스토리, 스케줄, 사용자
│   ├── .env.enc        # 민감 환경변수 암호화본
│   ├── .enc_key        # Fernet 마스터 키 (chmod 600)
│   └── rate_lockouts.json  # 로그인 잠금 상태 영속화
├── output/             # 콘텐츠·리포트·카드뉴스 PNG (gitignore)
├── logs/               # 구조화 로그 app.log (gitignore)
├── app.py              # Flask 웹 서버 (gunicorn 호환)
├── orchestrator.py     # CLI 파이프라인 실행기 (--resume 체크포인트)
├── marketing-agent.service  # systemd 서비스 유닛
├── setup.sh            # GCP VM 최초 설정 스크립트
├── deploy.sh           # 로컬 → VM 배포 스크립트
└── requirements.txt
```

---

## 웹 UI

```
┌──────────────────────── 글로벌 네비바 ──────────────────────────┐
│  마케팅 자동화   수집 › 분석 › 작성 › 카드뉴스 › ...    로그아웃  │
├──────── 사이드바 (280px) ────────┬────────── 메인 영역 ──────────┤
│  성공률 도넛 차트                │  KPI 카드 6개                │
│  ────────────────               │  전체실행 / 이번주 / 최다키워드 │
│  키워드 입력  [실행] [자동발행]  │  평균소요 / 성공률 / 오류     │
│  [퀵태그: AI마케팅] [...]        │  ──────────────────────────  │
│  ────────────────               │  결과 패널 (SSE 실시간)       │
│  진행 상황                       │   ▶ 수집  ▶ 분석  ⏳ 작성   │
│  ✓ 수집   ✓ 분석                │   콘텐츠 카드 / 카드뉴스 갤러리│
│  ✓ 작성   ✓ 리포트              │  ──────────────────────────  │
│  ✓ 모니터 ✓ 카드뉴스            │  히스토리 테이블              │
│  ⏳ 포스팅 ...                  │  [전체][완료][오류] 🔍 기간▼  │
│                                  │  상태│키워드│날짜│소요│액션  │
│                                  │  ──────────────────────────  │
│                                  │  예약 관리 (접기/펼치기)      │
└──────────────────────────────────┴───────────────────────────────┘
```

**승인 게이트 흐름** (auto_post=False 시)
1. Part 1 완료 → 황색 승인 배너 표시 + 이메일·슬랙 알림
2. 블로그 제목, 인스타 캡션·해시태그, 광고 카피 인라인 수정 가능
3. `[✓ 승인 후 게시]` 클릭 → Part 2 발행 시작 (실시간 진행 표시)
4. `[✗ 거절]` 클릭 → `rejected` 상태로 전환, 콘텐츠 보존

**히스토리 테이블 기능**
- 필터 탭: 전체 / 완료 / 오류
- 키워드 검색 + 기간 선택(7일 / 30일 / 전체)
- 오류 잡 → 🔍 버튼으로 DB·Instagram 에러 상세 조회
- ↺ 버튼으로 같은 키워드 재실행
- 완료 잡 → 네이버·Instagram 링크 아이콘

---

## 시작하기

### 1. 설치

```bash
git clone https://github.com/heewonn09/marketing-agent.git
cd marketing-agent

python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

### 2. 환경 변수

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
# ── AI 핵심 ────────────────────────────────────────
GEMINI_API_KEY=your-gemini-api-key

# ── 네이버 데이터 수집 ────────────────────────────
NAVER_CLIENT_ID=your-naver-client-id
NAVER_CLIENT_SECRET=your-naver-client-secret

# ── 네이버 블로그 포스팅 (로컬 전용) ─────────────
NAVER_ID=your-naver-id@naver.com
NAVER_PW=your-naver-password            # → .env.enc 암호화 권장

# ── Instagram Graph API ────────────────────────────
IG_ACCESS_TOKEN=your-instagram-access-token
IG_ACCOUNT_ID=your-instagram-account-id

# ── Unsplash 이미지 (Instagram 발행 시 자동 선택) ─
UNSPLASH_ACCESS_KEY=your-unsplash-access-key
INSTAGRAM_DEFAULT_IMAGE_URL=https://...  # Unsplash 실패 시 폴백

# ── 알림 (이메일·슬랙) ─────────────────────────────
SMTP_USER=you@gmail.com
SMTP_PASSWORD=gmail-앱-비밀번호-16자
ALERT_EMAIL=you@gmail.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# ── 보안 ────────────────────────────────────────────
ADMIN_USER=admin                          # 미설정 시 인증 비활성
ADMIN_PASSWORD_HASH=werkzeug-hash         # (권장) python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('pw'))"
API_KEY=random-hex-secret                 # X-API-Key 헤더 인증 키
FORCE_HTTPS=1                             # HTTPS 리버스 프록시 운영 시
SECRET_KEY=flask-session-secret           # 미설정 시 data/.flask_secret 자동 생성

# ── 튜닝 (선택, 미설정 시 기본값 사용) ─────────────
COLLECT_TARGET_COUNT=30
DATALAB_KEYWORD_LIMIT=5
MONITOR_SEEN_LIMIT=500
MONITOR_INTERVAL_MIN=360
IG_POLL_ATTEMPTS=12
CARDNEWS_BASE_URL=https://your-domain.com  # 알림 이메일 링크용
```

| 키 | 발급처 |
|----|--------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com) |
| `NAVER_CLIENT_ID/SECRET` | [네이버 개발자센터](https://developers.naver.com) — 검색 API + 데이터랩 권한 필요 |
| `IG_ACCESS_TOKEN/ACCOUNT_ID` | [Meta for Developers](https://developers.facebook.com) — Instagram Graph API |
| `UNSPLASH_ACCESS_KEY` | [Unsplash Developers](https://unsplash.com/developers) — 무료 발급 |

### 3. 민감 환경변수 암호화 (선택, 권장)

```bash
# .env 읽어서 NAVER_PW·ADMIN_PASSWORD 등을 data/.env.enc에 암호화
python scripts/encrypt_env.py

# 이후 .env에서 해당 키 삭제 가능 — 앱 시작 시 .env.enc 자동 복호화
```

### 4. 네이버 쿠키 초기화 (poster 첫 실행, 로컬 전용)

```bash
python agents/poster/main.py --keyword "테스트" --manual-login
# 브라우저 열림 → 네이버 로그인 → Enter
# data/naver_cookies.json 에 Fernet 암호화하여 저장
```

---

## 실행

### 웹 UI (권장)

```bash
python app.py
# http://localhost:5000
```

운영 환경(gunicorn):

```bash
gunicorn app:app --workers 1 --worker-class gthread --threads 4 --timeout 0 --bind 0.0.0.0:5000
```

> **workers=1 필수**: `jobs` dict가 in-memory라 멀티 워커 시 상태 공유 불가.

### CLI

```bash
# 단일 키워드 (자동 발행)
python orchestrator.py --keyword "AI 마케팅" --auto-post

# 멀티 키워드 (승인 게이트)
python orchestrator.py --keyword "AI 마케팅" "디지털 마케팅"

# 실패 지점부터 재개
python orchestrator.py --keyword "AI 마케팅" --resume
```

### 에이전트 개별 실행

```bash
python agents/collector/main.py  --keyword "AI 마케팅"
python agents/analyzer/main.py   --keyword "AI 마케팅"
python agents/writer/main.py     --keyword "AI 마케팅"
python agents/reporter/main.py   --date 2026-06-28
python agents/monitor/main.py    --keywords "AI 마케팅" --once
python agents/cardnews/main.py   --keyword "AI 마케팅"
python agents/poster/main.py     --keyword "AI 마케팅" --date 2026-06-28
python agents/instagram/main.py  --keyword "AI 마케팅" --date 2026-06-28 --carousel
python agents/healthcheck/main.py --once
```

---

## 웹 예약 관리

웹 UI 하단 **예약 관리** 섹션에서 키워드별 자동 실행 스케줄을 관리합니다.

| 기능 | 설명 |
|------|------|
| 스케줄 추가 | 이름, 키워드(복수), 요일, 시각, 채널(블로그/인스타) 설정 |
| 활성화 토글 | on/off — 서버 재시작 없이 즉시 적용 |
| 수정 / 삭제 | 기존 스케줄 인라인 수정 또는 삭제 |
| 실행 방식 | APScheduler CronTrigger, `auto_post=True` 로 실행 |
| 오류 알림 | 스케줄 실행 실패 시 이메일·슬랙 자동 알림 |

---

## 테스트 / CI

```bash
.\venv\Scripts\python.exe -m pytest tests/ -q
# 174 tests passing
```

`main` 브랜치 푸시·PR 시 GitHub Actions(`.github/workflows/ci.yml`)가 자동으로 `pytest`를 실행합니다.

---

## 출력 결과

| 파일 | 설명 |
|------|------|
| `data/{키워드}_{날짜}.json` | 수집된 블로그 포스트 |
| `data/analyzed_{키워드}_{날짜}.json` | 트렌드·인사이트·DataLab·감성 분석 결과 |
| `data/ig_pending_{키워드}_{날짜}.json` | Instagram 캐러셀 컨테이너 캐시 (8h TTL) |
| `data/instagram_error_{날짜}.json` | Instagram 포스팅 오류 로그 (14일 보존) |
| `data/jobs.db` | SQLite — 잡 상태, 스케줄, 사용자 |
| `output/content_{키워드}_{날짜}.json` | 생성된 마케팅 콘텐츠 3종 |
| `output/cardnews_{키워드}_{날짜}_{1-4}.png` | 카드뉴스 이미지 4장 |
| `output/cardnews_urls_{키워드}_{날짜}.json` | 카드뉴스 업로드 URL 목록 |
| `output/report_{날짜}.html` | 웹 리포트 |
| `output/report_{날짜}.pdf` | PDF 리포트 |
| `logs/app.log` | 구조화 로그 (RotatingFile 2MB×5) |

### 콘텐츠 JSON 구조

```json
{
  "naver_blog": {
    "title": "블로그 제목 (검색량 변화율 등 실데이터 포함)",
    "body": "## 소제목\n본문 (수치·사례 포함)...",
    "hashtags": ["#해시태그1", "#해시태그2"]
  },
  "instagram": {
    "caption": "캡션 (실데이터 기반, 팔로우 CTA 포함) 🔥",
    "hashtags": ["#해시태그1", "#해시태그2"]
  },
  "ad_copy": {
    "headline": "광고 헤드라인 (구체적 수치 포함)",
    "subheadline": "서브헤드라인",
    "cta": "지금 시작하기"
  }
}
```

---

## GCP VM 배포

### 최초 설정

```bash
scp setup.sh jhjttmtmtmjgt@34.11.175.125:~/
ssh jhjttmtmtmjgt@34.11.175.125 "bash ~/setup.sh"
ssh jhjttmtmtmjgt@34.11.175.125 "nano ~/marketing-agent/.env"
```

`setup.sh` 자동 처리: Python 설치, 저장소 클론, venv 구성, Playwright Chromium 설치, systemd 서비스 등록

### 코드 업데이트

```bash
ssh jhjttmtmtmjgt@34.11.175.125 "cd ~/marketing-agent && git pull && sudo systemctl restart marketing-agent"
```

또는 로컬에서:

```bash
bash deploy.sh
```

### 서비스 상태 확인

```bash
ssh jhjttmtmtmjgt@34.11.175.125 "sudo systemctl status marketing-agent"
ssh jhjttmtmtmjgt@34.11.175.125 "journalctl -u marketing-agent -n 50 --no-pager"
```

### VM vs 로컬 동작 차이

| 에이전트 | 로컬 | GCP VM |
|----------|------|--------|
| collector / analyzer / writer / reporter / monitor / cardnews | ✅ | ✅ |
| instagram | ✅ | ✅ |
| poster (네이버 블로그) | ✅ | ⚠️ 봇 감지 차단 가능 — 실패해도 파이프라인 계속 |

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| AI 분석·생성 | Google Gemini API (`gemini-2.5-flash-lite`) |
| 카드뉴스 이미지 | Gemini Imagen API |
| 검색량 트렌드 | 네이버 데이터랩 API |
| 데이터 수집 | 네이버 검색 API |
| 브라우저 자동화 | Playwright + Chromium (stealth) |
| Instagram 발행 | Instagram Graph API v21.0 |
| 이미지 검색 | Unsplash API (Gemini 번역 후 영문 검색) |
| 병렬 처리 | `concurrent.futures.ThreadPoolExecutor` |
| 웹 서버 | Flask + gunicorn (`--workers 1 --worker-class gthread --threads 4`) |
| 실시간 스트리밍 | SSE (Server-Sent Events) |
| 리포트 | Jinja2 HTML 템플릿 → Playwright PDF |
| 스케줄링 | APScheduler CronTrigger |
| 데이터베이스 | SQLite (`data/jobs.db`) — 잡·스케줄·사용자 |
| 암호화 | Fernet (`cryptography`) — `.env.enc` + 쿠키 at-rest |
| 보안 | CSRF 토큰, LoginRateLimiter, ADMIN_PASSWORD_HASH |
| 로깅 | `logging.handlers.RotatingFileHandler` + JSON 포맷 |
| 알림 | Gmail SMTP + 슬랙 Incoming Webhook |
| 배포 | GCP e2-micro (`34.11.175.125`) + systemd |
| CI | GitHub Actions → pytest (174 tests) |
