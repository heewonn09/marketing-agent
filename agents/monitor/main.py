import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# 프로젝트 루트를 sys.path에 추가해 collector 임포트
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agents.collector.main import collect_naver_blog
from utils.alert_sender import send_alert

load_dotenv(Path(__file__).parent.parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "monitor_state.json"
MONITOR_DIR = Path(__file__).parent


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"seen_links": {}, "last_checked": {}}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_keywords() -> list[str]:
    keywords_file = MONITOR_DIR / "keywords.json"
    if not keywords_file.exists():
        return []
    with open(keywords_file, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("keywords", [])


def assess_significance(keyword: str, new_posts: list[dict], client) -> dict:
    posts_text = "\n".join(
        f"- {p['title']}: {p.get('summary', '')[:80]}" for p in new_posts
    )
    prompt = f"""'{keyword}' 키워드 새 블로그 포스트 {len(new_posts)}개:

{posts_text}

아래 JSON으로만 응답 (마크다운 코드블록 없이):
{{
  "is_significant": true,
  "level": "high",
  "summary": "한 문장 요약",
  "reasons": ["이유1", "이유2"]
}}

is_significant: 마케터가 주목해야 할 트렌드/변화가 있으면 true
level: high(즉시 대응), medium(관심 필요), low(일반 업데이트)"""

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
    )
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def check_keyword(keyword: str, state: dict, client) -> dict | None:
    is_first_run = keyword not in state["seen_links"]
    seen = set(state["seen_links"].get(keyword, []))

    print(f"  [{keyword}] 수집 중...", end="", flush=True)
    try:
        posts = collect_naver_blog(keyword)
    except Exception as e:
        print(f" 실패: {e}")
        return None
    print(f" {len(posts)}개")

    new_posts = [p for p in posts if p["link"] not in seen]

    # 최근 500개 링크만 유지
    updated_links = list(seen | {p["link"] for p in posts})
    state["seen_links"][keyword] = updated_links[-500:]
    state["last_checked"][keyword] = datetime.now().isoformat()

    # 첫 실행은 기준선 초기화만 수행 (알림 없음)
    if is_first_run:
        print(f"  [{keyword}] 초기화 완료 ({len(posts)}개 포스트 등록)")
        return None

    if not new_posts:
        print(f"  [{keyword}] 새 포스트 없음")
        return None

    print(f"  [{keyword}] 새 포스트 {len(new_posts)}개 → Gemini 분석 중...", end="", flush=True)
    try:
        significance = assess_significance(keyword, new_posts, client)
    except Exception as e:
        print(f" 실패: {e}")
        significance = {
            "is_significant": True,
            "level": "medium",
            "summary": "분석 실패 (새 포스트 발견됨)",
            "reasons": [],
        }
    print(f" 완료 (level={significance.get('level', '?')})")

    return {
        "keyword": keyword,
        "new_post_count": len(new_posts),
        "is_significant": significance.get("is_significant", False),
        "level": significance.get("level", "medium"),
        "summary": significance.get("summary", ""),
        "reasons": significance.get("reasons", []),
        "new_posts": [{"title": p["title"], "link": p["link"]} for p in new_posts],
        "checked_at": datetime.now().isoformat(),
    }


def run_check_cycle(keywords: list[str], client) -> list[dict]:
    state = load_state()
    alerts = []

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] 모니터링 사이클 시작 ({len(keywords)}개 키워드)")

    for keyword in keywords:
        result = check_keyword(keyword, state, client)
        if result:
            alerts.append(result)

    save_state(state)

    if alerts:
        log_path = DATA_DIR / f"monitor_log_{datetime.now().strftime('%Y-%m-%d')}.json"
        existing: list = []
        if log_path.exists():
            with open(log_path, encoding="utf-8") as f:
                existing = json.load(f)
        existing.extend(alerts)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        significant = [a for a in alerts if a["is_significant"]]
        print(f"\n[결과] 새 포스트: {len(alerts)}개 키워드 / 중요 알림: {len(significant)}개")
        for a in significant:
            print(f"  [{a['level'].upper()}] {a['keyword']}: {a['summary']}")
            subject = f"[{a['level'].upper()}] {a['keyword']} 마케팅 트렌드 알림"
            body = (
                f"키워드: {a['keyword']}\n"
                f"수준: {a['level']}\n"
                f"요약: {a['summary']}\n"
                f"새 포스트: {a['new_post_count']}개\n"
                f"이유: {', '.join(a.get('reasons', []))}\n"
                f"확인 시각: {a['checked_at']}"
            )
            send_alert(subject, body)
        print(f"  로그 저장: {log_path}")
    else:
        print("[결과] 새 포스트 없음")

    return alerts


def main():
    parser = argparse.ArgumentParser(description="마케팅 키워드 지속 모니터")
    parser.add_argument(
        "--keywords", nargs="+",
        help="모니터링할 키워드 (미지정 시 keywords.json 사용)",
    )
    parser.add_argument(
        "--interval", type=int, default=360,
        help="체크 주기(분, 기본값: 360=6시간)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="1회 실행 후 종료",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("오류: GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        raise SystemExit(1)

    client = genai.Client(api_key=api_key)

    keywords = args.keywords or load_keywords()
    if not keywords:
        print("오류: 모니터링할 키워드가 없습니다.")
        print("keywords.json을 편집하거나 --keywords 옵션을 사용하세요.")
        raise SystemExit(1)

    print(f"모니터링 키워드: {keywords}")

    if args.once:
        run_check_cycle(keywords, client)
    else:
        print(f"체크 주기: {args.interval}분 (Ctrl+C로 종료)")
        while True:
            run_check_cycle(keywords, client)
            next_check = datetime.now().strftime("%H:%M")
            print(f"\n다음 체크까지 {args.interval}분 대기...")
            time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
