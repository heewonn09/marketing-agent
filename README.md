# marketing-agent

키워드 하나로 **수집 → 분석 → 콘텐츠 생성 → 리포트 → 모니터링**까지 자동화하는 마케팅 멀티 에이전트 시스템입니다.

## 주요 기능

- **자동 파이프라인**: 키워드 입력 한 번으로 5개 에이전트가 순차 실행
- **네이버 블로그 수집**: Playwright로 실시간 크롤링
- **AI 분석**: Gemini API로 트렌드·인사이트·감성 분석
- **콘텐츠 자동 생성**: 네이버 블로그·인스타그램·광고 카피 3종 생성
- **PDF 리포트**: HTML 템플릿 렌더링 → Playwright PDF 변환
- **키워드 모니터링**: 새 포스트 감지 및 중요도 자동 평가
- **웹 UI**: Flask 기반 실시간 진행 상황 스트리밍 (SSE)

## 시스템 구성

```
marketing-agent/
├── agents/
│   ├── collector/   # 에이전트 1: 네이버 블로그 수집
│   ├── analyzer/    # 에이전트 2: AI 데이터 분석
│   ├── writer/      # 에이전트 3: 콘텐츠 생성
│   ├── reporter/    # 에이전트 4: PDF 리포트 생성
│   └── monitor/     # 에이전트 5: 키워드 모니터링
├── templates/       # Flask 웹 UI 템플릿
├── orchestrator.py  # 전체 파이프라인 CLI 실행기
├── app.py           # Flask 웹 서버
└── requirements.txt
```

## 시작하기

### 1. 환경 설정

```powershell
# 가상환경 생성 및 활성화
python -m venv venv
.\venv\Scripts\Activate.ps1

# 패키지 설치
pip install -r requirements.txt

# Playwright 브라우저 설치
playwright install chromium
```

### 2. API 키 설정

프로젝트 루트에 `.env` 파일을 생성합니다.

```
GEMINI_API_KEY=your-gemini-api-key
```

> Gemini API 키는 [Google AI Studio](https://aistudio.google.com)에서 발급받을 수 있습니다.

### 3. 실행

**웹 UI (권장)**

```powershell
.\venv\Scripts\python.exe app.py
```

브라우저에서 `http://localhost:5000` 접속 후 키워드를 입력하고 실행합니다.

**CLI**

```powershell
.\venv\Scripts\python.exe orchestrator.py --keyword "AI 마케팅"
```

**에이전트 개별 실행**

```powershell
# 1. 수집
.\venv\Scripts\python.exe agents\collector\main.py --keyword "AI 마케팅"

# 2. 분석
.\venv\Scripts\python.exe agents\analyzer\main.py --keyword "AI 마케팅"

# 3. 콘텐츠 생성
.\venv\Scripts\python.exe agents\writer\main.py --keyword "AI 마케팅"

# 4. 리포트 생성
.\venv\Scripts\python.exe agents\reporter\main.py --date 2024-01-01 --keyword "AI 마케팅"

# 5. 모니터링 (1회)
.\venv\Scripts\python.exe agents\monitor\main.py --keywords "AI 마케팅" --once
```

## 출력 결과

| 파일 | 설명 |
|------|------|
| `data/{키워드}_{날짜}.json` | 수집된 블로그 포스트 |
| `data/analyzed_{키워드}_{날짜}.json` | 트렌드·인사이트·감성 분석 결과 |
| `output/content_{키워드}_{날짜}.json` | 생성된 마케팅 콘텐츠 3종 |
| `output/report_{날짜}.html` | 웹 리포트 |
| `output/report_{날짜}.pdf` | PDF 리포트 |

## 기술 스택

| 분류 | 사용 기술 |
|------|-----------|
| AI 분석·생성 | Google Gemini API (`gemini-2.5-flash-lite`) |
| 웹 크롤링 | Playwright |
| 웹 서버 | Flask |
| 리포트 | Jinja2 + Playwright PDF |
| 환경 변수 | python-dotenv |
