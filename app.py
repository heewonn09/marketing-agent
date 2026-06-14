import base64
import os
import queue
import subprocess
import sys
import threading
import uuid
from datetime import date
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from utils.job_store import init_db, upsert_job
from utils.cleanup import cleanup_old_files

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32).hex()

ROOT = Path(__file__).parent
PYTHON = sys.executable

ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# SSE 스트림과 카드뉴스 이미지는 인증 면제 (job_id/파일명이 추측 불가 토큰 역할)
_AUTH_EXEMPT_PREFIXES = ("/stream/", "/cardnews/")
_AUTH_EXEMPT_PATHS = ("/login",)

# job_id -> {status, queue, date}
jobs: dict[str, dict] = {}

init_db(ROOT / "data" / "jobs.db")


def _check_credentials(user: str, pwd: str) -> bool:
    return bool(ADMIN_USER) and user == ADMIN_USER and pwd == ADMIN_PASSWORD


@app.before_request
def _require_auth():
    if not ADMIN_USER or not ADMIN_PASSWORD:
        return  # 미설정 시 인증 생략 (로컬 개발)
    if request.path in _AUTH_EXEMPT_PATHS:
        return
    if any(request.path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
        return

    # 1) 세션 쿠키 확인 (로그인 폼 방식)
    if session.get("authenticated"):
        return

    # 2) Basic Auth (curl / API 클라이언트 호환)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            user, pwd = base64.b64decode(auth[6:]).decode().split(":", 1)
            if _check_credentials(user, pwd):
                return
        except Exception:
            pass

    # 3) 브라우저 → 로그인 페이지로 리다이렉트 / API 클라이언트 → 401
    if "text/html" in request.headers.get("Accept", ""):
        return redirect(url_for("login", next=request.path))
    return Response("인증이 필요합니다", 401,
                    {"WWW-Authenticate": 'Basic realm="Marketing Agent"'})


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("username", "")
        pwd = request.form.get("password", "")
        if _check_credentials(user, pwd):
            session["authenticated"] = True
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _run_cmd(job_id: str, name: str, script: str, args: list[str], fatal: bool = True) -> bool:
    q: queue.Queue = jobs[job_id]["queue"]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    q.put(f"STEP:{name}")
    cmd = [PYTHON, str(ROOT / script)] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                q.put(f"LOG:{line}")
        proc.wait()
        if proc.returncode != 0:
            q.put(f"ERROR:{name} 실패 (종료 코드: {proc.returncode})")
            if fatal:
                jobs[job_id]["status"] = "error"
                upsert_job(job_id, "error")
                q.put("DONE")
            return False
    except Exception as e:
        q.put(f"ERROR:{e}")
        if fatal:
            jobs[job_id]["status"] = "error"
            upsert_job(job_id, "error")
            q.put("DONE")
        return False
    return True


def run_pipeline(job_id: str, keywords: list[str]) -> None:
    today = date.today().isoformat()

    # 키워드별 순차 실행 (수집→분석→작성)
    for keyword in keywords:
        per_kw_steps = [
            (f"수집 [{keyword}]", "agents/collector/main.py", ["--keyword", keyword]),
            (f"분석 [{keyword}]", "agents/analyzer/main.py",  ["--keyword", keyword]),
            (f"작성 [{keyword}]", "agents/writer/main.py",    ["--keyword", keyword]),
        ]
        for name, script, step_args in per_kw_steps:
            if not _run_cmd(job_id, name, script, step_args):
                return

    # 통합 리포트 및 모니터
    combined_steps = [
        ("리포트 [통합]", "agents/reporter/main.py", ["--date", today]),
        ("모니터 [통합]", "agents/monitor/main.py",  ["--keywords"] + keywords + ["--once"]),
    ]
    for name, script, step_args in combined_steps:
        if not _run_cmd(job_id, name, script, step_args):
            return

    # 카드뉴스 생성: 실패해도 파이프라인 계속 (의존성: analyzer 출력)
    for keyword in keywords:
        ok = _run_cmd(
            job_id,
            f"카드뉴스 [{keyword}]",
            "agents/cardnews/main.py",
            ["--keyword", keyword, "--date", today],
            fatal=False,
        )
        if not ok:
            jobs[job_id]["queue"].put(
                "LOG:[cardnews] 카드뉴스 생성 실패 — 다음 스텝 계속 진행."
            )

    # 포스팅: 실패해도 파이프라인 계속 (VM에서는 네이버 CAPTCHA로 차단될 수 있음)
    for keyword in keywords:
        ok = _run_cmd(
            job_id,
            f"포스팅 [{keyword}]",
            "agents/poster/main.py",
            ["--keyword", keyword, "--date", today],
            fatal=False,
        )
        if not ok:
            jobs[job_id]["queue"].put(
                "LOG:[poster] 네이버 봇 감지 또는 로그인 실패 — 로컬에서 별도 실행 필요. 다음 스텝 계속 진행."
            )

    # 인스타그램: 카드뉴스 4장이 모두 있으면 캐러셀, 없으면 단일 이미지
    import re as _re
    for keyword in keywords:
        safe_kw = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
        cardnews_ready = all(
            (ROOT / "output" / f"cardnews_{safe_kw}_{today}_{i}.png").exists()
            for i in range(1, 5)
        )
        ig_args = ["--keyword", keyword, "--date", today]
        if cardnews_ready:
            ig_args.append("--carousel")
            jobs[job_id]["queue"].put(f"LOG:[instagram] 카드뉴스 4장 감지 → 캐러셀 업로드")
        if not _run_cmd(job_id, f"인스타그램 [{keyword}]",
                        "agents/instagram/main.py", ig_args):
            return

    jobs[job_id]["status"] = "done"
    jobs[job_id]["date"] = today
    upsert_job(job_id, "done", keywords, today)
    jobs[job_id]["queue"].put(f"DONE:{today}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    # PowerShell 등 일부 클라이언트가 JSON 바디를 cp949로 전송하는 경우 대비
    # get_data()로 원시 바이트를 받아 UTF-8 강제 디코딩 후 파싱
    import json as _json
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

    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"status": "running", "queue": queue.Queue(), "date": None}
    upsert_job(job_id, "running", keywords)
    threading.Thread(target=run_pipeline, args=(job_id, keywords), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    if job_id not in jobs:
        return "Job not found", 404
    q = jobs[job_id]["queue"]

    def generate():
        while True:
            try:
                msg = q.get(timeout=60)
                yield f"data: {msg}\n\n"
                if msg.startswith("DONE") or msg == "DONE":
                    break
            except queue.Empty:
                yield "data: PING\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/result/<report_date>/<path:keyword>")
def result(report_date: str, keyword: str):
    import re, json
    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    content_path = ROOT / "output" / f"content_{safe_keyword}_{report_date}.json"
    if not content_path.exists():
        return jsonify({"error": "콘텐츠 파일을 찾을 수 없습니다"}), 404
    with open(content_path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/cardnews/<path:filename>")
def serve_cardnews(filename: str):
    """생성된 카드뉴스 PNG를 공개 URL로 서빙 (Instagram carousel image_url용)."""
    import re as _re
    safe = _re.sub(r'[^a-zA-Z0-9가-힣 ._\-]', '', filename)
    img_path = ROOT / "output" / safe
    if not img_path.exists() or img_path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        return "이미지를 찾을 수 없습니다", 404
    return send_file(str(img_path), mimetype="image/png")


@app.route("/download/<report_date>")
def download(report_date: str):
    pdf_path = ROOT / "output" / f"report_{report_date}.pdf"
    if not pdf_path.exists():
        return "PDF를 찾을 수 없습니다", 404
    return send_file(
        str(pdf_path),
        as_attachment=True,
        download_name=f"marketing_report_{report_date}.pdf",
    )


def scheduled_run():
    keywords_env = os.environ.get("SCHEDULED_KEYWORDS", "")
    keywords = [k.strip() for k in keywords_env.split(",") if k.strip()]
    if not keywords:
        print("[scheduler] SCHEDULED_KEYWORDS가 설정되지 않아 실행 생략")
        return
    print(f"[scheduler] 자동 실행 시작: {keywords}")
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"status": "running", "queue": queue.Queue(), "date": None}
    upsert_job(job_id, "running", keywords)
    threading.Thread(target=run_pipeline, args=(job_id, keywords), daemon=True).start()


def _run_cleanup():
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
