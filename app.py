import base64
import hmac
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
from utils.job_store import (init_db, upsert_job, get_job, list_jobs, get_stats,
                             create_schedule, get_schedule, list_schedules,
                             update_schedule, delete_schedule)
from utils.schedule_util import validate_schedule, normalize_days
from utils.cleanup import cleanup_old_files
from utils.backup import backup_state
from utils.notifier import notify_done, notify_error, notify_approval_pending
from utils.auth_guard import verify_credentials, LoginRateLimiter
from utils.user_store import (init_users, upsert_admin, verify_user,
                               create_user, get_user_by_id, get_user_by_username,
                               list_users, update_user, delete_user)

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
API_KEY = os.environ.get("API_KEY", "").strip()

_AUTH_EXEMPT_PREFIXES = ("/stream/", "/cardnews/", "/share/")
_AUTH_EXEMPT_PATHS = ("/login",)

_rate_limiter = LoginRateLimiter(max_attempts=5, window=300, lockout=900)

jobs: dict[str, dict] = {}

init_db(ROOT / "data" / "jobs.db")
init_users()  # users 테이블 생성 (_DEFAULT_DB 사용)

# env var 관리자 → DB 자동 동기화 (하위 호환)
if ADMIN_USER and (ADMIN_PASSWORD or ADMIN_PASSWORD_HASH):
    from werkzeug.security import generate_password_hash as _gph
    _admin_hash = ADMIN_PASSWORD_HASH or _gph(ADMIN_PASSWORD)
    upsert_admin(ADMIN_USER, _admin_hash)


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
    if session.get("user_id") is not None:
        return
    # X-API-Key 헤더 — 프로그래밍 접근용 (Basic Auth 대체)
    req_api_key = request.headers.get("X-API-Key", "").strip()
    if req_api_key and API_KEY and hmac.compare_digest(
        req_api_key.encode(), API_KEY.encode()
    ):
        return
    # 브라우저: 로그인 페이지로 리디렉트
    if "text/html" in request.headers.get("Accept", ""):
        return redirect(url_for("login", next=request.path))
    # API 클라이언트: 401 (WWW-Authenticate 헤더 없이 — Basic Auth 팝업 방지)
    return Response("인증이 필요합니다. X-API-Key 헤더를 사용하세요.", 401)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _rate_limiter.is_locked(ip):
            error = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."
            return render_template("login.html", error=error), 429
        username = request.form.get("username", "")
        pwd = request.form.get("password", "")

        # 1) DB 사용자 확인
        user_dict = verify_user(username, pwd)
        # 2) DB에 없으면 env var 어드민 폴백 (하위 호환 + 테스트 용이성)
        if user_dict is None and _check_credentials(username, pwd):
            user_dict = get_user_by_username(username) or {
                "id": 0, "username": ADMIN_USER, "role": "admin",
                "plan": "agency", "enabled": True,
            }

        if user_dict and user_dict.get("enabled"):
            _rate_limiter.register_success(ip)
            session["user_id"]  = user_dict["id"]
            session["username"] = user_dict["username"]
            session["role"]     = user_dict.get("role", "user")
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)

        _rate_limiter.register_failure(ip)
        error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── 관리자 ────────────────────────────────────────────────────────────────────
import functools as _functools


def _require_admin(f):
    @_functools.wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return Response("관리자만 접근할 수 있습니다.", 403)
        return f(*args, **kwargs)
    return wrapper


@app.route("/admin")
@_require_admin
def admin_page():
    return render_template("admin.html")


@app.route("/admin/users", methods=["GET"])
@_require_admin
def admin_users_list():
    users = list_users()
    safe = [{k: v for k, v in u.items() if k != "password_hash"} for u in users]
    return jsonify({"users": safe})


@app.route("/admin/users", methods=["POST"])
@_require_admin
def admin_users_create():
    from werkzeug.security import generate_password_hash as _gph2
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    plan     = data.get("plan", "starter")
    role     = data.get("role", "user")
    if not username or not password:
        return jsonify({"error": "username과 password는 필수입니다"}), 400
    if plan not in ("starter", "pro", "agency"):
        return jsonify({"error": "plan은 starter/pro/agency 중 하나입니다"}), 400
    try:
        uid = create_user(username, _gph2(password), role=role, plan=plan)
        return jsonify({"id": uid, "username": username}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 409


@app.route("/admin/users/<int:uid>", methods=["PATCH"])
@_require_admin
def admin_users_update(uid: int):
    from werkzeug.security import generate_password_hash as _gph2
    data = request.get_json(silent=True) or {}
    fields: dict = {}
    if "plan" in data:
        fields["plan"] = data["plan"]
    if "enabled" in data:
        fields["enabled"] = bool(data["enabled"])
    if "role" in data:
        fields["role"] = data["role"]
    if "password" in data and data["password"]:
        fields["password_hash"] = _gph2(data["password"])
    if not fields:
        return jsonify({"error": "변경할 항목이 없습니다"}), 400
    update_user(uid, **fields)
    u = get_user_by_id(uid)
    if not u:
        return jsonify({"error": "사용자를 찾을 수 없습니다"}), 404
    return jsonify({k: v for k, v in u.items() if k != "password_hash"})


@app.route("/admin/users/<int:uid>", methods=["DELETE"])
@_require_admin
def admin_users_delete(uid: int):
    u = get_user_by_id(uid)
    if not u:
        return jsonify({"error": "사용자를 찾을 수 없습니다"}), 404
    delete_user(uid)
    return jsonify({"ok": True})


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
                upsert_job(job_id, "error", error_message=err_msg)
                q.put("DONE")
                kws = jobs[job_id].get("keywords") or []
                threading.Thread(target=notify_error, args=(kws, name, err_msg), daemon=True).start()
            return False
    except Exception as e:
        err_msg = str(e)
        q.put(f"ERROR:{err_msg}")
        if fatal:
            jobs[job_id]["status"] = "error"
            upsert_job(job_id, "error", error_message=err_msg)
            q.put("DONE")
            kws = jobs[job_id].get("keywords") or []
            threading.Thread(target=notify_error, args=(kws, name, err_msg), daemon=True).start()
        return False
    return True


def _run_pipeline_part2(job_id: str, keywords: list[str], today: str,
                        post_blog: bool = True, post_instagram: bool = True,
                        user_id: int | None = None) -> None:
    """포스팅 + 인스타그램 (승인 후 실행)"""
    if post_blog:
        for keyword in keywords:
            ok = _run_cmd(job_id, f"포스팅 [{keyword}]", "agents/poster/main.py",
                          ["--keyword", keyword, "--date", today], fatal=False)
            if not ok:
                jobs[job_id]["queue"].put(
                    "LOG:[poster] 네이버 봇 감지 또는 로그인 실패 — 로컬에서 별도 실행 필요. 다음 스텝 계속 진행."
                )

    if post_instagram:
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
    _uid = user_id if user_id is not None else jobs[job_id].get("user_id")
    upsert_job(
        job_id, "done", keywords, today,
        naver_post_url=jobs[job_id].get("naver_post_url"),
        instagram_media_id=jobs[job_id].get("instagram_media_id"),
        instagram_permalink=jobs[job_id].get("instagram_permalink"),
        duration_seconds=duration, user_id=_uid,
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


def run_pipeline(job_id: str, keywords: list[str], auto_post: bool = False,
                 post_blog: bool = True, post_instagram: bool = True,
                 user_id: int | None = None) -> None:
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

    if post_instagram:
        for keyword in keywords:
            ok = _run_cmd(job_id, f"카드뉴스 [{keyword}]", "agents/cardnews/main.py",
                          ["--keyword", keyword, "--date", today], fatal=False)
            if not ok:
                jobs[job_id]["queue"].put("LOG:[cardnews] 카드뉴스 생성 실패 — 다음 스텝 계속 진행.")

    if auto_post:
        _run_pipeline_part2(job_id, keywords, today, post_blog, post_instagram, user_id=user_id)
    else:
        # 승인 대기 — 프론트엔드가 /approve/<job_id>를 호출할 때까지 큐 유지
        jobs[job_id]["status"] = "pending_approval"
        jobs[job_id]["date"] = today
        upsert_job(job_id, "pending_approval", keywords, today, user_id=user_id)
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


def _resolve_job_date(keywords: list[str], preferred_date: str | None) -> str:
    """pending_approval 복원 시 올바른 날짜를 찾는다.

    DB의 date가 null인 잡이라도 output/ 디렉터리에서 실제 콘텐츠 파일을 스캔해 날짜를 복구한다.
    """
    if preferred_date:
        return preferred_date
    for kw in keywords:
        safe_kw = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", kw)
        files = sorted(ROOT.glob(f"output/content_{safe_kw}_*.json"), reverse=True)
        if files:
            m = _re.search(r'_(\d{4}-\d{2}-\d{2})\.json$', files[0].name)
            if m:
                return m.group(1)
    return date.today().isoformat()


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
    uid = session.get("user_id")
    jobs[job_id] = {
        "status": "running", "queue": queue.Queue(), "date": None,
        "keywords": keywords, "last_step": None,
        "started_at": time.time(), "user_id": uid,
        "naver_post_url": None, "instagram_media_id": None, "instagram_permalink": None,
    }
    upsert_job(job_id, "running", keywords, user_id=uid)
    threading.Thread(
        target=run_pipeline, args=(job_id, keywords),
        kwargs={"user_id": uid}, daemon=True,
    ).start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    if job_id not in jobs:
        # 서버 재시작 후 pending_approval 잡 복원
        db_job = get_job(job_id)
        if db_job and db_job.get("status") == "pending_approval":
            keywords = db_job.get("keywords", [])
            today = _resolve_job_date(keywords, db_job.get("date"))
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
        keywords = db_job.get("keywords", [])
        today = _resolve_job_date(keywords, db_job.get("date"))
        if job_id not in jobs:
            jobs[job_id] = {"status": "pending_approval", "queue": queue.Queue(),
                            "date": today, "keywords": keywords, "last_step": None}
        job_info = jobs[job_id]

    keywords = job_info.get("keywords", [])
    today = _resolve_job_date(keywords, job_info.get("date"))
    uid = job_info.get("user_id")
    jobs[job_id]["status"] = "posting"
    upsert_job(job_id, "posting", keywords, today, user_id=uid)
    threading.Thread(
        target=_run_pipeline_part2, args=(job_id, keywords, today),
        kwargs={"user_id": uid}, daemon=True,
    ).start()
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
    page     = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(100, int(request.args.get("per_page", 10))))
    status   = request.args.get("status", "")
    q        = request.args.get("q", "")
    from_d   = request.args.get("from", "")
    to_d     = request.args.get("to", "")
    role = session.get("role", "user")
    uid  = None if role == "admin" else session.get("user_id")
    result   = list_jobs(page=page, per_page=per_page, status=status, q=q,
                         from_date=from_d, to_date=to_d, user_id=uid)
    return jsonify(result)


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


@app.route("/share/<job_id>")
def share(job_id: str):
    """인증 없이 접근 가능한 읽기 전용 공유 링크.

    job_id에 해당하는 잡 정보 + 생성된 콘텐츠 요약을 반환.
    콘텐츠 파일이 없으면 메타 정보만 반환.
    """
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "공유 링크를 찾을 수 없습니다"}), 404

    result = {
        "job_id": job_id,
        "status": job.get("status"),
        "date": job.get("date"),
        "keywords": job.get("keywords", []),
        "contents": [],
    }

    for keyword in job.get("keywords", []):
        safe_kw = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
        report_date = job.get("date") or ""
        content_path = ROOT / "output" / f"content_{safe_kw}_{report_date}.json"
        entry: dict = {"keyword": keyword}
        if content_path.exists():
            with open(content_path, encoding="utf-8") as f:
                content = _json.load(f)
            entry["naver_blog_title"] = content.get("naver_blog", {}).get("title", "")
            entry["instagram_caption"] = content.get("instagram", {}).get("caption", "")[:100]
            entry["ad_headline"] = content.get("ad_copy", {}).get("headline", "")
            entry["cardnews"] = [
                f"/cardnews/cardnews_{safe_kw}_{report_date}_{i}.png"
                for i in range(1, 5)
                if (ROOT / "output" / f"cardnews_{safe_kw}_{report_date}_{i}.png").exists()
            ]
        result["contents"].append(entry)

    return jsonify(result)


# ── /schedules CRUD ────────────────────────────────────────────────────────

@app.route("/schedules", methods=["GET"])
def schedules_list():
    out = []
    for s in list_schedules():
        job = scheduler.get_job(f"sched_{s['id']}")
        s = dict(s)
        s["next_run"] = job.next_run_time.isoformat() if (job and job.next_run_time) else None
        out.append(s)
    return jsonify(out)


@app.route("/schedules", methods=["POST"])
def schedules_create():
    data = request.get_json(silent=True) or {}
    ok, err = validate_schedule(data)
    if not ok:
        return jsonify({"error": err}), 400
    sid = create_schedule(
        name=data.get("name", ""), keywords=[k.strip() for k in data["keywords"] if str(k).strip()],
        days=normalize_days(data["days"]), hour=data["hour"], minute=data["minute"],
        post_blog=bool(data.get("post_blog", False)), post_instagram=bool(data.get("post_instagram", False)),
        enabled=bool(data.get("enabled", True)))
    sched = get_schedule(sid)
    if sched["enabled"]:
        _apply_schedule(sched)
    return jsonify({"id": sid})


@app.route("/schedules/<int:sid>", methods=["PUT"])
def schedules_update(sid):
    if not get_schedule(sid):
        return jsonify({"error": "없는 스케줄"}), 404
    data = request.get_json(silent=True) or {}
    ok, err = validate_schedule(data)
    if not ok:
        return jsonify({"error": err}), 400
    update_schedule(sid, name=data.get("name", ""),
                    keywords=[k.strip() for k in data["keywords"] if str(k).strip()],
                    days=normalize_days(data["days"]), hour=data["hour"], minute=data["minute"],
                    post_blog=bool(data.get("post_blog", False)), post_instagram=bool(data.get("post_instagram", False)),
                    enabled=bool(data.get("enabled", True)))
    sched = get_schedule(sid)
    _unschedule(sid)
    if sched["enabled"]:
        _apply_schedule(sched)
    return jsonify({"ok": True})


@app.route("/schedules/<int:sid>", methods=["DELETE"])
def schedules_delete(sid):
    _unschedule(sid)
    delete_schedule(sid)
    return jsonify({"ok": True})


@app.route("/schedules/<int:sid>/toggle", methods=["POST"])
def schedules_toggle(sid):
    s = get_schedule(sid)
    if not s:
        return jsonify({"error": "없는 스케줄"}), 404
    new_enabled = not s["enabled"]
    update_schedule(sid, enabled=new_enabled)
    _unschedule(sid)
    if new_enabled:
        _apply_schedule(get_schedule(sid))
    return jsonify({"enabled": new_enabled})


# ── 스케줄러 ───────────────────────────────────────────────────────────────

def scheduled_run(schedule_id: int):
    sched = get_schedule(schedule_id)
    if not sched or not sched["enabled"]:
        print(f"[scheduler] 스케줄 {schedule_id} 없음/비활성 — 생략")
        return
    keywords = sched["keywords"]
    if not keywords:
        return
    print(f"[scheduler] 자동 실행: id={schedule_id} {keywords}")
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {
        "status": "running", "queue": queue.Queue(), "date": None,
        "keywords": keywords, "last_step": None, "started_at": time.time(),
        "schedule_id": schedule_id,
        "naver_post_url": None, "instagram_media_id": None, "instagram_permalink": None,
    }
    upsert_job(job_id, "running", keywords)

    def _safe_run():
        try:
            run_pipeline(job_id, keywords, auto_post=True,
                         post_blog=sched["post_blog"],
                         post_instagram=sched["post_instagram"])
        except Exception as e:
            err_msg = f"스케줄 실행 중 예외 발생: {e}"
            print(f"[scheduler] {err_msg}")
            if jobs.get(job_id, {}).get("status") == "running":
                jobs[job_id]["status"] = "error"
                upsert_job(job_id, "error", error_message=err_msg)
                jobs[job_id]["queue"].put(f"ERROR:{err_msg}")
                jobs[job_id]["queue"].put("DONE")

    threading.Thread(target=_safe_run, daemon=True).start()


def _apply_schedule(sched: dict):
    from utils.schedule_util import cron_kwargs
    scheduler.add_job(
        scheduled_run, CronTrigger(timezone="Asia/Seoul", **cron_kwargs(sched["days"], sched["hour"], sched["minute"])),
        args=[sched["id"]], id=f"sched_{sched['id']}",
        replace_existing=True, coalesce=True, max_instances=1)


def _unschedule(schedule_id: int):
    try:
        scheduler.remove_job(f"sched_{schedule_id}")
    except Exception:
        pass


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


def _refresh_ig_token_job() -> None:
    """Instagram 액세스 토큰 주간 갱신 — 60일 만료 방지.

    INSTAGRAM_ACCESS_TOKEN 미설정 시 건너뜀.
    갱신 실패 시 notify_error로 알림.
    """
    import requests as _req
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not access_token:
        print("[ig-token] INSTAGRAM_ACCESS_TOKEN 미설정 - 건너뜀")
        return
    try:
        res = _req.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": access_token},
            timeout=15,
        )
        if not res.ok:
            msg = f"토큰 갱신 실패 {res.status_code}: {res.text[:120]}"
            print(f"[ig-token] {msg}")
            threading.Thread(
                target=notify_error, args=([], "Instagram 토큰 갱신", msg), daemon=True
            ).start()
            return
        data = res.json()
        new_token = data.get("access_token", "")
        days = data.get("expires_in", 0) // 86400
        print(f"[ig-token] 갱신 완료 - 만료까지 {days}일")
        if new_token and new_token != access_token:
            env_path = ROOT / ".env"
            if env_path.exists():
                text = env_path.read_text(encoding="utf-8")
                import re as _re2
                text = _re2.sub(
                    r"^INSTAGRAM_ACCESS_TOKEN=.*$",
                    f"INSTAGRAM_ACCESS_TOKEN={new_token}",
                    text,
                    flags=_re2.MULTILINE,
                )
                env_path.write_text(text, encoding="utf-8")
            os.environ["INSTAGRAM_ACCESS_TOKEN"] = new_token
            print("[ig-token] .env 토큰 업데이트 완료")
    except Exception as e:
        msg = f"토큰 갱신 예외: {e}"
        print(f"[ig-token] {msg}")
        threading.Thread(
            target=notify_error, args=([], "Instagram 토큰 갱신", msg), daemon=True
        ).start()


scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(_run_cleanup, CronTrigger(hour=2, minute=0, timezone="Asia/Seoul"))
scheduler.add_job(
    _refresh_ig_token_job,
    CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="Asia/Seoul"),
    id="ig_token_refresh",
    replace_existing=True,
)
# 기존 매일 09:00 scheduled_run 잡은 제거 (웹 스케줄로 대체)

if os.environ.get("DISABLE_SCHEDULER") != "1":
    for _s in list_schedules():
        if _s["enabled"]:
            _apply_schedule(_s)
    # 서버 시작 시 IG 토큰 상태 선제 갱신
    threading.Thread(target=_refresh_ig_token_job, daemon=True).start()
    scheduler.start()


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
