# 마케팅 자동화 시스템

키워드 하나로 **수집 → 분석 → 콘텐츠 생성 → 리포트 → 모니터링 → 네이버 블로그 → Instagram**까지 자동화하는 7단계 멀티 에이전트 시스템입니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 자동 파이프라인 | 키워드 입력 한 번으로 7개 에이전트 순차 실행 |
| 네이버 블로그 수집 | 네이버 검색 API로 최대 30개 포스트 병렬 수집 |
| AI 분석 | Gemini API로 트렌드·인사이트·감성 분석 + 검색량 변화율 |
| 데이터랩 연동 | 네이버 데이터랩 실제 검색량 트렌드(최근 4주) + 주간 변화율 |
| 히스토리 추적 | 지난 주 추천 키워드의 실제 검색량 변화 자동 검증 |
| 콘텐츠 자동 생성 | 실데이터 기반 네이버 블로그·인스타그램·광고 카피 3종 생성 |
| PDF 리포트 | Jinja2 HTML 렌더링 → Playwright PDF 변환 |
| 키워드 모니터링 | 새 포스트 감지 및 Gemini 중요도 자동 평가 |
| **네이버 블로그 자동 발행** | Playwright로 SmartEditor ONE 조작, 마크다운 → HTML 변환 후 발행 |
| **Instagram 자동 발행** | Graph API + Unsplash 키워드 이미지 자동 검색 후 발행 |
| **웹 예약 관리** | APScheduler 기반 크론 스케줄 CRUD — 웹에서 예약 추가·수정·삭제·활성화 |
| **대시보드 UI** | 글로벌 네비바 + 2-컬럼 레이아웃(사이드바/메인), KPI 카드 6개, 히스토리 테이블 |
| 실시간 스트리밍 | Flask + SSE 기반 파이프라인 진행 상황 단계별 스트리밍 |
| Windows 스케줄러 | 매일 오전 10시 네이버 블로그 자동 포스팅 |
| GCP 배포 | GCP e2-micro VM, gunicorn + systemd 운영 |

---

## 파이프라인

```
키워드 입력
    │
    ▼
① collector   네이버 검색 API → 포스트 30개 수집
    │
    ▼
② analyzer    Gemini + DataLab → 트렌드·인사이트·감성 분석·검색량 변화율
    │
    ▼
③ writer      Gemini → 실데이터 기반 블로그·인스타·광고 카피 3종 생성
              (interest_estimation 수준에 따라 트렌드/실용팁/틈새 포맷 자동 분기)
    │
    ▼
④ reporter    Jinja2 + Playwright → HTML/PDF 리포트
    │
    ▼
⑤ monitor     새 포스트 감지 + Gemini 중요도 평가
    │
    ▼
⑥ poster      Playwright → 네이버 블로그 자동 발행  ※ 로컬 전용
    │
    ▼
⑦ instagram   Graph API + Unsplash 이미지 → Instagram 피드 자동 발행
```

> **참고**: poster(⑥)는 네이버 봇 감지 정책으로 GCP VM에서 실행 불가. 실패해도 파이프라인은 계속 진행되며 instagram(⑦)은 VM에서도 정상 동작합니다.

---

## 시스템 구성

```
marketing-agent/
├── agents/
│   ├── collector/      # 에이전트 1: 네이버 검색 API 병렬 수집
│   ├── analyzer/       # 에이전트 2: Gemini 분석 + DataLab 트렌드 + 히스토리 추적
│   ├── writer/         # 에이전트 3: Gemini 콘텐츠 3종 생성 (포맷 자동 분기)
│   ├── reporter/       # 에이전트 4: PDF 리포트 + 예측 검증
│   ├── monitor/        # 에이전트 5: 키워드 모니터링
│   ├── poster/         # 에이전트 6: 네이버 블로그 자동 포스팅 (Playwright, 로컬 전용)
│   └── instagram/      # 에이전트 7: Instagram Graph API 자동 발행 + Unsplash 이미지
├── templates/          # Flask 웹 UI
├── data/               # 수집·분석 데이터 (JSON)
├── output/             # 생성 콘텐츠·리포트 (JSON, HTML, PDF)
├── logs/               # 스케줄러 실행 로그
├── orchestrator.py     # 전체 파이프라인 CLI 실행기
├── app.py              # Flask 웹 서버 (gunicorn 호환)
├── poster_schedule.py  # Windows 작업 스케줄러용 자동 포스팅 스크립트
├── poster_schedule.bat # 작업 스케줄러 실행 배치 파일
├── setup.sh            # GCP VM 최초 설정 스크립트
├── deploy.sh           # 로컬 → VM 코드 배포 스크립트
├── marketing-agent.service  # systemd 서비스 유닛
└── requirements.txt
```

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
# AI 분석·콘텐츠 생성
GEMINI_API_KEY=your-gemini-api-key

# 네이버 데이터 수집
NAVER_CLIENT_ID=your-naver-client-id
NAVER_CLIENT_SECRET=your-naver-client-secret

# 네이버 블로그 자동 포스팅 (로컬 전용)
NAVER_ID=your-naver-id@naver.com
NAVER_PW=your-naver-password

# Instagram Graph API
INSTAGRAM_ACCESS_TOKEN=your-instagram-access-token
INSTAGRAM_ACCOUNT_ID=your-instagram-account-id

# Unsplash 이미지 검색 (Instagram 포스팅 시 자동 이미지)
UNSPLASH_ACCESS_KEY=your-unsplash-access-key
INSTAGRAM_DEFAULT_IMAGE_URL=https://images.unsplash.com/photo-1611532736597-de2d4265fba3

# 스케줄러 자동 실행 키워드
SCHEDULED_KEYWORDS=AI 마케팅,디지털 마케팅

# ── 보안 (선택, 자세한 내용은 docs/security.md) ──
ADMIN_USER=admin              # 웹 UI 로그인 (미설정 시 인증 비활성)
ADMIN_PASSWORD_HASH=          # (권장) werkzeug 해시. 설정 시 ADMIN_PASSWORD 불필요
FORCE_HTTPS=1                 # HTTPS(리버스 프록시) 운영 시 세션 쿠키 Secure
COOKIE_ENCRYPTION_KEY=        # 미설정 시 data/.enc_key 자동 생성
POSTER_PROXY=                 # poster 봇 감지 우회용 프록시 (권장: residential)
SALES_ENABLED=                # sales 콜드메일 실제 발송 허용(=1). 미설정 시 발송 차단(법적 리스크)

# ── 튜닝 (선택, 미설정 시 기본값) ──
COLLECT_TARGET_COUNT=30       # collector 키워드당 수집 포스트 수
DATALAB_KEYWORD_LIMIT=5       # analyzer 데이터랩 1회 조회 키워드 수
MONITOR_SEEN_LIMIT=500        # monitor 키워드별 보관 링크 수
MONITOR_INTERVAL_MIN=360      # monitor 기본 체크 주기(분)
IG_POLL_ATTEMPTS=12           # instagram 미디어 처리 폴링 횟수(×5초)
```

| 키 | 발급처 |
|----|--------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com) |
| `NAVER_CLIENT_ID/SECRET` | [네이버 개발자센터](https://developers.naver.com) — 검색 API + 데이터랩 권한 필요 |
| `NAVER_ID/PW` | 포스팅할 네이버 계정 |
| `INSTAGRAM_ACCESS_TOKEN/ACCOUNT_ID` | [Meta for Developers](https://developers.facebook.com) — Instagram Graph API |
| `UNSPLASH_ACCESS_KEY` | [Unsplash Developers](https://unsplash.com/developers) — 무료 발급 |

> **보안**: 자격증명 보호(HTTPS·로그인 시도 제한·비밀번호 해시), 네이버 쿠키 at-rest 암호화,
> poster 봇 감지 회피(stealth·프록시) 설정은 [`docs/security.md`](docs/security.md) 참고.
>
> **아키텍처/API**: 시스템 구조·파이프라인·웹 API 레퍼런스·DB 스키마·배포 토폴로지는
> [`docs/architecture.md`](docs/architecture.md) 참고.

### 3. 네이버 로그인 쿠키 초기화 (poster 첫 실행 시, 로컬만)

네이버 봇 감지 우회를 위해 최초 1회 수동 로그인이 필요합니다.

```bash
python agents/poster/main.py --keyword "테스트" --manual-login
# 브라우저가 열리면 직접 로그인 후 터미널에서 Enter
# 쿠키가 data/naver_cookies.json에 저장됩니다
```

이후 실행부터는 저장된 쿠키로 자동 로그인됩니다.

---

## 실행

### 웹 UI (권장)

```bash
python app.py
# http://localhost:5000 접속 후 키워드 입력 → 실행
```

**UI 구성**

```
┌─────────────────────── 글로벌 네비바 ────────────────────────┐
│  마케팅 자동화   수집 › 분석 › 작성 › 카드뉴스 › ...   로그아웃 │
├──────────── 사이드바(280px) ────┬──────── 메인 영역 ──────────┤
│  성공률 도넛 차트              │  KPI 카드 6개               │
│  ─────────────────            │  전체실행 / 이번주 / 최다키워드│
│  키워드 입력  [실행]           │  평균소요 / 성공률 / 오류     │
│  [퀵태그 AI마케팅] [...]       │  ───────────────────────    │
│  ─────────────────            │  결과 패널 (SSE 실시간)      │
│  진행 상황 (실행 시 표시)      │  ───────────────────────    │
│   ✓ 수집  ✓ 분석  ⏳ 작성    │  히스토리 테이블             │
│                               │  [전체][완료][오류] 🔍 기간▼ │
│                               │  상태│키워드│날짜│소요│액션  │
│                               │  ───────────────────────    │
│                               │  예약 관리 (접기/펼치기)     │
└───────────────────────────────┴──────────────────────────────┘
```

**히스토리 테이블 기능**
- 필터 탭: 전체 / 완료 / 오류
- 키워드 검색 + 기간 선택(7일 / 30일 / 전체)
- 오류 행 hover → 에러 원인 툴팁
- 3회 연속 오류 키워드 → "설정 점검하기" 버튼으로 자동 전환
- 페이지네이션 (10개/페이지)

### CLI

```bash
# 단일 키워드
python orchestrator.py --keyword "AI 마케팅"

# 멀티 키워드
python orchestrator.py --keyword "AI 마케팅" "디지털 마케팅"
```

### 에이전트 개별 실행

```bash
# 1. 수집
python agents/collector/main.py --keyword "AI 마케팅"

# 2. 분석
python agents/analyzer/main.py --keyword "AI 마케팅"

# 3. 콘텐츠 생성
python agents/writer/main.py --keyword "AI 마케팅"

# 4. 리포트
python agents/reporter/main.py --date 2026-06-11

# 5. 모니터링 (1회)
python agents/monitor/main.py --keywords "AI 마케팅" --once

# 6. 네이버 블로그 포스팅 (로컬 전용)
python agents/poster/main.py --keyword "AI 마케팅" --date 2026-06-11

# 7. Instagram 포스팅
python agents/instagram/main.py --keyword "AI 마케팅" --date 2026-06-11

# 헬스체크 (각 에이전트가 오늘자 출력을 생성했는지 점검 → logs/healthcheck_*.log)
python agents/healthcheck/main.py --once
```

---

## 테스트 / CI

```bash
.\venv\Scripts\python.exe -m pytest tests/ -q
```

`main` 푸시·PR 시 GitHub Actions(`.github/workflows/ci.yml`)가 자동으로 `pytest`를 실행합니다.

---

## 웹 예약 관리

웹 UI 하단 **예약 관리** 섹션에서 키워드별 자동 실행 스케줄을 추가·수정·삭제할 수 있습니다. 별도 서버 설정 없이 브라우저에서 바로 관리합니다.

| 기능 | 설명 |
|------|------|
| 스케줄 추가 | 이름, 키워드, 요일, 시각, 채널(블로그/인스타) 설정 |
| 활성화 토글 | 스케줄별 on/off — 서버 재시작 없이 즉시 적용 |
| 수정 / 삭제 | 기존 스케줄 인라인 수정 또는 삭제 |
| 실행 방식 | APScheduler CronTrigger — VM 재시작 후 자동 복원 |

---

## Windows 자동 포스팅 스케줄러

매일 오전 10시에 `.env`의 `SCHEDULED_KEYWORDS` 키워드로 네이버 블로그 자동 포스팅을 실행합니다.

```powershell
# 작업 스케줄러 등록 (최초 1회)
schtasks /create /tn "MarketingAgent\NaverBlogPoster" `
  /tr "C:\path\to\marketing-agent\poster_schedule.bat" `
  /sc daily /st 10:00 /f

# 즉시 테스트 실행
schtasks /run /tn "MarketingAgent\NaverBlogPoster"

# 실행 로그 확인
type logs\poster_schedule_20260611.log
```

실행 로그는 `logs/poster_schedule_YYYYMMDD.log`에 날짜별로 저장됩니다.

---

## 출력 결과

| 파일 | 설명 |
|------|------|
| `data/{키워드}_{날짜}.json` | 수집된 블로그 포스트 |
| `data/analyzed_{키워드}_{날짜}.json` | 트렌드·인사이트·DataLab·감성 분포 포함 분석 결과 |
| `data/history.json` | 날짜별 추천 키워드·DataLab 스냅샷 (예측 검증용) |
| `data/naver_cookies.json` | 네이버 로그인 세션 쿠키 |
| `data/instagram_error_{날짜}.json` | Instagram 포스팅 오류 로그 |
| `output/content_{키워드}_{날짜}.json` | 생성된 마케팅 콘텐츠 3종 |
| `output/report_{날짜}.html` | 웹 리포트 |
| `output/report_{날짜}.pdf` | PDF 리포트 |
| `logs/poster_schedule_{날짜}.log` | 스케줄러 실행 로그 |

### 콘텐츠 JSON 구조

```json
{
  "naver_blog": {
    "title": "블로그 제목 (검색량 변화율 등 실데이터 포함)",
    "body": "## 소제목\n본문 (소제목마다 수치·사례 포함)...",
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
scp setup.sh user@VM_IP:~/
ssh user@VM_IP "bash ~/setup.sh"
ssh user@VM_IP "nano ~/marketing-agent/.env"
```

`setup.sh`이 자동 처리: Python 3.11 설치, 저장소 클론, venv 구성, Playwright Chromium 설치, systemd 서비스 등록

### 이후 배포

```bash
bash deploy.sh
# git pull → pip install → 서비스 재시작 자동 실행
```

### VM vs 로컬 동작 차이

| 에이전트 | 로컬 | GCP VM |
|----------|------|--------|
| collector / analyzer / writer / reporter / monitor | ✅ | ✅ |
| instagram | ✅ | ✅ |
| poster (네이버 블로그) | ✅ | ⚠️ 네이버 봇 감지 차단 — 실패해도 파이프라인 계속 진행 |

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| AI 분석·생성 | Google Gemini API (`gemini-2.5-flash-lite`) |
| 검색량 트렌드 | 네이버 데이터랩 API |
| 데이터 수집 | 네이버 검색 API |
| 브라우저 자동화 | Playwright + Chromium |
| Instagram 발행 | Instagram Graph API v21.0 |
| 이미지 검색 | Unsplash API (Gemini 번역 후 영문 검색) |
| 병렬 처리 | `concurrent.futures.ThreadPoolExecutor` |
| 웹 서버 | Flask + gunicorn (gthread) |
| 실시간 스트리밍 | SSE (Server-Sent Events) |
| 리포트 | Jinja2 HTML 템플릿 |
| 스케줄링 | APScheduler (VM) / Windows 작업 스케줄러 (로컬) |
| 환경 변수 | python-dotenv |
| 배포 | GCP e2-micro + systemd |
