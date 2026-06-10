from playwright.sync_api import sync_playwright
import json, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(".env"))

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    with open("data/naver_cookies.json", encoding="utf-8") as f:
        ctx.add_cookies(json.load(f))

    # 블로그 메인
    page.goto("https://blog.naver.com/heewonnn09", wait_until="domcontentloaded")
    time.sleep(3)
    page.screenshot(path="data/blog_check.png")
    print("메인 스크린샷 저장: data/blog_check.png")

    # 페이지/iframe 목록 출력
    print("frames:", [f.name for f in page.frames])

    # JS로 iframe 내 최신 포스트 logNo 추출
    post_no = page.evaluate("""
        () => {
            try {
                var f = document.querySelector('iframe#mainFrame');
                if (!f) return null;
                var doc = f.contentDocument || f.contentWindow.document;
                // 링크에서 logNo 파라미터 추출
                var links = Array.from(doc.querySelectorAll('a[href*="logNo"]'));
                for (var l of links) {
                    var m = l.href.match(/logNo=(\d+)/);
                    if (m) return m[1];
                }
                // data-log-no 속성
                var el = doc.querySelector('[data-log-no]');
                if (el) return el.dataset.logNo;
            } catch(e) {}
            return null;
        }
    """)
    print(f"최신 포스트 logNo: {post_no}")

    if post_no:
        post_url = f"https://blog.naver.com/heewonnn09/{post_no}"
        print(f"접속: {post_url}")
        page.goto(post_url, wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path="data/blog_post.png")
        print("포스트 스크린샷 저장: data/blog_post.png")
    else:
        # PostView.naver API로 최신 글 목록 조회
        page.goto(
            "https://blog.naver.com/PostList.naver?blogId=heewonnn09&currentPage=1",
            wait_until="domcontentloaded"
        )
        time.sleep(3)
        page.screenshot(path="data/blog_post.png")
        print("포스트 목록 스크린샷 저장: data/blog_post.png")

    browser.close()
