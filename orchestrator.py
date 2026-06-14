import argparse
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = sys.executable

sys.path.insert(0, str(ROOT))
from utils.logging_setup import get_logger

log = get_logger("pipeline", log_file=ROOT / "logs" / f"pipeline_{date.today().isoformat()}.log")


def run_step(name: str, script: str, args: list[str]) -> bool:
    log.info("─" * 50)
    log.info("시작: %s", name)

    cmd = [PYTHON, str(ROOT / script)] + args
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    t = time.time()
    result = subprocess.run(cmd, env=env)
    elapsed = time.time() - t

    if result.returncode != 0:
        log.error("실패: %s (종료 코드 %d, %.1f초)", name, result.returncode, elapsed)
        return False
    log.info("완료: %s (%.1f초)", name, elapsed)
    return True


def main():
    parser = argparse.ArgumentParser(description="마케팅 에이전트 파이프라인")
    parser.add_argument("--keyword", nargs="+", required=True, help="분석할 키워드 (여러 개 가능)")
    args = parser.parse_args()

    keywords = args.keyword
    today = date.today().isoformat()
    t_total = time.time()

    log.info("파이프라인 시작 — 키워드: %s | 날짜: %s", keywords, today)
    log.info("단계: collector → analyzer → writer → reporter → monitor → poster → instagram")

    # 1. 수집: 키워드 전체 한 번에 전달 (collector 내부에서 ThreadPoolExecutor 처리)
    if not run_step(
        f"수집 (collector) — {len(keywords)}개 키워드 병렬",
        "agents/collector/main.py",
        ["--keyword"] + keywords,
    ):
        sys.exit(1)

    # 2. 분석: 키워드 전체 한 번에 전달 (analyzer 내부에서 ThreadPoolExecutor 처리)
    if not run_step(
        f"분석 (analyzer) — {len(keywords)}개 키워드 병렬",
        "agents/analyzer/main.py",
        ["--keyword"] + keywords,
    ):
        sys.exit(1)

    # 3. 작성: 키워드별 순차 (의존성: 각 키워드의 분석 결과 필요)
    for i, keyword in enumerate(keywords, 1):
        if not run_step(
            f"작성 (writer) [{i}/{len(keywords)}] — {keyword}",
            "agents/writer/main.py",
            ["--keyword", keyword],
        ):
            sys.exit(1)

    # 4. 리포트
    if not run_step("리포트 (reporter)", "agents/reporter/main.py", ["--date", today]):
        sys.exit(1)

    # 5. 모니터
    if not run_step("모니터 (monitor)", "agents/monitor/main.py", ["--keywords"] + keywords + ["--once"]):
        sys.exit(1)

    # 6. 포스팅: 실패해도 계속 진행 (VM에서는 네이버 CAPTCHA로 차단될 수 있음)
    for i, keyword in enumerate(keywords, 1):
        if not run_step(
            f"포스팅 (poster) [{i}/{len(keywords)}] — {keyword}",
            "agents/poster/main.py",
            ["--keyword", keyword, "--date", today],
        ):
            log.warning("포스팅 실패 (네이버 봇 감지 가능성) — 로컬에서 별도 실행 필요: %s", keyword)

    # 7. 인스타그램: 키워드별 순차 (의존성: writer 출력 필요)
    for i, keyword in enumerate(keywords, 1):
        if not run_step(
            f"인스타그램 (instagram) [{i}/{len(keywords)}] — {keyword}",
            "agents/instagram/main.py",
            ["--keyword", keyword, "--date", today],
        ):
            sys.exit(1)

    log.info("파이프라인 완료! 총 %.1f초 | 리포트: output/report_%s.pdf", time.time() - t_total, today)


if __name__ == "__main__":
    main()
