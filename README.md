# 마케팅 자동화 시스템

키워드 하나로 **수집 → 분석 → 콘텐츠 생성 → 리포트 → 모니터링 → 블로그 포스팅**까지 자동화하는 6단계 멀티 에이전트 시스템입니다.

![웹 UI](data/ui_done.png)

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 자동 파이프라인 | 키워드 입력 한 번으로 6개 에이전트 순차 실행 |
| 네이버 블로그 수집 | 네이버 검색 API로 최대 30개 포스트 병렬 수집 |
| AI 분석 | Gemini API로 트렌드·인사이트·감성 분석 |
| 데이터랩 연동 | 네이버 데이터랩 실제 검색량 트렌드(최근 4주) + 주간 변화율 |
| 히스토리 추적 | 지난 주 추천 키워드의 실제 검색량 변화 자동 검증 |
| 콘텐츠 자동 생성 | 네이버 블로그·인스타그램·광고 카피 3종 생성 |
| PDF 리포트 | Jinja2 HTML 렌더링 → Playwright PDF 변환 |
| 키워드 모니터링 | 새 포스트 감지 및 Gemini 중요도 자동 평가 |
| **블로그 자동 발행** | Playwright로 네이버 SmartEditor ONE 조작, 마크다운 → HTML 변환 후 발행 |
| 웹 UI | Flask + SSE 기반 실시간 진행 상황 스트리밍 |
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
② analyzer    Gemini + DataLab → 트렌드·인사이트·감성 분석
    │
    ▼
③ writer      Gemini → 블로그·인스타·광고 카피 3종 생성
    │
    ▼
④ reporter    Jinja2 + Playwright → HTML/PDF 리포트
    │
    ▼
⑤ monitor     새 포스트 감지 + Gemini 중요도 평가
    │
    ▼
⑥ poster      Playwright → 네이버 블로그 자동 발행
```

---

## 시스템 구성

```
marketing-agent/
├── agents/
│   ├── collector/   # 에이전트 1: 네이버 검색 API 병렬 수집
│   ├── analyzer/    # 에이전트 2: Gemini 분석 + DataLab 트렌드 + 히스토리 추적
│   ├── writer/      # 에이전트 3: Gemini 콘텐츠 3종 생성
│   ├── reporter/    # 에이전트 4: PDF 리포트 + 예측 검증
│   ├── monitor/     # 에이전트 5: 키워드 모니터링
│   └── poster/      # 에이전트 6: 네이버 블로그 자동 포스팅 (Playwright)
├── templates/       # Flask 웹 UI
├── data/            # 수집·분석 데이터 (JSON)
├── output/          # 생성 콘텐츠·리포트 (JSON, HTML, PDF)
├── orchestrator.py  # 전체 파이프라인 CLI 실행기
├── app.py           # Flask 웹 서버 (gunicorn 호환)
├── setup.sh         # GCP VM 최초 설정 스크립트
├── deploy.sh        # 로컬 → VM 코드 배포 스크립트
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

# 네이버 블로그 자동 포스팅
NAVER_ID=your-naver-id@naver.com
NAVER_PW=your-naver-password

# 스케줄러 자동 실행 키워드 (선택)
SCHEDULED_KEYWORDS=AI 마케팅,디지털 마케팅
```

| 키 | 발급처 |
|----|--------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com) |
| `NAVER_CLIENT_ID/SECRET` | [네이버 개발자센터](https://developers.naver.com) — 검색 API + 데이터랩 권한 필요 |
| `NAVER_ID/PW` | 포스팅할 네이버 계정 |

### 3. 네이버 로그인 쿠키 초기화 (포스터 첫 실행 시)

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
python agents/reporter/main.py --date 2026-06-10

# 5. 모니터링 (1회)
python agents/monitor/main.py --keywords "AI 마케팅" --once

# 6. 포스팅
python agents/poster/main.py --keyword "AI 마케팅" --date 2026-06-10
```

---

## 출력 결과

| 파일 | 설명 |
|------|------|
| `data/{키워드}_{날짜}.json` | 수집된 블로그 포스트 |
| `data/analyzed_{키워드}_{날짜}.json` | 트렌드·인사이트·DataLab 포함 분석 결과 |
| `data/history.json` | 날짜별 추천 키워드·DataLab 스냅샷 (예측 검증용) |
| `data/naver_cookies.json` | 네이버 로그인 세션 쿠키 |
| `output/content_{키워드}_{날짜}.json` | 생성된 마케팅 콘텐츠 3종 |
| `output/report_{날짜}.html` | 웹 리포트 |
| `output/report_{날짜}.pdf` | PDF 리포트 |

### 콘텐츠 JSON 구조

```json
{
  "naver_blog": {
    "title": "블로그 제목",
    "body": "## 소제목\n본문 내용...",
    "hashtags": ["#해시태그1", "#해시태그2"]
  },
  "instagram": {
    "caption": "캡션 내용 🔥",
    "hashtags": ["#해시태그1", "#해시태그2"]
  },
  "ad_copy": {
    "headline": "광고 헤드라인",
    "subheadline": "서브헤드라인",
    "cta": "지금 시작하기"
  }
}
```

---

## GCP VM 배포

### 최초 설정

```bash
# VM에 setup.sh 전송 후 실행
scp setup.sh user@VM_IP:~/
ssh user@VM_IP "bash ~/setup.sh"

# .env 파일 편집
ssh user@VM_IP "nano ~/marketing-agent/.env"
```

`setup.sh`이 자동 처리하는 항목: Python 3.11 설치, 저장소 클론, venv 구성, Playwright Chromium 설치, systemd 서비스 등록

### 이후 배포

```bash
bash deploy.sh
# git pull → pip install → playwright install → 서비스 재시작 자동 실행
```

### 방화벽 설정

```bash
gcloud compute firewall-rules create allow-marketing-agent \
  --allow=tcp:5000 \
  --source-ranges=0.0.0.0/0
```

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| AI 분석·생성 | Google Gemini API (`gemini-2.5-flash-lite`) |
| 검색량 트렌드 | 네이버 데이터랩 API |
| 데이터 수집 | 네이버 검색 API |
| 브라우저 자동화 | Playwright + Chromium |
| 병렬 처리 | `concurrent.futures.ThreadPoolExecutor` |
| 웹 서버 | Flask + gunicorn (gthread) |
| 리포트 | Jinja2 HTML 템플릿 |
| 스케줄링 | APScheduler |
| 환경 변수 | python-dotenv |
| 배포 | GCP e2-micro + systemd |
