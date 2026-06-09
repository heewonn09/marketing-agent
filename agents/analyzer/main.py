import argparse
import json
import os
import re
import threading
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_STOP_WORDS = {
    "이", "그", "저", "의", "을", "를", "가", "은", "는", "에", "와", "과",
    "도", "로", "으로", "에서", "부터", "까지", "하다", "있다", "되다", "없다",
    "수", "것", "한", "및", "등", "더", "이번", "하는", "하고", "하면",
    "않는", "않고", "위해", "통해", "위한", "대한", "있는", "없는", "통한",
    "the", "a", "an", "of", "in", "to", "for", "is", "are", "and",
}

_history_lock = threading.Lock()


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
  ],
  "interest_estimation": [
    {{"keyword": "키워드", "level": "높음|중간|낮음", "reason": "관심도 근거 한 줄"}},
    ...
  ],
  "competition_saturation": {{
    "level": "높음|중간|낮음",
    "analysis": "경쟁 포화도 분석 2~3문장",
    "opportunity": "틈새 기회 한 줄"
  }},
  "target_audience": {{
    "primary": "주요 타겟 독자층 (직업/연령/상황 포함)",
    "secondary": "부 타겟 독자층",
    "pain_points": ["페인포인트1", "페인포인트2", "페인포인트3"],
    "motivations": ["관심 동기1", "관심 동기2", "관심 동기3"]
  }},
  "next_week_keywords": [
    {{"keyword": "추천 키워드", "reason": "추천 근거 한 줄"}},
    {{"keyword": "추천 키워드", "reason": "추천 근거 한 줄"}},
    {{"keyword": "추천 키워드", "reason": "추천 근거 한 줄"}},
    {{"keyword": "추천 키워드", "reason": "추천 근거 한 줄"}},
    {{"keyword": "추천 키워드", "reason": "추천 근거 한 줄"}}
  ]
}}

규칙:
- posts_sentiment: 포스트마다 index(1부터), sentiment(긍정/부정/중립), reason
- trend_summary: 전체 흐름을 2~3문장으로 요약
- trends: 3-5개, 데이터에서 발견되는 주요 흐름
- insights: 3-5개, 마케터가 바로 활용 가능한 인사이트
- keywords: 10-15개, 가장 중요한 키워드를 relevance 순으로
- interest_estimation: 상위 5-7개 키워드에 대해 일반 소비자 관심도 추정
- competition_saturation: 해당 키워드의 콘텐츠 경쟁 포화도 평가
- target_audience: 이 키워드에 관심 가질 주요/부 타겟과 페인포인트/동기
- next_week_keywords: 현재 트렌드 기반 다음 주 도전할 키워드 정확히 5개
- 반드시 유효한 JSON만 반환하고, 다른 텍스트는 포함하지 마세요"""


def fetch_search_trends(keywords: list[str], client_id: str, client_secret: str) -> list[dict]:
    if not keywords:
        return []
    today = datetime.now()
    # 현재 진행 중인 주는 부분 집계라 변화율이 왜곡됨 → 지난 주 일요일 기준으로 완전한 4주만 수집
    days_since_sunday = (today.weekday() + 1) % 7
    last_sunday = today - timedelta(days=days_since_sunday or 7)
    start_date = (last_sunday - timedelta(weeks=4)).strftime("%Y-%m-%d")
    end_date = last_sunday.strftime("%Y-%m-%d")

    keyword_groups = [{"groupName": kw, "keywords": [kw]} for kw in keywords[:5]]
    payload = json.dumps({
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "week",
        "keywordGroups": keyword_groups,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openapi.naver.com/v1/datalab/search",
        data=payload,
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"네이버 데이터랩 API 오류: {e.code} {e.reason}")
        return []
    except Exception as e:
        print(f"네이버 데이터랩 API 연결 오류: {e}")
        return []

    trends = []
    for result in data.get("results", []):
        values = [round(d["ratio"]) for d in result.get("data", [])]
        if not values:
            continue
        change_rate = "0%"
        if len(values) >= 2 and values[0] > 0:
            rate = (values[-1] - values[0]) / values[0] * 100
            change_rate = f"+{rate:.0f}%" if rate >= 0 else f"{rate:.0f}%"
        elif len(values) >= 2 and values[-1] > 0:
            change_rate = "신규"
        trends.append({
            "keyword": result["title"],
            "trend": values,
            "change_rate": change_rate,
        })
    return trends


def load_history(data_dir: Path) -> dict:
    history_path = data_dir / "history.json"
    if not history_path.exists():
        return {}
    with open(history_path, encoding="utf-8") as f:
        return json.load(f)


def save_history_entry(
    data_dir: Path,
    date_str: str,
    keyword: str,
    next_week_keywords: list[str],
    trends_snapshot: dict,
) -> None:
    history_path = data_dir / "history.json"
    with _history_lock:
        history = {}
        if history_path.exists():
            with open(history_path, encoding="utf-8") as f:
                history = json.load(f)
        if date_str not in history:
            history[date_str] = {}
        history[date_str][keyword] = {
            "next_week_keywords": next_week_keywords,
            "search_trends_snapshot": trends_snapshot,
        }
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)


def _compute_prediction_verification(
    prev_recommended: list[str],
    prev_snapshot: dict,
    verify_current_trends: list[dict],
) -> dict:
    if not prev_recommended:
        return {"no_data": True, "items": [], "hit_count": 0, "total_checked": 0, "hit_rate": 0}

    current_map = {
        t["keyword"]: (t["trend"][-1] if t.get("trend") else None)
        for t in verify_current_trends
    }

    items = []
    hit_count = 0
    total_checked = 0

    for kw in prev_recommended[:5]:
        last_val = prev_snapshot.get(kw)
        curr_val = current_map.get(kw)

        if curr_val is None:
            items.append({"keyword": kw, "last_week_value": last_val, "this_week_value": None, "status": "unknown"})
            continue

        total_checked += 1
        if last_val is None:
            status = "new"
            hit_count += 1  # 검색량이 처음 나타난 것도 적중으로 간주
        elif curr_val > last_val:
            status = "up"
            hit_count += 1
        elif curr_val < last_val:
            status = "down"
        else:
            status = "same"

        items.append({
            "keyword": kw,
            "last_week_value": last_val,
            "this_week_value": curr_val,
            "status": status,
        })

    hit_rate = round(hit_count / total_checked * 100) if total_checked > 0 else 0
    return {
        "no_data": len(items) == 0,
        "hit_count": hit_count,
        "total_checked": total_checked,
        "hit_rate": hit_rate,
        "entries": items,
    }


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


def analyze_with_gemini(keyword: str, posts: list[dict], client) -> dict:
    posts_text = format_posts_for_prompt(posts)
    user_message = ANALYSIS_PROMPT.format(
        keyword=keyword,
        count=len(posts),
        posts=posts_text,
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=16384,
            response_mime_type="application/json",
        ),
    )

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


def analyze_keyword(keyword: str, client, naver_id: str, naver_secret: str, data_dir: Path) -> Path:
    tag = f"[{keyword}]"

    # 지난 주 데이터 로드 (DataLab 검증 호출을 Gemini와 병렬로 실행하기 위해 미리 로드)
    history = load_history(data_dir)
    last_week_str = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    last_week_kw_data = history.get(last_week_str, {}).get(keyword, {})
    prev_recommended: list[str] = last_week_kw_data.get("next_week_keywords", [])
    prev_snapshot: dict = last_week_kw_data.get("search_trends_snapshot", {})

    source_file = find_latest_file(data_dir, keyword)
    if not source_file:
        raise FileNotFoundError(
            f"{tag} 데이터 파일 없음. collector를 먼저 실행하세요."
        )

    print(f"{tag} 입력 파일: {source_file.name}")
    with open(source_file, encoding="utf-8") as f:
        posts = json.load(f)
    print(f"{tag} 포스트 {len(posts)}개, 키워드 빈도 분석 중...")
    keyword_frequency = count_keywords(posts)

    # Gemini 분석과 DataLab(지난 주 추천 키워드 현황) 동시 실행
    print(f"{tag} Gemini 분석 중...", flush=True)
    if prev_recommended and naver_id and naver_secret:
        print(f"{tag} 지난 주 추천 키워드 {len(prev_recommended)}개 DataLab 검증 병렬 실행...", flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_gemini = pool.submit(analyze_with_gemini, keyword, posts, client)
            fut_verify = pool.submit(fetch_search_trends, prev_recommended[:5], naver_id, naver_secret)
            analysis = fut_gemini.result()
            verify_current_trends = fut_verify.result()
    else:
        analysis = analyze_with_gemini(keyword, posts, client)
        verify_current_trends = []
    print(f"{tag} Gemini 완료")

    # 예측 검증 계산
    prediction_verification = _compute_prediction_verification(
        prev_recommended, prev_snapshot, verify_current_trends
    )
    if not prediction_verification["no_data"]:
        print(f"{tag} 예측 검증: {prediction_verification['hit_count']}/{prediction_verification['total_checked']} 적중 ({prediction_verification['hit_rate']}%)")

    # 이번 주 DataLab: 메인+관심도 키워드(A) / 다음 주 추천 키워드 베이스라인(B) 동시 실행
    interest_kws = [
        ie.get("keyword", "") for ie in analysis.get("interest_estimation", [])[:4]
        if ie.get("keyword", "") and ie.get("keyword", "") != keyword
    ]
    next_week_kw_names = [
        k.get("keyword", "") for k in analysis.get("next_week_keywords", [])
        if k.get("keyword", "")
    ][:5]

    search_trends: list[dict] = []
    next_week_snapshot_data: list[dict] = []
    if naver_id and naver_secret:
        print(f"{tag} 데이터랩 트렌드 수집 중...", flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_a = pool.submit(fetch_search_trends, [keyword] + interest_kws, naver_id, naver_secret)
            fut_b = pool.submit(fetch_search_trends, next_week_kw_names, naver_id, naver_secret)
            search_trends = fut_a.result()
            next_week_snapshot_data = fut_b.result()
        print(f"{tag} 데이터랩 완료 ({len(search_trends)}개 키워드)")
    else:
        print(f"{tag} 경고: NAVER_CLIENT_ID/SECRET 미설정, 검색량 트렌드 생략")

    # 히스토리 업데이트: 오늘의 추천 키워드 + DataLab 스냅샷 저장
    today_str = datetime.now().strftime("%Y-%m-%d")
    next_week_snapshot = {
        t["keyword"]: t["trend"][-1]
        for t in next_week_snapshot_data
        if t.get("trend")
    }
    save_history_entry(data_dir, today_str, keyword, next_week_kw_names, next_week_snapshot)
    print(f"{tag} 히스토리 저장 완료 (다음 주 추천 {len(next_week_kw_names)}개, 스냅샷 {len(next_week_snapshot)}개)")

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

    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = data_dir / f"analyzed_{safe_keyword}_{date_str}.json"

    result = {
        "keyword": keyword,
        "analyzed_at": datetime.now().isoformat(),
        "source_file": source_file.name,
        "item_count": len(posts),
        "keyword_frequency": keyword_frequency,
        "posts_sentiment": posts_with_sentiment,
        "trend_summary": analysis.get("trend_summary", ""),
        "trends": analysis.get("trends", []),
        "insights": analysis.get("insights", []),
        "keywords": analysis.get("keywords", []),
        "interest_estimation": analysis.get("interest_estimation", []),
        "competition_saturation": analysis.get("competition_saturation", {}),
        "target_audience": analysis.get("target_audience", {}),
        "next_week_keywords": analysis.get("next_week_keywords", []),
        "search_trends": search_trends,
        "prediction_verification": prediction_verification,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    sentiment_dist = Counter(p["sentiment"] for p in posts_with_sentiment)
    print(f"{tag} 분석 완료 -> {output_path.name}"
          f" (트렌드 {len(result['trends'])}개 | 인사이트 {len(result['insights'])}개 | 감성: {dict(sentiment_dist)})")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="마케팅 데이터 AI 분석기")
    parser.add_argument("--keyword", nargs="+", required=True, help="분석할 키워드 (여러 개 가능)")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("오류: GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        raise SystemExit(1)

    client = genai.Client(api_key=api_key)
    naver_id = os.environ.get("NAVER_CLIENT_ID", "")
    naver_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    data_dir = Path(__file__).parent.parent.parent / "data"

    if len(args.keyword) == 1:
        analyze_keyword(args.keyword[0], client, naver_id, naver_secret, data_dir)
    else:
        print(f"키워드 {len(args.keyword)}개 병렬 분석 중... (max_workers=2)")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(analyze_keyword, kw, client, naver_id, naver_secret, data_dir): kw
                for kw in args.keyword
            }
            for fut in as_completed(futures):
                fut.result()  # 예외 전파


if __name__ == "__main__":
    main()
