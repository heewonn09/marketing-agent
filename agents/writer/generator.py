import json
import os
from pathlib import Path

from dotenv import load_dotenv
import google.genai as genai

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
from google.genai import types


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

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(analyzed_data)

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    return json.loads(response.text)
