import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
import google.genai as genai

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
from google.genai import types


def _sentiment_summary(posts_sentiment: list) -> str:
    counts = {"긍정": 0, "중립": 0, "부정": 0}
    for p in posts_sentiment:
        s = p.get("sentiment", "중립")
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values()) or 1
    parts = [f"{k} {v}건({v*100//total}%)" for k, v in counts.items() if v]
    return ", ".join(parts)


def _dominant_interest(interest_estimation: list) -> str:
    counts = {"높음": 0, "중간": 0, "낮음": 0}
    for item in interest_estimation:
        lv = item.get("level", "중간")
        counts[lv] = counts.get(lv, 0) + 1
    return max(counts, key=counts.get)


def _trend_stats(search_trends: list, keyword: str) -> str:
    for t in search_trends:
        if keyword in t.get("keyword", "") or t.get("keyword", "") in keyword:
            rate = t.get("change_rate", "")
            if rate and rate != "0%":
                return rate
    rates = [t.get("change_rate", "") for t in search_trends if t.get("change_rate", "") not in ("", "0%")]
    return rates[0] if rates else ""


def _post_format_guide(interest_level: str, keyword: str) -> str:
    if interest_level == "높음":
        return f"""포스트 유형: 트렌드 분석 포스트
- 도입부: "{keyword}이(가) 왜 지금 주목받는가?" 형식의 질문으로 시작
- 본문: 최신 트렌드 데이터와 시장 변화 중심
- 각 소제목마다 구체적 수치나 사례 1개 포함 (예: "검색량 XX% 증가", "성공 사례: ~")
- 마무리: "여러분은 어떻게 활용하고 계신가요? 댓글로 공유해주세요!" 형식의 CTA"""
    elif interest_level == "중간":
        return f"""포스트 유형: 실용 팁 포스트
- 도입부: 독자가 겪는 구체적 문제 공감 문장 (예: "~때문에 막막하셨나요?")
- 본문: 바로 적용 가능한 단계별 팁 중심
- 각 소제목마다 실제 적용 사례나 수치 1개 포함
- 마무리: "이 중 가장 도움된 팁은 무엇인가요? 댓글로 알려주세요!" 형식의 CTA"""
    else:
        return f"""포스트 유형: 틈새 기회 포스트
- 도입부: 아직 많이 알려지지 않은 기회임을 강조하는 문장
- 본문: 경쟁이 낮은 지금이 적기임을 데이터로 제시
- 각 소제목마다 구체적 기회 요소나 차별화 포인트 1개 포함
- 마무리: "지금 바로 시작해보셨나요? 경험을 댓글로 나눠주세요!" 형식의 CTA"""


def build_prompt(data: dict) -> str:
    keyword = data.get("keyword", "")
    kw_tag = keyword.replace(" ", "")

    # 데이터 추출
    trends = "\n".join(f"- {t}" for t in data.get("trends", []))
    insights = "\n".join(f"- {i}" for i in data.get("insights", []))
    trend_summary = data.get("trend_summary", "")
    sentiment_str = _sentiment_summary(data.get("posts_sentiment", []))
    interest_level = _dominant_interest(data.get("interest_estimation", []))
    change_rate = _trend_stats(data.get("search_trends", []), keyword)
    competition = data.get("competition_saturation", {})
    audience = data.get("target_audience", {})
    pain_points = "\n".join(f"- {p}" for p in audience.get("pain_points", []))
    motivations = "\n".join(f"- {m}" for m in audience.get("motivations", []))
    primary_audience = audience.get("primary", "마케터 및 소상공인")
    opportunity = competition.get("opportunity", "")
    post_format = _post_format_guide(interest_level, keyword)
    top_keywords = ", ".join(
        k["word"] for k in data.get("keywords", []) if k.get("relevance") == "high"
    )

    # 검색량 변화 문구
    trend_stat_line = f"현재 검색량 변화율: {change_rate}" if change_rate else "검색량 데이터: 제한적"

    return f"""당신은 전문 한국어 마케팅 콘텐츠 작성자입니다.

[핵심 지시사항]
모든 콘텐츠는 반드시 "{keyword}"를 주제로 작성합니다.
아래 분석 데이터의 실제 수치와 인사이트를 콘텐츠에 직접 활용하세요.
모호한 표현("고민 끝!", "최고의 선택" 등) 대신 구체적 수치와 사례를 사용하세요.

## 키워드
{keyword}

## 시장 데이터
- 관심도 수준: {interest_level}
- {trend_stat_line}
- 포스트 감성 분포: {sentiment_str}
- 경쟁 강도: {competition.get("level", "미확인")}
- 틈새 기회: {opportunity}

## 트렌드 요약
{trend_summary}

## 주요 트렌드
{trends}

## 핵심 인사이트
{insights}

## 고빈도 연관 키워드
{top_keywords}

## 타겟 독자
- 주요: {primary_audience}
- 페인포인트:
{pain_points}
- 동기:
{motivations}

## 블로그 포스트 작성 가이드
{post_format}

---

다음 JSON만 출력하세요. 다른 텍스트 없이 JSON만.

{{
  "naver_blog": {{
    "title": "블로그 제목 (50자 이내, '{keyword}' 포함, 검색 최적화, 숫자나 구체적 혜택 포함)",
    "body": "블로그 본문 (1000~1400자, 위 포스트 가이드 형식 준수, ## 소제목 3~4개, 각 소제목 아래 구체적 수치/사례 1개, 마지막에 댓글 유도 CTA)",
    "hashtags": ["#{kw_tag}", "#해시태그2", "#해시태그3", "#해시태그4", "#해시태그5"]
  }},
  "instagram": {{
    "caption": "인스타그램 캡션 (200자 이내, 도입: 실제 데이터나 수치 1개, 본문: 핵심 인사이트 2~3줄, 마무리: 팔로우할 이유 명확히 제시, 이모지 자연스럽게 사용)",
    "hashtags": ["#{kw_tag}", "#해시태그2", "#해시태그3", "#해시태그4", "#해시태그5"]
  }},
  "ad_copy": {{
    "headline": "광고 헤드라인 (30자 이내, 타겟: {primary_audience.split('(')[0].strip().split(',')[0].strip()}, 구체적 수치 포함, 모호한 표현 금지)",
    "subheadline": "서브헤드라인 (50자 이내, 페인포인트 해결 + 구체적 혜택)",
    "cta": "행동 유도 문구 (15자 이내, 명확한 다음 행동)"
  }}
}}\
"""


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
