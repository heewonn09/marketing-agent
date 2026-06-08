---
title: Reporter Agent (에이전트 4) 설계
date: 2026-06-08
---

## 개요

`output/content_키워드_날짜.json`을 읽어 Claude API로 분석 후 HTML + PDF 주간 마케팅 리포트를 생성하는 에이전트.

## 파일 구조

```
agents/reporter/
├── main.py          # 진입점, CLI, 오케스트레이션
└── template.html    # Jinja2 HTML 리포트 템플릿
```

## content JSON 형식 (입력)

```json
[
  {
    "keyword": "AI 마케팅",
    "title": "블로그 제목",
    "summary": "본문 요약",
    "target": "타겟 독자",
    "created_at": "2026-06-08T10:00:00"
  }
]
```

## 리포트 섹션

1. 트렌드 키워드 TOP 5 (rank, keyword, reason)
2. 콘텐츠 성과 예측 (title, predicted_level: 높음/중간/낮음, reason)
3. 다음 주 추천 키워드 5개 (keyword, rationale)

## 기술 스택

- Claude API (`claude-haiku-4-5-20251001`) — 분석 인사이트 생성
- Jinja2 — HTML 템플릿 렌더링
- Playwright — HTML → PDF 변환 (기존 의존성 재사용)

## 실행

```powershell
$env:ANTHROPIC_API_KEY = "your-key"
.\venv\Scripts\python.exe agents\reporter\main.py --date 2026-06-08
```

출력: `output/report_2026-06-08.html`, `output/report_2026-06-08.pdf`
