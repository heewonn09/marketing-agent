# Writer Agent (에이전트 3) 설계 문서

**날짜:** 2026-06-08  
**상태:** 승인됨

---

## 개요

`analyzed_키워드_날짜.json`을 읽어 Gemini API(gemini-2.0-flash)로 SNS 마케팅 콘텐츠를 자동 생성하고 `output/content_키워드_날짜.json`으로 저장하는 에이전트.

---

## 아키텍처

```
analyzed_키워드_날짜.json
        ↓
    WriterAgent (main.py)
        ↓
  generator.py → Gemini 2.0 Flash (단일 API 호출, JSON schema output)
        ↓
output/content_키워드_날짜.json
```

---

## 입력 파일 스키마

`data/analyzed_<키워드>_YYYY-MM-DD.json`:

```json
{
  "keyword": "AI 마케팅",
  "analyzed_at": "2026-06-08T12:00:00",
  "source_file": "AI_마케팅_2026-06-08.json",
  "item_count": 10,
  "trends": ["트렌드 설명 1", "트렌드 설명 2"],
  "insights": ["인사이트 1", "인사이트 2"],
  "keywords": [
    {"word": "생성형 AI", "relevance": "high", "context": "설명"},
    {"word": "콘텐츠 자동화", "relevance": "medium", "context": "설명"}
  ],
  "posts": [
    {
      "title": "블로그 제목",
      "summary": "본문 요약",
      "tags": ["태그1", "태그2"]
    }
  ]
}
```

---

## 출력 파일 스키마

`output/content_<키워드>_YYYY-MM-DD.json`:

```json
{
  "keyword": "AI 마케팅",
  "generated_at": "2026-06-08T12:00:00",
  "source_file": "analyzed_AI_마케팅_2026-06-08.json",
  "naver_blog": {
    "title": "블로그 제목 (50자 이내)",
    "body": "본문 (800~1200자, 단락 구분 포함)",
    "hashtags": ["#AI마케팅", "#생성형AI"]
  },
  "instagram": {
    "caption": "캡션 (150자 이내, 이모지 포함)",
    "hashtags": ["#AI", "#마케팅자동화"]
  },
  "ad_copy": {
    "headline": "헤드라인 (30자 이내)",
    "subheadline": "서브헤드라인 (50자 이내)",
    "cta": "행동 유도 문구 (15자 이내)"
  }
}
```

---

## 파일 구조

```
agents/writer/
  __init__.py
  main.py        # CLI 진입점 (--keyword 또는 --input 인자)
  generator.py   # Gemini API 호출 + 콘텐츠 생성 로직
data/
  analyzed_AI_마케팅_2026-06-08.json   # 테스트용 샘플 (새로 생성)
output/                                # 결과물 저장 디렉토리 (자동 생성)
requirements.txt                       # google-generativeai 패키지 추가
```

---

## Gemini API 호출 전략

- **모델:** `gemini-2.0-flash`
- **방식:** 단일 API 호출, `response_mime_type="application/json"` + `response_schema`로 3가지 포맷 동시 생성
- **환경변수:** `GEMINI_API_KEY`

---

## CLI 실행 방법

```powershell
# 키워드로 자동 파일 탐색 (data/analyzed_<키워드>_*.json 최신 파일)
.\venv\Scripts\python.exe agents\writer\main.py --keyword "AI 마케팅"

# analyzed 파일 직접 지정
.\venv\Scripts\python.exe agents\writer\main.py --input data\analyzed_AI_마케팅_2026-06-08.json
```

---

## 에러 처리

- `GEMINI_API_KEY` 미설정 시 명확한 오류 메시지 출력
- 입력 파일 없을 때 오류 메시지 출력
- Gemini API 오류는 google-generativeai SDK 예외로 처리 (재시도 없음, 즉시 실패)

---

## 범위 외 (YAGNI)

- 재시도 로직
- 스트리밍 (콘텐츠가 짧아서 불필요)
- 콘텐츠 품질 검증
- 다국어 지원
