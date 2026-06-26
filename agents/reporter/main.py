import argparse
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from jinja2 import Environment, FileSystemLoader

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.gemini_retry import gemini_retry
from playwright.sync_api import sync_playwright

load_dotenv()

AGENT_DIR = Path(__file__).parent
BASE_DIR = AGENT_DIR.parent.parent
OUTPUT_DIR = BASE_DIR / "output"


def load_content_files(date_str: str, keyword: str | None = None) -> tuple[list[dict], list[Path]]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    if keyword:
        safe_kw = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
        pattern = f"content_{safe_kw}_{date_str}.json"
    else:
        pattern = f"content_*_{date_str}.json"
    files = sorted(OUTPUT_DIR.glob(pattern))
    items = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            items.append(json.load(fp))
    return items, files


_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]


@gemini_retry
def _call_gemini_model(client, model: str, prompt: str) -> dict:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=8192,
            response_mime_type="application/json",
        ),
    )
    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw.strip())
    return json.loads(raw)


def _call_gemini(client, prompt: str) -> dict:
    last_exc = None
    for model in _MODELS:
        try:
            return _call_gemini_model(client, model, prompt)
        except Exception as e:
            print(f"[reporter] {model} 실패 — 다음 모델로 전환: {e}")
            last_exc = e
    raise last_exc


def analyze_with_gemini(items: list[dict]) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    content_text = json.dumps(items, ensure_ascii=False, indent=2)

    prompt = f"""다음은 이번 주 생성된 마케팅 콘텐츠 목록입니다.

{content_text}

아래 JSON 형식으로 분석 결과를 반환해주세요. JSON만 반환하고 마크다운 코드블록이나 다른 텍스트는 포함하지 마세요.

{{
  "trend_keywords": [
    {{"rank": 1, "keyword": "키워드", "reason": "이유"}},
    {{"rank": 2, "keyword": "키워드", "reason": "이유"}},
    {{"rank": 3, "keyword": "키워드", "reason": "이유"}},
    {{"rank": 4, "keyword": "키워드", "reason": "이유"}},
    {{"rank": 5, "keyword": "키워드", "reason": "이유"}}
  ],
  "performance_predictions": [
    {{"title": "콘텐츠 제목", "predicted_level": "높음", "reason": "이유"}}
  ],
  "next_week_keywords": [
    {{"keyword": "키워드", "rationale": "근거"}},
    {{"keyword": "키워드", "rationale": "근거"}},
    {{"keyword": "키워드", "rationale": "근거"}},
    {{"keyword": "키워드", "rationale": "근거"}},
    {{"keyword": "키워드", "rationale": "근거"}}
  ]
}}

규칙:
- performance_predictions는 입력된 모든 콘텐츠에 대해 각각 예측해주세요.
- predicted_level은 반드시 "높음", "중간", "낮음" 중 하나를 사용해주세요.
- 모든 텍스트는 한국어로 작성해주세요."""

    return _call_gemini(client, prompt)


def load_prediction_verification(keyword: str | None) -> dict:
    data_dir = BASE_DIR / "data"
    if keyword:
        safe_kw = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
        pattern = f"analyzed_{safe_kw}_*.json"
    else:
        pattern = "analyzed_*_*.json"

    all_items: list[dict] = []
    total_hit = 0
    total_checked = 0

    for f in sorted(data_dir.glob(pattern), reverse=True):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        pv = data.get("prediction_verification", {})
        if not pv or pv.get("no_data", True):
            continue
        all_items.extend(pv.get("entries", []))
        total_hit += pv.get("hit_count", 0)
        total_checked += pv.get("total_checked", 0)

    if not all_items:
        return {"no_data": True, "entries": [], "hit_count": 0, "total_checked": 0, "hit_rate": 0}

    hit_rate = round(total_hit / total_checked * 100) if total_checked > 0 else 0
    return {
        "no_data": False,
        "hit_count": total_hit,
        "total_checked": total_checked,
        "hit_rate": hit_rate,
        "entries": all_items,
    }


def load_search_trends(keyword: str | None) -> list[dict]:
    data_dir = BASE_DIR / "data"
    if keyword:
        safe_kw = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
        pattern = f"analyzed_{safe_kw}_*.json"
    else:
        pattern = "analyzed_*_*.json"
    trends: list[dict] = []
    seen: set[str] = set()
    for f in sorted(data_dir.glob(pattern), reverse=True):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        for t in data.get("search_trends", []):
            if t["keyword"] not in seen:
                seen.add(t["keyword"])
                trends.append(t)
    return trends


def render_html(
    items: list[dict],
    analysis: dict,
    date_str: str,
    search_trends: list[dict] | None = None,
    prediction_verification: dict | None = None,
) -> str:
    env = Environment(loader=FileSystemLoader(str(AGENT_DIR)))
    template = env.get_template("template.html")
    return template.render(
        date=date_str,
        items=items,
        trend_keywords=analysis["trend_keywords"],
        performance_predictions=analysis["performance_predictions"],
        next_week_keywords=analysis["next_week_keywords"],
        search_trends=search_trends or [],
        prediction_verification=prediction_verification or {"no_data": True},
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.pdf(path=str(pdf_path), format="A4", print_background=True)
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="주간 마케팅 리포트 생성기")
    parser.add_argument(
        "--date",
        default=date.today().strftime("%Y-%m-%d"),
        help="리포트 날짜 (YYYY-MM-DD, 기본값: 오늘)",
    )
    parser.add_argument(
        "--keyword",
        default=None,
        help="특정 키워드만 리포트에 포함 (미지정 시 해당 날짜 전체)",
    )
    args = parser.parse_args()

    print(f"[reporter] {args.date} 콘텐츠 파일 검색 중..." + (f" (키워드: {args.keyword})" if args.keyword else ""))
    items, files = load_content_files(args.date, args.keyword)

    if not items:
        kw_hint = f"content_{args.keyword}_{args.date}.json" if args.keyword else f"content_*_{args.date}.json"
        print(f"[reporter] 오류: output/{kw_hint} 파일을 찾을 수 없습니다.")
        return

    print(f"[reporter] {len(files)}개 파일 / {len(items)}개 콘텐츠 로드 완료")
    print("[reporter] Gemini API 분석 중...")
    analysis = analyze_with_gemini(items)

    search_trends = load_search_trends(args.keyword)
    print(f"[reporter] 검색량 트렌드: {len(search_trends)}개 키워드")

    prediction_verification = load_prediction_verification(args.keyword)
    if prediction_verification["no_data"]:
        print("[reporter] 예측 검증: 데이터 없음 (첫 주 또는 히스토리 없음)")
    else:
        print(f"[reporter] 예측 검증: {prediction_verification['hit_count']}/{prediction_verification['total_checked']} 적중 ({prediction_verification['hit_rate']}%)")

    print("[reporter] HTML 렌더링 중...")
    html_content = render_html(items, analysis, args.date, search_trends, prediction_verification)

    html_path = OUTPUT_DIR / f"report_{args.date}.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"[reporter] HTML 저장: {html_path}")

    pdf_path = OUTPUT_DIR / f"report_{args.date}.pdf"
    print("[reporter] PDF 변환 중 (Playwright)...")
    html_to_pdf(html_path, pdf_path)
    print(f"[reporter] PDF 저장: {pdf_path}")
    print("[reporter] 완료!")


if __name__ == "__main__":
    main()
