"""
Windows 작업 스케줄러용 네이버 블로그 자동 포스팅 스크립트.
.env의 SCHEDULED_KEYWORDS를 읽어 키워드별로 poster 에이전트 순차 실행.
"""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
POSTER = ROOT / "agents" / "poster" / "main.py"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


def main():
    keywords_raw = os.environ.get("SCHEDULED_KEYWORDS", "")
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    if not keywords:
        print("[poster_schedule] SCHEDULED_KEYWORDS가 .env에 설정되지 않았습니다.")
        sys.exit(1)

    today = date.today().isoformat()
    print(f"[poster_schedule] 실행 날짜: {today}  키워드: {keywords}")

    results = []
    for keyword in keywords:
        print(f"\n[poster_schedule] ▶ 포스팅 시작: {keyword}")
        proc = subprocess.run(
            [str(PYTHON), str(POSTER), "--keyword", keyword, "--date", today],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        status = "성공" if proc.returncode == 0 else "실패"
        results.append((keyword, status))
        print(f"[poster_schedule] {status}: {keyword}")

    print("\n[poster_schedule] ── 결과 요약 ──")
    for kw, st in results:
        print(f"  {st}  {kw}")


if __name__ == "__main__":
    main()
