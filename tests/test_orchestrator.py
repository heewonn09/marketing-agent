"""orchestrator 체크포인트/재개(run_step) e2e 테스트 (subprocess 모킹, 오프라인)."""
import orchestrator as o
from utils.checkpoint import load_completed


class _Result:
    def __init__(self, returncode):
        self.returncode = returncode


def test_run_step_skips_completed_on_resume(monkeypatch, tmp_path):
    calls = {"n": 0}
    monkeypatch.setattr(o.subprocess, "run",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or _Result(0))
    o.CHECKPOINT_PATH = tmp_path / "cp.json"
    o._resume = True
    o._completed = {"collector"}
    # 이미 완료된 단계 → 서브프로세스 실행 없이 True
    assert o.run_step("collector", "수집", "agents/collector/main.py", []) is True
    assert calls["n"] == 0


def test_run_step_marks_checkpoint_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(o.subprocess, "run", lambda *a, **k: _Result(0))
    o.CHECKPOINT_PATH = tmp_path / "cp.json"
    o._resume = False
    o._completed = set()
    assert o.run_step("analyzer", "분석", "agents/analyzer/main.py", []) is True
    assert "analyzer" in load_completed(o.CHECKPOINT_PATH)


def test_run_step_failure_not_marked(monkeypatch, tmp_path):
    monkeypatch.setattr(o.subprocess, "run", lambda *a, **k: _Result(1))
    o.CHECKPOINT_PATH = tmp_path / "cp.json"
    o._resume = False
    o._completed = set()
    assert o.run_step("writer", "작성", "agents/writer/main.py", []) is False
    assert "writer" not in load_completed(o.CHECKPOINT_PATH)


def test_run_step_no_checkpoint_when_path_none(monkeypatch):
    monkeypatch.setattr(o.subprocess, "run", lambda *a, **k: _Result(0))
    o.CHECKPOINT_PATH = None
    o._resume = False
    o._completed = set()
    # CHECKPOINT_PATH 없으면 기록 시도 없이 정상 동작
    assert o.run_step("reporter", "리포트", "agents/reporter/main.py", []) is True
