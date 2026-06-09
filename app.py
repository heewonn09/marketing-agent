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
from flask import Flask, Response, jsonify, render_template, request, send_file

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)

ROOT = Path(__file__).parent
PYTHON = sys.executable

# job_id -> {status, queue, date}
jobs: dict[str, dict] = {}


def _run_cmd(job_id: str, name: str, script: str, args: list[str]) -> bool:
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
            jobs[job_id]["status"] = "error"
            q.put("DONE")
            return False
    except Exception as e:
        q.put(f"ERROR:{e}")
        jobs[job_id]["status"] = "error"
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

    jobs[job_id]["status"] = "done"
    jobs[job_id]["date"] = today
    jobs[job_id]["queue"].put(f"DONE:{today}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
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
    threading.Thread(target=run_pipeline, args=(job_id, keywords), daemon=True).start()


scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(scheduled_run, CronTrigger(hour=9, minute=0))
scheduler.start()


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
