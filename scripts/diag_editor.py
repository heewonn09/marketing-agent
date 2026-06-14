"""포스터 로그인+에디터 진단 — 발행하지 않고 붙여넣기 로그인 후 .se-container 확인.

cookies 로 에디터 접속 시도 → 로그인 페이지로 튕기면 붙여넣기 로그인(_do_login)
→ 에디터 재접속 → .se-container 가시성 확인. 발행은 하지 않는다.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from playwright.sync_api import sync_playwright
from agents.poster.main import _launch_kwargs, _STEALTH_JS, _load_cookies, _do_login, _save_cookies

naver_id = os.environ.get("NAVER_ID", "")
naver_pw = os.environ.get("NAVER_PW", "")
blog_id = naver_id.split("@")[0] if "@" in naver_id else naver_id
editor_url = f"https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}"

with sync_playwright() as pw:
    browser = pw.chromium.launch(**_launch_kwargs(True))
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        viewport={"width": 1280, "height": 900},
        locale="ko-KR", timezone_id="Asia/Seoul",
        permissions=["clipboard-read", "clipboard-write"],
    )
    ctx.add_init_script(_STEALTH_JS)
    page = ctx.new_page()
    _load_cookies(ctx)

    page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
    print(f"[1] 에디터 접속 url={page.url[:70]}")

    if "nidlogin" in page.url or "nid.naver.com" in page.url:
        print("[2] 로그인 페이지로 튕김 → 붙여넣기 로그인 시도")
        _do_login(page, naver_id, naver_pw)
        print(f"    로그인 후 url={page.url[:70]}")
        # 로그인 성공 여부: 로그인 페이지를 벗어났는가
        if "nidlogin" in page.url or "nid.naver.com" in page.url:
            print("    [실패] 여전히 로그인 페이지 (캡차/차단 가능성)")
        else:
            print("    [성공] 로그인 통과")
            _save_cookies(ctx)
        page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
        print(f"[3] 에디터 재접속 url={page.url[:70]}")

    # .se-container 확인 (최대 20초)
    found = False
    deadline = time.time() + 20
    while time.time() < deadline:
        if page.locator(".se-container").count() > 0:
            found = True
            break
        time.sleep(1)
    print(f"[결과] .se-container 발견 = {found}")

    try:
        body_txt = page.inner_text("body")[:200].replace("\n", " ")
        print(f"[body] {body_txt}")
    except Exception:
        pass

    page.screenshot(path=str(ROOT / "data" / "diag_editor.png"))
    print("[screenshot] data/diag_editor.png")
    browser.close()
