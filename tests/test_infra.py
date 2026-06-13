import json
import pytest
from pathlib import Path


# ── job_store ──────────────────────────────────────────────────
def test_init_db_creates_table(tmp_path):
    from utils.job_store import init_db
    db = tmp_path / "jobs.db"
    init_db(db)
    import sqlite3
    with sqlite3.connect(db) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
    assert "jobs" in tables


def test_upsert_and_get_job(tmp_path):
    from utils.job_store import init_db, upsert_job, get_job
    db = tmp_path / "jobs.db"
    init_db(db)
    upsert_job("abc123", "running", ["AI 마케팅"], db_path=db)
    job = get_job("abc123", db_path=db)
    assert job["status"] == "running"
    assert "AI 마케팅" in job["keywords"]


def test_upsert_preserves_created_at(tmp_path):
    from utils.job_store import init_db, upsert_job, get_job
    import sqlite3, time
    db = tmp_path / "jobs.db"
    init_db(db)
    upsert_job("j1", "running", db_path=db)
    with sqlite3.connect(db) as conn:
        created1 = conn.execute("SELECT created_at FROM jobs WHERE job_id='j1'").fetchone()[0]
    time.sleep(0.05)
    upsert_job("j1", "done", db_path=db)
    with sqlite3.connect(db) as conn:
        created2 = conn.execute("SELECT created_at FROM jobs WHERE job_id='j1'").fetchone()[0]
    assert created1 == created2


def test_mark_interrupted_changes_running_jobs(tmp_path):
    from utils.job_store import init_db, upsert_job, mark_interrupted, get_job
    db = tmp_path / "jobs.db"
    init_db(db)
    upsert_job("running1", "running", db_path=db)
    upsert_job("done1", "done", db_path=db)
    count = mark_interrupted(db)
    assert count == 1
    assert get_job("running1", db_path=db)["status"] == "interrupted"
    assert get_job("done1", db_path=db)["status"] == "done"


def test_get_job_returns_none_for_missing(tmp_path):
    from utils.job_store import init_db, get_job
    db = tmp_path / "jobs.db"
    init_db(db)
    assert get_job("no-such-id", db_path=db) is None


# ── cleanup ────────────────────────────────────────────────────
import time as _time
import os as _os


def _make_old_file(path: Path, days_old: int) -> Path:
    path.write_text("x")
    old_ts = _time.time() - days_old * 86400
    _os.utime(path, (old_ts, old_ts))
    return path


def test_cleanup_deletes_old_output_files(tmp_path):
    from utils.cleanup import cleanup_old_files
    root = tmp_path
    (root / "output").mkdir()
    (root / "data").mkdir()
    _make_old_file(root / "output" / "report_2026-01-01.pdf", 8)
    _make_old_file(root / "output" / "report_2026-01-01.html", 8)
    _make_old_file(root / "output" / "cardnews_test_2026-01-01_1.png", 8)
    deleted = cleanup_old_files(root, days=7)
    names = [f.name for f in deleted]
    assert "report_2026-01-01.pdf" in names
    assert "report_2026-01-01.html" in names
    assert "cardnews_test_2026-01-01_1.png" in names


def test_cleanup_keeps_recent_files(tmp_path):
    from utils.cleanup import cleanup_old_files
    root = tmp_path
    (root / "output").mkdir()
    recent = root / "output" / "report_2026-06-14.pdf"
    recent.write_text("x")
    deleted = cleanup_old_files(root, days=7)
    assert not any(f.name == recent.name for f in deleted)
    assert recent.exists()


def test_cleanup_preserves_protected_files(tmp_path):
    from utils.cleanup import cleanup_old_files, KEEP
    root = tmp_path
    (root / "data").mkdir()
    for name in KEEP:
        _make_old_file(root / "data" / name, 30)
    deleted = cleanup_old_files(root, days=7)
    deleted_names = {f.name for f in deleted}
    for name in KEEP:
        assert name not in deleted_names


def test_cleanup_deletes_old_analyzed_json(tmp_path):
    from utils.cleanup import cleanup_old_files
    root = tmp_path
    (root / "data").mkdir()
    old = _make_old_file(root / "data" / "analyzed_AI마케팅_2026-01-01.json", 8)
    deleted = cleanup_old_files(root, days=7)
    assert any(f.name == old.name for f in deleted)


# ── alert_sender ───────────────────────────────────────────────
import os as _os2
from unittest.mock import patch, MagicMock


def test_send_alert_uses_email_when_configured():
    from utils.alert_sender import send_alert
    env = {"ALERT_EMAIL": "ops@example.com", "GMAIL_USER": "sender@gmail.com",
           "GMAIL_APP_PASSWORD": "pw"}
    with patch.dict(_os2.environ, env):
        with patch("utils.alert_sender._send_email") as mock_email:
            send_alert("제목", "내용")
    mock_email.assert_called_once_with(
        to="ops@example.com", subject="제목", body="내용"
    )


def test_send_alert_uses_slack_when_configured():
    from utils.alert_sender import send_alert
    env = {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/fake"}
    with patch.dict(_os2.environ, env, clear=False):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            send_alert("제목", "내용")
    mock_urlopen.assert_called_once()


def test_send_alert_silent_when_nothing_configured(capsys):
    from utils.alert_sender import send_alert
    env = {k: v for k, v in _os2.environ.items()
           if k not in ("ALERT_EMAIL", "SLACK_WEBHOOK_URL")}
    with patch.dict(_os2.environ, env, clear=True):
        send_alert("제목", "내용")
    captured = capsys.readouterr()
    assert "미설정" in captured.out


def test_send_alert_continues_on_email_failure():
    from utils.alert_sender import send_alert
    env = {"ALERT_EMAIL": "ops@example.com",
           "SLACK_WEBHOOK_URL": "https://hooks.slack.com/fake"}
    with patch.dict(_os2.environ, env):
        with patch("utils.alert_sender._send_email", side_effect=Exception("SMTP 오류")):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.return_value.__enter__ = lambda s: s
                mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
                send_alert("제목", "내용")
    mock_urlopen.assert_called_once()


# ── monitor alert integration ───────────────────────────────────
def test_run_check_cycle_calls_send_alert_for_significant(tmp_path, monkeypatch):
    import agents.monitor.main as monitor_mod

    fake_alert = {
        "keyword": "AI 마케팅",
        "new_post_count": 3,
        "is_significant": True,
        "level": "high",
        "summary": "AI 마케팅 급등",
        "reasons": ["검색량 증가"],
        "new_posts": [],
        "checked_at": "2026-06-14T10:00:00",
    }

    monkeypatch.setattr(monitor_mod, "load_state",
                        lambda: {"seen_links": {}, "last_checked": {}})
    monkeypatch.setattr(monitor_mod, "save_state", lambda s: None)
    monkeypatch.setattr(monitor_mod, "check_keyword",
                        lambda kw, state, client: fake_alert)
    monkeypatch.setattr(monitor_mod, "DATA_DIR", tmp_path)

    sent_alerts = []
    monkeypatch.setattr(monitor_mod, "send_alert",
                        lambda s, b: sent_alerts.append((s, b)))

    monitor_mod.run_check_cycle(["AI 마케팅"], client=None)

    assert len(sent_alerts) == 1
    assert "AI 마케팅" in sent_alerts[0][0]
    assert "high" in sent_alerts[0][0].lower()
