import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
import google.genai as genai

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
from google.genai import types

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from utils.gemini_retry import gemini_retry


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
    next_week_raw = data.get("next_week_keywords", [])[:2]
    next_week_kw = ", ".join(
        item["keyword"] if isinstance(item, dict) else item
        for item in next_week_raw
    )

    # 검색량 변화 문구
    trend_stat_line = f"현재 검색량 변화율: {change_rate}" if change_rate else "검색량 데이터: 제한적"

    return f"""당신은 전문 한국어 마케팅 콘텐츠 작성자입니다.

[핵심 지시사항]
모든 콘텐츠는 반드시 "{keyword}"를 주제로 작성합니다.
아래 분석 데이터의 실제 수치와 인사이트를 콘텐츠에 직접 활용하세요.
모호한 표현("고민 끝!", "최고의 선택" 등) 대신 구체적 수치와 사례를 사용하세요.
블로그 본문에서 "{keyword}"를 자연스럽게 10~15회 포함해 키워드 밀도 0.4~0.6%를 유지하세요.
연관 키워드({top_keywords})도 본문 전체에 골고루 분산해 포함하세요.

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

## 다음 주 주목 키워드
{next_week_kw if next_week_kw else "데이터 없음"}

## 타겟 독자
- 주요: {primary_audience}
- 페인포인트:
{pain_points}
- 동기:
{motivations}

## 블로그 포스트 작성 가이드
{post_format}

## 블로그 디자인 포맷 규칙 (반드시 준수)

### 1. 타이포그래피 위계

**포스트 제목 (title 필드)**
- 반드시 숫자로 시작 (예: "5가지", "3초 만에", "TOP 3", "2024년")
- 호기심을 자극하는 물음표·화살표·수치 활용 (예: "수익 200%↑? 이유 있었다")
- 50자 이내, '{keyword}' 포함, 검색 최적화

**대제목 H2 — 인용구 버티컬 라인 마킹**
각 섹션 소제목은 반드시 아래 형식으로 작성:
```
[인용구] 소제목 텍스트
```
예시: `[인용구] 1. AI와 {keyword} — 생산성 50% 높이는 법`

**소제목 H3 — 이모지 체크 마킹**
H3 소제목은 반드시 `✅` 또는 `📌` 이모지로 시작:
```
✅ 핵심 포인트 소제목
📌 참고 데이터 소제목
```

**본문 어조**
- 딱딱한 문어체(~이다, ~한다) 금지
- 신뢰감 있는 구어체 유지: ~요, ~죠, ~네요, ~답니다 스타일
- 독자에게 직접 말 걸기: "여러분도 느끼셨나요?", "혹시 이런 경험 있으셨나요?"

### 2. 문단 구조 — 모바일 2~3줄 법칙

- 한 문단은 **최대 2~3문장**, 모바일에서 5줄을 넘지 않도록
- 문단과 문단 사이 반드시 **빈 줄(엔터 2회)** 추가
- 핵심 수치·용어에 **굵은 글씨** 필수: `**수익 200%↑**`, `**95%가 긍정적**`, `**월 500만 원**`
- 서술형 나열은 불릿으로 전환:
  ```
  • 항목1: 수치/내용
  • 항목2: 수치/내용
  • 항목3: 수치/내용
  ```

### 3. 이미지 삽입 위치 (H2 섹션 직후 필수)
각 대제목 바로 아래에 `[IMAGE: 상세 가이드]` 태그 삽입:
- 섹션 1(AI·자동화 관련): [IMAGE: 노트북 화면에 ChatGPT와 {keyword} 로드맵이 세련되게 띄워진 고화질 3D 일러스트, 밝고 따뜻한 색감]
- 섹션 2(매출·수익 관련): [IMAGE: 개인 가치 상승을 우상향 그래프와 화살표로 표현한 따뜻한 톤 비즈니스 인포그래픽]
- 섹션 3(전략·방법론 관련): [IMAGE: 단계별 로드맵을 시각화한 깔끔한 플랫 디자인 인포그래픽, 민트·네이비 배색]
- 섹션 4(이미지·컬러·외면 관련): [IMAGE: 웜톤·쿨톤 팔레트 배경에 스마트한 정장 인물 실루엣이 겹친 감각적인 퍼스널 컬러 이미지]
- 주제와 맞지 않으면 해당 섹션 키워드에 맞는 고품질 이미지 가이드로 대체

### 4. 링크 카드형 CTA (글 마지막 필수)
```
---
[CTA_BOX]
💡 **함께 읽으면 수익이 달라지는 추천 글**

[LINK_CARD]
📰 {keyword} 관련 추천 글 제목 1 — 실제 데이터 기반 인사이트를 담은 구체적 제목
🔗 https://blog.naver.com/heewonnn09
[/LINK_CARD]

[LINK_CARD]
📰 {keyword} 관련 추천 글 제목 2 — 실전 적용 사례 중심의 구체적 제목
🔗 https://blog.naver.com/heewonnn09
[/LINK_CARD]

📌 **이웃추가**하면 매주 네이버 실시간 데이터 기반 마케팅 인사이트를 가장 먼저 받아볼 수 있어요!
[/CTA_BOX]
---
```

---

다음 JSON만 출력하세요. 다른 텍스트 없이 JSON만.

인스타그램 hashtags는 25개를 반드시 생성하세요:
- 대표 키워드 태그 5개: '{keyword}' 직접 관련 (띄어쓰기 제거, # 포함)
- 중간 범위 태그 10개: 상위 카테고리 또는 연관 주제 (예: 키워드가 "AI 마케팅"이면 "#디지털마케팅" "#콘텐츠마케팅" 등)
- 틈새 태그 9개: 경쟁이 낮은 구체적 태그 (예: "#AI마케팅전략", "#마케팅자동화툴" 등)
  각 태그는 "#" 포함, 한글 또는 영문, 중복 없이.

{{
  "naver_blog": {{
    "title": "블로그 제목 (50자 이내, 반드시 숫자로 시작, '{keyword}' 포함, 호기심 유발 수치·화살표 활용, 검색 최적화)",
    "body": "블로그 본문 (2500자 이상, 위 포스트 가이드·디자인 포맷 규칙 모두 준수)\\n규칙 체크리스트:\\n✔ H2 소제목: [인용구] 텍스트 형식\\n✔ H3 소제목: ✅ 또는 📌 이모지로 시작\\n✔ 핵심 수치·용어: **볼드** 처리 (예: **수익 200%↑**, **95% 긍정**)\\n✔ 문단: 최대 2~3문장, 문단 간 빈 줄\\n✔ 나열 데이터: • 불릿 변환\\n✔ 각 H2 직후: [IMAGE: 섹션별 상세 가이드] 삽입\\n✔ 마지막: [CTA_BOX]...[LINK_CARD]...[/LINK_CARD]...[/CTA_BOX] 삽입\\n✔ 본문 어조: 구어체(~요/~죠/~네요)\\n'{keyword}'를 본문에 10~15회 자연스럽게 포함(키워드 밀도 0.4~0.6%), 연관 키워드({top_keywords}) 각 섹션에 분산 배치",
    "hashtags": ["#{kw_tag}", "#해시태그2", "#해시태그3", "#해시태그4", "#해시태그5", "#해시태그6", "#해시태그7", "#해시태그8", "#해시태그9", "#해시태그10"]
  }},
  "instagram": {{
    "caption": "인스타그램 캡션 (실제 줄바꿈 사용, JSON 내 \\n 아닌 실제 개행). 구조:\n① 첫 줄 훅 (15자 이내): 아래 중 하나 선택 — (A) 놀라운 수치로 시작 예:'이 키워드 검색량 3주 만에 2배↑' (B) 역설적 질문 예:'잘 될수록 손해? {keyword}의 함정' (C) 커리어 공감 예:'마케터 10명 중 7명이 놓치는 {keyword} 타이밍'. 금지: '지금 바로','강력 추천','일상 탈출' 등 뻔한 표현. 이모지 0개.\n② 빈 줄 후, '↓ 이 3가지 체크했나요?' 또는 '핵심만 추렸습니다 👇' (한 줄)\n③ 핵심 포인트 3개: 각각 '✅ ' 또는 '📌 '로 시작, 25자 이내, trend_summary·insights 실제 데이터 활용\n④ 빈 줄 후 마지막 줄: '📅 매주 네이버 실시간 데이터 기반 · 팔로우하면 알림 받기' 형식",
    "hashtags": ["#{kw_tag}", "대표키워드태그1", "대표키워드태그2", "대표키워드태그3", "대표키워드태그4", "대표키워드태그5", "중간범위태그1", "중간범위태그2", "중간범위태그3", "중간범위태그4", "중간범위태그5", "중간범위태그6", "중간범위태그7", "중간범위태그8", "중간범위태그9", "중간범위태그10", "틈새태그1", "틈새태그2", "틈새태그3", "틈새태그4", "틈새태그5", "틈새태그6", "틈새태그7", "틈새태그8", "틈새태그9"]
  }},
  "ad_copy": {{
    "headline": "광고 헤드라인 (30자 이내, 타겟: {primary_audience.split('(')[0].strip().split(',')[0].strip()}, 구체적 수치 포함, 모호한 표현 금지)",
    "subheadline": "서브헤드라인 (50자 이내, 페인포인트 해결 + 구체적 혜택)",
    "cta": "행동 유도 문구 (15자 이내, 명확한 다음 행동)"
  }}
}}\
"""


@gemini_retry
def _call_gemini(client, prompt: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return response.text.strip()


def generate_content(analyzed_data: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY 환경변수가 설정되지 않았습니다.\n"
            "PowerShell: $env:GEMINI_API_KEY = 'your-api-key'"
        )

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(analyzed_data)

    text = _call_gemini(client, prompt)

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
