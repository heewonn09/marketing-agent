import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# 네이버 블로그 포스트 URL 패턴: blog.naver.com/username/postid
_POST_PATTERN = re.compile(r"https?://blog\.naver\.com/[^/]+/\d+")


def collect_naver_blog(keyword: str) -> list[dict]:
    collected_at = datetime.now().isoformat()
    post_links: dict[str, list[str]] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        url = f"https://search.naver.com/search.naver?where=blog&query={keyword}"
        print(f"URL: {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)

        # 같은 href를 공유하는 링크들로 제목/요약 추출
        # Naver는 sds-comps-* 해시 클래스를 사용하므로 href 패턴으로 접근
        for link in page.query_selector_all("a[href]"):
            href = link.get_attribute("href") or ""
            if not _POST_PATTERN.match(href):
                continue
            text = link.inner_text().strip()
            if href not in post_links:
                post_links[href] = []
            post_links[href].append(text)

        browser.close()

    results = []
    for href, texts in post_links.items():
        # texts[0]=제목, texts[1]=요약, 이후 숫자(좋아요/댓글수)는 무시
        title = texts[0] if texts else ""
        summary = texts[1] if len(texts) > 1 else ""
        if not title:
            continue
        results.append({
            "title": title,
            "link": href,
            "summary": summary,
            "collected_at": collected_at,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 검색 결과 수집기")
    parser.add_argument("--keyword", required=True, help="검색 키워드")
    args = parser.parse_args()

    print(f"키워드 '{args.keyword}' 검색 중...")
    results = collect_naver_blog(args.keyword)

    data_dir = Path(__file__).parent.parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", args.keyword)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = data_dir / f"{safe_keyword}_{date_str}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"수집 완료: {len(results)}개 항목 → {output_path}")


if __name__ == "__main__":
    main()
