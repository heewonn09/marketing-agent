"""파이프라인 헬스체크 — 각 에이전트가 오늘자 출력을 정상 생성했는지 점검한다.

키워드 모니터(agents/monitor)와는 목적이 다르다:
- monitor: 새 블로그 포스트 감지 + 중요도 평가
- healthcheck: 파이프라인 산출물 존재 여부로 에이전트 동작 상태 점검 (관측성)

CLI:
  python agents/healthcheck/main.py --once     # 1회 점검
  python agents/healthcheck/main.py            # 5분 주기 반복
출력: logs/healthcheck_YYYY-MM-DD.log
"""

import argparse
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
INTERVAL_SECONDS = 300


@dataclass
class AgentDef:
    number: int
    name: str
    script: Path
    output_dir: Path
    output_glob: str
    exclude_prefix: str | None


@dataclass
class CheckResult:
    agent: AgentDef
    status: str
    detail: str


def check_agent(agent: AgentDef, today: date) -> CheckResult:
    """스크립트 존재 + 오늘자 출력 파일 유무로 상태를 판정한다."""
    try:
        if not agent.script.exists():
            return CheckResult(agent, "MISSING", "스크립트 없음")

        today_str = today.strftime("%Y-%m-%d")
        files = [
            f for f in agent.output_dir.glob(agent.output_glob)
            if today_str in f.name
        ]
        if agent.exclude_prefix:
            files = [f for f in files if not f.name.startswith(agent.exclude_prefix)]

        if files:
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return CheckResult(agent, "OK", f"최근 파일: {files[0].name}")
        return CheckResult(agent, "WARNING", "오늘 출력 없음")
    except Exception as exc:  # noqa: BLE001 - 점검 자체가 파이프라인을 막아선 안 됨
        return CheckResult(agent, "ERROR", str(exc))


def _make_agents() -> list[AgentDef]:
    data = BASE_DIR / "data"
    output = BASE_DIR / "output"
    a = lambda n, name, sub, odir, glob, ex: AgentDef(  # noqa: E731
        n, name, BASE_DIR / "agents" / sub / "main.py", odir, glob, ex
    )
    return [
        a(1, "collector", "collector", data, "*_*.json", "analyzed_"),
        a(2, "analyzer", "analyzer", data, "analyzed_*.json", None),
        a(3, "writer", "writer", output, "content_*.json", None),
        a(4, "reporter", "reporter", output, "report_*.pdf", None),
        a(5, "monitor", "monitor", data, "monitor_log_*.json", None),
        a(6, "cardnews", "cardnews", output, "cardnews_*.png", None),
    ]


def _format_line(ts: str, r: CheckResult) -> str:
    return f"[{ts}] [{r.status:<7}] 에이전트 {r.agent.number} ({r.agent.name:<10}): {r.detail}"


def run_check(agents: list[AgentDef], log_dir: Path, today: date) -> list[CheckResult]:
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"healthcheck_{today.strftime('%Y-%m-%d')}.log"

    results = [check_agent(ag, today) for ag in agents]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    counts: dict[str, int] = {"OK": 0, "WARNING": 0, "MISSING": 0, "ERROR": 0}
    lines = [f"[{ts}] === 헬스체크 시작 ==="]
    for r in results:
        lines.append(_format_line(ts, r))
        counts[r.status] = counts.get(r.status, 0) + 1
        print(lines[-1])

    summary = " / ".join(f"{k} {v}" for k, v in counts.items())
    lines.append(f"[{ts}] === 요약: {summary} ===")
    lines.append("")
    print(lines[-2])

    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"로그 저장: {log_path}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="마케팅 파이프라인 헬스체크")
    parser.add_argument("--once", action="store_true", help="1회만 점검하고 종료")
    args = parser.parse_args()

    agents = _make_agents()
    log_dir = BASE_DIR / "logs"
    while True:
        run_check(agents, log_dir, date.today())
        if args.once:
            break
        print(f"{INTERVAL_SECONDS // 60}분 후 다음 점검... (Ctrl+C로 종료)")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
