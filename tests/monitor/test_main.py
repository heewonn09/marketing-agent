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
