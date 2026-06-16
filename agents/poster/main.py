import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PWTimeout

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
from utils.secrets import load_encrypted_json, save_encrypted_json

_COOKIE_PATH = _ROOT / "data" / "naver_cookies.json"
_ERROR_SCREENSHOT = _ROOT / "data" / "poster_error.png"

# 봇 탐지 회피용 stealth init 스크립트 (navigator 지문 위장)
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
const _origQuery = window.navigator.permissions && window.navigator.permissions.query;
if (_origQuery) {
  window.navigator.permissions.query = (p) => (
    p && p.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : _origQuery(p)
  );
}
"""


# ---------------------------------------------------------------------------
# Cookie helpers (at-rest 암호화 + 레거시 평문 자동 마이그레이션)
# ---------------------------------------------------------------------------

def _load_cookies(context) -> bool:
    if not _COOKIE_PATH.exists():
        return False
    cookies, was_encrypted = load_encrypted_json(_COOKIE_PATH)
    context.add_cookies(cookies)
    if not was_encrypted:
        # 평문 → 암호화 형식으로 즉시 마이그레이션
        save_encrypted_json(_COOKIE_PATH, context.cookies())
        print("쿠키 파일을 암호화 형식으로 마이그레이션했습니다.")
    return True


def _save_cookies(context):
    save_encrypted_json(_COOKIE_PATH, context.cookies())


# ---------------------------------------------------------------------------
# Stealth / proxy helpers
# ---------------------------------------------------------------------------

def _launch_kwargs(headless: bool) -> dict:
    """봇 탐지 회피용 Chromium 실행 인자."""
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    return {"headless": headless, "args": args}


def _proxy_config() -> dict | None:
    """POSTER_PROXY 환경변수가 있으면 Playwright proxy 설정 반환."""
    server = os.environ.get("POSTER_PROXY")
    if not server:
        return None
    cfg = {"server": server}
    user = os.environ.get("POSTER_PROXY_USER")
    pwd = os.environ.get("POSTER_PROXY_PASS")
    if user:
        cfg["username"] = user
    if pwd:
        cfg["password"] = pwd
    return cfg


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------

def _cookies_valid(context) -> bool:
    """NID_SES 쿠키가 존재하고 만료되지 않았는지 확인 (네트워크 요청 없음)."""
    now = time.time()
    for c in context.cookies():
        if c.get("name") == "NID_SES":
            exp = c.get("expires", -1)
            return exp < 0 or exp > now  # session cookie or not yet expired
    return False


def _is_logged_in(context, page) -> bool:
    """goto 없이 쿠키·현재 URL로 로그인 상태 확인."""
    # 1순위: 세션 쿠키 유무 (가장 확실한 지표)
    if _cookies_valid(context):
        return True
    # 2순위: 현재 URL이 네이버 도메인이고 로그인 페이지가 아닌 경우
    url = page.url
    if "naver.com" in url and "nidlogin" not in url and "nid.naver.com" not in url:
        try:
            page.locator("a.btn_login, a:has-text('NAVER 로그인')").first.wait_for(
                state="visible", timeout=1500
            )
            return False  # 로그인 버튼 있음 → 비로그인
        except PWTimeout:
            return True   # 로그인 버튼 없음 → 로그인 상태
    return False


def _paste_into(page, selector: str, value: str):
    """클립보드 붙여넣기로 입력 — 네이버는 한 글자씩 타이핑(키 입력)을 봇으로
    감지해 차단하므로, 브라우저 클립보드에 값을 넣고 Ctrl+V 로 붙여넣어 우회한다.
    (서버에는 시스템 클립보드가 없어 pyperclip 대신 브라우저 clipboard API 사용)
    클립보드가 막히면 fill() 로 폴백."""
    field = page.locator(selector)
    field.click()
    time.sleep(0.4)
    try:
        page.evaluate("(v) => navigator.clipboard.writeText(v)", value)
        time.sleep(0.2)
        page.keyboard.press("Control+V")
    except Exception:
        field.fill(value)  # 클립보드 불가 시 한 번에 값 설정(타이핑 아님)
    time.sleep(0.8)


def _do_login(page, naver_id: str, naver_pw: str):
    """클립보드 붙여넣기 방식 로그인 (IP보안 비활성화 후 붙여넣기)."""
    print("로그인 페이지 접속...")
    page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
    time.sleep(2)

    # IP보안 모드 OFF - ON 상태면 #pw가 직접 입력을 차단함
    ip_toggle = page.locator(".ico_bool")
    try:
        if ip_toggle.first.is_visible(timeout=2000):
            ip_toggle.first.click()
            print("  IP보안 OFF 전환")
            time.sleep(0.8)
    except PWTimeout:
        pass

    # 아이디/비밀번호 — 붙여넣기(Ctrl+V)로 입력 (@naver.com 제거)
    login_id = naver_id.split("@")[0] if "@" in naver_id else naver_id
    print("  아이디/비밀번호 붙여넣기 입력...")
    _paste_into(page, "#id", login_id)
    _paste_into(page, "#pw", naver_pw)

    page.click(".btn_login")
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    time.sleep(2.5)
    page.screenshot(path=str(_ROOT / "data" / "poster_after_login.png"))


def manual_login(context, page) -> bool:
    """브라우저를 열어 사용자가 직접 로그인하도록 대기 후 쿠키 저장."""
    try:
        page.goto("https://nid.naver.com/nidlogin.login", wait_until="commit", timeout=15000)
    except Exception:
        pass  # 리다이렉트 발생해도 계속 진행
    print("\n브라우저가 열렸습니다. 직접 로그인해 주세요.")
    print("로그인 완료 후 이 터미널에서 Enter를 누르세요...")
    input()

    # goto 없이 현재 URL·쿠키로만 판단
    current_url = page.url
    has_session = any(c.get("name") in ("NID_SES", "NID_AUT") for c in context.cookies())
    on_naver = "naver.com" in current_url and "nidlogin" not in current_url

    if has_session or on_naver:
        _save_cookies(context)
        print(f"쿠키 저장 완료: {_COOKIE_PATH}")
        return True
    print(f"로그인 확인 실패. 현재 URL: {current_url}")
    return False


def ensure_logged_in(context, page, naver_id: str, naver_pw: str) -> bool:
    if _load_cookies(context):
        print("저장된 쿠키 로드...")
        if _is_logged_in(context, page):
            print("쿠키 세션 유효 - 로그인 유지")
            return True
        print("쿠키 만료 → 재로그인")

    _do_login(page, naver_id, naver_pw)

    if _is_logged_in(context, page):
        _save_cookies(context)
        print(f"로그인 성공, 쿠키 저장: {_COOKIE_PATH}")
        return True

    return False


# ---------------------------------------------------------------------------
# Content reader
# ---------------------------------------------------------------------------

def _read_content(keyword: str, date: str, output_dir: Path) -> dict:
    safe_kw = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    path = output_dir / f"content_{safe_kw}_{date}.json"
    if not path.exists():
        matches = sorted(output_dir.glob(f"content_{safe_kw}_*.json"), reverse=True)
        if not matches:
            raise FileNotFoundError(
                f"콘텐츠 파일 없음: output/content_{safe_kw}_*.json\n"
                "먼저 에이전트 3(writer)을 실행하세요."
            )
        path = matches[0]
        print(f"날짜 파일 없음, 최신 파일 사용: {path.name}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Blog posting
# ---------------------------------------------------------------------------

def _dismiss_all_popups(page):
    """모든 팝업/다이얼로그 닫기 — 에디터 진입 초기화 및 포인터 이벤트 차단 해제."""
    page.evaluate("""
        () => {
            // 1) se-popup-alert-confirm 등 alert 다이얼로그 — 확인 버튼 클릭
            var popups = Array.from(document.querySelectorAll('[data-group="popupLayer"]'));
            for (var p of popups) {
                var btns = Array.from(p.querySelectorAll('button'));
                for (var b of btns) {
                    b.click();
                }
            }
            // 2) 도움말 패널 close 버튼
            var allBtns = Array.from(document.querySelectorAll('button'));
            for (var i = 0; i < allBtns.length; i++) {
                var cls = allBtns[i].className.toString();
                if ((cls.indexOf('close') >= 0 || cls.indexOf('Close') >= 0) &&
                    allBtns[i].closest('[class*="help"]')) {
                    allBtns[i].click();
                }
            }
        }
    """)
    time.sleep(0.5)
    page.keyboard.press("Escape")
    time.sleep(0.3)


def _close_help_popup(page):
    """SmartEditor ONE 도움말 팝업 닫기 — JS로 직접 클릭."""
    page.evaluate("""
        () => {
            var btns = Array.from(document.querySelectorAll('button'));
            for (var i = 0; i < btns.length; i++) {
                var cls = btns[i].className.toString();
                if ((cls.indexOf('close') >= 0 || cls.indexOf('Close') >= 0) &&
                    btns[i].closest('[class*="help"]')) {
                    btns[i].click();
                    return true;
                }
            }
            return false;
        }
    """)
    page.keyboard.press("Escape")
    time.sleep(0.5)


def _type_lines(page, text: str):
    """줄 단위로 keyboard.type - 제목 입력용."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        page.keyboard.type(line, delay=12)
        if i < len(lines) - 1:
            page.keyboard.press("Enter")
            time.sleep(0.02)


def _inline_md(text: str) -> str:
    """인라인 마크다운 + 커스텀 태그 변환."""
    # [HL]텍스트[/HL] → 하이라이트 배경 (볼드와 함께 쓰임)
    text = re.sub(
        r'\[HL\](.+?)\[/HL\]',
        r'<mark style="background-color:#fff740;padding:1px 3px;">\1</mark>',
        text,
    )
    # **볼드** (HL 처리 후에 실행해야 중첩 안전)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # 링크 [텍스트](URL)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2">\1</a>', text)
    return text


def _md_to_html(text: str) -> str:
    """마크다운 + 커스텀 태그 → HTML 변환 (SmartEditor ONE clipboard 삽입용)."""
    # [IMAGE: ...] → 편집자 참고용 HTML 주석
    text = re.sub(
        r'\[IMAGE:\s*([^\]]+)\]',
        lambda m: f'<!-- 이미지 삽입 위치: {m.group(1).strip()} -->',
        text,
    )

    # [LINK_CARD]...[/LINK_CARD] → 링크 카드 스타일 박스
    def _link_card(m):
        inner = m.group(1).strip()
        # 📰 제목 줄 추출
        title_line = ""
        url_line = ""
        for ln in inner.splitlines():
            ln = ln.strip()
            if ln.startswith("📰"):
                title_line = ln[1:].strip()
            elif ln.startswith("🔗"):
                url_line = ln[1:].strip()
        if url_line:
            return (
                '<div style="border:1px solid #e0e0e0;border-radius:8px;'
                'padding:14px 18px;margin:10px 0;background:#fff;'
                'box-shadow:0 1px 4px rgba(0,0,0,0.08);">'
                f'<a href="{url_line}" style="text-decoration:none;color:#222;">'
                f'<span style="font-size:13px;color:#2db400;font-weight:bold;">▶ 추천 글</span><br>'
                f'<span style="font-size:15px;font-weight:bold;line-height:1.6;">{title_line}</span><br>'
                f'<span style="font-size:12px;color:#888;">{url_line}</span>'
                '</a></div>'
            )
        return _md_to_html_lines(inner)
    text = re.sub(r'\[LINK_CARD\]([\s\S]*?)\[/LINK_CARD\]', _link_card, text)

    # [CTA_BOX]...[/CTA_BOX] → 녹색 테두리 박스
    def _cta_block(m):
        inner = _md_to_html_lines(m.group(1).strip())
        return (
            '<div style="border:2px solid #2db400;border-radius:10px;'
            'padding:18px 22px;background:#f8fff8;margin:28px 0;">'
            + inner + '</div>'
        )
    text = re.sub(r'\[CTA_BOX\]([\s\S]*?)\[/CTA_BOX\]', _cta_block, text)

    # [QUOTE]...[/QUOTE] → 버티컬 라인 인용구 (하위 호환)
    def _quote_wrap(m):
        inner = _inline_md(m.group(1).strip())
        return (
            '<blockquote style="border-left:4px solid #2db400;'
            'padding:10px 16px;background:#f5f5f5;margin:16px 0;'
            'font-size:19px;font-weight:bold;line-height:1.5;">'
            + inner + '</blockquote>'
        )
    text = re.sub(r'\[QUOTE\]([\s\S]*?)\[/QUOTE\]', _quote_wrap, text)

    return _md_to_html_lines(text)


def _md_to_html_lines(text: str) -> str:
    """줄 단위 마크다운 → HTML (재귀 호출용 내부 함수)."""
    _BULLET_STYLE = 'style="margin:4px 0;padding-left:8px;line-height:1.8;font-size:15px;"'
    _P_STYLE      = 'style="line-height:1.8;font-size:15px;margin:6px 0;"'
    _H3_STYLE     = ('style="font-size:16px;font-weight:bold;margin:14px 0 6px;'
                     'padding:6px 10px;background:#f0faf0;border-radius:4px;"')
    _QUOTE_STYLE  = ('style="border-left:4px solid #2db400;padding:10px 16px;'
                     'background:#f5f5f5;margin:16px 0;font-size:19px;'
                     'font-weight:bold;line-height:1.5;"')
    # 이미 HTML 블록 요소로 변환된 줄은 그대로 통과 (중첩 <p> 방지)
    _BLOCK_PREFIXES = ("<blockquote", "<div", "<h1", "<h2", "<h3", "<!--")
    parts = []
    for line in text.split("\n"):
        s = line.strip()
        if any(s.startswith(p) for p in _BLOCK_PREFIXES):
            parts.append(s)
        # [인용구] 접두사 → 버티컬 라인 blockquote (H2 대제목)
        elif s.startswith("[인용구]"):
            inner = _inline_md(s[len("[인용구]"):].strip())
            parts.append(f'<blockquote {_QUOTE_STYLE}>{inner}</blockquote>')
        elif s.startswith("### "):
            parts.append(f"<h3>{_inline_md(s[4:])}</h3>")
        elif s.startswith("## "):
            parts.append(f"<h2>{_inline_md(s[3:])}</h2>")
        elif s.startswith("# "):
            parts.append(f"<h1>{_inline_md(s[2:])}</h1>")
        # ✅ / 📌 접두사 → H3 소제목 박스
        elif s.startswith("✅ ") or s.startswith("📌 "):
            parts.append(f'<p {_H3_STYLE}>{_inline_md(s)}</p>')
        elif s.startswith("• ") or s.startswith("- ") or s.startswith("* "):
            content = s[2:]
            parts.append(f"<p {_BULLET_STYLE}>• {_inline_md(content)}</p>")
        elif s == "" or s == "---":
            parts.append("<br>")
        else:
            parts.append(f"<p {_P_STYLE}>{_inline_md(s)}</p>")
    return "".join(parts)


def _insert_html_to_body(page, html: str) -> str:
    """SmartEditor ONE 본문에 HTML을 클립보드 붙여넣기로 삽입.

    innerHTML / execCommand 는 SmartEditor ONE React 상태를 갱신하지 않아
    발행 시 내용이 무시됨. 클립보드에 text/html 포맷으로 넣고 Ctrl+V 하면
    에디터 자체 paste 핸들러가 서식을 유지하며 삽입됨.
    """
    # 1) 클립보드에 HTML 복사 (Web Clipboard API, text/html 포맷)
    page.evaluate("""
        async (html) => {
            try {
                await navigator.clipboard.write([
                    new ClipboardItem({
                        'text/html': new Blob([html], { type: 'text/html' }),
                        'text/plain': new Blob([html.replace(/<[^>]+>/g, '')], { type: 'text/plain' })
                    })
                ]);
            } catch (e) {
                // 권한 없으면 execCommand fallback
                var ta = document.createElement('textarea');
                ta.value = html;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            }
        }
    """, html)
    time.sleep(0.3)

    # 2) 본문 클릭 후 Ctrl+V
    page.locator(".se-section-text").first.click(force=True)
    time.sleep(0.4)
    page.keyboard.press("Control+a")
    time.sleep(0.2)
    page.keyboard.press("Control+v")
    time.sleep(0.5)
    return "OK_CLIPBOARD"


def post_blog(page, title: str, body: str, naver_id: str, naver_pw: str = ""):
    """SmartEditor ONE - 클릭 후 keyboard.type으로 입력."""
    blog_id = naver_id.split("@")[0] if "@" in naver_id else naver_id
    editor_url = f"https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}"

    def _goto_editor():
        print(f"블로그 에디터 접속... (blogId={blog_id})")
        page.goto(editor_url, wait_until="domcontentloaded", timeout=25000)
        # 로그인 페이지로 리다이렉트됐으면 재로그인
        if "nidlogin" in page.url or "nid.naver.com" in page.url:
            print("쿠키 세션 만료(IP 변경 등) → ID/PW 재로그인 시도...")
            if not naver_pw:
                raise RuntimeError("세션 만료 — .env에 NAVER_PW 필요")
            _do_login(page, naver_id, naver_pw)
            print("재로그인 후 에디터 재접속...")
            page.goto(editor_url, wait_until="domcontentloaded", timeout=25000)

    _goto_editor()

    # 에디터 완전 로딩 대기
    page.wait_for_selector(".se-container", timeout=15000)
    time.sleep(2.5)

    # 초기 팝업/다이얼로그 전부 닫기 (pointer-events 차단 해제)
    _dismiss_all_popups(page)
    time.sleep(0.5)

    # ── 제목 입력 ──────────────────────────────────────────────────
    print("제목 입력...")
    page.locator(".se-section-documentTitle").click(force=True)
    time.sleep(0.5)
    _type_lines(page, title)
    print("  제목 입력 완료")
    time.sleep(0.5)

    # ── 본문 입력 (마크다운 → HTML → innerHTML 삽입) ──────────────
    print("본문 입력...")
    html_body = _md_to_html(body)
    result = _insert_html_to_body(page, html_body)
    print(f"  본문 HTML 삽입 완료 (result={result})")
    time.sleep(1)

    # 발행 전 스크린샷 (디버깅)
    page.screenshot(path=str(_ROOT / "data" / "poster_before_publish.png"))

    # ── 발행 버튼 ──────────────────────────────────────────────────
    print("발행 버튼 클릭...")
    # 도움말 팝업 한 번 더 닫기 (발행 버튼 가림 방지)
    _close_help_popup(page)
    time.sleep(0.5)

    # 페이지 최상단으로 스크롤 (발행 버튼이 상단에 있음)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.5)

    # Playwright force click — React 이벤트 핸들러 발동
    publish_btn = page.locator("button[class*='publish_btn']").first
    try:
        publish_btn.wait_for(state="attached", timeout=5000)
        publish_btn.scroll_into_view_if_needed()
        publish_btn.click(force=True)
        print("  발행 클릭 (force)")
    except Exception as e:
        raise RuntimeError(f"발행 버튼 클릭 실패: {e}")

    time.sleep(2)
    page.screenshot(path=str(_ROOT / "data" / "poster_after_publish_click.png"))

    # ── 발행 확인 다이얼로그 ───────────────────────────────────────
    # 다이얼로그에서 '발행' 또는 '확인' 버튼 클릭
    dialog_clicked = False
    for confirm_sel in [
        "button[class*='confirm']:has-text('발행')",
        "button[class*='publish']:not([class*='reserve'])",
        ".se-modal button:has-text('발행')",
        "button:has-text('확인')",
        ".btn_ok",
    ]:
        try:
            btn = page.locator(confirm_sel).first
            if btn.is_visible(timeout=4000):
                btn.click(force=True)
                dialog_clicked = True
                print(f"  다이얼로그 확인 클릭 ({confirm_sel})")
                time.sleep(3)
                break
        except Exception:
            continue

    try:
        page.screenshot(path=str(_ROOT / "data" / "poster_final.png"), timeout=10000)
    except Exception:
        pass  # 발행 후 페이지 이동 중 타임아웃은 무시
    print("블로그 글 발행 완료!")

    # 발행 후 URL 수집 (성과 트래킹용)
    time.sleep(2)
    try:
        current_url = page.url
        if (
            "blog.naver.com" in current_url
            and "PostWriteForm" not in current_url
            and "nidlogin" not in current_url
        ):
            print(f"[RESULT_URL]:{current_url}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 포스터 (에이전트 6)")
    parser.add_argument("--keyword", required=True, help="포스팅할 키워드")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="콘텐츠 날짜 (기본값: 오늘, 형식: YYYY-MM-DD)",
    )
    parser.add_argument("--login-only", action="store_true", help="로그인 테스트만 실행")
    parser.add_argument("--manual-login", action="store_true", help="브라우저에서 직접 로그인 후 쿠키 저장")
    parser.add_argument("--headless", action="store_true", help="헤드리스 모드 (UI 없음)")
    args = parser.parse_args()

    naver_id = os.environ.get("NAVER_ID")
    naver_pw = os.environ.get("NAVER_PW")
    if not naver_id or not naver_pw:
        raise EnvironmentError(".env에 NAVER_ID / NAVER_PW가 없습니다.")

    data_dir = _ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    # $DISPLAY 없는 환경(Linux VM 등)에서는 headless 강제 적용
    headless = args.headless or (not os.environ.get("DISPLAY"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**_launch_kwargs(headless))
        context_kwargs = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            permissions=["clipboard-read", "clipboard-write"],
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        proxy = _proxy_config()
        if proxy:
            context_kwargs["proxy"] = proxy
            print(f"프록시 사용: {proxy['server']}")
        context = browser.new_context(**context_kwargs)
        # 모든 페이지에 stealth 스크립트 주입 (navigator.webdriver 등 위장)
        context.add_init_script(_STEALTH_JS)
        page = context.new_page()

        try:
            if args.manual_login:
                ok = manual_login(context, page)
                browser.close()
                raise SystemExit(0 if ok else 1)

            logged_in = ensure_logged_in(context, page, naver_id, naver_pw)
            if not logged_in:
                page.screenshot(path=str(_ERROR_SCREENSHOT))
                raise RuntimeError(
                    f"자동 로그인 실패. 스크린샷: {_ERROR_SCREENSHOT}\n"
                    "CAPTCHA 감지 시 --manual-login 옵션으로 직접 로그인하세요:\n"
                    f"  python agents/poster/main.py --keyword X --manual-login"
                )

            if args.login_only:
                success_path = data_dir / "poster_login_ok.png"
                page.screenshot(path=str(success_path))
                print(f"로그인 테스트 성공! 스크린샷: {success_path}")
                return

            # ── 콘텐츠 로드 ───────────────────────────────────────
            output_dir = _ROOT / "output"
            content_data = _read_content(args.keyword, args.date, output_dir)

            naver_blog = content_data.get("naver_blog", {})
            title = (
                content_data.get("naver_title")
                or naver_blog.get("title")
                or args.keyword
            )
            body = (
                content_data.get("naver_content")
                or naver_blog.get("body")
                or title
            )

            print(f"\n제목: {title}")
            print(f"본문 길이: {len(body)}자\n")

            post_blog(page, title, body, naver_id, naver_pw)

        except Exception as e:
            try:
                page.screenshot(path=str(_ERROR_SCREENSHOT))
                print(f"오류 스크린샷 저장: {_ERROR_SCREENSHOT}")
            except Exception:
                pass
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
