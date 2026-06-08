import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = str(ROOT / "venv" / "Scripts" / "python.exe")


def run_step(name: str, script: str, args: list[str]) -> bool:
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")

    cmd = [PYTHON, str(ROOT / script)] + args
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    result = subprocess.run(cmd, env=env)

    if result.returncode != 0:
        print(f"\n[오류] {name} 실패 (종료 코드: {result.returncode})")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="마케팅 에이전트 파이프라인")
    parser.add_argument("--keyword", required=True, help="분석할 키워드")
    args = parser.parse_args()

    keyword = args.keyword
    today = date.today().isoformat()

    steps = [
        ("1/5  수집   (collector)", "agents/collector/main.py", ["--keyword", keyword]),
        ("2/5  분석   (analyzer)",  "agents/analyzer/main.py",  ["--keyword", keyword]),
        ("3/5  작성   (writer)",    "agents/writer/main.py",    ["--keyword", keyword]),
        ("4/5  리포트 (reporter)",  "agents/reporter/main.py",  ["--date", today, "--keyword", keyword]),
        ("5/5  모니터 (monitor)",   "agents/monitor/main.py",   ["--keywords", keyword, "--once"]),
    ]

    print(f"\n키워드: '{keyword}'  |  날짜: {today}")
    print("파이프라인: collector → analyzer → writer → reporter → monitor")

    for name, script, step_args in steps:
        if not run_step(name, script, step_args):
            print(f"\n파이프라인 중단: {name}에서 오류 발생")
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print("  파이프라인 완료!")
    print(f"{'=' * 60}")
    print(f"  리포트: output/report_{today}.pdf")
    print(f"  콘텐츠: output/content_*_{today}.json")


if __name__ == "__main__":
    main()
