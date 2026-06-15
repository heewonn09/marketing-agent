from datetime import date, timedelta

from utils.backup import backup_state


def _make_state(root):
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "jobs.db").write_text("db")
    (data / "history.json").write_text("{}")
    (data / "ignored_other.json").write_text("x")  # 대상 아님
    return data


def test_backup_copies_state_files(tmp_path):
    _make_state(tmp_path)
    copied = backup_state(tmp_path)
    assert set(copied) == {"jobs.db", "history.json"}
    dest = tmp_path / "data" / "backups" / date.today().isoformat()
    assert (dest / "jobs.db").read_text() == "db"
    assert (dest / "history.json").read_text() == "{}"
    assert not (dest / "ignored_other.json").exists()


def test_backup_skips_missing_files(tmp_path):
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "jobs.db").write_text("db")
    copied = backup_state(tmp_path)
    assert copied == ["jobs.db"]  # 존재하는 것만


def test_backup_prunes_old_dirs(tmp_path):
    _make_state(tmp_path)
    old = tmp_path / "data" / "backups" / (date.today() - timedelta(days=30)).isoformat()
    old.mkdir(parents=True)
    (old / "jobs.db").write_text("old")
    recent = tmp_path / "data" / "backups" / (date.today() - timedelta(days=2)).isoformat()
    recent.mkdir(parents=True)

    backup_state(tmp_path, keep_days=14)

    assert not old.exists()      # 14일 초과 → 삭제
    assert recent.exists()       # 14일 이내 → 유지
    assert (tmp_path / "data" / "backups" / date.today().isoformat()).exists()
