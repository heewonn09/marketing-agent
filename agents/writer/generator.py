import json
import os
import re
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

[핵심 지시사항]
아래 모든 콘텐츠는 반드시 "{keyword}"를 주제로 작성해야 합니다.
제목·본문·해시태그 전부 "{keyword}"와 직접 관련된 내용이어야 합니다.
참고 포스트는 문체·구성 참고용이며, 그 포스트의 주제를 그대로 사용하지 마세요.

## 목표 키워드 (반드시 콘텐츠 주제로 사용)
{keyword}

## 시장 트렌드 (참고)
{trends}

## 인사이트 (참고)
{insights}

## 관련 키워드 (참고)
{keywords}

## 참고 포스트 (문체·구성만 참고, 주제 따르지 말 것)
{posts}

## 출력 형식

다음 JSON만 출력하세요. 다른 텍스트 없이 JSON만.

{{
  "naver_blog": {{
    "title": "블로그 제목 (50자 이내, '{keyword}' 키워드 포함, 검색 최적화)",
    "body": "블로그 본문 (800~1200자, '{keyword}' 주제, ## 소제목 포함, 단락 구분)",
    "hashtags": ["#{keyword.replace(' ', '')}", "#해시태그2", "#해시태그3", "#해시태그4", "#해시태그5"]
  }},
  "instagram": {{
    "caption": "인스타그램 캡션 (150자 이내, '{keyword}' 주제, 이모지 포함)",
    "hashtags": ["#{keyword.replace(' ', '')}", "#해시태그2", "#해시태그3", "#해시태그4", "#해시태그5", "#해시태그6", "#해시태그7", "#해시태그8", "#해시태그9", "#해시태그10"]
  }},
  "ad_copy": {{
    "headline": "광고 헤드라인 (30자 이내, '{keyword}' 관련, 강렬하고 직접적)",
    "subheadline": "서브헤드라인 (50자 이내, 혜택 강조)",
    "cta": "행동 유도 문구 (15자 이내)"
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

    text = response.text.strip()
    # 마크다운 코드블록 제거
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 1차: 무효 이스케이프 수정 (\( \% 등 → \\( \\% )
        # 유효 JSON 이스케이프: \" \\ \/ \b \f \n \r \t \uXXXX
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            # 2차: 리터럴 줄바꿈 허용 (strict=False)
            return json.loads(fixed, strict=False)
