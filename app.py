import os
import queue
import subprocess
import threading
import uuid
from datetime import date
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

app = Flask(__name__)

ROOT = Path(__file__).parent
PYTHON = str(ROOT / "venv" / "Scripts" / "python.exe")

STEPS = [
    ("1/5  수집", "agents/collector/main.py", "keyword"),
    ("2/5  분석", "agents/analyzer/main.py",  "keyword"),
    ("3/5  작성", "agents/writer/main.py",    "keyword"),
    ("4/5  리포트", "agents/reporter/main.py", "date_keyword"),
    ("5/5  모니터", "agents/monitor/main.py",  "keywords_once"),
]

# job_id -> {status, queue, date}
jobs: dict[str, dict] = {}


def run_pipeline(job_id: str, keyword: str) -> None:
    q: queue.Queue = jobs[job_id]["queue"]
    today = date.today().isoformat()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    step_args_map = {
        "keyword":       lambda: ["--keyword", keyword],
        "date_keyword":  lambda: ["--date", today, "--keyword", keyword],
        "keywords_once": lambda: ["--keywords", keyword, "--once"],
    }

    for name, script, arg_type in STEPS:
        q.put(f"STEP:{name}")
        cmd = [PYTHON, str(ROOT / script)] + step_args_map[arg_type]()
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
                return
        except Exception as e:
            q.put(f"ERROR:{e}")
            jobs[job_id]["status"] = "error"
            q.put("DONE")
            return

    jobs[job_id]["status"] = "done"
    jobs[job_id]["date"] = today
    q.put(f"DONE:{today}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    keyword = (request.json or {}).get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "키워드를 입력하세요"}), 400

    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"status": "running", "queue": queue.Queue(), "date": None}
    threading.Thread(target=run_pipeline, args=(job_id, keyword), daemon=True).start()
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


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
