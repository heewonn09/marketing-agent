# Marketing Agent - 마케팅 자동화 멀티 에이전트 시스템

## 프로젝트 개요

마케팅 데이터 수집부터 리포트 생성까지 자동화하는 5개 에이전트 시스템.

## 구조

```
marketing-agent/
├── agents/
│   ├── collector/    # 에이전트 1: 네이버 블로그 등 데이터 수집
│   ├── analyzer/     # 에이전트 2: 수집 데이터 분석
│   ├── writer/       # 에이전트 3: 마케팅 콘텐츠 생성
│   ├── reporter/     # 에이전트 4: 리포트 생성
│   ├── monitor/      # 에이전트 5: 지속 모니터링
│   └── poster/       # 에이전트 6: 네이버 블로그 자동 포스팅
├── data/             # 수집된 원시 데이터 (JSON)
├── output/           # 최종 결과물
├── venv/             # Python 가상환경
└── requirements.txt
```

## 환경 설정

```powershell
# 가상환경 활성화 (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# 또는 직접 venv python 사용
.\venv\Scripts\python.exe <script>
```

## 에이전트 실행

### 에이전트 1: 데이터 수집 (collector)

네이버 블로그 검색 결과를 수집해 JSON으로 저장한다.

```powershell
.\venv\Scripts\python.exe agents\collector\main.py --keyword "AI 마케팅"
```

출력: `data/<키워드>_YYYY-MM-DD.json`

JSON 구조:
```json
[
  {
    "title": "블로그 제목",
    "link": "https://...",
    "summary": "본문 요약",
    "collected_at": "2026-06-08T12:00:00"
  }
]
```

### 에이전트 2: 데이터 분석 (analyzer)

에이전트 1이 수집한 JSON 데이터를 Gemini API로 분석해 트렌드/인사이트/키워드를 추출한다.

```powershell
# .env 파일에 GEMINI_API_KEY 설정 필요 (프로젝트 루트)
# GEMINI_API_KEY=your-api-key

.\venv\Scripts\python.exe agents\analyzer\main.py --keyword "AI 마케팅"
```

출력: `data/analyzed_<키워드>_YYYY-MM-DD.json`

JSON 구조:
```json
{
  "keyword": "AI 마케팅",
  "analyzed_at": "2026-06-08T12:00:00",
  "source_file": "AI_마케팅_2026-06-08.json",
  "item_count": 10,
  "keyword_frequency": [{"word": "생성형", "count": 5}],
  "posts_sentiment": [{"title": "...", "link": "...", "sentiment": "긍정", "sentiment_reason": "..."}],
  "trend_summary": "전반적 트렌드 요약",
  "trends": ["트렌드 설명 1", "트렌드 설명 2"],
  "insights": ["인사이트 1", "인사이트 2"],
  "keywords": [
    {"word": "생성형 AI", "relevance": "high", "context": "설명"},
    {"word": "콘텐츠 자동화", "relevance": "medium", "context": "설명"}
  ]
}
```

테스트용 샘플 데이터: `data/AI_마케팅_2026-06-08.json` (10개 포스트)

### 에이전트 5: 지속 모니터링 (monitor)

키워드를 주기적으로 수집해 새 포스트를 감지하고, Gemini로 중요도를 평가해 알림을 기록한다.

```powershell
# 1회 실행
.\venv\Scripts\python.exe agents\monitor\main.py --once

# 6시간마다 지속 실행 (기본값)
.\venv\Scripts\python.exe agents\monitor\main.py

# 체크 주기 변경 (분 단위)
.\venv\Scripts\python.exe agents\monitor\main.py --interval 60

# 키워드 직접 지정
.\venv\Scripts\python.exe agents\monitor\main.py --keywords "AI 마케팅" "디지털 마케팅"
```

모니터링 키워드 설정: `agents/monitor/keywords.json`

```json
["AI 마케팅", "디지털 마케팅", "콘텐츠 마케팅"]
```

출력:
- `data/monitor_state.json` — 키워드별 확인한 포스트 링크 목록 (중복 방지용)
- `data/monitor_log_YYYY-MM-DD.json` — 일별 알림 로그

로그 구조:
```json
[
  {
    "keyword": "AI 마케팅",
    "new_post_count": 5,
    "is_significant": true,
    "level": "high",
    "summary": "생성형 AI 도입 사례 급증",
    "reasons": ["이유1", "이유2"],
    "new_posts": [{"title": "...", "link": "..."}],
    "checked_at": "2026-06-08T12:00:00"
  }
]
```

**동작 방식:**
- 첫 실행 시: 현재 포스트를 기준선으로 등록만 하고 알림 없음
- 이후 실행: 새 포스트 발견 시 Gemini가 중요도(high/medium/low) 평가
- `is_significant=true`인 알림만 콘솔에 강조 출력

### 에이전트 6: 네이버 블로그 자동 포스팅 (poster)

`output/content_{키워드}_{날짜}.json`(writer 출력)을 읽어 네이버 블로그에 발행한다.

```powershell
# ① 최초 1회: 브라우저에서 직접 로그인 후 쿠키 저장 (CAPTCHA 우회)
.\venv\Scripts\python.exe agents\poster\main.py --keyword "AI 마케팅" --manual-login

# ② 이후: 저장된 쿠키로 자동 포스팅
.\venv\Scripts\python.exe agents\poster\main.py --keyword "AI 마케팅" --date 2026-06-10

# 로그인 상태 확인만
.\venv\Scripts\python.exe agents\poster\main.py --keyword "AI 마케팅" --login-only
```

**동작 방식:**
- `data/naver_cookies.json` 존재 시 쿠키로 세션 재사용
- 쿠키 만료 시 자동 재로그인 시도, 실패 시 `--manual-login` 안내
- 오류 발생 시 스크린샷 → `data/poster_error.png`
- 네이버 봇 감지로 자동 로그인이 막히면 `--manual-login`으로 수동 쿠키 획득

**콘텐츠 소스**: `output/content_{키워드}_{날짜}.json`
- `naver_blog.title` → 블로그 제목
- `naver_blog.body` → 블로그 본문
- (또는 `naver_title`, `naver_content` 필드도 지원)

## Python 버전

Python 3.14 (venv 경로: `C:\Users\이희원\AppData\Local\Python\bin\python.exe`)
