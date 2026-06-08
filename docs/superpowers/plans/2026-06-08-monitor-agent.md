# Monitor Agent (Agent 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a file-based monitoring agent that checks all 4 agents every 5 minutes and logs status to `logs/monitor_YYYY-MM-DD.log`.

**Architecture:** Single Python script using stdlib only. Per-agent config defines script path + output dir + file pattern. `check_agent()` checks script existence and today's output files. Results appended to a daily log file. `--once` flag enables single-run mode; default is a 5-minute loop.

**Tech Stack:** Python stdlib (pathlib, datetime, time, argparse, dataclasses), pytest for tests.

---

### Task 1: Create sample analyzer output (Agent 2 sample data)

**Files:**
- Create: `data/analyzed_AI_마케팅_2026-06-08.json`

- [ ] **Step 1: Create the file**

Create `data/analyzed_AI_마케팅_2026-06-08.json` with this content:
```json
{
  "keyword": "AI 마케팅",
  "analyzed_at": "2026-06-08T09:30:00",
  "source_file": "AI_마케팅_2026-06-08.json",
  "item_count": 10,
  "trends": [
    "생성형 AI를 활용한 콘텐츠 자동화가 확산되며 중소기업의 마케팅 비용이 평균 50-70% 절감되고 있다. ChatGPT, Claude 등 다양한 AI 도구가 블로그, SNS 콘텐츠 제작에 활용된다. 퍼스널라이제이션과 결합한 AI 마케팅이 높은 전환율을 기록하는 추세다.",
    "AI 챗봇이 단순 고객 응대를 넘어 마케팅 도구로 진화하고 있다. 24시간 개인화 상품 추천과 장바구니 이탈 방지 기능이 매출 향상에 직접 기여한다. 카카오톡 채널 연동 AI 자동화가 높은 ROI를 기록하고 있다.",
    "퍼포먼스 마케팅에서 AI 입찰 전략이 수동 운영 대비 ROAS 45% 이상 개선을 달성하고 있다. 구글 애즈, 메타 광고의 AI 기능 활용이 표준화되고 있다. 실시간 타겟 최적화가 광고 효율을 크게 높이고 있다."
  ],
  "insights": [
    "소상공인도 월 10만원 수준의 구독형 AI 도구 조합으로 자동화 마케팅 구축이 가능하다. 인스타그램 자동 게시, 이메일 AI 작성, SEO 블로그 포스팅을 우선 도입하면 효과적이다.",
    "AI SEO 전략에서 E-E-A-T 기반 고품질 콘텐츠가 핵심이다. AI 생성 콘텐츠에 전문가 검수를 결합한 하이브리드 전략이 구글 AI 오버뷰 시대에 가장 효과적이다.",
    "AI 마케팅 도입 시 윤리 이슈(딥페이크, 가짜 리뷰)를 사전에 검토해야 한다. 공정거래위원회의 AI 콘텐츠 표시 의무화 동향을 주시하며 브랜드 신뢰도 관리 전략을 병행해야 한다."
  ],
  "keywords": [
    {"word": "생성형 AI", "relevance": "high", "context": "콘텐츠 자동화의 핵심 기술"},
    {"word": "AI 챗봇", "relevance": "high", "context": "마케팅 자동화 및 고객 응대"},
    {"word": "퍼포먼스 마케팅", "relevance": "high", "context": "AI 입찰 전략으로 ROAS 향상"},
    {"word": "콘텐츠 자동화", "relevance": "high", "context": "비용 절감 및 생산성 향상"},
    {"word": "퍼스널라이제이션", "relevance": "high", "context": "개인화 마케팅 전환율 개선"},
    {"word": "SEO", "relevance": "medium", "context": "AI 오버뷰 시대 콘텐츠 전략"},
    {"word": "ROAS", "relevance": "medium", "context": "광고 효율 측정 지표"},
    {"word": "카카오 모먼트", "relevance": "medium", "context": "국내 AI 마케팅 플랫폼"},
    {"word": "가상 인플루언서", "relevance": "medium", "context": "AI 인플루언서 마케팅 트렌드"},
    {"word": "고객 이탈 예측", "relevance": "medium", "context": "AI 리텐션 마케팅"},
    {"word": "E-E-A-T", "relevance": "medium", "context": "구글 콘텐츠 품질 기준"},
    {"word": "소상공인", "relevance": "low", "context": "저비용 AI 마케팅 수요층"},
    {"word": "딥페이크", "relevance": "low", "context": "AI 마케팅 윤리 이슈"},
    {"word": "쇼츠", "relevance": "low", "context": "AI 영상 마케팅 포맷"}
  ]
}
```

- [ ] **Step 2: Verify file parses correctly**

```powershell
.\venv\Scripts\python.exe -c "import json; d=json.load(open('data/analyzed_AI_마케팅_2026-06-08.json', encoding='utf-8')); print('OK:', d['keyword'], '/ trends:', len(d['trends']))"
```
Expected: `OK: AI 마케팅 / trends: 3`

---

### Task 2: Write failing tests for monitor

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/monitor/__init__.py`
- Create: `tests/monitor/test_main.py`

- [ ] **Step 1: Install pytest**

```powershell
.\venv\Scripts\python.exe -m pip install pytest
```
Expected: `Successfully installed pytest-...`

- [ ] **Step 2: Create test package files**

Create empty `tests/__init__.py` and `tests/monitor/__init__.py`.

- [ ] **Step 3: Write test file**

Create `tests/monitor/test_main.py`:
```python
from datetime import date
from pathlib import Path

import pytest

from agents.monitor.main import AgentDef, CheckResult, check_agent


@pytest.fixture
def tmp_agent(tmp_path):
    script = tmp_path / "agents" / "dummy" / "main.py"
    output_dir = tmp_path / "data"
    script.parent.mkdir(parents=True)
    output_dir.mkdir()
    return AgentDef(
        number=99,
        name="dummy",
        script=script,
        output_dir=output_dir,
        output_glob="dummy_*.json",
        exclude_prefix=None,
    )


def test_check_agent_missing_script(tmp_agent):
    result = check_agent(tmp_agent, date(2026, 6, 8))
    assert result.status == "MISSING"
    assert "스크립트 없음" in result.detail


def test_check_agent_warning_no_output(tmp_agent):
    tmp_agent.script.touch()
    result = check_agent(tmp_agent, date(2026, 6, 8))
    assert result.status == "WARNING"
    assert "오늘 출력 없음" in result.detail


def test_check_agent_ok(tmp_agent):
    tmp_agent.script.touch()
    (tmp_agent.output_dir / "dummy_2026-06-08.json").write_text("[]")
    result = check_agent(tmp_agent, date(2026, 6, 8))
    assert result.status == "OK"
    assert "dummy_2026-06-08.json" in result.detail


def test_check_agent_excludes_prefix(tmp_path):
    script = tmp_path / "agents" / "collector" / "main.py"
    output_dir = tmp_path / "data"
    script.parent.mkdir(parents=True)
    script.touch()
    output_dir.mkdir()
    # analyzed_ file should NOT count as collector output
    (output_dir / "analyzed_test_2026-06-08.json").write_text("[]")
    agent = AgentDef(
        number=1,
        name="collector",
        script=script,
        output_dir=output_dir,
        output_glob="*_2026-06-08.json",
        exclude_prefix="analyzed_",
    )
    result = check_agent(agent, date(2026, 6, 8))
    assert result.status == "WARNING"


def test_check_agent_ok_with_exclude_prefix(tmp_path):
    script = tmp_path / "agents" / "collector" / "main.py"
    output_dir = tmp_path / "data"
    script.parent.mkdir(parents=True)
    script.touch()
    output_dir.mkdir()
    (output_dir / "AI_마케팅_2026-06-08.json").write_text("[]")
    (output_dir / "analyzed_AI_마케팅_2026-06-08.json").write_text("{}")
    agent = AgentDef(
        number=1,
        name="collector",
        script=script,
        output_dir=output_dir,
        output_glob="*_2026-06-08.json",
        exclude_prefix="analyzed_",
    )
    result = check_agent(agent, date(2026, 6, 8))
    assert result.status == "OK"
```

- [ ] **Step 4: Run tests to confirm they fail**

```powershell
.\venv\Scripts\python.exe -m pytest tests/monitor/test_main.py -v
```
Expected: `ModuleNotFoundError: No module named 'agents.monitor'`

---

### Task 3: Implement agents/monitor/main.py

**Files:**
- Create: `agents/__init__.py`
- Create: `agents/monitor/__init__.py`
- Create: `agents/monitor/main.py`

- [ ] **Step 1: Create package init files**

Create empty `agents/__init__.py` and `agents/monitor/__init__.py`.

- [ ] **Step 2: Implement main.py**

Create `agents/monitor/main.py`:
```python
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
    try:
        if not agent.script.exists():
            return CheckResult(agent, "MISSING", "스크립트 없음")

        today_str = today.strftime("%Y-%m-%d")
        glob_pattern = agent.output_glob.replace("*", f"*{today_str}*")
        files = list(agent.output_dir.glob(glob_pattern))
        if agent.exclude_prefix:
            files = [f for f in files if not f.name.startswith(agent.exclude_prefix)]

        if files:
            return CheckResult(agent, "OK", f"최근 파일: {files[0].name}")
        return CheckResult(agent, "WARNING", "오늘 출력 없음")
    except Exception as exc:
        return CheckResult(agent, "ERROR", str(exc))


def _make_agents() -> list[AgentDef]:
    return [
        AgentDef(1, "collector",
                 BASE_DIR / "agents/collector/main.py",
                 BASE_DIR / "data",
                 "*_*.json",
                 "analyzed_"),
        AgentDef(2, "analyzer",
                 BASE_DIR / "agents/analyzer/main.py",
                 BASE_DIR / "data",
                 "analyzed_*.json",
                 None),
        AgentDef(3, "writer",
                 BASE_DIR / "agents/writer/main.py",
                 BASE_DIR / "output",
                 "content_*.json",
                 None),
        AgentDef(4, "reporter",
                 BASE_DIR / "agents/reporter/main.py",
                 BASE_DIR / "output",
                 "report_*.json",
                 None),
    ]


def _format_line(ts: str, result: CheckResult) -> str:
    status_padded = f"[{result.status:<7}]"
    name_padded = f"({result.agent.name:<10})"
    return (
        f"[{ts}] {status_padded} "
        f"에이전트 {result.agent.number} {name_padded}: {result.detail}"
    )


def run_check(agents: list[AgentDef], log_dir: Path, today: date) -> list[CheckResult]:
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"monitor_{today.strftime('%Y-%m-%d')}.log"

    results = [check_agent(a, today) for a in agents]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    counts: dict[str, int] = {"OK": 0, "WARNING": 0, "MISSING": 0, "ERROR": 0}
    lines = [f"[{ts}] === 상태 체크 시작 ==="]
    for r in results:
        lines.append(_format_line(ts, r))
        counts[r.status] = counts.get(r.status, 0) + 1
        print(lines[-1])

    summary = " / ".join(f"{k} {v}" for k, v in counts.items())
    lines.append(f"[{ts}] === 요약: {summary} ===")
    lines.append(f"[{ts}] 다음 체크: {INTERVAL_SECONDS // 60}분 후")
    lines.append("")

    print(lines[-3])

    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"로그 저장: {log_path}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="마케팅 에이전트 모니터")
    parser.add_argument("--once", action="store_true", help="1회만 체크하고 종료")
    args = parser.parse_args()

    agents = _make_agents()
    log_dir = BASE_DIR / "logs"

    while True:
        run_check(agents, log_dir, date.today())
        if args.once:
            break
        print(f"{INTERVAL_SECONDS // 60}분 후 다음 체크... (Ctrl+C로 종료)")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/monitor/test_main.py -v
```
Expected: 5 tests PASSED

- [ ] **Step 4: Commit**

```powershell
git add agents/monitor/ tests/ data/analyzed_AI_마케팅_2026-06-08.json
git commit -m "feat: add monitor agent (agent 5) with sample data"
```

---

### Task 4: End-to-end verification

- [ ] **Step 1: Run once mode**

```powershell
.\venv\Scripts\python.exe agents\monitor\main.py --once
```
Expected output (console):
```
[2026-06-08 HH:MM:SS] [OK     ] 에이전트 1 (collector  ): 최근 파일: AI_마케팅_2026-06-08.json
[2026-06-08 HH:MM:SS] [OK     ] 에이전트 2 (analyzer   ): 최근 파일: analyzed_AI_마케팅_2026-06-08.json
[2026-06-08 HH:MM:SS] [MISSING] 에이전트 3 (writer     ): 스크립트 없음
[2026-06-08 HH:MM:SS] [MISSING] 에이전트 4 (reporter   ): 스크립트 없음
[2026-06-08 HH:MM:SS] === 요약: OK 2 / WARNING 0 / MISSING 2 / ERROR 0 ===
```

- [ ] **Step 2: Verify log file created**

```powershell
Get-Content "logs\monitor_2026-06-08.log" -Encoding UTF8
```
Expected: Same content as console output above, appended to log file.
