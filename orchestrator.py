import argparse
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = sys.executable


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
    parser.add_argument("--keyword", nargs="+", required=True, help="분석할 키워드 (여러 개 가능)")
    args = parser.parse_args()

    keywords = args.keyword
    today = date.today().isoformat()
    t_total = time.time()

    print(f"\n키워드: {keywords}  |  날짜: {today}")
    print(f"파이프라인: collector → analyzer → writer → reporter → monitor → poster → instagram")

    # 1. 수집: 키워드 전체 한 번에 전달 (collector 내부에서 ThreadPoolExecutor 처리)
    t = time.time()
    ok = run_step(
        f"수집 (collector) — {len(keywords)}개 키워드 병렬",
        "agents/collector/main.py",
        ["--keyword"] + keywords,
    )
    if not ok:
        sys.exit(1)
    print(f"  → 수집 {time.time() - t:.1f}초")

    # 2. 분석: 키워드 전체 한 번에 전달 (analyzer 내부에서 ThreadPoolExecutor 처리)
    t = time.time()
    ok = run_step(
        f"분석 (analyzer) — {len(keywords)}개 키워드 병렬",
        "agents/analyzer/main.py",
        ["--keyword"] + keywords,
    )
    if not ok:
        sys.exit(1)
    print(f"  → 분석 {time.time() - t:.1f}초")

    # 3. 작성: 키워드별 순차 (의존성: 각 키워드의 분석 결과 필요)
    for i, keyword in enumerate(keywords, 1):
        t = time.time()
        ok = run_step(
            f"작성 (writer) [{i}/{len(keywords)}] — {keyword}",
            "agents/writer/main.py",
            ["--keyword", keyword],
        )
        if not ok:
            sys.exit(1)
        print(f"  → 작성 {time.time() - t:.1f}초")

    # 4. 리포트
    t = time.time()
    ok = run_step("리포트 (reporter)", "agents/reporter/main.py", ["--date", today])
    if not ok:
        sys.exit(1)
    print(f"  → 리포트 {time.time() - t:.1f}초")

    # 5. 모니터
    t = time.time()
    ok = run_step("모니터 (monitor)", "agents/monitor/main.py", ["--keywords"] + keywords + ["--once"])
    if not ok:
        sys.exit(1)
    print(f"  → 모니터 {time.time() - t:.1f}초")

    # 6. 포스팅: 키워드별 순차 (의존성: writer 출력 필요)
    for i, keyword in enumerate(keywords, 1):
        t = time.time()
        ok = run_step(
            f"포스팅 (poster) [{i}/{len(keywords)}] — {keyword}",
            "agents/poster/main.py",
            ["--keyword", keyword, "--date", today],
        )
        if not ok:
            sys.exit(1)
        print(f"  → 포스팅 {time.time() - t:.1f}초")

    # 7. 인스타그램: 키워드별 순차 (의존성: writer 출력 필요)
    for i, keyword in enumerate(keywords, 1):
        t = time.time()
        ok = run_step(
            f"인스타그램 (instagram) [{i}/{len(keywords)}] — {keyword}",
            "agents/instagram/main.py",
            ["--keyword", keyword, "--date", today],
        )
        if not ok:
            sys.exit(1)
        print(f"  → 인스타그램 {time.time() - t:.1f}초")

    total = time.time() - t_total
    print(f"\n{'=' * 60}")
    print(f"  파이프라인 완료!  총 {total:.1f}초")
    print(f"{'=' * 60}")
    print(f"  리포트: output/report_{today}.pdf")
    print(f"  콘텐츠: output/content_*_{today}.json")
    print(f"  포스팅: 네이버 블로그 + Instagram 발행 완료")


if __name__ == "__main__":
    main()
