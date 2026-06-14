import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from utils.gemini_retry import gemini_retry
from utils.logging_setup import get_logger
from utils.config import env_int

log = get_logger(
    "instagram",
    log_file=Path(__file__).resolve().parent.parent.parent / "logs" / f"instagram_{datetime.now():%Y-%m-%d}.log",
)

# Windows cp949 콘솔에서 이모지 등 비cp949 문자 출력 오류 방지
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    _out = open(sys.stdout.fileno(), mode='wb', closefd=False)
    def _print(msg: str = "") -> None:
        _out.write((str(msg) + "\n").encode("utf-8", errors="replace"))
        _out.flush()
else:
    _print = print

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

ROOT = Path(__file__).resolve().parent.parent.parent
API_BASE = "https://graph.instagram.com/v21.0"
UNSPLASH_API = "https://api.unsplash.com/search/photos"
# picsum.photos: 안정적인 공개 이미지 서비스, Instagram Graph API 접근 가능
DEFAULT_IMAGE_URL = os.environ.get(
    "INSTAGRAM_DEFAULT_IMAGE_URL",
    "https://picsum.photos/1080/1080",
)
LAST_RESORT_URL = "https://picsum.photos/1080/1080"
# 미디어 컨테이너 처리 완료 폴링 횟수 (×5초)
POLL_ATTEMPTS = env_int("IG_POLL_ATTEMPTS", 12)


def _safe_keyword(keyword: str) -> str:
    return re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)


def _refresh_token(access_token: str) -> str:
    """Instagram 장기 액세스 토큰 갱신 후 .env 저장. 실패 시 기존 토큰 반환."""
    try:
        res = requests.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": access_token},
            timeout=15,
        )
        if not res.ok:
            _print(f"[token] 갱신 실패 {res.status_code}: {res.text[:80]}")
            return access_token
        data = res.json()
        new_token = data.get("access_token", access_token)
        days = data.get("expires_in", 0) // 86400
        _print(f"[token] 갱신 완료 — 만료까지 {days}일")
        if new_token != access_token:
            _save_env_token(new_token)
        return new_token
    except Exception as e:
        _print(f"[token] 갱신 예외: {e}")
        return access_token


def _save_env_token(new_token: str) -> None:
    env_path = ROOT / ".env"
    try:
        text = env_path.read_text(encoding="utf-8")
        text = re.sub(
            r"^INSTAGRAM_ACCESS_TOKEN=.*$",
            f"INSTAGRAM_ACCESS_TOKEN={new_token}",
            text,
            flags=re.MULTILINE,
        )
        env_path.write_text(text, encoding="utf-8")
        _print("[token] .env 토큰 업데이트 완료")
    except Exception as e:
        _print(f"[token] .env 저장 실패: {e}")


def ensure_fresh_token(access_token: str) -> str:
    """토큰 유효성 확인 후 자동 갱신. 매 실행마다 60일 갱신하여 만료 방지."""
    try:
        res = requests.get(
            f"{API_BASE}/me",
            params={"fields": "id,username", "access_token": access_token},
            timeout=10,
        )
        if not res.ok:
            _print(f"[token] 검증 실패 {res.status_code} — 갱신 시도")
            return _refresh_token(access_token)
        username = res.json().get("username", res.json().get("id", "?"))
        _print(f"[token] 유효 (계정: {username}) — 갱신 중...")
    except Exception as e:
        _print(f"[token] 검증 예외: {e}")
        return access_token
    return _refresh_token(access_token)


def load_content(keyword: str, post_date: str) -> dict:
    path = ROOT / "output" / f"content_{_safe_keyword(keyword)}_{post_date}.json"
    if not path.exists():
        raise FileNotFoundError(f"콘텐츠 파일 없음: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_error_log(keyword: str, error: str) -> None:
    log_path = ROOT / "data" / f"instagram_error_{date.today().isoformat()}.json"
    logs = []
    if log_path.exists():
        with open(log_path, encoding="utf-8") as f:
            logs = json.load(f)
    logs.append({"keyword": keyword, "error": error, "time": datetime.now().isoformat()})
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
    _print(f"[ERROR LOG] {log_path}")


@gemini_retry
def _translate_keyword(keyword: str) -> str:
    """Gemini로 키워드를 Unsplash 검색용 영어 쿼리로 변환."""
    try:
        import google.genai as genai
        from google.genai import types as gtypes
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return keyword
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=f'Translate this Korean marketing keyword to a short English phrase for image search (2-4 words, no explanation): "{keyword}"',
            config=gtypes.GenerateContentConfig(
                response_mime_type="text/plain",
                max_output_tokens=20,
            ),
        )
        translated = resp.text.strip().strip('"').strip("'")
        _print(f"[unsplash] 키워드 번역: {keyword} → {translated}")
        return translated
    except Exception:
        return keyword


def _check_url_accessible(url: str) -> bool:
    """HEAD 요청으로 URL이 실제로 접근 가능한지 확인."""
    try:
        res = requests.head(url, timeout=8, allow_redirects=True)
        return res.status_code < 400
    except requests.RequestException:
        return False


def _pick_accessible_fallback() -> str:
    """DEFAULT_IMAGE_URL → LAST_RESORT_URL 순서로 접근 가능한 폴백 반환.

    키워드 관련 이미지(카드뉴스/Unsplash)를 얻지 못해 일반 플레이스홀더로
    대체되는 품질 저하 상황이므로 WARNING 으로 영속 기록한다.
    """
    if DEFAULT_IMAGE_URL != LAST_RESORT_URL and _check_url_accessible(DEFAULT_IMAGE_URL):
        log.warning("키워드 이미지 확보 실패 — 기본 폴백 이미지 사용: %s", DEFAULT_IMAGE_URL)
        _print(f"[image] 폴백 이미지 사용: {DEFAULT_IMAGE_URL}")
        return DEFAULT_IMAGE_URL
    log.warning("키워드 이미지 확보 실패 — 최종 폴백 이미지 사용: %s", LAST_RESORT_URL)
    _print(f"[image] 최종 폴백 사용: {LAST_RESORT_URL}")
    return LAST_RESORT_URL


def fetch_slide1_url(keyword: str, post_date: str) -> str | None:
    """카드뉴스 슬라이드 1 이미지 URL 반환 (CARDNEWS_BASE_URL 기반).
    Meta 크롤러가 접근 가능한지 HEAD 요청으로 사전 확인."""
    base_url = os.environ.get("CARDNEWS_BASE_URL", "").rstrip("/")
    if not base_url:
        return None
    safe_kw = _safe_keyword(keyword)
    url = f"{base_url}/cardnews/{quote(f'cardnews_{safe_kw}_{post_date}_1.png')}"
    _print(f"[image] 카드뉴스 슬라이드1 URL 확인: {url[:80]}...")
    if _check_url_accessible(url):
        _print("[image] 카드뉴스 슬라이드1 사용")
        return url
    _print("[image] 카드뉴스 슬라이드1 접근 불가 — Unsplash로 대체")
    return None


def fetch_unsplash_image(keyword: str) -> str:
    """Unsplash에서 키워드 관련 이미지 URL 반환.
    각 후보 URL은 requests.head()로 접근 가능 여부 확인 후 사용."""
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    # 미설정이거나 ASCII 범위 밖 문자(한글 플레이스홀더 등) 포함 시 폴백
    if not access_key or not access_key.isascii():
        _print("[unsplash] UNSPLASH_ACCESS_KEY 미설정 — 기본 이미지 사용")
        return _pick_accessible_fallback()

    query = _translate_keyword(keyword)

    try:
        res = requests.get(
            UNSPLASH_API,
            params={"query": query, "per_page": 1, "orientation": "squarish"},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10,
        )
        if res.ok:
            results = res.json().get("results", [])
            if results:
                # Unsplash /download 엔드포인트 URL은 Meta 크롤러가 리다이렉트 미지원으로
                # 접근 실패하는 경우가 있음 → raw URLs 중 접근 가능한 것 선택
                for url_key in ("full", "regular", "small"):
                    candidate = results[0]["urls"].get(url_key, "")
                    if not candidate:
                        continue
                    desc = results[0].get("alt_description") or "no description"
                    _print(f"[unsplash] 이미지 후보({url_key}): {desc[:50]}")
                    if _check_url_accessible(candidate):
                        _print(f"[unsplash] URL 접근 가능: {candidate[:80]}...")
                        return candidate
                _print("[unsplash] 모든 URL 접근 불가 — 폴백 사용")
        _print(f"[unsplash] 검색 결과 없음 ({res.status_code}) — 기본 이미지 사용")
    except requests.RequestException as e:
        _print(f"[unsplash] 요청 실패: {e} — 기본 이미지 사용")

    return _pick_accessible_fallback()


def build_caption(ig: dict) -> str:
    caption = ig.get("caption", "")
    hashtags = ig.get("hashtags", [])
    if hashtags:
        caption = caption.rstrip() + "\n\n" + " ".join(hashtags)
    return caption


def post_instagram(keyword: str, post_date: str) -> None:
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    account_id = os.environ.get("INSTAGRAM_ACCOUNT_ID")

    if not access_token:
        _print("[ERROR] INSTAGRAM_ACCESS_TOKEN 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    if not account_id:
        _print("[ERROR] INSTAGRAM_ACCOUNT_ID 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    access_token = ensure_fresh_token(access_token)
    _print(f"[instagram] 키워드: {keyword} / 날짜: {post_date}")

    content = load_content(keyword, post_date)
    ig = content.get("instagram", {})
    caption = build_caption(ig)

    _print(f"[instagram] 캡션 ({len(caption)}자):\n{caption[:200]}{'...' if len(caption) > 200 else ''}")

    # 이미지 우선순위: 카드뉴스 슬라이드1 → Unsplash → picsum 폴백
    # Unsplash CDN URL은 Meta 크롤러가 리다이렉트 실패로 "Media ID is not available" 유발 가능
    image_url = fetch_slide1_url(keyword, post_date) or fetch_unsplash_image(keyword)
    _print(f"[instagram] 최종 이미지 URL: {image_url[:80]}{'...' if len(image_url) > 80 else ''}")

    try:
        # Step 1: 미디어 컨테이너 생성
        _print("\n[1/3] 미디어 컨테이너 생성 중...")
        res = requests.post(
            f"{API_BASE}/{account_id}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": access_token,
            },
            timeout=30,
        )
        if not res.ok:
            err = res.json().get("error", {})
            msg = f"미디어 생성 실패 {res.status_code}: {err.get('message', res.text)}"
            _print(f"[ERROR] {msg}")
            save_error_log(keyword, msg)
            sys.exit(1)

        creation_id = res.json().get("id")
        _print(f"      creation_id: {creation_id}")

        # Step 2: 컨테이너 처리 완료 대기 (FINISHED 상태까지 폴링, 지수 백오프)
        import time
        _print("[2/3] 컨테이너 처리 대기 중...")
        for attempt in range(POLL_ATTEMPTS):
            wait = min(3 + attempt * 2, 15)  # 3s → 5s → 7s … 최대 15s
            time.sleep(wait)
            status_res = requests.get(
                f"{API_BASE}/{creation_id}",
                params={"fields": "status_code", "access_token": access_token},
                timeout=15,
            )
            if status_res.ok:
                status_code = status_res.json().get("status_code", "")
                _print(f"      상태: {status_code} ({attempt + 1}/{POLL_ATTEMPTS}, {wait}s 대기)")
                if status_code == "FINISHED":
                    break
                if status_code == "ERROR":
                    msg = "컨테이너 처리 오류 (status_code=ERROR)"
                    _print(f"[ERROR] {msg}")
                    save_error_log(keyword, msg)
                    sys.exit(1)
        else:
            msg = "컨테이너 처리 타임아웃"
            _print(f"[ERROR] {msg}")
            save_error_log(keyword, msg)
            sys.exit(1)

        # Step 3: 발행
        _print("[3/3] 포스트 발행 중...")
        pub_res = requests.post(
            f"{API_BASE}/{account_id}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": access_token,
            },
            timeout=30,
        )
        if not pub_res.ok:
            err = pub_res.json().get("error", {})
            msg = f"발행 실패 {pub_res.status_code}: {err.get('message', pub_res.text)}"
            _print(f"[ERROR] {msg}")
            save_error_log(keyword, msg)
            sys.exit(1)

        media_id = pub_res.json().get("id")
        _print(f"\n[OK] Instagram 포스팅 완료 — media_id: {media_id}")

        # permalink 수집 (성과 트래킹용)
        if media_id:
            try:
                detail_res = requests.get(
                    f"{API_BASE}/{media_id}",
                    params={"fields": "permalink", "access_token": access_token},
                    timeout=10,
                )
                permalink = detail_res.json().get("permalink", "") if detail_res.ok else ""
                _print(f"[RESULT_MEDIA]:{media_id}:{permalink}")
            except Exception:
                _print(f"[RESULT_MEDIA]:{media_id}:")

    except requests.RequestException as e:
        msg = f"네트워크 오류: {e}"
        _print(f"[ERROR] {msg}")
        save_error_log(keyword, msg)
        sys.exit(1)


def post_carousel(keyword: str, post_date: str) -> None:
    """카드뉴스 4장을 Instagram 캐러셀로 업로드.

    CARDNEWS_BASE_URL 환경변수로 이미지 공개 URL의 베이스를 지정한다.
    Instagram Graph API는 외부에서 접근 가능한 URL을 요구하므로,
    VM Flask 서버가 /cardnews/<filename> 라우트를 통해 이미지를 서빙해야 한다.
    """
    import time

    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    account_id   = os.environ.get("INSTAGRAM_ACCOUNT_ID")
    base_url     = os.environ.get("CARDNEWS_BASE_URL", "http://34.11.175.125:5000").rstrip("/")

    if not access_token:
        _print("[ERROR] INSTAGRAM_ACCESS_TOKEN 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    if not account_id:
        _print("[ERROR] INSTAGRAM_ACCOUNT_ID 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    access_token = ensure_fresh_token(access_token)

    safe_kw = _safe_keyword(keyword)
    image_urls = [
        f"{base_url}/cardnews/{quote(f'cardnews_{safe_kw}_{post_date}_{i}.png')}"
        for i in range(1, 5)
    ]

    _print(f"[carousel] 키워드: {keyword} / 날짜: {post_date}")
    _print("[carousel] 이미지 URL:")
    for url in image_urls:
        _print(f"  {url}")

    # Step 0: 모든 이미지 URL이 실제 접근 가능한지 사전 확인
    #         (Meta 크롤러가 페치하기 전에 우리가 먼저 확인 — 서버 재시작/일시 장애 조기 감지)
    _print("\n[0/4] 이미지 URL 접근성 사전 확인...")
    for idx, url in enumerate(image_urls, start=1):
        ok = False
        for retry in range(3):
            if _check_url_accessible(url):
                ok = True
                break
            _print(f"      이미지 {idx} 접근 불가 — 재시도 {retry + 1}/3")
            time.sleep(3)
        if not ok:
            msg = f"이미지 {idx} URL 접근 불가 (서버 미응답): {url[:80]}"
            _print(f"[ERROR] {msg}")
            save_error_log(keyword, msg)
            sys.exit(1)
    _print("      모든 이미지 접근 가능 확인됨")

    # Step 1: 각 이미지 item container 생성 (Meta 페치 실패 시 재시도)
    item_ids: list[str] = []
    for idx, url in enumerate(image_urls, start=1):
        _print(f"\n[1/4-{idx}] item container 생성 중...")
        item_id = None
        last_msg = ""
        for retry in range(3):
            res = requests.post(
                f"{API_BASE}/{account_id}/media",
                data={"image_url": url, "is_carousel_item": "true",
                      "access_token": access_token},
                timeout=30,
            )
            if res.ok:
                item_id = res.json().get("id")
                break
            err = res.json().get("error", {})
            last_msg = f"item {idx} 생성 실패 {res.status_code}: {err.get('message', res.text)}"
            # "Only photo or video..." = Meta가 이미지 페치 실패 → 잠시 후 재시도
            _print(f"      {last_msg} — 재시도 {retry + 1}/3")
            time.sleep(5)
        if item_id is None:
            _print(f"[ERROR] {last_msg}")
            save_error_log(keyword, last_msg)
            sys.exit(1)
        item_ids.append(item_id)
        _print(f"      item_id: {item_id}")

    # Step 2: 캐러셀 컨테이너 생성 (캡션 포함)
    content = load_content(keyword, post_date)
    caption = build_caption(content.get("instagram", {}))

    _print("\n[2/3] 캐러셀 컨테이너 생성 중...")
    res = requests.post(
        f"{API_BASE}/{account_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    if not res.ok:
        err = res.json().get("error", {})
        msg = f"캐러셀 생성 실패 {res.status_code}: {err.get('message', res.text)}"
        _print(f"[ERROR] {msg}")
        save_error_log(keyword, msg)
        sys.exit(1)
    carousel_id = res.json().get("id")
    _print(f"      carousel_id: {carousel_id}")

    # Step 3: FINISHED 상태 대기 (지수 백오프)
    _print("[carousel] 처리 대기 중...")
    for attempt in range(POLL_ATTEMPTS):
        wait = min(3 + attempt * 2, 15)  # 3s → 5s → … 최대 15s
        time.sleep(wait)
        status_res = requests.get(
            f"{API_BASE}/{carousel_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=15,
        )
        if status_res.ok:
            status_code = status_res.json().get("status_code", "")
            _print(f"      상태: {status_code} ({attempt + 1}/{POLL_ATTEMPTS}, {wait}s 대기)")
            if status_code == "FINISHED":
                break
            if status_code == "ERROR":
                msg = "캐러셀 처리 오류 (status_code=ERROR)"
                _print(f"[ERROR] {msg}")
                save_error_log(keyword, msg)
                sys.exit(1)
    else:
        msg = "캐러셀 처리 타임아웃"
        _print(f"[ERROR] {msg}")
        save_error_log(keyword, msg)
        sys.exit(1)

    # Step 4: 발행
    _print("[3/3] 캐러셀 발행 중...")
    pub_res = requests.post(
        f"{API_BASE}/{account_id}/media_publish",
        data={"creation_id": carousel_id, "access_token": access_token},
        timeout=30,
    )
    if not pub_res.ok:
        err = pub_res.json().get("error", {})
        msg = f"발행 실패 {pub_res.status_code}: {err.get('message', pub_res.text)}"
        _print(f"[ERROR] {msg}")
        save_error_log(keyword, msg)
        sys.exit(1)

    media_id = pub_res.json().get("id")
    _print(f"\n[OK] Instagram 캐러셀 업로드 완료 — media_id: {media_id}")

    # permalink 수집 (성과 트래킹용)
    if media_id:
        try:
            detail_res = requests.get(
                f"{API_BASE}/{media_id}",
                params={"fields": "permalink", "access_token": access_token},
                timeout=10,
            )
            permalink = detail_res.json().get("permalink", "") if detail_res.ok else ""
            _print(f"[RESULT_MEDIA]:{media_id}:{permalink}")
        except Exception:
            _print(f"[RESULT_MEDIA]:{media_id}:")


def main():
    parser = argparse.ArgumentParser(description="Instagram Graph API 자동 포스팅")
    parser.add_argument("--keyword", required=True, help="포스팅할 키워드")
    parser.add_argument("--date", default=date.today().isoformat(), help="콘텐츠 날짜 (YYYY-MM-DD)")
    parser.add_argument("--carousel", action="store_true",
                        help="카드뉴스 4장을 캐러셀로 업로드 (단일 이미지 대신)")
    args = parser.parse_args()
    if args.carousel:
        post_carousel(args.keyword, args.date)
    else:
        post_instagram(args.keyword, args.date)


if __name__ == "__main__":
    main()
