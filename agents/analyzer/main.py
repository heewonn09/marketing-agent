import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_STOP_WORDS = {
    "이", "그", "저", "의", "을", "를", "가", "은", "는", "에", "와", "과",
    "도", "로", "으로", "에서", "부터", "까지", "하다", "있다", "되다", "없다",
    "수", "것", "한", "및", "등", "더", "이번", "하는", "하고", "하면",
    "않는", "않고", "위해", "통해", "위한", "대한", "있는", "없는", "통한",
    "the", "a", "an", "of", "in", "to", "for", "is", "are", "and",
}


def count_keywords(posts: list[dict], top_n: int = 20) -> list[dict]:
    text = " ".join(
        f"{p.get('title', '')} {p.get('summary', '')}" for p in posts
    )
    words = re.findall(r"[가-힣]{2,}|[a-zA-Z]{3,}", text)
    filtered = [w for w in words if w not in _STOP_WORDS]
    return [
        {"word": w, "count": c}
        for w, c in Counter(filtered).most_common(top_n)
    ]


SYSTEM_PROMPT = """당신은 한국 마케팅 데이터를 분석하는 전문 애널리스트입니다.
블로그 포스트 데이터를 분석해서 마케팅 관점의 트렌드, 인사이트, 핵심 키워드를 추출합니다.
반드시 JSON 형식으로만 응답하세요."""

ANALYSIS_PROMPT = """다음은 "{keyword}" 키워드로 수집한 네이버 블로그 포스트 {count}개입니다.

{posts}

위 데이터를 분석해서 아래 JSON 형식으로 결과를 반환하세요:

{{
  "posts_sentiment": [
    {{"index": 1, "sentiment": "긍정|부정|중립", "reason": "한 줄 이유"}},
    ...
  ],
  "trend_summary": "전반적인 트렌드를 2~3문장으로 요약",
  "trends": [
    "트렌드 설명 (구체적인 수치나 사례 포함, 2-3문장)",
    ...
  ],
  "insights": [
    "마케터가 활용할 수 있는 실용적 인사이트 (2-3문장)",
    ...
  ],
  "keywords": [
    {{"word": "핵심 키워드", "relevance": "high|medium|low", "context": "한 줄 설명"}},
    ...
  ]
}}

규칙:
- posts_sentiment: 포스트마다 index(1부터), sentiment(긍정/부정/중립), reason
- trend_summary: 전체 흐름을 2~3문장으로 요약
- trends: 3-5개, 데이터에서 발견되는 주요 흐름
- insights: 3-5개, 마케터가 바로 활용 가능한 인사이트
- keywords: 10-15개, 가장 중요한 키워드를 relevance 순으로
- 반드시 유효한 JSON만 반환하고, 다른 텍스트는 포함하지 마세요"""


def find_latest_file(data_dir: Path, keyword: str) -> Path | None:
    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    matches = sorted(data_dir.glob(f"{safe_keyword}_*.json"), reverse=True)
    # analyzed_ 파일 제외
    matches = [f for f in matches if not f.name.startswith("analyzed_")]
    return matches[0] if matches else None


def format_posts_for_prompt(posts: list[dict]) -> str:
    lines = []
    for i, post in enumerate(posts, 1):
        lines.append(f"[{i}] 제목: {post['title']}")
        lines.append(f"    요약: {post['summary']}")
        lines.append("")
    return "\n".join(lines)


def analyze_with_gemini(keyword: str, posts: list[dict]) -> dict:
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction=SYSTEM_PROMPT,
    )

    posts_text = format_posts_for_prompt(posts)
    user_message = ANALYSIS_PROMPT.format(
        keyword=keyword,
        count=len(posts),
        posts=posts_text,
    )

    print("Gemini가 분석 중...", end="", flush=True)
    response = model.generate_content(
        user_message,
        generation_config=genai.types.GenerationConfig(max_output_tokens=4096),
    )
    print(" 완료")

    raw = response.text.strip()
    # ```json ... ``` 블록 제거
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description="마케팅 데이터 AI 분석기")
    parser.add_argument("--keyword", required=True, help="분석할 키워드")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("오류: GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        raise SystemExit(1)

    genai.configure(api_key=api_key)

    data_dir = Path(__file__).parent.parent.parent / "data"
    source_file = find_latest_file(data_dir, args.keyword)

    if not source_file:
        print(f"오류: '{args.keyword}' 키워드에 해당하는 데이터 파일을 찾을 수 없습니다.")
        print(f"먼저 에이전트 1을 실행하세요: .\\venv\\Scripts\\python.exe agents\\collector\\main.py --keyword \"{args.keyword}\"")
        raise SystemExit(1)

    print(f"입력 파일: {source_file.name}")

    with open(source_file, encoding="utf-8") as f:
        posts = json.load(f)

    print(f"포스트 수: {len(posts)}개")

    # 키워드 빈도 분석 (로컬)
    print("키워드 빈도 분석 중...")
    keyword_frequency = count_keywords(posts)

    # Gemini AI: 감성 분석 + 트렌드 + 인사이트
    analysis = analyze_with_gemini(args.keyword, posts)

    # 감성 분석 결과를 포스트에 병합
    sentiment_map = {
        item["index"]: item
        for item in analysis.get("posts_sentiment", [])
    }
    posts_with_sentiment = [
        {
            "title": p["title"],
            "link": p["link"],
            "sentiment": sentiment_map.get(i, {}).get("sentiment", "알 수 없음"),
            "sentiment_reason": sentiment_map.get(i, {}).get("reason", ""),
        }
        for i, p in enumerate(posts, start=1)
    ]

    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", args.keyword)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = data_dir / f"analyzed_{safe_keyword}_{date_str}.json"

    result = {
        "keyword": args.keyword,
        "analyzed_at": datetime.now().isoformat(),
        "source_file": source_file.name,
        "item_count": len(posts),
        "keyword_frequency": keyword_frequency,
        "posts_sentiment": posts_with_sentiment,
        "trend_summary": analysis.get("trend_summary", ""),
        "trends": analysis.get("trends", []),
        "insights": analysis.get("insights", []),
        "keywords": analysis.get("keywords", []),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n분석 완료 → {output_path}")
    print(f"  상위 키워드: {[k['word'] for k in keyword_frequency[:5]]}")
    print(f"  감성 분포: {Counter(p['sentiment'] for p in posts_with_sentiment)}")
    print(f"  트렌드: {len(result['trends'])}개 | 인사이트: {len(result['insights'])}개")


if __name__ == "__main__":
    main()
