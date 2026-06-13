import argparse
import json
import math
import os
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_TARGET_COUNT = 30
_DISPLAY_PER_REQUEST = 10  # Naver API 최대 100, 안정적으로 10씩


def _fetch_page(keyword: str, start: int, client_id: str, client_secret: str) -> list[dict]:
    collected_at = datetime.now().isoformat()
    enc_kw = urllib.parse.quote(keyword)
    url = (
        f"https://openapi.naver.com/v1/search/blog.json"
        f"?query={enc_kw}&display={_DISPLAY_PER_REQUEST}&start={start}&sort=sim"
    )
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", client_id)
    req.add_header("X-Naver-Client-Secret", client_secret)

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("items", []):
        link = item.get("link", "")
        if not link:
            continue
        results.append({
            "title": re.sub(r"<[^>]+>", "", item.get("title", "")),
            "link": link,
            "summary": re.sub(r"<[^>]+>", "", item.get("description", "")),
            "collected_at": collected_at,
        })
    return results


def collect_naver_blog(keyword: str, target: int = _TARGET_COUNT) -> list[dict]:
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise EnvironmentError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET가 .env에 없습니다.")

    pages_needed = math.ceil(target / _DISPLAY_PER_REQUEST)
    starts = [
        1 + i * _DISPLAY_PER_REQUEST
        for i in range(pages_needed)
        if 1 + i * _DISPLAY_PER_REQUEST <= 1000 - _DISPLAY_PER_REQUEST + 1
    ]

    with ThreadPoolExecutor(max_workers=min(len(starts), 3)) as pool:
        futures = [pool.submit(_fetch_page, keyword, s, client_id, client_secret) for s in starts]
        page_results = [f.result() for f in futures]  # 페이지 순서 유지

    seen: set[str] = set()
    results: list[dict] = []
    for page in page_results:
        for item in page:
            if item["link"] not in seen:
                seen.add(item["link"])
                results.append(item)
                if len(results) >= target:
                    return results
    return results


def _fetch_news_page(keyword: str, start: int, client_id: str, client_secret: str) -> list[dict]:
    collected_at = datetime.now().isoformat()
    enc_kw = urllib.parse.quote(keyword)
    url = (
        f"https://openapi.naver.com/v1/search/news.json"
        f"?query={enc_kw}&display={_DISPLAY_PER_REQUEST}&start={start}&sort=sim"
    )
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", client_id)
    req.add_header("X-Naver-Client-Secret", client_secret)

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("items", []):
        link = item.get("originallink") or item.get("link", "")
        if not link:
            continue
        results.append({
            "title": re.sub(r"<[^>]+>", "", item.get("title", "")),
            "link": link,
            "summary": re.sub(r"<[^>]+>", "", item.get("description", "")),
            "source": "news",
            "collected_at": collected_at,
        })
    return results


def collect_naver_news(keyword: str, target: int = _TARGET_COUNT) -> list[dict]:
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise EnvironmentError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET가 .env에 없습니다.")

    pages_needed = math.ceil(target / _DISPLAY_PER_REQUEST)
    starts = [
        1 + i * _DISPLAY_PER_REQUEST
        for i in range(pages_needed)
        if 1 + i * _DISPLAY_PER_REQUEST <= 1000 - _DISPLAY_PER_REQUEST + 1
    ]

    with ThreadPoolExecutor(max_workers=min(len(starts), 3)) as pool:
        futures = [pool.submit(_fetch_news_page, keyword, s, client_id, client_secret) for s in starts]
        page_results = [f.result() for f in futures]

    seen: set[str] = set()
    results: list[dict] = []
    for page in page_results:
        for item in page:
            if item["link"] not in seen:
                seen.add(item["link"])
                results.append(item)
                if len(results) >= target:
                    return results
    return results


def _collect_and_save(keyword: str, target: int, data_dir: Path) -> Path:
    with ThreadPoolExecutor(max_workers=2) as pool:
        blog_fut = pool.submit(collect_naver_blog, keyword, target)
        news_fut = pool.submit(collect_naver_news, keyword, target)
        blog_results = blog_fut.result()
        news_results = news_fut.result()

    for item in blog_results:
        item.setdefault("source", "blog")

    results = blog_results + news_results
    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = data_dir / f"{safe_keyword}_{date_str}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[{keyword}] 수집 완료: 블로그 {len(blog_results)}개 + 뉴스 {len(news_results)}개 → {output_path.name}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 검색 결과 수집기 (Open API)")
    parser.add_argument("--keyword", nargs="+", required=True, help="검색 키워드 (여러 개 가능)")
    parser.add_argument("--count", type=int, default=_TARGET_COUNT, help=f"수집할 포스트 수 (기본값: {_TARGET_COUNT})")
    args = parser.parse_args()

    data_dir = Path(__file__).parent.parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    if len(args.keyword) == 1:
        print(f"키워드 '{args.keyword[0]}' 검색 중... (목표: {args.count}개)")
        _collect_and_save(args.keyword[0], args.count, data_dir)
    else:
        print(f"키워드 {len(args.keyword)}개 병렬 수집 중... (max_workers=3)")
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(_collect_and_save, kw, args.count, data_dir): kw
                for kw in args.keyword
            }
            for fut in as_completed(futures):
                fut.result()  # 예외 전파


if __name__ == "__main__":
    main()
