# Writer Agent (에이전트 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `data/analyzed_키워드_날짜.json`을 읽어 Gemini API로 네이버 블로그글·인스타 캡션·광고 카피 3종을 생성하고 `output/content_키워드_날짜.json`으로 저장하는 CLI 에이전트를 구현한다.

**Architecture:** `main.py`가 CLI 인자를 파싱하고 analyzed JSON을 로드한다. `generator.py`가 Gemini API를 단일 호출해 3가지 콘텐츠를 JSON으로 받는다. `main.py`가 메타데이터를 추가해 `output/`에 저장한다.

**Tech Stack:** Python 3.14, google-generativeai, argparse, pytest

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `requirements.txt` | `google-generativeai` 추가 |
| `agents/writer/__init__.py` | 패키지 마커 |
| `agents/writer/generator.py` | Gemini API 호출, 프롬프트 빌드, JSON 반환 |
| `agents/writer/main.py` | CLI 진입점: 파일 탐색 → generator 호출 → output 저장 |
| `data/analyzed_AI_마케팅_2026-06-08.json` | 테스트용 샘플 입력 데이터 |
| `tests/__init__.py` | 테스트 패키지 마커 |
| `tests/writer/__init__.py` | 테스트 패키지 마커 |
| `tests/writer/test_generator.py` | generator.py 단위 테스트 |

---

## Task 1: 의존성 추가 및 샘플 데이터 생성

**Files:**
- Modify: `requirements.txt`
- Create: `data/analyzed_AI_마케팅_2026-06-08.json`

- [ ] **Step 1: requirements.txt에 google-generativeai 추가**

`requirements.txt`를 다음으로 교체:

```
playwright==1.60.0
google-generativeai>=0.8.0
pytest>=8.0.0
```

- [ ] **Step 2: 패키지 설치**

```powershell
.\venv\Scripts\python.exe -m pip install google-generativeai>=0.8.0 pytest>=8.0.0
```

Expected: `Successfully installed google-generativeai-...`

- [ ] **Step 3: 테스트용 샘플 analyzed JSON 생성**

`data/analyzed_AI_마케팅_2026-06-08.json`을 다음 내용으로 생성:

```json
{
  "keyword": "AI 마케팅",
  "analyzed_at": "2026-06-08T12:00:00",
  "source_file": "AI_마케팅_2026-06-08.json",
  "item_count": 5,
  "trends": [
    "생성형 AI를 활용한 콘텐츠 자동화가 마케터들 사이에서 빠르게 확산되고 있다",
    "AI 기반 개인화 마케팅이 전통적 대중 마케팅을 대체하는 추세",
    "소규모 브랜드도 AI 도구로 대기업 수준의 콘텐츠 생산이 가능해짐"
  ],
  "insights": [
    "AI 마케팅 도입 기업의 ROI가 평균 37% 향상됨",
    "콘텐츠 제작 시간이 AI 도입 후 70% 단축되는 사례 다수",
    "고객 데이터 분석을 통한 초개인화 메시지가 클릭률 2.5배 향상"
  ],
  "keywords": [
    {"word": "생성형 AI", "relevance": "high", "context": "ChatGPT, Claude 등 LLM 기반 콘텐츠 생성 도구 활용 사례 급증"},
    {"word": "콘텐츠 자동화", "relevance": "high", "context": "블로그, SNS, 이메일 마케팅 등 다양한 채널의 콘텐츠를 AI로 자동 생성"},
    {"word": "초개인화", "relevance": "medium", "context": "고객 행동 데이터 분석 기반 맞춤형 메시지 발송"},
    {"word": "ROI 향상", "relevance": "medium", "context": "AI 마케팅 도입 후 측정 가능한 성과 지표 개선"},
    {"word": "소규모 브랜드", "relevance": "low", "context": "중소기업도 AI 도구로 대형 마케팅 캠페인 실행 가능"}
  ],
  "posts": [
    {
      "title": "AI로 마케팅 콘텐츠 10배 빠르게 만드는 법",
      "summary": "ChatGPT와 Claude를 활용해 블로그 포스트, SNS 카피, 이메일 뉴스레터를 자동화하는 실전 가이드. 프롬프트 작성법부터 결과물 검수까지.",
      "tags": ["AI마케팅", "콘텐츠자동화", "생성형AI", "마케팅자동화"]
    },
    {
      "title": "2026년 AI 마케팅 트렌드 총정리",
      "summary": "올해 마케팅 업계를 뒤흔든 AI 기술 5가지. 초개인화, 예측 분석, 자동화 캠페인 등 실제 브랜드 적용 사례와 함께 설명.",
      "tags": ["마케팅트렌드", "AI", "디지털마케팅", "2026트렌드"]
    },
    {
      "title": "소규모 브랜드를 위한 AI 마케팅 입문",
      "summary": "월 5만원으로 AI 마케팅 시작하기. 무료·저가 AI 툴 조합으로 대기업 부럽지 않은 마케팅 콘텐츠 제작하는 방법.",
      "tags": ["스몰브랜드", "AI툴", "마케팅입문", "비용절감"]
    },
    {
      "title": "AI 마케팅 ROI 측정 방법 완전 가이드",
      "summary": "AI 도입 후 마케팅 성과를 수치로 증명하는 법. KPI 설정, 대조군 실험, 데이터 분석 프레임워크 공개.",
      "tags": ["마케팅ROI", "데이터분석", "성과측정", "AI마케팅"]
    },
    {
      "title": "ChatGPT로 인스타그램 콘텐츠 한 달치 만들기",
      "summary": "30개 인스타 게시물을 2시간 만에 기획·제작하는 워크플로우. 프롬프트 템플릿과 실제 결과물 공개.",
      "tags": ["인스타그램마케팅", "ChatGPT", "SNS콘텐츠", "콘텐츠캘린더"]
    }
  ]
}
```

- [ ] **Step 4: 커밋**

```powershell
git add requirements.txt "data/analyzed_AI_마케팅_2026-06-08.json"
git commit -m "chore: add google-generativeai dependency and sample analyzed data"
```

---

## Task 2: generator.py TDD

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/writer/__init__.py`
- Create: `tests/writer/test_generator.py`
- Create: `agents/writer/__init__.py`
- Create: `agents/writer/generator.py`

- [ ] **Step 1: 테스트 디렉토리 및 패키지 파일 생성**

다음 빈 파일들을 생성:
- `tests/__init__.py` (빈 파일)
- `tests/writer/__init__.py` (빈 파일)
- `agents/writer/__init__.py` (빈 파일)

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/writer/test_generator.py`:

```python
import json
import os
import pytest
from unittest.mock import patch, MagicMock


def test_generate_content_returns_three_formats():
    """generator가 3가지 콘텐츠 포맷을 반환하는지 확인."""
    from agents.writer.generator import generate_content

    sample_data = {
        "keyword": "AI 마케팅",
        "trends": ["트렌드1"],
        "insights": ["인사이트1"],
        "keywords": [{"word": "AI", "relevance": "high", "context": "설명"}],
        "posts": [{"title": "제목", "summary": "요약", "tags": ["태그"]}],
    }

    fake_response_text = json.dumps({
        "naver_blog": {
            "title": "AI 마케팅 완전 정복",
            "body": "본문 내용입니다.",
            "hashtags": ["#AI마케팅"]
        },
        "instagram": {
            "caption": "✨ AI로 마케팅 혁신!",
            "hashtags": ["#AI"]
        },
        "ad_copy": {
            "headline": "AI로 매출 2배",
            "subheadline": "지금 바로 시작하세요",
            "cta": "무료 체험하기"
        }
    })

    mock_response = MagicMock()
    mock_response.text = fake_response_text

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch("google.generativeai.GenerativeModel", return_value=mock_model):
            with patch("google.generativeai.configure"):
                result = generate_content(sample_data)

    assert "naver_blog" in result
    assert "instagram" in result
    assert "ad_copy" in result
    assert "title" in result["naver_blog"]
    assert "body" in result["naver_blog"]
    assert "hashtags" in result["naver_blog"]
    assert "caption" in result["instagram"]
    assert "hashtags" in result["instagram"]
    assert "headline" in result["ad_copy"]
    assert "subheadline" in result["ad_copy"]
    assert "cta" in result["ad_copy"]


def test_generate_content_raises_when_api_key_missing():
    """GEMINI_API_KEY 미설정 시 EnvironmentError 발생 확인."""
    from agents.writer.generator import generate_content

    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("GEMINI_API_KEY", None)
        with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
            generate_content({"keyword": "test"})


def test_build_prompt_includes_keyword():
    """프롬프트에 키워드가 포함되는지 확인."""
    from agents.writer.generator import build_prompt

    data = {
        "keyword": "AI 마케팅",
        "trends": ["트렌드1", "트렌드2"],
        "insights": ["인사이트1"],
        "keywords": [{"word": "생성형 AI", "relevance": "high", "context": "설명"}],
        "posts": [],
    }

    prompt = build_prompt(data)

    assert "AI 마케팅" in prompt
    assert "트렌드1" in prompt
    assert "인사이트1" in prompt
    assert "생성형 AI" in prompt
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

```powershell
.\venv\Scripts\python.exe -m pytest tests/writer/test_generator.py -v
```

Expected: `ImportError` 또는 `ModuleNotFoundError` — `agents.writer.generator` 미존재

- [ ] **Step 4: generator.py 구현**

`agents/writer/generator.py`:

```python
import json
import os

import google.generativeai as genai


def build_prompt(data: dict) -> str:
    keyword = data.get("keyword", "")
    trends = "\n".join(f"- {t}" for t in data.get("trends", []))
    insights = "\n".join(f"- {i}" for i in data.get("insights", []))
    keywords = "\n".join(
        f"- {k['word']} ({k['relevance']}): {k['context']}"
        for k in data.get("keywords", [])
    )
    posts = "\n".join(
        f"- {p['title']}: {p['summary']}"
        for p in data.get("posts", [])
    )

    return f"""당신은 전문 한국어 마케팅 콘텐츠 작성자입니다.
다음 마케팅 분석 데이터를 바탕으로 SNS 콘텐츠 3가지를 한국어로 생성해주세요.

## 키워드
{keyword}

## 주요 트렌드
{trends}

## 인사이트
{insights}

## 핵심 키워드
{keywords}

## 참고 블로그 포스트
{posts}

## 생성 요구사항

다음 JSON 형식으로 정확히 응답하세요. 다른 텍스트 없이 JSON만 출력하세요.

{{
  "naver_blog": {{
    "title": "블로그 제목 (50자 이내, 검색 최적화 포함)",
    "body": "블로그 본문 (800~1200자, 소제목과 단락 구분 포함, 전문적이고 유익한 내용)",
    "hashtags": ["#해시태그1", "#해시태그2", "#해시태그3", "#해시태그4", "#해시태그5"]
  }},
  "instagram": {{
    "caption": "인스타그램 캡션 (150자 이내, 이모지 포함, 공감 가는 톤)",
    "hashtags": ["#해시태그1", "#해시태그2", "#해시태그3", "#해시태그4", "#해시태그5", "#해시태그6", "#해시태그7", "#해시태그8", "#해시태그9", "#해시태그10"]
  }},
  "ad_copy": {{
    "headline": "광고 헤드라인 (30자 이내, 강렬하고 직접적)",
    "subheadline": "서브헤드라인 (50자 이내, 혜택 강조)",
    "cta": "행동 유도 문구 (15자 이내, 클릭 유도)"
  }}
}}"""


def generate_content(analyzed_data: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY 환경변수가 설정되지 않았습니다.\n"
            "PowerShell: $env:GEMINI_API_KEY = 'your-api-key'"
        )

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
        ),
    )

    prompt = build_prompt(analyzed_data)
    response = model.generate_content(prompt)
    return json.loads(response.text)
```

- [ ] **Step 5: 테스트 재실행 → 통과 확인**

```powershell
.\venv\Scripts\python.exe -m pytest tests/writer/test_generator.py -v
```

Expected:
```
tests/writer/test_generator.py::test_generate_content_returns_three_formats PASSED
tests/writer/test_generator.py::test_generate_content_raises_when_api_key_missing PASSED
tests/writer/test_generator.py::test_build_prompt_includes_keyword PASSED
3 passed
```

- [ ] **Step 6: 커밋**

```powershell
git add agents/writer/__init__.py agents/writer/generator.py tests/__init__.py tests/writer/__init__.py tests/writer/test_generator.py
git commit -m "feat: add writer generator with Gemini API integration"
```

---

## Task 3: main.py 구현

**Files:**
- Create: `agents/writer/main.py`
- Create: `output/.gitkeep`

- [ ] **Step 1: output 디렉토리 생성**

```powershell
New-Item -ItemType Directory -Force output
New-Item -ItemType File -Force output/.gitkeep
```

- [ ] **Step 2: main.py 작성**

`agents/writer/main.py`:

```python
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def find_analyzed_file(keyword: str, data_dir: Path) -> Path:
    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    pattern = f"analyzed_{safe_keyword}_*.json"
    matches = sorted(data_dir.glob(pattern), reverse=True)
    if not matches:
        raise FileNotFoundError(
            f"'{pattern}' 파일을 {data_dir}에서 찾을 수 없습니다.\n"
            "먼저 에이전트 2(analyzer)를 실행해 analyzed 파일을 생성하세요."
        )
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="마케팅 콘텐츠 생성기 (에이전트 3)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--keyword", help="키워드 (data/analyzed_<키워드>_*.json 자동 탐색)")
    group.add_argument("--input", help="analyzed JSON 파일 경로 직접 지정")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent.parent

    if args.input:
        input_path = Path(args.input)
    else:
        input_path = find_analyzed_file(args.keyword, project_root / "data")

    if not input_path.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"입력 파일: {input_path}")

    with open(input_path, encoding="utf-8") as f:
        analyzed_data = json.load(f)

    keyword = analyzed_data.get("keyword", args.keyword or "unknown")
    print(f"키워드 '{keyword}' 콘텐츠 생성 중...")

    from agents.writer.generator import generate_content
    content = generate_content(analyzed_data)

    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = output_dir / f"content_{safe_keyword}_{date_str}.json"

    result = {
        "keyword": keyword,
        "generated_at": datetime.now().isoformat(),
        "source_file": input_path.name,
        **content,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"생성 완료 → {output_path}")
    print(f"  네이버 블로그 제목: {content['naver_blog']['title']}")
    print(f"  인스타 캡션: {content['instagram']['caption'][:50]}...")
    print(f"  광고 헤드라인: {content['ad_copy']['headline']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 커밋**

```powershell
git add agents/writer/main.py output/.gitkeep
git commit -m "feat: add writer main.py CLI entrypoint"
```

---

## Task 4: CLAUDE.md 업데이트 및 통합 테스트

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: CLAUDE.md에 에이전트 3 섹션 추가**

`CLAUDE.md`의 `## Python 버전` 섹션 바로 위에 다음을 추가:

```markdown
### 에이전트 3: 콘텐츠 생성 (writer)

analyzed JSON을 읽어 Gemini API로 SNS 마케팅 콘텐츠 3종을 자동 생성한다.

```powershell
# GEMINI_API_KEY 환경변수 필요
$env:GEMINI_API_KEY = "your-api-key"

# 키워드로 자동 파일 탐색
.\venv\Scripts\python.exe agents\writer\main.py --keyword "AI 마케팅"

# 파일 직접 지정
.\venv\Scripts\python.exe agents\writer\main.py --input data\analyzed_AI_마케팅_2026-06-08.json
```

출력: `output/content_<키워드>_YYYY-MM-DD.json`

JSON 구조:
```json
{
  "keyword": "AI 마케팅",
  "generated_at": "2026-06-08T12:00:00",
  "source_file": "analyzed_AI_마케팅_2026-06-08.json",
  "naver_blog": {
    "title": "블로그 제목",
    "body": "본문 (800~1200자)",
    "hashtags": ["#AI마케팅"]
  },
  "instagram": {
    "caption": "캡션 (150자 이내)",
    "hashtags": ["#AI"]
  },
  "ad_copy": {
    "headline": "헤드라인",
    "subheadline": "서브헤드라인",
    "cta": "무료 체험하기"
  }
}
```
```

- [ ] **Step 2: 전체 테스트 실행**

```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v
```

Expected:
```
tests/writer/test_generator.py::test_generate_content_returns_three_formats PASSED
tests/writer/test_generator.py::test_generate_content_raises_when_api_key_missing PASSED
tests/writer/test_generator.py::test_build_prompt_includes_keyword PASSED
3 passed
```

- [ ] **Step 3: 실제 API 키가 있다면 통합 테스트 (선택)**

```powershell
$env:GEMINI_API_KEY = "your-actual-key"
.\venv\Scripts\python.exe agents\writer\main.py --input "data\analyzed_AI 마케팅_2026-06-08.json"
```

Expected:
```
입력 파일: data\analyzed_AI 마케팅_2026-06-08.json
키워드 'AI 마케팅' 콘텐츠 생성 중...
생성 완료 → output\content_AI_마케팅_2026-06-08.json
  네이버 블로그 제목: ...
  인스타 캡션: ...
  광고 헤드라인: ...
```

- [ ] **Step 4: 최종 커밋**

```powershell
git add CLAUDE.md
git commit -m "docs: add writer agent documentation to CLAUDE.md"
```
