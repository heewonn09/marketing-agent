"""웹 UI 흐름을 그대로 구동: /run -> (pending_approval) -> /approve -> 발행.
SSE 스트림을 읽어 단계/로그/완료를 출력한다. 인증 비밀번호는 .env에서 읽어 출력하지 않음.

사용: python scripts/web_run.py "키워드"
"""
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

AUTH = (os.environ.get("ADMIN_USER", ""), os.environ.get("ADMIN_PASSWORD", ""))
if not AUTH[0]:
    AUTH = None
BASE = "http://127.0.0.1:5000"
kw = sys.argv[1]

r = requests.post(f"{BASE}/run", json={"keywords": kw}, auth=AUTH, timeout=30)
r.raise_for_status()
job = r.json()["job_id"]
print(f"[run] job_id={job}  keyword={kw}", flush=True)

approved = False
with requests.get(f"{BASE}/stream/{job}", stream=True, timeout=(10, 120)) as resp:
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        msg = line[5:].strip()
        if msg == "PING":
            continue
        print(msg, flush=True)
        if msg.startswith("PENDING") and not approved:
            approved = True
            ar = requests.post(f"{BASE}/approve/{job}", auth=AUTH, timeout=30)
            print(f"[approve] HTTP {ar.status_code} — 발행(Part2) 시작", flush=True)
        if msg.startswith("DONE"):
            print("[완료] 파이프라인 종료", flush=True)
            break
        if msg.startswith("REJECTED"):
            print("[거부됨]", flush=True)
            break
