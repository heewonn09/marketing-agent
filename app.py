import base64
import json as _json
import os
import queue
import re as _re
import subprocess
import sys
import threading
import time
import uuid
from datetime import date
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from utils.job_store import init_db, upsert_job, get_job, list_jobs, get_stats
from utils.cleanup import cleanup_old_files
from utils.backup import backup_state
from utils.notifier import notify_done, notify_error, notify_approval_pending
from utils.auth_guard import verify_credentials, LoginRateLimiter

ROOT = Path(__file__).parent
PYTHON = sys.executable


def _resolve_secret_key() -> str:
    """SECRET_KEY 우선순위: env > data/.flask_secret 파일(영구) > 신규 생성.

    os.urandom 폴백을 영구화해 재시작 시 세션이 무효화되지 않게 한다.
    """
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = ROOT / "data" / ".flask_secret"
    if key_file.exists():
        return key_file.read_text().strip()
    key = os.urandom(32).hex()
    key_file.parent.mkdir(exist_ok=True)
    key_file.write_text(key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


app = Flask(__name__)
app.secret_key = _resolve_secret_key()

# 리버스 프록시(HTTPS 종단) 뒤에서 동작 시 원래 스킴/호스트 인식
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# HTTPS 운영 시 FORCE_HTTPS=1 → 세션 쿠키 Secure 플래그
_force_https = os.environ.get("FORCE_HTTPS", "").lower() in ("1", "true", "yes")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=_force_https,
)

ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

_AUTH_EXEMPT_PREFIXES = ("/stream/", "/cardnews/")
_AUTH_EXEMPT_PATHS = ("/login",)

_rate_limiter = LoginRateLimiter(max_attempts=5, window=300, lockout=900)

jobs: dict[str, dict] = {}

init_db(ROOT / "data" / "jobs.db")


def _auth_enabled() -> bool:
    return bool(ADMIN_USER) and bool(ADMIN_PASSWORD or ADMIN_PASSWORD_HASH)


def _check_credentials(user: str, pwd: str) -> bool:
    return verify_credentials(user, pwd, ADMIN_USER, ADMIN_PASSWORD, ADMIN_PASSWORD_HASH)


@app.before_request
def _require_auth():
    if not _auth_enabled():
        return
    if request.path in _AUTH_EXEMPT_PATHS:
        return
    if any(request.path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
        return
    if session.get("authenticated"):
        return
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        if _rate_limiter.is_locked(request.remote_addr or "?"):
            return Response("로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.", 429)
        try:
            user, pwd = base64.b64decode(auth[6:]).decode().split(":", 1)
            if _check_credentials(user, pwd):
                _rate_limiter.register_success(request.remote_addr or "?")
                return
            _rate_limiter.register_failure(request.remote_addr or "?")
        except Exception:
            pass
    if "text/html" in request.headers.get("Accept", ""):
        return redirect(url_for("login", next=request.path))
    return Response("인증이 필요합니다", 401,
                    {"WWW-Authenticate": 'Basic realm="Marketing Agent"'})


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _rate_limiter.is_locked(ip):
            error = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."
            return render_template("login.html", error=error), 429
        user = request.form.get("username", "")
        pwd = request.form.get("password", "")
        if _check_credentials(user, pwd):
            _rate_limiter.register_success(ip)
            session["authenticated"] = True
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        _rate_limiter.register_failure(ip)
        error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── 파이프라인 ─────────────────────────────────────────────────────────────

def _run_cmd(job_id: str, name: str, script: str, args: list[str], fatal: bool = True) -> bool:
    q: queue.Queue = jobs[job_id]["queue"]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    jobs[job_id]["last_step"] = name
    q.put(f"STEP:{name}")
    cmd = [PYTHON, str(ROOT / script)] + args
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
        )
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            # 에이전트 결과 메타데이터 파싱 (로그로 노출하지 않음)
            if line.startswith("[RESULT_URL]:"):
                jobs[job_id]["naver_post_url"] = line[13:].strip()
                continue
            if line.startswith("[RESULT_MEDIA]:"):
                parts = line[15:].strip().split(":", 1)
                if len(parts) == 2:
                    jobs[job_id]["instagram_media_id"] = parts[0]
                    jobs[job_id]["instagram_permalink"] = parts[1]
                elif len(parts) == 1:
                    jobs[job_id]["instagram_media_id"] = parts[0]
                continue
            q.put(f"LOG:{line}")
        proc.wait()
        if proc.returncode != 0:
            err_msg = f"{name} 실패 (종료 코드: {proc.returncode})"
            q.put(f"ERROR:{err_msg}")
            if fatal:
                jobs[job_id]["status"] = "error"
                upsert_job(job_id, "error")
                q.put("DONE")
                kws = jobs[job_id].get("keywords") or []
                threading.Thread(target=notify_error, args=(kws, name, err_msg), daemon=True).start()
            return False
    except Exception as e:
        err_msg = str(e)
        q.put(f"ERROR:{err_msg}")
        if fatal:
            jobs[job_id]["status"] = "error"
            upsert_job(job_id, "error")
            q.put("DONE")
            kws = jobs[job_id].get("keywords") or []
            threading.Thread(target=notify_error, args=(kws, name, err_msg), daemon=True).start()
        return False
    return True


def _run_pipeline_part2(job_id: str, keywords: list[str], today: str) -> None:
    """포스팅 + 인스타그램 (승인 후 실행)"""
    for keyword in keywords:
        ok = _run_cmd(job_id, f"포스팅 [{keyword}]", "agents/poster/main.py",
                      ["--keyword", keyword, "--date", today], fatal=False)
        if not ok:
            jobs[job_id]["queue"].put(
                "LOG:[poster] 네이버 봇 감지 또는 로그인 실패 — 로컬에서 별도 실행 필요. 다음 스텝 계속 진행."
            )

    for keyword in keywords:
        safe_kw = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
        cardnews_ready = all(
            (ROOT / "output" / f"cardnews_{safe_kw}_{today}_{i}.png").exists()
            for i in range(1, 5)
        )
        ig_args = ["--keyword", keyword, "--date", today]
        if cardnews_ready:
            ig_args.append("--carousel")
            jobs[job_id]["queue"].put("LOG:[instagram] 카드뉴스 4장 감지 → 캐러셀 업로드")
        if not _run_cmd(job_id, f"인스타그램 [{keyword}]", "agents/instagram/main.py", ig_args):
            return

    jobs[job_id]["status"] = "done"
    jobs[job_id]["date"] = today
    duration = int(time.time() - jobs[job_id].get("started_at", time.time()))
    jobs[job_id]["duration_seconds"] = duration
    upsert_job(
        job_id, "done", keywords, today,
        naver_post_url=jobs[job_id].get("naver_post_url"),
        instagram_media_id=jobs[job_id].get("instagram_media_id"),
        instagram_permalink=jobs[job_id].get("instagram_permalink"),
        duration_seconds=duration,
    )
    jobs[job_id]["queue"].put(f"DONE:{today}")
    base_url = os.environ.get("CARDNEWS_BASE_URL", "")
    threading.Thread(target=notify_done, args=(keywords, today, base_url), daemon=True).start()


def _run_per_keyword(job_id: str, keyword: str, fatal: bool = True) -> bool:
    """키워드 하나의 수집→분석→작성을 순차 실행. 실패 시 False 반환.
    fatal=False면 실패해도 잡 전체를 error로 만들지 않음(복수 키워드 부분 실패 허용용)."""
    for name, script, args in [
        (f"수집 [{keyword}]", "agents/collector/main.py", ["--keyword", keyword]),
        (f"분석 [{keyword}]", "agents/analyzer/main.py",  ["--keyword", keyword]),
        (f"작성 [{keyword}]", "agents/writer/main.py",    ["--keyword", keyword]),
    ]:
        if not _run_cmd(job_id, name, script, args, fatal=fatal):
            return False
    return True


def run_pipeline(job_id: str, keywords: list[str], auto_post: bool = False) -> None:
    import concurrent.futures
    today = date.today().isoformat()

    if len(keywords) == 1:
        # 단일 키워드: 직접 실행 (실패 시 잡 error)
        if not _run_per_keyword(job_id, keywords[0]):
            return
    else:
        # 복수 키워드: 부분 실패 허용 — 실패한 키워드는 제외하고 성공한 것으로 계속 진행
        ok_keywords: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(keywords), 3)) as ex:
            futures = {ex.submit(_run_per_keyword, job_id, kw, False): kw for kw in keywords}
            for fut in concurrent.futures.as_completed(futures):
                kw = futures[fut]
                if fut.result():
                    ok_keywords.append(kw)
                else:
                    jobs[job_id]["queue"].put(f"LOG:[{kw}] 수집/분석/작성 실패 — 이 키워드는 제외하고 계속 진행")
        if not ok_keywords:
            jobs[job_id]["status"] = "error"
            upsert_job(job_id, "error")
            jobs[job_id]["queue"].put("ERROR:모든 키워드 처리 실패")
            jobs[job_id]["queue"].put("DONE")
            threading.Thread(target=notify_error,
                             args=(keywords, "전체 키워드", "모든 키워드 처리 실패"),
                             daemon=True).start()
            return
        keywords = ok_keywords  # 이후 단계(리포트/모니터/카드뉴스/발행)는 성공한 키워드로만

    for name, script, step_args in [
        ("리포트 [통합]", "agents/reporter/main.py", ["--date", today]),
        ("모니터 [통합]", "agents/monitor/main.py",  ["--keywords"] + keywords + ["--once"]),
    ]:
        if not _run_cmd(job_id, name, script, step_args):
            return

    for keyword in keywords:
        ok = _run_cmd(job_id, f"카드뉴스 [{keyword}]", "agents/cardnews/main.py",
                      ["--keyword", keyword, "--date", today], fatal=False)
        if not ok:
            jobs[job_id]["queue"].put("LOG:[cardnews] 카드뉴스 생성 실패 — 다음 스텝 계속 진행.")

    if auto_post:
        _run_pipeline_part2(job_id, keywords, today)
    else:
        # 승인 대기 — 프론트엔드가 /approve/<job_id>를 호출할 때까지 큐 유지
        jobs[job_id]["status"] = "pending_approval"
        jobs[job_id]["date"] = today
        upsert_job(job_id, "pending_approval", keywords, today)
        jobs[job_id]["queue"].put(f"PENDING:{today}")
        # 승인 대기 알림 (이메일 + 슬랙)
        base_url = os.environ.get("CARDNEWS_BASE_URL", "")
        threading.Thread(
            target=notify_approval_pending,
            args=(keywords, today, base_url),
            daemon=True,
        ).start()


# 종료(terminal) 상태 — 일정 시간 후 메모리에서 정리 대상
_TERMINAL_STATUSES = {"done", "error", "rejected", "interrupted"}


def _prune_jobs(max_age: int = 3600) -> None:
    """메모리 누수 방지: 종료된 잡을 max_age(기본 1시간) 경과 후 in-memory dict에서 제거.
    상태는 jobs.db에 남아 /history·재연결 복원에는 영향 없음. 진행 중 잡은 유지."""
    now = time.time()
    stale = [
        jid for jid, info in list(jobs.items())
        if info.get("status") in _TERMINAL_STATUSES
        and now - info.get("started_at", now) > max_age
    ]
    for jid in stale:
        jobs.pop(jid, None)


# ── 라우트 ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    try:
        raw = request.get_data()
        data = _json.loads(raw.decode("utf-8"))
    except Exception:
        data = request.json or {}
    keyword_input = data.get("keywords") or data.get("keyword", "")
    if isinstance(keyword_input, list):
        keywords = [k.strip() for k in keyword_input if k.strip()]
    else:
        keywords = [k.strip() for k in keyword_input.split(",") if k.strip()]

    if not keywords:
        return jsonify({"error": "키워드를 입력하세요"}), 400

    _prune_jobs()  # 종료된 옛 잡 정리 (메모리 누수 방지)
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {
        "status": "running", "queue": queue.Queue(), "date": None,
        "keywords": keywords, "last_step": None,
        "started_at": time.time(),
        "naver_post_url": None, "instagram_media_id": None, "instagram_permalink": None,
    }
    upsert_job(job_id, "running", keywords)
    threading.Thread(target=run_pipeline, args=(job_id, keywords), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    if job_id not in jobs:
        # 서버 재시작 후 pending_approval 잡 복원
        db_job = get_job(job_id)
        if db_job and db_job.get("status") == "pending_approval":
            today = db_job.get("date") or date.today().isoformat()
            keywords = db_job.get("keywords", [])
            q = queue.Queue()
            jobs[job_id] = {"status": "pending_approval", "queue": q,
                            "date": today, "keywords": keywords, "last_step": None}
        else:
            return "Job not found", 404

    job_info = jobs[job_id]
    q = job_info["queue"]

    def generate():
        # 재연결 시: 이미 pending_approval 상태면 즉시 PENDING 이벤트 재전송
        if job_info.get("status") == "pending_approval":
            today = job_info.get("date") or date.today().isoformat()
            yield f"data: PENDING:{today}\n\n"

        while True:
            try:
                msg = q.get(timeout=60)
                yield f"data: {msg}\n\n"
                if msg.startswith("DONE") or msg == "DONE" or msg == "REJECTED":
                    break
                # PENDING: 스트림 유지 — 승인 후 Part2 메시지가 이어서 들어옴
            except queue.Empty:
                yield "data: PING\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/approve/<job_id>", methods=["POST"])
def approve(job_id: str):
    job_info = jobs.get(job_id)
    if not job_info or job_info.get("status") != "pending_approval":
        # 서버 재시작 후 메모리 손실된 경우 DB에서 복원
        db_job = get_job(job_id)
        if not db_job or db_job.get("status") != "pending_approval":
            return jsonify({"error": "승인 대기 상태가 아닙니다"}), 400
        today = db_job.get("date") or date.today().isoformat()
        keywords = db_job.get("keywords", [])
        if job_id not in jobs:
            jobs[job_id] = {"status": "pending_approval", "queue": queue.Queue(),
                            "date": today, "keywords": keywords, "last_step": None}
        job_info = jobs[job_id]

    keywords = job_info.get("keywords", [])
    today = job_info.get("date") or date.today().isoformat()
    jobs[job_id]["status"] = "posting"
    upsert_job(job_id, "posting", keywords, today)
    threading.Thread(target=_run_pipeline_part2, args=(job_id, keywords, today), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/reject/<job_id>", methods=["POST"])
def reject(job_id: str):
    if job_id in jobs:
        jobs[job_id]["status"] = "rejected"
        jobs[job_id]["queue"].put("REJECTED")
    upsert_job(job_id, "rejected")
    return jsonify({"ok": True})


@app.route("/edit-content/<report_date>/<path:keyword>", methods=["POST"])
def edit_content(report_date: str, keyword: str):
    safe_keyword = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    content_path = ROOT / "output" / f"content_{safe_keyword}_{report_date}.json"
    if not content_path.exists():
        return jsonify({"error": "파일 없음"}), 404
    try:
        data = request.json or {}
        with open(content_path, encoding="utf-8") as f:
            existing = _json.load(f)
        for section in ["naver_blog", "instagram", "ad_copy"]:
            if section in data:
                existing[section] = {**existing.get(section, {}), **data[section]}
        with open(content_path, "w", encoding="utf-8") as f:
            _json.dump(existing, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/result/<report_date>/<path:keyword>")
def result(report_date: str, keyword: str):
    safe_keyword = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    content_path = ROOT / "output" / f"content_{safe_keyword}_{report_date}.json"
    if not content_path.exists():
        return jsonify({"error": "콘텐츠 파일을 찾을 수 없습니다"}), 404
    with open(content_path, encoding="utf-8") as f:
        return jsonify(_json.load(f))


@app.route("/cardnews/<path:filename>")
def serve_cardnews(filename: str):
    safe = _re.sub(r'[^a-zA-Z0-9가-힣 ._\-]', '', filename)
    img_path = ROOT / "output" / safe
    if not img_path.exists() or img_path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        return "이미지를 찾을 수 없습니다", 404
    return send_file(str(img_path), mimetype="image/png")


@app.route("/history")
def history():
    return jsonify(list_jobs(limit=20))


@app.route("/stats")
def stats():
    return jsonify(get_stats())


@app.route("/rerun/<job_id>", methods=["POST"])
def rerun(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "잡을 찾을 수 없습니다"}), 404
    keywords = job.get("keywords") or []
    if not keywords:
        return jsonify({"error": "키워드 정보가 없습니다"}), 400
    new_id = uuid.uuid4().hex[:8]
    jobs[new_id] = {
        "status": "running", "queue": queue.Queue(), "date": None,
        "keywords": keywords, "last_step": None,
        "started_at": time.time(),
        "naver_post_url": None, "instagram_media_id": None, "instagram_permalink": None,
    }
    upsert_job(new_id, "running", keywords)
    threading.Thread(target=run_pipeline, args=(new_id, keywords), daemon=True).start()
    return jsonify({"job_id": new_id, "keywords": keywords})


@app.route("/cardnews-files/<report_date>/<path:keyword>")
def cardnews_files(report_date: str, keyword: str):
    safe_kw = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    files = [
        f"cardnews_{safe_kw}_{report_date}_{i}.png"
        for i in range(1, 5)
        if (ROOT / "output" / f"cardnews_{safe_kw}_{report_date}_{i}.png").exists()
    ]
    return jsonify({"files": files})


@app.route("/test-notify", methods=["POST"])
def test_notify():
    kind = (request.json or {}).get("kind", "done")
    base_url = os.environ.get("CARDNEWS_BASE_URL", "")
    if kind == "error":
        threading.Thread(target=notify_error,
                         args=(["테스트 키워드"], "테스트 스텝", "이것은 테스트 오류 메시지입니다."),
                         daemon=True).start()
    else:
        threading.Thread(target=notify_done,
                         args=(["테스트 키워드"], "2026-06-14", base_url),
                         daemon=True).start()
    return jsonify({"sent": kind})


@app.route("/download/<report_date>")
def download(report_date: str):
    pdf_path = ROOT / "output" / f"report_{report_date}.pdf"
    if not pdf_path.exists():
        return "PDF를 찾을 수 없습니다", 404
    return send_file(str(pdf_path), as_attachment=True,
                     download_name=f"marketing_report_{report_date}.pdf")


# ── 스케줄러 ───────────────────────────────────────────────────────────────

def scheduled_run():
    keywords_env = os.environ.get("SCHEDULED_KEYWORDS", "")
    keywords = [k.strip() for k in keywords_env.split(",") if k.strip()]
    if not keywords:
        print("[scheduler] SCHEDULED_KEYWORDS가 설정되지 않아 실행 생략")
        return
    print(f"[scheduler] 자동 실행 시작: {keywords}")
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {
        "status": "running", "queue": queue.Queue(), "date": None,
        "keywords": keywords, "last_step": None,
        "started_at": time.time(),
        "naver_post_url": None, "instagram_media_id": None, "instagram_permalink": None,
    }
    upsert_job(job_id, "running", keywords)
    # 스케줄러는 승인 없이 자동 게시
    threading.Thread(target=run_pipeline, args=(job_id, keywords, True), daemon=True).start()


def _run_cleanup():
    # 정리 전에 상태 파일 백업 (실수 삭제·손상 대비 복구점)
    try:
        copied = backup_state(ROOT)
        print(f"[backup] 상태 파일 {len(copied)}개 백업: {copied}")
    except Exception as e:
        print(f"[backup] 실패: {e}")
    deleted = cleanup_old_files(ROOT)
    if deleted:
        names = [f.name for f in deleted[:5]]
        extra = f" 외 {len(deleted) - 5}개" if len(deleted) > 5 else ""
        print(f"[cleanup] {len(deleted)}개 삭제: {names}{extra}")
    else:
        print("[cleanup] 삭제 대상 없음")


scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(scheduled_run, CronTrigger(hour=9, minute=0))
scheduler.add_job(_run_cleanup, CronTrigger(hour=2, minute=0, timezone="Asia/Seoul"))
scheduler.start()


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
