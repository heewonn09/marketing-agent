# marketing-agent

키워드 하나로 **수집 → 분석 → 콘텐츠 생성 → 리포트 → 모니터링**까지 자동화하는 마케팅 멀티 에이전트 시스템입니다.

## 주요 기능

- **자동 파이프라인**: 키워드 입력 한 번으로 5개 에이전트가 순차 실행
- **네이버 블로그 수집**: 네이버 검색 API로 병렬 수집 (ThreadPoolExecutor)
- **AI 분석**: Gemini API로 트렌드·인사이트·감성 분석 (멀티 키워드 병렬 처리)
- **네이버 데이터랩 연동**: 실제 검색량 트렌드(최근 4주) + 주간 변화율 시각화
- **히스토리 추적 & 예측 검증**: 지난 주 추천 키워드가 실제로 검색량이 올랐는지 매주 자동 검증
- **콘텐츠 자동 생성**: 네이버 블로그·인스타그램·광고 카피 3종 생성
- **PDF 리포트**: HTML 템플릿 렌더링 → Playwright PDF 변환
- **키워드 모니터링**: 새 포스트 감지 및 중요도 자동 평가
- **웹 UI**: Flask 기반 실시간 진행 상황 스트리밍 (SSE)
- **GCP 배포**: GCP e2-micro VM에 gunicorn + systemd 서비스로 운영

## 시스템 구성

```
marketing-agent/
├── agents/
│   ├── collector/   # 에이전트 1: 네이버 검색 API 병렬 수집
│   ├── analyzer/    # 에이전트 2: AI 분석 + DataLab 트렌드 + 히스토리 추적
│   ├── writer/      # 에이전트 3: 콘텐츠 생성
│   ├── reporter/    # 에이전트 4: PDF 리포트 + 예측 검증 섹션
│   └── monitor/     # 에이전트 5: 키워드 모니터링
├── templates/       # Flask 웹 UI 템플릿
├── orchestrator.py  # 전체 파이프라인 CLI 실행기
├── app.py           # Flask 웹 서버 (gunicorn 호환)
├── setup.sh         # GCP VM 최초 설정 스크립트
├── deploy.sh        # 로컬 → VM 코드 배포 스크립트
├── marketing-agent.service  # systemd 서비스 유닛 파일
└── requirements.txt
```

## 시작하기

### 1. 환경 설정

```bash
# 가상환경 생성 및 활성화
python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1

# Linux / macOS
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt

# Playwright 브라우저 설치
playwright install chromium
```

### 2. API 키 설정

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
GEMINI_API_KEY=your-gemini-api-key
NAVER_CLIENT_ID=your-naver-client-id
NAVER_CLIENT_SECRET=your-naver-client-secret
SCHEDULED_KEYWORDS=AI 마케팅,디지털 마케팅
```

| 키 | 발급처 |
|----|--------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | [네이버 개발자센터](https://developers.naver.com) — 검색 API + 데이터랩(통합 트렌드) 권한 필요 |

### 3. 실행

**웹 UI (권장)**

```bash
python app.py
```

브라우저에서 `http://localhost:5000` 접속 후 키워드를 입력하고 실행합니다.

**CLI**

```bash
# 단일 키워드
python orchestrator.py --keyword "AI 마케팅"

# 멀티 키워드 (병렬 처리)
python orchestrator.py --keyword "AI 마케팅" "디지털 마케팅"
```

**에이전트 개별 실행**

```bash
# 1. 수집
python agents/collector/main.py --keyword "AI 마케팅"

# 2. 분석 (DataLab 트렌드 + 히스토리 저장)
python agents/analyzer/main.py --keyword "AI 마케팅"

# 3. 콘텐츠 생성
python agents/writer/main.py --keyword "AI 마케팅"

# 4. 리포트 생성
python agents/reporter/main.py --date 2024-01-01 --keyword "AI 마케팅"

# 5. 모니터링 (1회)
python agents/monitor/main.py --keywords "AI 마케팅" --once
```

## 리포트 구성

매주 생성되는 HTML/PDF 리포트에 포함되는 섹션:

| 섹션 | 내용 |
|------|------|
| 이번 주 트렌드 키워드 TOP 5 | Gemini 분석 기반 트렌드 키워드 순위 |
| 키워드 검색량 트렌드 (최근 4주) | 네이버 데이터랩 실제 검색 지수 막대 그래프 + 주간 변화율 |
| 생성된 콘텐츠 성과 예측 | AI가 예측한 콘텐츠별 기대 성과 |
| 다음 주 추천 키워드 | AI 추천 키워드 + 추천 이유 |
| 지난 주 예측 검증 | 지난 주 추천 키워드의 실제 검색량 변화(상승/하락/유지) + 적중률 |

## 출력 결과

| 파일 | 설명 |
|------|------|
| `data/{키워드}_{날짜}.json` | 수집된 블로그 포스트 |
| `data/analyzed_{키워드}_{날짜}.json` | 트렌드·인사이트·DataLab 검색량 포함 분석 결과 |
| `data/history.json` | 날짜/키워드별 추천 기록 및 DataLab 스냅샷 (예측 검증용) |
| `output/content_{키워드}_{날짜}.json` | 생성된 마케팅 콘텐츠 3종 |
| `output/report_{날짜}.html` | 웹 리포트 |
| `output/report_{날짜}.pdf` | PDF 리포트 |

## GCP VM 배포

### 최초 설정

```bash
# 1. 로컬에서 VM으로 setup.sh 전송 후 실행
scp setup.sh user@VM_IP:~/
ssh user@VM_IP "bash ~/setup.sh"

# 2. VM에서 .env 파일 편집
nano ~/marketing-agent/.env

# 3. 서비스 시작
sudo systemctl start marketing-agent
```

`setup.sh`가 자동으로 처리하는 항목:
- Python 3.11, git 설치
- 저장소 클론 및 venv 구성
- Playwright Chromium 설치
- systemd 서비스 등록 및 활성화

### 이후 배포 (코드 업데이트)

```bash
bash deploy.sh
```

`deploy.sh`가 자동으로 처리하는 항목: git pull → pip install → playwright install → 서비스 재시작

### GCP 방화벽 설정

```bash
gcloud compute firewall-rules create allow-marketing-agent \
  --allow=tcp:5000 \
  --source-ranges=0.0.0.0/0
```

## 기술 스택

| 분류 | 사용 기술 |
|------|-----------|
| AI 분석·생성 | Google Gemini API (`gemini-2.5-flash-lite`) |
| 검색량 트렌드 | 네이버 데이터랩 API |
| 데이터 수집 | 네이버 검색 API |
| 병렬 처리 | Python `concurrent.futures.ThreadPoolExecutor` |
| 웹 크롤링·PDF | Playwright + Chromium |
| 웹 서버 | Flask + gunicorn (gthread) |
| 리포트 | Jinja2 템플릿 |
| 스케줄링 | APScheduler |
| 환경 변수 | python-dotenv |
| 배포 | GCP e2-micro + systemd |
